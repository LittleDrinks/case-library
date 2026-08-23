from __future__ import annotations

from datetime import UTC, datetime, timedelta

import mongomock
import pytest

from app.modules.search.outbox import SearchOutbox


NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class PassthroughSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def with_transaction(self, callback):
        return callback(None)


class AbortedSession(PassthroughSession):
    def __init__(self, database) -> None:
        self.database = database

    def with_transaction(self, callback):
        outbox = list(self.database.search_outbox.find())
        revoked = list(self.database.search_revocations.find())
        generation = list(self.database.search_catalog_generation.find())
        callback(None)
        self.database.search_outbox.delete_many({})
        self.database.search_revocations.delete_many({})
        self.database.search_catalog_generation.delete_many({})
        self.database.search_outbox.insert_many(outbox)
        self.database.search_revocations.insert_many(revoked)
        self.database.search_catalog_generation.insert_many(generation)
        raise RuntimeError("transaction aborted")


def outbox() -> tuple[SearchOutbox, Clock]:
    database = mongomock.MongoClient(tz_aware=True)["search_outbox_test"]
    database.client.start_session = lambda: PassthroughSession()
    _set_target(database)
    clock = Clock()
    return SearchOutbox(database, clock), clock


def _set_target(database, epoch="epoch-0") -> None:
    database.search_catalog_generation.insert_one(
        {
            "_id": "catalog",
            "generation": "generation-1",
            "indexUid": "catalog-1",
            "indexEpoch": epoch,
            "retiredIndexUids": [],
        }
    )


def complete(queue: SearchOutbox, claim, epoch="epoch-1") -> bool:
    return queue.complete(claim, queue.target(), epoch)


def test_enqueue_converges_on_the_latest_source_sequence() -> None:
    queue, _clock = outbox()

    queue.enqueue("case:case-1", 3, session=None)
    queue.enqueue("case:case-1", 2, session=None)
    queue.enqueue("case:case-1", 3, session=None)

    claim = queue.claim("worker-1")
    assert claim is not None
    assert (claim.logical_key, claim.sequence) == ("case:case-1", 3)
    assert claim.lease_expires_at == NOW + timedelta(seconds=60)
    assert set(claim.as_event()) == {"logicalKey", "sequence"}


def test_repeated_enqueue_preserves_the_first_pending_time() -> None:
    database = mongomock.MongoClient(tz_aware=True)["search_pending_age_test"]
    database.client.start_session = lambda: PassthroughSession()
    clock = Clock()
    queue = SearchOutbox(database, clock)

    queue.enqueue("case:case-hot", 1, session=None)
    clock.advance(9)
    queue.enqueue("case:case-hot", 2, session=None)
    clock.advance(9)
    queue.enqueue("case:case-hot", 3, session=None)

    row = database.search_outbox.find_one({"_id": "case:case-hot"})
    assert row["pendingSince"] == NOW
    assert (row["sequence"], row["updatedAt"]) == (3, clock.now)


def test_catch_up_deletes_the_row_and_next_enqueue_starts_pending_time() -> None:
    database = mongomock.MongoClient(tz_aware=True)["search_pending_reset_test"]
    database.client.start_session = lambda: PassthroughSession()
    _set_target(database)
    clock = Clock()
    queue = SearchOutbox(database, clock)
    queue.enqueue("case:case-reset", 1, session=None)
    claim = queue.claim("worker-1")

    clock.advance(5)
    assert complete(queue, claim) is True
    assert database.search_outbox.find_one() is None
    queue.enqueue("case:case-reset", 2, session=None)

    assert database.search_outbox.find_one()["pendingSince"] == clock.now


def test_record_groups_keys_under_a_global_monotonic_sequence() -> None:
    queue, _clock = outbox()

    first = queue.record(["case:case-1", "material:material-1"], session=None)
    second = queue.record(["material:material-2"], session=None)
    claims = [queue.claim(f"worker-{index}") for index in range(3)]

    assert (first, second) == (1, 2)
    assert {(claim.logical_key, claim.sequence) for claim in claims} == {
        ("case:case-1", 1),
        ("material:material-1", 1),
        ("material:material-2", 2),
    }


