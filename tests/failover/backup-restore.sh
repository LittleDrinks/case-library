#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
database="case_library_backup_fixture_$$"
unrelated_database="case_library_backup_unrelated_$$"
bucket="case-library-backup-fixture-$$"
scope_bucket="case-library-restore-scope-$$"
work="$(mktemp -d)"
export COMPOSE_ENV_FILES="$project_dir/.env.example"
export COMPOSE_DISABLE_ENV_FILE=1
export MONGODB_DB_NAME="$database"
export OBJECT_STORE_BUCKET="$bucket"

compose() {
  docker compose --project-directory "$project_dir" "$@"
}

drop_fixture() {
  compose exec -T mongo1 mongosh mongodb://mongo1:27017 --quiet \
    --eval "db.getSiblingDB('$database').dropDatabase()" >/dev/null 2>&1 || true
}

drop_unrelated() {
  compose exec -T mongo1 mongosh mongodb://mongo1:27017 --quiet \
    --eval "db.getSiblingDB('$unrelated_database').dropDatabase()" >/dev/null 2>&1 || true
}

remove_fixture_bucket() {
  compose --profile ops run --rm --no-deps -T -e OBJECT_STORE_BUCKET=case-library \
    backup-tools remove-bucket "$bucket" >/dev/null 2>&1 || true
}

cleanup() {
  drop_fixture
  drop_unrelated
  remove_fixture_bucket
  compose --profile ops run --rm --no-deps -T -e OBJECT_STORE_BUCKET=case-library \
    backup-tools remove-bucket "$scope_bucket" >/dev/null 2>&1 || true
  compose --profile restore rm -sfv restore-mongo >/dev/null 2>&1 || true
  rm -rf -- "$work"
}

assert_bundle_database_scope() {
  compose --profile restore up -d --wait restore-mongo >/dev/null
  compose --profile restore run --rm --no-deps -T -e RESTORE_BUCKET="$scope_bucket" \
    -v "$bundle:/bundle:ro" restore-tools restore /bundle >/dev/null
  restored="$(compose exec -T restore-mongo mongosh --quiet --eval \
    "print(db.adminCommand({listDatabases:1,nameOnly:true}).databases.some(x => x.name === '$unrelated_database'))")"
  test "$restored" = "false"
  sessions="$(compose exec -T restore-mongo mongosh --quiet --eval \
    "print(db.getSiblingDB('$database').sessions.countDocuments({}))")"
  test "$sessions" -eq 0
  usage="$(compose exec -T restore-mongo mongosh --quiet --eval \
    "print(db.getSiblingDB('$database').ai_usage.countDocuments({}))")"
  test "$usage" -eq 0
  assert_search_state_excluded
  assert_restored_object_scope
  compose --profile restore run --rm --no-deps -T \
    restore-tools remove-bucket "$scope_bucket" >/dev/null
  compose --profile restore rm -sfv restore-mongo >/dev/null
}

assert_search_state_excluded() {
  names="search_outbox search_revocations search_catalog_state search_control search_catalog_generation search_worker_state"
  for name in $names; do
    count="$(compose exec -T restore-mongo mongosh --quiet --eval \
      "print(db.getSiblingDB('$database').getCollection('$name').countDocuments({}))")"
    test "$count" -eq 0
  done
}

assert_restored_object_scope() {
  compose --profile restore run --rm --no-deps -T --entrypoint sh \
    -e RESTORE_BUCKET="$scope_bucket" restore-tools -eu -c '
      access="$(tr -d "\r\n" <"$OBJECT_STORE_ACCESS_KEY_FILE")"
      secret="$(tr -d "\r\n" <"$OBJECT_STORE_SECRET_KEY_FILE")"
      mc alias set store "http://$OBJECT_STORE_ENDPOINT" "$access" "$secret" --api S3v4 >/dev/null
      test "$(mc ls --recursive "store/$RESTORE_BUCKET" | wc -l | tr -d " ")" -eq 3
      ! mc stat "store/$RESTORE_BUCKET/blobs/unreferenced" >/dev/null 2>&1
    '
}

