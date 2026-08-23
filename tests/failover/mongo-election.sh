#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
database="case_library_failover"
marker="$(date -u +%Y%m%dT%H%M%SZ)-$$"
uri="mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0"
cd "$project_dir"
. "$project_dir/scripts/test-database.sh"

compose() {
  docker compose "$@"
}

write_probe() {
  node="$1"
  phase="$2"
  compose exec -T "$node" mongosh "$uri" --quiet --eval "
    db.getSiblingDB('$database').probes.insertOne(
      {_id: '$marker-$phase', phase: '$phase'},
      {writeConcern: {w: 'majority'}}
    )
  " >/dev/null
}

clear_probes() {
  node="$1"
  compose exec -T "$node" mongosh "$uri" --quiet --eval \
    "db.getSiblingDB('$database').probes.deleteMany({})" >/dev/null
}

verify_probes() {
  node="$1"
  compose exec -T "$node" mongosh "$uri" --quiet --eval "
    const count = db.getSiblingDB('$database').probes.countDocuments(
      {_id: {\$in: ['$marker-before', '$marker-after']}}
    );
    quit(count === 2 ? 0 : 1);
  "
}

primary_name() {
  node="$1"
  compose exec -T "$node" mongosh --quiet --eval \
    'db.hello().primary || ""' 2>/dev/null | tail -n 1 | sed 's/:27017$//'
}

worker_updated_at() {
  node="$1"
  compose exec -T "$node" mongosh "$uri" --quiet --eval "
    const heartbeat = db.getSiblingDB('$database').search_worker_state.findOne({_id: 'catalog'});
    print(heartbeat && heartbeat.updatedAt ? heartbeat.updatedAt.getTime() : '');
  " 2>/dev/null | tail -n 1
}

pick_probe() {
  failed="$1"
  for node in mongo1 mongo2 mongo3; do
    if [ "$node" != "$failed" ]; then
      echo "$node"
      return
    fi
  done
}

wait_for_new_primary() {
  probe="$1"
  previous="$2"
  attempts=30
  while [ "$attempts" -gt 0 ]; do
    current="$(primary_name "$probe" || true)"
    if [ -n "$current" ] && [ "$current" != "$previous" ]; then
      echo "$current"
      return
    fi
    attempts=$((attempts - 1))
    sleep 2
  done
  return 1
}

wait_for_worker_advance() {
  probe="$1"
  previous="$2"
  attempts=30
  while [ "$attempts" -gt 0 ]; do
    current="$(worker_updated_at "$probe" || true)"
    if [ -n "$current" ] && [ "$current" -gt "$previous" ]; then
      return
    fi
    attempts=$((attempts - 1))
    sleep 2
  done
  return 1
}

wait_for_rejoin() {
  probe="$1"
  restored="$2"
  attempts=30
  while [ "$attempts" -gt 0 ]; do
    state="$(compose exec -T "$probe" mongosh --quiet --eval \
      "rs.status().members.find(m => m.name === '$restored:27017')?.stateStr || ''" 2>/dev/null | tail -n 1)"
    if [ "$state" = "SECONDARY" ] || [ "$state" = "PRIMARY" ]; then
      return
    fi
    attempts=$((attempts - 1))
    sleep 2
  done
  return 1
}

original="$(primary_name mongo1)"
test -n "$original"
probe="$(pick_probe "$original")"
clear_probes "$probe"
write_probe "$probe" before
heartbeat_before="$(worker_updated_at "$probe")"
test -n "$heartbeat_before"
trap 'compose start "$original" >/dev/null 2>&1 || true; drop_test_database "$database" || true' EXIT INT TERM

echo "Stopping MongoDB primary: $original"
compose stop "$original" >/dev/null
replacement="$(wait_for_new_primary "$probe" "$original")"
echo "Elected replacement primary: $replacement"
wait_for_worker_advance "$probe" "$heartbeat_before"
write_probe "$probe" after
verify_probes "$probe"

compose exec -T app python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health/ready', timeout=5)"

compose start "$original" >/dev/null
wait_for_rejoin "$replacement" "$original"
verify_probes "$original"
clear_probes "$original"
trap - EXIT INT TERM
echo "Restored replica-set member: $original"