def test_record_persists_revocations_at_the_same_sequence() -> None:
    database = mongomock.MongoClient(tz_aware=True)["search_outbox_test"]
    queue = SearchOutbox(database, Clock())

    sequence = queue.record(
        ["case:case-1", "material:material-1"],
        revoke=["case:case-1", "material:material-1"],
        session=None,
    )
    rows = list(database.search_revocations.find().sort("logicalKey", 1))

    assert [(row["logicalKey"], row["id"], row["sequence"]) for row in rows] == [
        ("case:case-1", "case-1", sequence),
        ("material:material-1", "material-1", sequence),
    ]


def test_expired_claim_replays_and_only_the_current_lease_can_ack() -> None:
    queue, clock = outbox()
    queue.enqueue("material:material-1", 7, session=None)

    expired = queue.claim("worker-1")
    clock.advance(59)
    assert queue.claim("worker-2") is None
    clock.advance(2)
    replay = queue.claim("worker-2")

    assert replay is not None
    assert replay.sequence == 7
    assert replay.token != expired.token
    assert complete(queue, expired) is False
    assert complete(queue, replay) is True
    clock.advance(1)
    assert queue.sequence("material:material-1") is None


def test_an_expired_lease_cannot_ack_before_it_is_reclaimed() -> None:
    queue, clock = outbox()
    queue.enqueue("case:case-2", 4, session=None)
    expired = queue.claim("worker-1")

    assert expired is not None
    clock.advance(60)
    assert complete(queue, expired) is False
    assert queue.claim("worker-2") is not None


def test_complete_advances_claim_while_a_newer_sequence_stays_pending() -> None:
    queue, clock = outbox()
    database = queue._database
    queue.enqueue("case:case-3", 8, session=None)
    current = queue.claim("worker-1")

    clock.advance(1)
    queue.enqueue("case:case-3", 9, session=None)
    clock.advance(1)
    assert complete(queue, current) is True
    row = database.search_outbox.find_one({"_id": "case:case-3"})
    assert (row["sequence"], row["appliedSequence"]) == (9, 8)
    assert row["pendingSince"] == NOW
    assert "leaseToken" not in row
    next_claim = queue.claim("worker-2")

    assert next_claim is not None
    assert next_claim.sequence == 9


def test_claim_is_not_current_after_a_newer_source_sequence_arrives() -> None:
    queue, _clock = outbox()
    queue.enqueue("material:material-2", 4, session=None)
    stale = queue.claim("worker-1")

    queue.enqueue("material:material-2", 5, session=None)

    assert queue.current(stale) is False
    assert queue.release(stale) is True
    current = queue.claim("worker-2")
    assert current is not None
    assert current.sequence == 5


def test_rebuild_pause_invalidates_current_claim_and_blocks_new_work() -> None:
    queue, _clock = outbox()
    queue.enqueue("case:case-5", 1, session=None)
    claim = queue.claim("worker-1")

    assert queue.pause("rebuild-1") is True

    assert queue.paused() is True
    assert queue.current(claim) is False
    assert queue.has_active_claims() is True
    assert queue.release(claim) is True
    assert queue.resume("another-token") is False
    assert queue.resume("rebuild-1") is True


def test_rebuild_pause_is_exclusive_and_only_owner_can_resume() -> None:
    queue, _clock = outbox()

    assert queue.pause("rebuild-1") is True
    with pytest.raises(RuntimeError, match="检索目录正在重建"):
        queue.pause("rebuild-2")
    assert queue.resume("rebuild-2") is False
    assert queue.paused() is True
    assert queue.resume("rebuild-1") is True


def test_expired_rebuild_lease_can_be_taken_over_atomically() -> None:
    queue, clock = outbox()

    assert queue.pause("rebuild-1") is True
    clock.advance(30)

    assert queue.paused() is False
    assert queue.pause("rebuild-2") is True
    assert queue.resume("rebuild-1") is False
    assert queue.paused() is True
    assert queue.resume("rebuild-2") is True


