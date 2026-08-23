#!/bin/sh
set -eu

work=""

cleanup() {
  if [ -n "$work" ]; then rm -rf -- "$work"; fi
}

make_work() {
  work="$(mktemp -d)"
}

secret_value() {
  test -s "$1"
  tr -d '\r\n' <"$1"
}

configure_store() {
  access="$(secret_value "$OBJECT_STORE_ACCESS_KEY_FILE")"
  secret="$(secret_value "$OBJECT_STORE_SECRET_KEY_FILE")"
  mc alias set store "http://$OBJECT_STORE_ENDPOINT" "$access" "$secret" --api S3v4 >/dev/null
  unset access secret
}

dump_database() {
  mongodump --uri="$MONGODB_ADMIN_URI" --archive="$work/mongo.archive.gz" \
    --gzip --db="$MONGODB_DB_NAME" --excludeCollection=sessions \
    --excludeCollection=ai_usage --excludeCollection=search_outbox \
    --excludeCollection=search_revocations --excludeCollection=search_catalog_state \
    --excludeCollection=search_control --excludeCollection=search_catalog_generation \
    --excludeCollection=search_worker_state
}

write_inventory() {
  mongosh "$MONGODB_ADMIN_URI" --quiet --eval '
    const source = db.getSiblingDB(process.env.MONGODB_DB_NAME);
    const excluded = new Set([
      "sessions", "ai_usage", "search_outbox", "search_revocations",
      "search_catalog_state", "search_control", "search_catalog_generation",
      "search_worker_state",
    ]);
    const names = source.getCollectionNames().filter(name => !excluded.has(name)).sort();
    const collections = Object.fromEntries(names.map(name => [name, source.getCollection(name).countDocuments({})]));
    const blobIds = new Set(source.getCollection("attachments").distinct("blobId"));
    for (const id of source.getCollection("case_versions").distinct("attachments.blobId")) blobIds.add(id);
    for (const id of source.getCollection("case_snapshots").distinct("attachments.blobId")) blobIds.add(id);
    for (const id of source.getCollection("material_candidates").distinct("blobId")) blobIds.add(id);
    const referencedObjectKeys = Array.from(blobIds).filter(Boolean).sort().map(id => `blobs/${id}`);
    print(JSON.stringify({collections, referencedObjectKeys}));
  ' >"$work/inventory.json"
}

copy_objects() {
  mkdir -p "$work/objects"
  jq -r '.referencedObjectKeys[]' "$work/inventory.json" |
    while IFS= read -r key; do
      mkdir -p "$work/objects/$(dirname -- "$key")"
      mc cp "store/$OBJECT_STORE_BUCKET/$key" "$work/objects/$key" >/dev/null
    done
}

object_count() {
  find "$1" -type f -printf x | wc -c | tr -d ' '
}

write_hashes() {
  (cd "$work" && sha256sum mongo.archive.gz >mongo.sha256)
  (cd "$work" && find objects -type f -print0 | sort -z | xargs -0 -r sha256sum >objects.sha256)
}

write_manifest() {
  mongo_sha="$(cut -d ' ' -f 1 "$work/mongo.sha256")"
  object_hashes_sha="$(sha256sum "$work/objects.sha256" | cut -d ' ' -f 1)"
  count="$(object_count "$work/objects")"
  jq -n --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg git_sha "$BUNDLE_GIT_SHA" \
    --argjson git_dirty "$BUNDLE_GIT_DIRTY" --arg app_image_id "$BUNDLE_APP_IMAGE_ID" \
    --arg database "$MONGODB_DB_NAME" --arg bucket "$OBJECT_STORE_BUCKET" \
    --arg mongo_sha "$mongo_sha" --arg object_hashes_sha "$object_hashes_sha" \
    --argjson object_count "$count" \
    --slurpfile inventory "$work/inventory.json" -f /usr/local/share/backup-manifest.jq >"$work/manifest.json"
  (cd "$work" && sha256sum manifest.json >manifest.sha256)
}

verify_layout() {
  test -f "$work/manifest.json" && test -f "$work/manifest.sha256"
  test -f "$work/mongo.archive.gz" && test -f "$work/mongo.sha256"
  test -f "$work/objects.sha256" && test -d "$work/objects"
  test -z "$(find "$work" -type l -print -quit)"
  jq -e '.formatVersion == 1 and (.gitSha | test("^[0-9a-f]{40,64}$"))' "$work/manifest.json" >/dev/null
}

verify_hashes() {
  (cd "$work" && sha256sum -c manifest.sha256 >/dev/null)
  (cd "$work" && sha256sum -c mongo.sha256 >/dev/null)
  test "$(sha256sum "$work/mongo.archive.gz" | cut -d ' ' -f 1)" = \
    "$(jq -r '.database.sha256' "$work/manifest.json")"
  test "$(sha256sum "$work/objects.sha256" | cut -d ' ' -f 1)" = \
    "$(jq -r '.objectStore.hashListSha256' "$work/manifest.json")"
  if [ -s "$work/objects.sha256" ]; then
    (cd "$work" && sha256sum -c objects.sha256 >/dev/null)
  fi
}

verify_object_count() {
  expected="$(jq -r '.objectStore.count' "$work/manifest.json")"
  actual="$(object_count "$work/objects")"
  hashes="$(wc -l <"$work/objects.sha256" | tr -d ' ')"
  test "$actual" = "$expected" && test "$hashes" = "$expected"
}

