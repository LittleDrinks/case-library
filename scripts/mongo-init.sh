#!/bin/sh
set -eu

wait_for_node() {
  host="$1"
  until mongosh --host "$host" --quiet --eval \
    "quit(db.adminCommand('ping').ok ? 0 : 1)" >/dev/null 2>&1; do
    sleep 2
  done
}

is_initialized() {
  mongosh --host mongo1 --quiet --eval \
    "const s=db.adminCommand({replSetGetStatus:1}); quit(s.ok === 1 ? 0 : 1)" \
    >/dev/null 2>&1
}

init_replica_set() {
  mongosh --host mongo1 --quiet --eval '
    rs.initiate({
      _id: "rs0",
      members: [
        {_id: 0, host: "mongo1:27017", priority: 2},
        {_id: 1, host: "mongo2:27017", priority: 1},
        {_id: 2, host: "mongo3:27017", priority: 1}
      ]
    })' >/dev/null
}

replica_set_ready() {
  mongosh --host mongo1 --quiet --eval '
    const expected = ["mongo1:27017", "mongo2:27017", "mongo3:27017"];
    const status = db.adminCommand({replSetGetStatus: 1});
    const members = status.members || [];
    const names = members.map(member => member.name).sort();
    const states = members.map(member => member.stateStr);
    const healthy = members.every(member => member.health === 1);
    const config = rs.conf().members.map(member => member.host).sort();
    const exact = JSON.stringify(names) === JSON.stringify(expected);
    const configured = JSON.stringify(config) === JSON.stringify(expected);
    quit(exact && configured && healthy &&
      states.filter(state => state === "PRIMARY").length === 1 &&
      states.filter(state => state === "SECONDARY").length === 2 ? 0 : 1);
  ' >/dev/null 2>&1
}

for host in mongo1 mongo2 mongo3; do
  wait_for_node "$host"
done

if ! is_initialized; then
  init_replica_set
fi

until replica_set_ready; do
  sleep 2
done