def test_only_the_rebuild_owner_can_renew_an_active_lease() -> None:
    queue, clock = outbox()

    queue.pause("rebuild-1")
    clock.advance(20)

    assert queue.renew_pause("rebuild-2") is False
    assert queue.renew_pause("rebuild-1") is True
    clock.advance(20)
    assert queue.paused() is True
    clock.advance(10)
    assert queue.paused() is False


def test_expired_owner_cannot_publish_after_a_new_owner_takes_over() -> None:
    queue, clock = outbox()
    queue.pause("old-rebuild")
    assert queue.renew_pause("old-rebuild") is True
    clock.advance(30)
    queue.pause("new-rebuild")

    assert (
        queue.publish(
            "new-rebuild",
            {
                "_id": "catalog",
                "generation": "new",
                "indexUid": "catalog-new",
                "indexEpoch": "epoch-new",
                "retiredIndexUids": ["catalog-old"],
            },
        )
        is True
    )
    assert (
        queue.publish(
            "old-rebuild",
            {
                "_id": "catalog",
                "generation": "old",
                "indexUid": "catalog-old",
                "indexEpoch": "epoch-old",
                "retiredIndexUids": [],
            },
        )
        is False
    )

    assert queue.target().generation == "new"


def test_complete_rolls_back_ack_and_revocation_on_transaction_failure() -> None:
    database = mongomock.MongoClient(tz_aware=True)["search_complete_test"]
    _set_target(database)
    queue = SearchOutbox(database, Clock())
    sequence = queue.record(["case:case-1"], revoke=["case:case-1"], session=None)
    claim = queue.claim("worker-1")
    database.client.start_session = lambda: AbortedSession(database)

    with pytest.raises(RuntimeError, match="transaction aborted"):
        complete(queue, claim)

    row = database.search_outbox.find_one({"_id": "case:case-1"})
    assert row["appliedSequence"] == -1
    assert row["leaseToken"] == claim.token
    assert database.search_revocations.find_one()["sequence"] == sequence
    assert queue.target().index_epoch == "epoch-0"


def test_complete_preserves_a_newer_revocation() -> None:
    database = mongomock.MongoClient(tz_aware=True)["search_newer_revoke_test"]
    database.client.start_session = lambda: PassthroughSession()
    _set_target(database)
    queue = SearchOutbox(database, Clock())
    applied = queue.record(["material:m-1"], revoke=["material:m-1"], session=None)
    claim = queue.claim("worker-1")
    newer = queue.record(["material:m-1"], revoke=["material:m-1"], session=None)

    assert complete(queue, claim) is True

    row = database.search_outbox.find_one({"_id": "material:m-1"})
    assert (row["sequence"], row["appliedSequence"]) == (newer, applied)
    assert "leaseToken" not in row
    revocation = database.search_revocations.find_one({"logicalKey": "material:m-1"})
    assert revocation["sequence"] == newer


def test_different_key_epoch_cas_loser_can_be_requeued() -> None:
    queue, _clock = outbox()
    queue.enqueue("case:case-a", 1, session=None)
    queue.enqueue("case:case-b", 1, session=None)
    first, second = queue.claim("worker-a"), queue.claim("worker-b")
    target = queue.target()

    assert queue.complete(first, target, "epoch-a") is True
    assert queue.complete(second, target, "epoch-b") is False

    row = queue._collection.find_one({"_id": "case:case-b"})
    assert row["appliedSequence"] == -1
    assert row["leaseToken"] == second.token
    queue.requeue(second.logical_key)
    assert queue.release(second) is True
    assert queue.claim("worker-c").logical_key == "case:case-b"


@pytest.mark.parametrize("logical_key, sequence", [("", 0), ("case:case-4", -1)])
def test_enqueue_rejects_an_invalid_identity(logical_key: str, sequence: int) -> None:
    queue, _clock = outbox()

    with pytest.raises(ValueError, match="logical key and sequence"):
        queue.enqueue(logical_key, sequence, session=None)
