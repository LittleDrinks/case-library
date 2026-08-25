from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.database import Database


LEASE_DURATION = timedelta(seconds=60)
REBUILD_LEASE_DURATION = timedelta(seconds=30)
REBUILD_HEARTBEAT_SECONDS = 10


class _CompletionConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    logical_key: str
    sequence: int
    token: str
    lease_expires_at: datetime

    def as_event(self) -> dict:
        return {"logicalKey": self.logical_key, "sequence": self.sequence}


@dataclass(frozen=True, slots=True)
class CatalogTarget:
    generation: str
    index_uid: str
    index_epoch: str


class RebuildLease:
    def __init__(self, outbox: SearchOutbox, owner: str) -> None:
        self._outbox, self._owner = outbox, owner
        self._stopped = threading.Event()
        self._failure: Exception | None = None
        self._thread = threading.Thread(
            target=self._heartbeat,
            name="search-rebuild-heartbeat",
            daemon=True,
        )

    def __enter__(self) -> RebuildLease:
        self._outbox.pause(self._owner)
        self._thread.start()
        return self

    def _heartbeat(self) -> None:
        while not self._stopped.wait(REBUILD_HEARTBEAT_SECONDS):
            try:
                self._renew()
            except Exception as error:
                self._failure = error
                return

    def _renew(self) -> None:
        if not self._outbox.renew_pause(self._owner):
            raise RuntimeError("重建租约已失效")

    def _stop(self) -> None:
        self._stopped.set()
        self._thread.join()

    def finish(self) -> None:
        self._stop()
        if self._failure is not None:
            raise RuntimeError("重建租约已失效") from self._failure
        self._renew()

    def __exit__(self, error_type, *_error) -> None:
        self._stop()
        try:
            if error_type is None and self._failure is not None:
                raise RuntimeError("重建租约已失效") from self._failure
        finally:
            self._outbox.resume(self._owner)


def _now() -> datetime:
    return datetime.now(UTC)


def _session_options(session) -> dict:
    return {} if session is None else {"session": session}


def _claim_query(now: datetime) -> dict:
    return {
        "$expr": {"$gt": ["$sequence", "$appliedSequence"]},
        "$or": [
            {"leaseExpiresAt": {"$exists": False}},
            {"leaseExpiresAt": {"$lte": now}},
        ],
    }


def _claim_update(worker: str, token: str, now: datetime) -> list[dict]:
    return [
        {
            "$set": {
                "claimedSequence": "$sequence",
                "leaseOwner": worker,
                "leaseToken": token,
                "leaseExpiresAt": now + LEASE_DURATION,
            }
        }
    ]


def _lease_query(claim: OutboxClaim, now: datetime) -> dict:
    return {
        "_id": claim.logical_key,
        "sequence": claim.sequence,
        "claimedSequence": claim.sequence,
        "leaseToken": claim.token,
        "leaseExpiresAt": {"$gt": now},
    }


def _completion_query(claim: OutboxClaim, now: datetime) -> dict:
    return {
        "_id": claim.logical_key,
        "claimedSequence": claim.sequence,
        "leaseToken": claim.token,
        "leaseExpiresAt": {"$gt": now},
    }


def _target_query(target: CatalogTarget) -> dict:
    return {
        "_id": "catalog",
        "generation": target.generation,
        "indexUid": target.index_uid,
        "indexEpoch": target.index_epoch,
    }


def _rebuild_lease_query(owner: str, timestamp: datetime) -> dict:
    return {
        "_id": "catalog",
        "leaseOwner": owner,
        "leaseExpiresAt": {"$gt": timestamp},
    }


def _renew_lease(timestamp: datetime) -> dict:
    return {"$set": {"leaseExpiresAt": timestamp + REBUILD_LEASE_DURATION}}


def _pause_query(owner: str, timestamp: datetime) -> dict:
    reusable = {"leaseExpiresAt": {"$lte": timestamp}}
    return {"_id": "catalog", "$or": [reusable, {"leaseOwner": owner}]}


def _pause_update(owner: str, timestamp: datetime) -> dict:
    return {
        "$set": {
            "leaseOwner": owner,
            "leaseExpiresAt": timestamp + REBUILD_LEASE_DURATION,
        }
    }


def _requeue_query(logical_key: str) -> dict:
    return {
        "_id": logical_key,
        "$expr": {"$lte": ["$sequence", "$appliedSequence"]},
    }


def _requeue_update(timestamp: datetime) -> list[dict]:
    values = {
        "appliedSequence": {"$subtract": ["$sequence", 1]},
        "pendingSince": timestamp,
        "updatedAt": timestamp,
    }
    return [{"$set": values}]


def _requeue_record(logical_key: str, sequence: int, timestamp: datetime) -> dict:
    return {
        "_id": logical_key,
        "sequence": sequence,
        "appliedSequence": sequence - 1,
        "pendingSince": timestamp,
        "updatedAt": timestamp,
    }