put_fixture_object() {
  key="$1"
  printf '%s' "$2" |
    compose --profile ops run --rm --no-deps -T --entrypoint sh \
      -e FIXTURE_OBJECT_KEY="$key" backup-tools -eu -c '
      access="$(tr -d "\r\n" <"$OBJECT_STORE_ACCESS_KEY_FILE")"
      secret="$(tr -d "\r\n" <"$OBJECT_STORE_SECRET_KEY_FILE")"
      mc alias set store "http://$OBJECT_STORE_ENDPOINT" "$access" "$secret" --api S3v4 >/dev/null
      mc mb --ignore-existing "store/$OBJECT_STORE_BUCKET" >/dev/null
      mc pipe "store/$OBJECT_STORE_BUCKET/blobs/$FIXTURE_OBJECT_KEY" >/dev/null
    '
}

create_missing_bundle() {
  compose --profile restore run --rm --no-deps -T --entrypoint sh \
    -v "$work:/bundles" restore-tools -eu -c '
      stage="$(mktemp -d)"; trap '\''rm -rf "$stage"'\'' EXIT
      age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "/bundles/$1" | tar -xzf - -C "$stage"
      rm "$stage/objects/blobs/fixture"
      (cd "$stage" && find objects -type f -print0 | sort -z | xargs -0 -r sha256sum >objects.sha256)
      count="$(find "$stage/objects" -type f -printf x | wc -c | tr -d " ")"
      hashes_sha="$(sha256sum "$stage/objects.sha256" | cut -d " " -f 1)"
      jq --argjson count "$count" --arg hashes_sha "$hashes_sha" \
        '\''.objectStore.count = $count | .objectStore.hashListSha256 = $hashes_sha'\'' \
        "$stage/manifest.json" >"$stage/next.json"
      mv "$stage/next.json" "$stage/manifest.json"
      (cd "$stage" && sha256sum manifest.json >manifest.sha256)
      tar -czf - -C "$stage" manifest.json manifest.sha256 mongo.archive.gz mongo.sha256 objects.sha256 objects |
        age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" --output "/bundles/$2"
    ' _ "$(basename -- "$1")" "$(basename -- "$2")"
}


create_omitted_reference_bundle() {
  compose --profile restore run --rm --no-deps -T --entrypoint sh \
    -v "$work:/bundles" restore-tools -eu -c '
      stage="$(mktemp -d)"; trap '\''rm -rf "$stage"'\'' EXIT
      age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "/bundles/$1" | tar -xzf - -C "$stage"
      rm "$stage/objects/blobs/material-only"
      (cd "$stage" && find objects -type f -print0 | sort -z | xargs -0 -r sha256sum >objects.sha256)
      count="$(find "$stage/objects" -type f -printf x | wc -c | tr -d " ")"
      hashes_sha="$(sha256sum "$stage/objects.sha256" | cut -d " " -f 1)"
      jq --argjson count "$count" --arg hashes_sha "$hashes_sha" \
        '\''.objectStore.count = $count | .objectStore.hashListSha256 = $hashes_sha | .referencedObjectKeys -= ["blobs/material-only"]'\'' \
        "$stage/manifest.json" >"$stage/next.json"
      mv "$stage/next.json" "$stage/manifest.json"
      (cd "$stage" && sha256sum manifest.json >manifest.sha256)
      tar -czf - -C "$stage" manifest.json manifest.sha256 mongo.archive.gz mongo.sha256 objects.sha256 objects |
        age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" --output "/bundles/$2"
    ' _ "$(basename -- "$1")" "$(basename -- "$2")"
}

