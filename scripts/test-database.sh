# Shared test-database helpers, sourced by scripts/run-e2e.sh,
# scripts/run-load.sh and the failover scripts. Callers set compose_project
# before sourcing. Every drop proves resource ownership first: the mongo1
# container must carry the Compose project label of the calling project, so a
# mis-set project name can never drop a database inside another stack.

validate_test_database() {
  case "$1" in
    case_library_load|case_library_e2e|case_library_failover) return 0 ;;
    *) echo "Refusing to modify non-test database: $1" >&2; return 1 ;;
  esac
}

verify_mongo_project_ownership() {
  mongo1_container="$(compose ps -q mongo1)"
  test -n "$mongo1_container" || {
    echo "mongo1 is not running in project $compose_project" >&2
    return 1
  }
  owner="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$mongo1_container")"
  test "$owner" = "$compose_project" || {
    echo "mongo1 in project $compose_project does not belong to this Compose project" >&2
    return 1
  }
}

drop_test_database() {
  database="$1"
  validate_test_database "$database"
  verify_mongo_project_ownership
  compose exec -T mongo1 mongosh \
    'mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0' \
    --quiet --eval "db.getSiblingDB('$database').dropDatabase()" >/dev/null
}