def _enqueue_update(sequence: int, timestamp: datetime) -> list[dict]:
    current = {"$ifNull": ["$sequence", -1]}
    applied = {"$ifNull": ["$appliedSequence", -1]}
    next_sequence = {"$max": [current, sequence]}
    pending_since = _pending_since(current, applied, next_sequence, timestamp)
    values = {
        "sequence": next_sequence,
        "appliedSequence": applied,
        "pendingSince": pending_since,
        "updatedAt": timestamp,
    }
    return [{"$set": values}]


def _pending_since(current, applied, next_sequence, timestamp) -> dict:
    return {
        "$cond": [
            {"$gt": [current, applied]},
            "$pendingSince",
            {"$cond": [{"$gt": [next_sequence, applied]}, timestamp, "$pendingSince"]},
        ]
    }


def _ack_update(claim: OutboxClaim) -> dict:
    unset = {
        "claimedSequence": "",
        "leaseOwner": "",
        "leaseToken": "",
        "leaseExpiresAt": "",
    }
    return {"$max": {"appliedSequence": claim.sequence}, "$unset": unset}


class SearchOutbox:
    def __init__(self, database: Database, clock=_now) -> None:
        self._database = database
        self._collection = database.search_outbox
        self._state = database.search_catalog_state
        self._generation = database.search_catalog_generation
        self._control = database.search_control
        self._revocations = database.search_revocations
        self._clock = clock

    def rebuild_lease(self, owner: str) -> RebuildLease:
        return RebuildLease(self, owner)

    def record(self, logical_keys: list[str], *, revoke=(), session) -> int:
        keys = list(dict.fromkeys(logical_keys))
        if not keys:
            raise ValueError("at least one logical key is required")
        sequence = self._next_sequence(session)
        for logical_key in keys:
            self.enqueue(logical_key, sequence, session=session)
        for logical_key in dict.fromkeys(revoke):
            self._revoke(logical_key, sequence, session)
        return sequence

    def _revoke(self, logical_key: str, sequence: int, session) -> None:
        parts = logical_key.split(":", 1)
        if len(parts) != 2 or parts[0] not in {"case", "material"} or not parts[1]:
            raise ValueError("revocation must identify a catalog entity")
        record = {
            "logicalKey": logical_key,
            "id": parts[1],
            "sequence": sequence,
            "updatedAt": self._clock(),
        }
        self._revocations.update_one(
            {"_id": logical_key},
            {"$set": record},
            upsert=True,
            **_session_options(session),
        )

    def _next_sequence(self, session) -> int:
        row = self._control.find_one_and_update(
            {"_id": "catalog"},
            {"$inc": {"sequence": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
            **_session_options(session),
        )
        return row["sequence"]

    def pause(self, owner: str) -> bool:
        timestamp = self._clock()
        try:
            self._state.find_one_and_update(
                _pause_query(owner, timestamp),
                _pause_update(owner, timestamp),
                upsert=True,
            )
        except DuplicateKeyError as error:
            raise RuntimeError("检索目录正在重建") from error
        return True

    def renew_pause(self, owner: str) -> bool:
        timestamp = self._clock()
        query = {
            "_id": "catalog",
            "leaseOwner": owner,
            "leaseExpiresAt": {"$gt": timestamp},
        }
        update = {
            "$set": {
                "leaseExpiresAt": timestamp + REBUILD_LEASE_DURATION,
            }
        }
        return self._state.update_one(query, update).matched_count == 1

    def _publish(self, owner: str, marker: dict, session) -> bool:
        timestamp = self._clock()
        options = _session_options(session)
        renewed = self._state.update_one(
            _rebuild_lease_query(owner, timestamp),
            _renew_lease(timestamp),
            **options,
        )
        if renewed.matched_count != 1:
            return False
        self._generation.replace_one(
            {"_id": "catalog"},
            marker,
            upsert=True,
            **options,
        )
        return True

    def publish(self, owner: str, marker: dict) -> bool:
        with self._database.client.start_session() as session:
            return session.with_transaction(
                lambda active: self._publish(owner, marker, active)
            )

    def resume(self, owner: str) -> bool:
        result = self._state.delete_one({"_id": "catalog", "leaseOwner": owner})
        return result.deleted_count == 1

    def paused(self) -> bool:
        query = {"_id": "catalog", "leaseExpiresAt": {"$gt": self._clock()}}
        return self._state.find_one(query, {"_id": 1}) is not None

    def target(self) -> CatalogTarget | None:
        row = self._generation.find_one({"_id": "catalog"})
        fields = ("generation", "indexUid", "indexEpoch")
        if not row or not all(row.get(field) for field in fields):
            return None
        return CatalogTarget(row["generation"], row["indexUid"], row["indexEpoch"])

    def writable(self, target: CatalogTarget) -> bool:
        if self.paused():
            return False
        return self._generation.find_one(_target_query(target)) is not None

    def has_active_claims(self) -> bool:
        return (
            self._collection.find_one(
                {"leaseExpiresAt": {"$gt": self._clock()}},
                {"_id": 1},
            )
            is not None
        )

    def enqueue(self, logical_key: str, sequence: int, *, session) -> None:
        if not logical_key or sequence < 0:
            raise ValueError("logical key and sequence must identify source state")
        self._collection.update_one(
            {"_id": logical_key},
            _enqueue_update(sequence, self._clock()),
            upsert=True,
            **_session_options(session),
        )

    def claim(self, worker: str) -> OutboxClaim | None:
        timestamp, token = self._clock(), secrets.token_hex(16)
        row = self._collection.find_one_and_update(
            _claim_query(timestamp),
            _claim_update(worker, token, timestamp),
            sort=[("updatedAt", 1), ("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not row:
            return None
        return OutboxClaim(
            row["_id"], row["claimedSequence"], token, row["leaseExpiresAt"]
        )

    def current(self, claim: OutboxClaim) -> bool:
        if self.paused():
            return False
        query = _lease_query(claim, self._clock())
        return self._collection.find_one(query, {"_id": 1}) is not None

    def renew(self, claim: OutboxClaim) -> bool:
        timestamp = self._clock()
        update = {"$set": {"leaseExpiresAt": timestamp + LEASE_DURATION}}
        return (
            self._collection.update_one(
                _lease_query(claim, timestamp),
                update,
            ).matched_count
            == 1
        )

    def sequence(self, logical_key: str) -> int | None:
        row = self._collection.find_one({"_id": logical_key}, {"sequence": 1})
        return None if row is None else row["sequence"]

    def release(self, claim: OutboxClaim) -> bool:
        query = {"_id": claim.logical_key, "leaseToken": claim.token}
        update = {
            "$unset": {
                "claimedSequence": "",
                "leaseOwner": "",
                "leaseToken": "",
                "leaseExpiresAt": "",
            }
        }
        return self._collection.update_one(query, update).modified_count == 1

    def _ack_claim(self, claim: OutboxClaim, session) -> bool:
        query = _completion_query(claim, self._clock())
        options = _session_options(session)
        caught_up = self._collection.delete_one(
            {**query, "sequence": claim.sequence},
            **options,
        )
        if caught_up.deleted_count == 1:
            return True
        newer = {**query, "sequence": {"$gt": claim.sequence}}
        result = self._collection.update_one(newer, _ack_update(claim), **options)
        return result.modified_count == 1

    def _requeue(self, logical_key: str, session, sequence=None) -> None:
        timestamp = self._clock()
        options = _session_options(session)
        result = self._collection.update_one(
            _requeue_query(logical_key),
            _requeue_update(timestamp),
            **options,
        )
        if sequence is None or result.matched_count == 1:
            return
        record = _requeue_record(logical_key, sequence, timestamp)
        self._collection.update_one(
            {"_id": logical_key},
            {"$setOnInsert": record},
            upsert=True,
            **options,
        )

    def _completion_current(self, claim, session) -> bool:
        options, timestamp = _session_options(session), self._clock()
        paused = self._state.find_one(
            {"_id": "catalog", "leaseExpiresAt": {"$gt": timestamp}},
            **options,
        )
        current = self._collection.find_one(
            _completion_query(claim, timestamp),
            {"_id": 1},
            **options,
        )
        return paused is None and current is not None

    def _complete(self, claim, target, index_epoch, session) -> bool:
        if not self._completion_current(claim, session):
            self._requeue(claim.logical_key, session, claim.sequence)
            return False
        if not self._update_epoch(target, index_epoch, session):
            self._requeue(claim.logical_key, session, claim.sequence)
            return False
        if not self._ack_claim(claim, session):
            raise _CompletionConflict
        self._clear_revocations(claim, session)
        return True

    def _update_epoch(self, target, index_epoch, session) -> bool:
        result = self._generation.update_one(
            _target_query(target),
            {"$set": {"indexEpoch": index_epoch}},
            **_session_options(session),
        )
        return result.matched_count == 1

    def _clear_revocations(self, claim, session) -> None:
        query = {"logicalKey": claim.logical_key, "sequence": {"$lte": claim.sequence}}
        self._revocations.delete_one(query, **_session_options(session))

    def complete(self, claim, target, index_epoch) -> bool:
        try:
            with self._database.client.start_session() as session:
                return session.with_transaction(
                    lambda active: self._complete(claim, target, index_epoch, active)
                )
        except _CompletionConflict:
            self._requeue(claim.logical_key, None, claim.sequence)
            return False

    def requeue(self, logical_key: str) -> None:
        self._requeue(logical_key, None)