restore_bucket_count() {
  compose --profile ops run --rm --no-deps -T --entrypoint sh backup-tools -eu -c '
    access="$(tr -d "\r\n" <"$OBJECT_STORE_ACCESS_KEY_FILE")"
    secret="$(tr -d "\r\n" <"$OBJECT_STORE_SECRET_KEY_FILE")"
    mc alias set store "http://$OBJECT_STORE_ENDPOINT" "$access" "$secret" --api S3v4 >/dev/null
    mc ls --json store | jq -r '\''select(.key | startswith("case-library-restore-")) | .key'\''
  ' | wc -l | tr -d ' '
}

bundle_object_count() {
  compose --profile restore run --rm --no-deps -T \
    -v "$bundle:/bundle:ro" restore-tools verify /bundle |
    jq -r '.objectStore.count'
}

assert_restore_cleanup() {
  test -z "$(compose --profile restore ps -q restore-mongo)"
  test "$(restore_bucket_count)" -eq 0
}

trap cleanup EXIT INT TERM
compose up -d --wait mongo-init minio
compose --profile ops build backup-tools
compose exec -T mongo1 mongosh mongodb://mongo1:27017 --quiet --eval \
  "const d=db.getSiblingDB('$database');d.attachments.insertOne({id:'att-fixture',blobId:'fixture'});d.case_versions.insertOne({id:'v-fixture',attachments:[{blobId:'fixture'}]});d.case_snapshots.insertOne({id:'s-fixture',attachments:[{blobId:'snapshot-only'}]});d.material_candidates.insertOne({id:'mc-fixture',blobId:'material-only'});d.sessions.insertOne({token_hash:'must-not-restore'});d.ai_usage.insertOne({_id:'must-not-restore',count:1});for(const name of ['search_outbox','search_revocations','search_catalog_state','search_control','search_catalog_generation','search_worker_state'])d.getCollection(name).insertOne({_id:'must-not-restore'});" >/dev/null
compose exec -T mongo1 mongosh mongodb://mongo1:27017 --quiet --eval \
  "db.getSiblingDB('$unrelated_database').sentinel.insertOne({unexpected:true})" >/dev/null
put_fixture_object fixture fixture-object-content
put_fixture_object unreferenced unrelated-object-content

if "$project_dir/scripts/mongo-backup.sh" "$work" >/dev/null 2>&1; then
  echo "Backup accepted a working snapshot with a missing object" >&2
  exit 1
fi
put_fixture_object snapshot-only snapshot-object-content

if "$project_dir/scripts/mongo-backup.sh" "$work" >/dev/null 2>&1; then
  echo "Backup accepted a material candidate with a missing object" >&2
  exit 1
fi
put_fixture_object material-only material-object-content

bundle="$($project_dir/scripts/mongo-backup.sh "$work")"
test -f "$bundle"
test "$(find "$work" -maxdepth 1 -name '*.bundle.tar.gz.age' | wc -l | tr -d ' ')" -eq 1
objects="$(bundle_object_count)"
if [ "$objects" -ne 3 ]; then
  echo "Backup bundled unreferenced objects: expected 3, got $objects" >&2
  exit 1
fi
if tar -tzf "$bundle" >/dev/null 2>&1; then
  echo "Backup bundle is not encrypted" >&2
  exit 1
fi
assert_bundle_database_scope
"$project_dir/scripts/restore-drill.sh" "$bundle" >/dev/null
assert_restore_cleanup

missing="$work/missing-object.bundle.tar.gz.age"
create_missing_bundle "$bundle" "$missing"
if "$project_dir/scripts/restore-drill.sh" "$missing" >/dev/null 2>&1; then
  echo "Restore drill accepted a Mongo attachment with no object" >&2
  exit 1
fi
assert_restore_cleanup

omitted="$work/omitted-reference.bundle.tar.gz.age"
create_omitted_reference_bundle "$bundle" "$omitted"
if "$project_dir/scripts/restore-drill.sh" "$omitted" >/dev/null 2>&1; then
  echo "Restore drill trusted a manifest that omitted a Mongo object reference" >&2
  exit 1
fi
assert_restore_cleanup
