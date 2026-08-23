from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import mongomock
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from conftest import EmptySearchCatalog, ReadyCatalogState
from tests.conftest import MemoryBlobStore


class PassthroughSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def with_transaction(self, callback):
        return callback(None)


class UnknownCommitSession(PassthroughSession):
    def with_transaction(self, callback):
        callback(None)
        raise RuntimeError("commit result unknown")


class BlockingBlobStore(MemoryBlobStore):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def put(self, blob_id, source, length, content_type) -> None:
        self.started.set()
        assert self.release.wait(5)
        super().put(blob_id, source, length, content_type)


def _client(store: MemoryBlobStore) -> TestClient:
    database = mongomock.MongoClient()["attachment_concurrency"]
    database.client.admin.command = lambda _name: {"ok": 1, "isWritablePrimary": True}
    database.client.start_session = lambda: PassthroughSession()
    settings = Settings(
        app_environment="test", enable_demo_seed=True, session_cookie_secure=False
    )
    return TestClient(
        create_app(
            database=database,
            settings=settings,
            blob_store=store,
            search_catalog=EmptySearchCatalog(),
            catalog_state=ReadyCatalogState(database),
        )
    )


def _login(client: TestClient) -> dict:
    return client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    ).json()


def _upload(client: TestClient, headers: dict, revision: int) -> dict:
    return client.post(
        "/api/cases/c-draft-1/attachments",
        headers=headers,
        data={"accessLevel": "public", "revision": revision},
        files={"file": ("kept.txt", b"kept", "text/plain")},
    ).json()


def _upload_response(client: TestClient, headers: dict, revision: int):
    return client.post(
        "/api/cases/c-draft-1/attachments",
        headers=headers,
        data={"accessLevel": "public", "revision": revision},
        files={"file": ("racing.txt", b"racing", "text/plain")},
    )


def _submit(client: TestClient, headers: dict, revision: int):
    return client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers,
        json={"command": "submit", "revision": revision},
    )


def _race_upload(client, store, headers, revision):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_upload_response, client, headers, revision)
        assert store.started.wait(5)
        submitted = _submit(client, headers, revision)
        store.release.set()
        return submitted, future.result()


def _block_lookup(database, attachment_id: str) -> tuple[Event, Event]:
    started, release = Event(), Event()
    original = database.attachments.find_one

    def find_one(query, *args, **kwargs):
        row = original(query, *args, **kwargs)
        if query.get("id") == attachment_id:
            started.set()
            assert release.wait(5)
        return row

    database.attachments.find_one = find_one
    return started, release


def _race_delete(client, headers, current, attachment, started, release):
    path = f"/api/cases/c-draft-1/attachments/{attachment['id']}"
    with ThreadPoolExecutor(max_workers=1) as pool:
        deletion = pool.submit(
            client.delete,
            path,
            headers=headers,
            params={"revision": current["revision"]},
        )
        assert started.wait(5)
        submitted = client.post(
            "/api/cases/c-draft-1/lifecycle",
            headers=headers,
            json={"command": "submit", "revision": current["revision"]},
        )
        release.set()
        return submitted, deletion.result()


def _delete_race_results(client, store):
    auth = _login(client)
    headers = {"X-CSRF-Token": auth["csrfToken"]}
    current = client.get("/api/cases/c-draft-1").json()
    attachment = _upload(client, headers, current["revision"])
    current = client.get("/api/cases/c-draft-1").json()
    started, release = _block_lookup(client.app.state.database, attachment["id"])
    submitted, deleted = _race_delete(
        client, headers, current, attachment, started, release
    )
    content = client.get(f"/api/cases/c-draft-1/attachments/{attachment['id']}/content")
    history = client.get("/api/cases/c-draft-1/history").json()
    return submitted, deleted, content, history, attachment


def test_upload_loses_revision_race_with_submit_and_cleans_blob() -> None:
    store = BlockingBlobStore()
    with _client(store) as client:
        auth = _login(client)
        case = client.get("/api/cases/c-draft-1").json()
        headers = {"X-CSRF-Token": auth["csrfToken"]}
        submitted, uploaded = _race_upload(client, store, headers, case["revision"])

    assert submitted.status_code == 200
    assert uploaded.status_code == 409
    assert store.objects == {}


def test_delete_loses_revision_race_and_keeps_submitted_blob() -> None:
    store = MemoryBlobStore()
    with _client(store) as client:
        results = _delete_race_results(client, store)
    submitted, deleted, content, history, attachment = results
    assert submitted.status_code == 200
    assert deleted.status_code == 409
    assert content.content == b"kept"
    assert history["versions"][0]["attachments"] == [attachment]
    assert len(store.objects) == 1


def test_upload_keeps_blob_when_commit_result_is_unknown() -> None:
    store = MemoryBlobStore()
    with _client(store) as client:
        auth = _login(client)
        database = client.app.state.database
        database.client.start_session = lambda: UnknownCommitSession()
        headers = {"X-CSRF-Token": auth["csrfToken"]}
        revision = client.get("/api/cases/c-draft-1").json()["revision"]

        try:
            _upload(client, headers, revision)
        except RuntimeError as error:
            assert str(error) == "commit result unknown"

        attachment = database.attachments.find_one({"caseId": "c-draft-1"})
        assert attachment is not None
        assert store.objects[attachment["blobId"]] == b"kept"
