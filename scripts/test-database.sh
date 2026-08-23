#!/bin/sh

validate_test_database() {
  case "$1" in
    case_library_load|case_library_e2e|case_library_failover) return 0 ;;
    *) echo "Refusing to modify non-test database: $1" >&2; return 1 ;;
  esac
}

drop_test_database() {
  database="$1"
  validate_test_database "$database"
  compose exec -T mongo1 mongosh \
    'mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0' \
    --quiet --eval "db.getSiblingDB('$database').dropDatabase()" >/dev/null
}