verify_references() {
  root="$1"
  jq -r '.referencedObjectKeys[]' "$work/manifest.json" |
    while IFS= read -r key; do test -f "$root/$key"; done
}

verify_extracted() {
  verify_layout
  verify_hashes
  verify_object_count
  verify_references "$work/objects"
}

extract_bundle() {
  make_work
  age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "$1" |
    tar --extract --gzip --directory="$work" --no-same-owner --no-same-permissions
}

write_bundle() {
  tar --create --gzip --directory="$work" --file=- manifest.json manifest.sha256 \
    mongo.archive.gz mongo.sha256 objects.sha256 objects |
    age --encrypt --recipient "$BACKUP_AGE_RECIPIENT"
}

create_bundle() {
  make_work
  configure_store
  dump_database
  write_inventory
  copy_objects
  write_hashes
  write_manifest
  verify_extracted
  write_bundle
}

verify_bundle() {
  extract_bundle "$1"
  verify_extracted
  jq -c '{gitSha,database,objectStore}' "$work/manifest.json"
}

restore_database() {
  mongorestore --uri="$RESTORE_MONGODB_URI" --archive="$work/mongo.archive.gz" \
    --gzip >/dev/null
}

restore_objects() {
  mc mb "store/$RESTORE_BUCKET" >/dev/null
  if [ "$(object_count "$work/objects")" -gt 0 ]; then
    mc mirror --overwrite "$work/objects" "store/$RESTORE_BUCKET" >/dev/null
  fi
}

verify_database_counts() {
  expected="$(jq -c '.database.collections' "$work/manifest.json")"
  database="$(jq -r '.database.name' "$work/manifest.json")"
  EXPECTED_COUNTS="$expected" RESTORE_DATABASE="$database" mongosh "$RESTORE_MONGODB_URI" --quiet --eval '
    const target = db.getSiblingDB(process.env.RESTORE_DATABASE);
    const names = target.getCollectionNames().sort();
    const actual = Object.fromEntries(names.map(name => [name, target.getCollection(name).countDocuments({})]));
    quit(JSON.stringify(actual) === JSON.stringify(JSON.parse(process.env.EXPECTED_COUNTS)) ? 0 : 1);
  '
}

verify_database_references() {
  expected="$(jq -c '.referencedObjectKeys' "$work/manifest.json")"
  database="$(jq -r '.database.name' "$work/manifest.json")"
  EXPECTED_REFERENCES="$expected" RESTORE_DATABASE="$database" \
    mongosh "$RESTORE_MONGODB_URI" --quiet --eval '
    const source = db.getSiblingDB(process.env.RESTORE_DATABASE);
    const blobIds = new Set(source.getCollection("attachments").distinct("blobId"));
    for (const id of source.getCollection("case_versions").distinct("attachments.blobId")) blobIds.add(id);
    for (const id of source.getCollection("case_snapshots").distinct("attachments.blobId")) blobIds.add(id);
    for (const id of source.getCollection("material_candidates").distinct("blobId")) blobIds.add(id);
    const actual = Array.from(blobIds).filter(Boolean).sort().map(id => `blobs/${id}`);
    quit(JSON.stringify(actual) === process.env.EXPECTED_REFERENCES ? 0 : 1);
  '
}

verify_database_scope() {
  database="$(jq -r '.database.name' "$work/manifest.json")"
  RESTORE_DATABASE="$database" mongosh "$RESTORE_MONGODB_URI" --quiet --eval '
    const ignored = new Set(["admin", "config", "local"]);
    const names = db.adminCommand({listDatabases: 1, nameOnly: true}).databases
      .map(item => item.name).filter(name => !ignored.has(name));
    quit(names.length === 1 && names[0] === process.env.RESTORE_DATABASE ? 0 : 1);
  '
}

verify_restored_objects() {
  mkdir -p "$work/restored"
  mc mirror "store/$RESTORE_BUCKET" "$work/restored" >/dev/null
  test "$(object_count "$work/restored")" = "$(jq -r '.objectStore.count' "$work/manifest.json")"
  if [ -s "$work/objects.sha256" ]; then
    sed 's#  objects/#  restored/#' "$work/objects.sha256" |
      (cd "$work" && sha256sum -c - >/dev/null)
  fi
  verify_references "$work/restored"
}

restore_bundle() {
  extract_bundle "$1"
  verify_extracted
  configure_store
  test "$RESTORE_BUCKET" != "$(jq -r '.objectStore.bucket' "$work/manifest.json")"
  restore_database
  restore_objects
  verify_database_counts
  verify_database_references
  verify_database_scope
  verify_restored_objects
  jq -c '{database:.database.name,collections:(.database.collections|length),objects:.objectStore.count}' "$work/manifest.json"
}

remove_bucket() {
  configure_store
  test "$1" != "$OBJECT_STORE_BUCKET"
  if mc stat "store/$1" >/dev/null 2>&1; then mc rb --force "store/$1" >/dev/null; fi
}

trap cleanup EXIT INT TERM
case "${1:-}" in
  create) create_bundle ;;
  verify) verify_bundle "$2" ;;
  restore) restore_bundle "$2" ;;
  remove-bucket) remove_bucket "$2" ;;
  *) echo "Usage: backup-bundle-tool create|verify BUNDLE|restore BUNDLE|remove-bucket BUCKET" >&2; exit 2 ;;
esac
