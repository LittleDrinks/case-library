from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from docx import Document
from app.core.config import Settings
from app.modules.agent.case_area import area_rows, retained_sources
from app.modules.agent.deps import ToolDeps
from app.modules.agent.search import CorpusSearchParams
from app.modules.agent.skills import read_source, search_corpus
from app.modules.agent.visibility import SourceGate, visible_parts
from app.modules.attachments.storage import minio_blob_store
from app.modules.search.client import (
    create_client,
    create_reader,
    index_epoch,
    wait_task,
)
from app.modules.search.indexer import CatalogRebuilder
from app.modules.search.meilisearch import MeilisearchCatalog
from app.modules.search.outbox import SearchOutbox
from app.modules.search.state import MongoCatalogState
from pymongo import MongoClient

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
pytestmark = pytest.mark.e2e(
    "CASE_LIBRARY_E2E_URL",
    "AUTH_QUERY_MONGODB_URI",
    "MEILI_CONTRACT_URL",
    "MEILI_CONTRACT_KEY_FILE",
    "OBJECT_STORE_ENDPOINT",
    "OBJECT_STORE_BUCKET",
    "OBJECT_STORE_ACCESS_KEY_FILE",
    "OBJECT_STORE_SECRET_KEY_FILE",
)


def _login(username: str, password: str) -> tuple[httpx.Client, dict]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return client, response.json()


def _streamed_text(response: httpx.Response) -> str:
    return "".join(
        json.loads(line[6:]).get("delta", "")
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"type":"text-delta"' in line
    )


def _unverified_user(role: str = "user") -> tuple[httpx.Client, dict]:
    username = f"private-boundary-{uuid.uuid4().hex}"
    password = f"Issue358-{uuid.uuid4().hex}!a"
    registered = httpx.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
    )
    assert registered.status_code == 201
    client, auth = _login(username, password)
    if role == "admin":
        mongo_client, database = _database()
        try:
            database.users.update_one(
                {"id": auth["user"]["id"]},
                {"$set": {"role": "admin", "campus_verified": False}},
            )
        finally:
            mongo_client.close()
        session = client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["user"]["role"] == "admin"
        assert session.json()["user"]["campusVerified"] is False
        auth["user"] = session.json()["user"]
    return client, auth


def _create_case(client: httpx.Client, auth: dict, title: str) -> dict:
    document = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": title}]}],
    }
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": title, "document": document},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _upload_private(
    client: httpx.Client, auth: dict, case_id: str, content: str,
    access_level: str = "private",
) -> dict:
    case = client.get(f"/api/cases/{case_id}").json()
    response = client.post(
        f"/api/cases/{case_id}/attachments",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        data={"accessLevel": access_level, "revision": case["revision"]},
        files={"file": (f"{content}.txt", content.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _transition(
    client: httpx.Client,
    auth: dict,
    case_id: str,
    command: str,
    revision: int,
    **extra,
) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"command": command, "revision": revision, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _published(
    client: httpx.Client, auth: dict, case_id: str, material_id: str | None = None
) -> dict:
    case = client.get(f"/api/cases/{case_id}").json()
    if material_id:
        mounted = client.post(
            f"/api/cases/{case_id}/materials",
            headers={"X-CSRF-Token": auth["csrfToken"]},
            json={"materialId": material_id, "revision": case["revision"]},
        )
        assert mounted.status_code == 201, mounted.text
        case = client.get(f"/api/cases/{case_id}").json()
    submitted = _transition(client, auth, case_id, "submit", case["revision"])
    admin, admin_auth = _login("admin", "admin123")
    review = admin.get(f"/api/cases/{case_id}/review").json()
    started = _transition(
        admin, admin_auth, case_id, "start", review["revision"]
    )
    approved = _transition(
        admin,
        admin_auth,
        case_id,
        "approve",
        started["case"]["revision"],
        submittedVersionId=submitted["version"]["id"],
    )
    return {"version": submitted["version"], "admin": admin, "adminAuth": admin_auth, "approved": approved}


def _database():
    client = MongoClient(os.environ["AUTH_QUERY_MONGODB_URI"])
    return client, client.get_default_database()


def _search_corpus_when_ready(context, params):
    deadline = time.monotonic() + 45
    while True:
        try:
            return asyncio.run(search_corpus(context, params))
        except RuntimeError as error:
            if str(error) != "检索服务暂不可用" or time.monotonic() >= deadline:
                raise
            time.sleep(0.2)


def _wait_for_search_directory() -> None:
    deadline = time.monotonic() + 45
    query = f"private-boundary-ready-{uuid.uuid4().hex}"
    with httpx.Client(base_url=BASE_URL, timeout=3) as client:
        while True:
            response = client.get(
                "/api/search",
                params={"q": query, "kind": "case", "pageSize": 1},
            )
            if response.status_code == 503:
                if response.json().get("detail") not in {
                    "检索目录正在同步",
                    "检索暂不可用",
                }:
                    raise AssertionError("检索目录返回了非就绪类 503")
                if time.monotonic() >= deadline:
                    raise AssertionError("检索目录在等待期限内未就绪")
                time.sleep(0.2)
                continue
            assert response.status_code == 200, response.text
            assert isinstance(response.json().get("items"), list)
            return


def _wait_for_search_item(client, query: str, kind: str, source_id: str) -> dict:
    deadline = time.monotonic() + 45
    while True:
        response = client.get(
            "/api/search", params={"q": query, "kind": kind, "pageSize": 20}
        )
        if response.status_code == 503:
            if response.json().get("detail") not in {
                "检索目录正在同步",
                "检索暂不可用",
            }:
                raise AssertionError("检索目录返回了非就绪类 503")
        else:
            assert response.status_code == 200, response.text
            item = next(
                (row for row in response.json()["items"] if row["id"] == source_id),
                None,
            )
            if item:
                return item
        if time.monotonic() >= deadline:
            raise AssertionError(f"检索目录未返回预期 {kind} 条目")
        time.sleep(0.2)


def _search_material(client, query: str, method: str) -> httpx.Response:
    params = {"q": query, "kind": "material", "pageSize": 20}
    if method == "GET":
        return client.get("/api/search", params=params)
    return client.post("/api/search", json=params)


def _assert_hidden_private_material_search(
    response: httpx.Response, material_id: str
) -> None:
    assert response.status_code == 200, response.text
    body = response.json()
    assert all(row["id"] != material_id for row in body["items"])
    assert body["total"] == 0
    assert body["counts"]["material"] == 0


def _assert_referenced_private_material_http_acl(
    author: httpx.Client,
    admin: httpx.Client,
    other: httpx.Client,
    query: str,
    material_id: str,
    database,
) -> None:
    assert database.materials.find_one({"id": material_id})[
        "publicReferenceCount"
    ] == 1
    _wait_for_search_item(author, query, "material", material_id)
    for method in ("GET", "POST"):
        owner_response = _search_material(author, query, method)
        assert owner_response.status_code == 200, owner_response.text
        owner_body = owner_response.json()
        assert [row["id"] for row in owner_body["items"]] == [material_id]
        assert owner_body["total"] == 1
        assert owner_body["counts"]["material"] == 1
        for reader in (admin, other):
            _assert_hidden_private_material_search(
                _search_material(reader, query, method), material_id
            )
        with httpx.Client(base_url=BASE_URL) as anonymous:
            _assert_hidden_private_material_search(
                _search_material(anonymous, query, method), material_id
            )


@pytest.fixture(scope="session", autouse=True)
def search_directory_ready() -> None:
    _wait_for_search_directory()


def test_real_http_mongo_minio_and_review_history_boundaries() -> None:
    author, author_auth = _login("user", "user123")
    admin, admin_auth = _login("admin", "admin123")
    stranger, _stranger_auth = _login("10000001", "Demo-10000001-2026!")
    anonymous = httpx.Client(base_url=BASE_URL)
    marker = f"private-review-{uuid.uuid4().hex}"
    case = _create_case(author, author_auth, marker)
    attachment = _upload_private(author, author_auth, case["id"], f"blob-{marker}")
    case_id = case["id"]
    content_path = f"/api/cases/{case_id}/attachments/{attachment['id']}/content"

    assert author.get(f"/api/cases/{case_id}").status_code == 200
    assert author.get(f"/api/cases/{case_id}/export.docx").status_code == 200
    assert author.get(content_path).content == f"blob-{marker}".encode()
    for reader in (admin, stranger, anonymous):
        for path in (
            f"/api/cases/{case_id}",
            f"/api/cases/{case_id}/sources",
            f"/api/cases/{case_id}/attachments",
            f"/api/cases/{case_id}/export.docx",
            content_path,
        ):
            assert reader.get(path).status_code in {401, 403, 404}
    admin_list = admin.get("/api/cases", params={"scope": "admin"}).json()
    assert case_id not in {row["id"] for row in admin_list}
    assert admin.get("/api/cases/drafts", params={"q": marker}).json()["total"] == 0
    assert admin.get(f"/api/cases/{case_id}/history").status_code == 403
    assert stranger.get(f"/api/cases/{case_id}/history").status_code == 403
    assert anonymous.get(f"/api/cases/{case_id}/history").status_code == 401

    client, database = _database()
    try:
        private_note = author.post(
            f"/api/cases/{case_id}/annotations",
            headers={"X-CSRF-Token": author_auth["csrfToken"]},
            json={
                "quote": marker,
                "section": "正文",
                "content": f"author-private-note-{marker}",
                "source": "manual",
                "revision": author.get(f"/api/cases/{case_id}").json()["revision"],
                "from": 1,
                "to": 1 + len(marker),
            },
        )
        assert private_note.status_code == 201, private_note.text
        reply = author.post(
            f"/api/cases/{case_id}/annotations/{private_note.json()['id']}/replies",
            headers={"X-CSRF-Token": author_auth["csrfToken"]},
            json={"content": f"author-private-reply-{marker}"},
        )
        assert reply.status_code == 200, reply.text
        submitted = _transition(
            author,
            author_auth,
            case_id,
            "submit",
            author.get(f"/api/cases/{case_id}").json()["revision"],
        )
        frozen_id = submitted["version"]["id"]
        stored = database.case_versions.find_one({"id": frozen_id, "caseId": case_id})
        assert stored["title"] == marker
        assert stored["attachments"][0]["id"] == attachment["id"]
        assert stored["attachments"][0]["accessLevel"] == "private"

        assert admin.get(f"/api/cases/{case_id}").status_code == 404
        assert admin.get(f"/api/cases/{case_id}/review").json()["document"] == stored["document"]
        assert admin.get(f"/api/cases/{case_id}/history").json()["versions"][0]["id"] == frozen_id
        started = _transition(
            admin, admin_auth, case_id, "start", submitted["case"]["revision"]
        )
        assert f"author-private-note-{marker}" not in str(started["version"])
        assert f"author-private-reply-{marker}" not in str(started["version"])
        assert stranger.get(f"/api/cases/{case_id}/review").status_code == 403
        assert anonymous.get(f"/api/cases/{case_id}/review").status_code == 401
        assert admin.get(f"/api/cases/{case_id}/attachments").status_code == 404
        frozen_attachments = admin.get(
            f"/api/cases/{case_id}/attachments", params={"versionId": frozen_id}
        )
        assert frozen_attachments.status_code == 200
        assert frozen_attachments.json()[0]["id"] == attachment["id"]
        assert admin.get(
            content_path, params={"versionId": frozen_id}
        ).status_code == 403
        source_rows = admin.get(
            f"/api/cases/{case_id}/sources", params={"versionId": frozen_id}
        ).json()["entries"]
        assert len(source_rows) == 1 and source_rows[0]["contentAvailable"] is False
        assert admin.get(f"/api/cases/{case_id}/review/export.docx").status_code == 200
        assert admin.get(f"/api/cases/{case_id}/export.docx").status_code == 404

        review_thread = admin.get(
            f"/api/cases/{case_id}/agent/thread",
            params={"versionId": frozen_id, "mode": "review"},
        )
        assert review_thread.status_code == 200
        thread = review_thread.json()
        assert thread["versionId"] == frozen_id
        assert admin.get(
            f"/api/cases/{case_id}/agent/thread",
            params={"versionId": "cv-stale", "mode": "review"},
        ).status_code == 409
        assert admin.get(f"/api/cases/{case_id}/agent/thread").status_code == 404
        assert author.get(
            f"/api/cases/{case_id}/agent/threads/{thread['id']}"
        ).status_code == 404
        ref = {
            "kind": "attachment",
            "id": attachment["id"],
            "title": attachment["name"],
            "snippet": f"blob-{marker}",
            "location": f"attachment:{case_id}/{attachment['id']}",
        }
        database.agent_messages.insert_one(
            {
                "id": f"history-{uuid.uuid4().hex}",
                "threadId": thread["id"],
                "runId": f"synthetic-{uuid.uuid4().hex}",
                "messageSeq": 1,
                "role": "assistant",
                "metadata": {},
                "parts": [
                    {"type": "text", "text": f"blob-{marker}"},
                    {
                        "type": "tool-read_source",
                        "output": {
                            "status": "ok",
                            "content": f"blob-{marker}",
                            "usedSourceRef": ref,
                        },
                    },
                    {"type": "tool-search_corpus", "output": {"sources": [ref]}},
                ],
                "createdAt": datetime.now(UTC),
            }
        )
        restored = admin.get(
            f"/api/cases/{case_id}/agent/thread", params={"mode": "review"}
        ).json()
        assistant = restored["messages"][0]
        assert f"blob-{marker}" not in str(assistant["parts"])
        assert assistant["parts"][0]["text"] == "该回答引用的来源当前不可读，相关内容已隐藏"
        assert assistant["parts"][1]["output"]["status"] == "no_access"
        assert assistant["parts"][2]["output"]["sources"] == []

        _transition(
            admin,
            admin_auth,
            case_id,
            "reject",
            started["case"]["revision"],
            submittedVersionId=frozen_id,
            reasonTypes=["内容需要补充或修改"],
        )
        returned_review = admin.get(
            f"/api/cases/{case_id}/review", params={"versionId": frozen_id}
        )
        assert returned_review.status_code == 200
        returned_record = returned_review.json()
        assert returned_record["title"] == marker
        assert returned_record["reviewRecordStatus"] == "returned"
        assert returned_record["isCurrentReviewVersion"] is False
        assert returned_record["availableActions"] == []
        assert returned_record["reviewFeedback"]["action"] == "reject"
        assert returned_record["reviewFeedback"]["reasonTypes"] == ["内容需要补充或修改"]
        frozen_annotation = admin.post(
            f"/api/cases/{case_id}/annotations?versionId={frozen_id}",
            headers={"X-CSRF-Token": admin_auth["csrfToken"]},
            json={
                "quote": marker,
                "section": "正文",
                "content": "退回后不应新增指导批注",
                "source": "admin",
                "revision": returned_record["revision"],
                "from": 1,
                "to": 1 + len(marker),
            },
        )
        assert frozen_annotation.status_code == 409
        approve_replay = admin.post(
            f"/api/cases/{case_id}/lifecycle",
            headers={"X-CSRF-Token": admin_auth["csrfToken"]},
            json={
                "command": "approve",
                "revision": returned_record["revision"],
                "submittedVersionId": frozen_id,
            },
        )
        assert approve_replay.status_code == 409
        assert admin.get(
            f"/api/cases/{case_id}/agent/threads/{thread['id']}"
        ).status_code in {403, 409}
        author_case = author.get(f"/api/cases/{case_id}").json()
        changed = author.patch(
            f"/api/cases/{case_id}",
            headers={"X-CSRF-Token": author_auth["csrfToken"]},
            json={"title": f"{marker}-edited", "revision": author_case["revision"]},
        )
        assert changed.status_code == 200
        resubmitted = _transition(
            author,
            author_auth,
            case_id,
            "submit",
            changed.json()["revision"],
        )
        assert resubmitted["version"]["title"] == f"{marker}-edited"
        assert resubmitted["version"]["id"] != frozen_id
        assert admin.get(
            f"/api/cases/{case_id}/agent/threads/{thread['id']}"
        ).status_code in {403, 409}
        current_review = admin.get(f"/api/cases/{case_id}/review").json()
        assert current_review["submittedVersionId"] == resubmitted["version"]["id"]
        assert current_review["title"] == f"{marker}-edited"
    finally:
        client.close()


def _tool_deps(
    database, user: dict, case_id: str, version_id: str, catalog, state, store,
    secret_path: str,
):
    return ToolDeps(
        database=database,
        case_id=case_id,
        thread_id=f"private-boundary-{user['id']}",
        run_id="read-only-e2e",
        user=user,
        catalog=catalog,
        catalog_state=state,
        secret_path=secret_path,
        store=store,
        version_id=version_id,
        sources=retained_sources(database, case_id, user, version_id),
    )


def test_withdrawn_submission_remains_version_scoped_and_cannot_be_approved() -> None:
    author, author_auth = _login("user", "user123")
    admin, admin_auth = _login("admin", "admin123")
    marker = f"withdrawn-review-{uuid.uuid4().hex}"
    case = _create_case(author, author_auth, marker)
    case_id = case["id"]
    frozen_attachment = _upload_private(
        author, author_auth, case_id, f"frozen-attachment-{marker}"
    )
    case = author.get(f"/api/cases/{case_id}").json()
    submitted = _transition(author, author_auth, case_id, "submit", case["revision"])
    version_id = submitted["version"]["id"]
    started = _transition(
        admin, admin_auth, case_id, "start", submitted["case"]["revision"]
    )
    review_thread = admin.get(
        f"/api/cases/{case_id}/agent/thread", params={"mode": "review"}
    )
    assert review_thread.status_code == 200
    review_thread_id = review_thread.json()["id"]

    def add_guidance(content: str, revision: int) -> dict:
        response = admin.post(
            f"/api/cases/{case_id}/annotations?versionId={version_id}",
            headers={"X-CSRF-Token": admin_auth["csrfToken"]},
            json={
                "quote": marker,
                "section": "正文",
                "content": content,
                "source": "admin",
                "revision": revision,
                "from": 1,
                "to": 1 + len(marker),
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    first = add_guidance("请补充课程目标", started["case"]["revision"])
    second = add_guidance("请核实材料来源", started["case"]["revision"])
    withdrawn = _transition(
        author, author_auth, case_id, "withdraw", started["case"]["revision"]
    )
    assert admin.get(
        f"/api/cases/{case_id}/agent/threads/{review_thread_id}"
    ).status_code in {403, 409}
    changed = author.patch(
        f"/api/cases/{case_id}",
        headers={"X-CSRF-Token": author_auth["csrfToken"]},
        json={"title": f"{marker}-private-edit", "revision": withdrawn["case"]["revision"]},
    )
    assert changed.status_code == 200
    live_attachment = _upload_private(
        author, author_auth, case_id, f"live-attachment-{marker}"
    )

    assert admin.get(f"/api/cases/{case_id}").status_code == 404
    assert admin.get(f"/api/cases/{case_id}/review").status_code == 404
    frozen_attachments = admin.get(
        f"/api/cases/{case_id}/attachments", params={"versionId": version_id}
    )
    assert frozen_attachments.status_code == 200
    assert [row["id"] for row in frozen_attachments.json()] == [frozen_attachment["id"]]
    assert admin.get(
        f"/api/cases/{case_id}/attachments/{frozen_attachment['id']}/content",
        params={"versionId": version_id},
    ).status_code == 403
    assert admin.get(
        f"/api/cases/{case_id}/attachments/{live_attachment['id']}/content",
        params={"versionId": version_id},
    ).status_code == 404
    assert admin.get(
        f"/api/cases/{case_id}/review/export.docx", params={"versionId": version_id}
    ).status_code == 200
    source_rows = admin.get(
        f"/api/cases/{case_id}/sources", params={"versionId": version_id}
    ).json()["entries"]
    assert len(source_rows) == 1 and source_rows[0]["contentAvailable"] is False
    frozen = admin.get(
        f"/api/cases/{case_id}/review", params={"versionId": version_id}
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["title"] == marker
    assert frozen.json()["reviewRecordStatus"] == "withdrawn"
    assert frozen.json()["availableActions"] == []
    assert marker + "-private-edit" not in frozen.text

    current = frozen.json()
    third = add_guidance("撤回后继续补充这一点", frozen.json()["revision"])
    rows = admin.get(
        f"/api/cases/{case_id}/annotations", params={"versionId": version_id}
    )
    assert rows.status_code == 200
    assert {row["id"] for row in rows.json()} == {first["id"], second["id"], third["id"]}
    assert {row["versionId"] for row in rows.json()} == {version_id}
    replay = admin.post(
        f"/api/cases/{case_id}/lifecycle",
        headers={"X-CSRF-Token": admin_auth["csrfToken"]},
        json={
            "command": "approve",
            "revision": current["revision"],
            "submittedVersionId": version_id,
        },
    )
    assert replay.status_code == 409
    author_rows = author.get(
        f"/api/cases/{case_id}/annotations", params={"versionId": version_id}
    )
    assert author_rows.status_code == 200
    assert {row["id"] for row in author_rows.json()} == {first["id"], second["id"], third["id"]}

    resubmitted = _transition(
        author,
        author_auth,
        case_id,
        "submit",
        author.get(f"/api/cases/{case_id}").json()["revision"],
    )
    assert resubmitted["version"]["id"] != version_id
    current_review = admin.get(f"/api/cases/{case_id}/review").json()
    assert current_review["submittedVersionId"] == resubmitted["version"]["id"]
    assert current_review["title"] == f"{marker}-private-edit"
    assert {
        row["id"]
        for row in admin.get(
            f"/api/cases/{case_id}/attachments",
            params={"versionId": resubmitted['version']['id']},
        ).json()
    } == {frozen_attachment["id"], live_attachment["id"]}
    old_review = admin.get(
        f"/api/cases/{case_id}/review", params={"versionId": version_id}
    )
    assert old_review.status_code == 200 and old_review.json()["title"] == marker
    assert old_review.json()["reviewRecordStatus"] == "withdrawn"
    new_rows = author.get(
        f"/api/cases/{case_id}/annotations",
        params={"versionId": resubmitted["version"]["id"]},
    )
    assert new_rows.status_code == 200 and new_rows.json() == []
    old_rows = author.get(
        f"/api/cases/{case_id}/annotations", params={"versionId": version_id}
    )
    assert {row["id"] for row in old_rows.json()} == {first["id"], second["id"], third["id"]}


def test_submitted_version_without_annotations_cannot_be_deleted_after_withdrawal() -> None:
    author, author_auth = _unverified_user()
    admin, _admin_auth = _unverified_user("admin")
    marker = f"frozen-record-{uuid.uuid4().hex}"
    case = _create_case(author, author_auth, marker)
    submitted = _transition(author, author_auth, case["id"], "submit", case["revision"])
    version_id = submitted["version"]["id"]
    withdrawn = _transition(
        author, author_auth, case["id"], "withdraw", submitted["case"]["revision"]
    )
    assert withdrawn["version"]["id"] == version_id
    assert withdrawn["version"].get("annotations", []) == []

    deleted = author.delete(
        f"/api/cases/{case['id']}/versions/{version_id}",
        headers={"X-CSRF-Token": author_auth["csrfToken"]},
    )
    assert deleted.status_code == 409, deleted.text
    historical = admin.get(f"/api/cases/{case['id']}/review", params={"versionId": version_id})
    assert historical.status_code == 200, historical.text
    assert historical.json()["title"] == marker
    assert admin.get(f"/api/cases/{case['id']}/history").json()["versions"][0]["id"] == version_id


def test_admin_case_owner_can_read_own_frozen_private_annotations() -> None:
    owner, owner_auth = _unverified_user("admin")
    marker = f"admin-owner-private-{uuid.uuid4().hex}"
    case = _create_case(owner, owner_auth, marker)
    note = owner.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={
            "quote": marker,
            "section": "正文",
            "content": f"owner-private-note-{marker}",
            "source": "manual",
            "revision": case["revision"],
            "from": 1,
            "to": 1 + len(marker),
        },
    )
    assert note.status_code == 201, note.text
    reply = owner.post(
        f"/api/cases/{case['id']}/annotations/{note.json()['id']}/replies",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"content": f"owner-private-reply-{marker}"},
    )
    assert reply.status_code == 200, reply.text

    submitted = _transition(owner, owner_auth, case["id"], "submit", case["revision"])
    history = owner.get(f"/api/cases/{case['id']}/history")
    assert history.status_code == 200, history.text
    frozen = next(
        row for row in history.json()["versions"]
        if row["id"] == submitted["version"]["id"]
    )
    assert f"owner-private-note-{marker}" in str(frozen["annotations"])
    assert f"owner-private-reply-{marker}" in str(frozen["annotations"])


@pytest.mark.parametrize("role", ["user", "admin"])
def test_case_owner_lists_frozen_private_annotations_and_own_versions(role: str) -> None:
    owner, owner_auth = _unverified_user(role)
    other_admin, _other_auth = _unverified_user("admin")
    marker = f"{role}-owner-list-{uuid.uuid4().hex}"
    case = _create_case(owner, owner_auth, marker)
    content = f"owner-private-list-{marker}"
    reply_content = f"owner-private-reply-{marker}"
    note = owner.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={
            "quote": marker,
            "section": "正文",
            "content": content,
            "source": "manual",
            "revision": case["revision"],
            "from": 1,
            "to": 1 + len(marker),
        },
    )
    assert note.status_code == 201, note.text
    reply = owner.post(
        f"/api/cases/{case['id']}/annotations/{note.json()['id']}/replies",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"content": reply_content},
    )
    assert reply.status_code == 200, reply.text

    own_draft_notes = owner.get(f"/api/cases/{case['id']}/annotations")
    assert own_draft_notes.status_code == 200, own_draft_notes.text
    assert content in str(own_draft_notes.json())
    assert other_admin.get(f"/api/cases/{case['id']}/annotations").status_code == 404

    current = owner.get(f"/api/cases/{case['id']}").json()
    manual_version = owner.post(
        f"/api/cases/{case['id']}/versions",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"title": f"{marker} v1", "revision": current["revision"]},
    )
    assert manual_version.status_code == 200, manual_version.text
    version_id = manual_version.json()["id"]

    current = owner.get(f"/api/cases/{case['id']}").json()
    later_note = owner.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={
            "quote": marker,
            "section": "正文",
            "content": f"live-only-after-version-{marker}",
            "source": "manual",
            "revision": current["revision"],
            "from": 1,
            "to": 1 + len(marker),
        },
    )
    assert later_note.status_code == 201, later_note.text

    own_version_notes = owner.get(
        f"/api/cases/{case['id']}/annotations",
        params={"versionId": version_id},
    )
    assert own_version_notes.status_code == 200, own_version_notes.text
    assert [row["content"] for row in own_version_notes.json()] == [content]
    assert [row["content"] for row in own_version_notes.json()[0]["replies"]] == [
        reply_content
    ]
    assert f"live-only-after-version-{marker}" not in str(own_version_notes.json())
    assert (
        other_admin.get(
            f"/api/cases/{case['id']}/annotations",
            params={"versionId": version_id},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("role", ["user", "admin"])
def test_case_owner_reads_live_sources_after_reopening_published_case(role: str) -> None:
    owner, owner_auth = _unverified_user(role)
    other_admin, _other_auth = _unverified_user("admin")
    marker = f"{role}-owner-reopen-source-{uuid.uuid4().hex}"
    case = _create_case(owner, owner_auth, marker)
    publication = _published(owner, owner_auth, case["id"])
    version_id = publication["version"]["id"]
    current = owner.get(f"/api/cases/{case['id']}").json()
    reopened = _transition(owner, owner_auth, case["id"], "reopen", current["revision"])
    assert reopened["case"]["workflowStatus"] == "draft"
    assert reopened["case"]["publishedVersionId"] == version_id

    mongo_client, database = _database()
    settings = Settings.from_environment()
    store = minio_blob_store(settings)
    attachment_text = f"private-attachment-{marker}"
    attachment = _upload_private(owner, owner_auth, case["id"], attachment_text)
    material_text = f"private-material-{marker}"
    material_id = f"m-{uuid.uuid4().hex}"
    blob_id = f"blob-{uuid.uuid4().hex}"
    store.put(blob_id, io.BytesIO(material_text.encode()), len(material_text), "text/plain")
    database.materials.insert_one(
        {
            "id": material_id,
            "title": material_text,
            "summary": "",
            "source": "合成私人来源",
            "sourceUrl": "",
            "filename": "private-material.txt",
            "mediaType": "text/plain",
            "size": len(material_text),
            "accessLevel": "private",
            "status": "active",
            "createdBy": owner_auth["user"]["id"],
            "blobId": blob_id,
            "publicReferenceCount": 0,
        }
    )
    try:
        current = owner.get(f"/api/cases/{case['id']}").json()
        mounted_material = owner.post(
            f"/api/cases/{case['id']}/materials",
            headers={"X-CSRF-Token": owner_auth["csrfToken"]},
            json={"materialId": material_id, "revision": current["revision"]},
        )
        assert mounted_material.status_code == 201, mounted_material.text

        source_case = _create_case(owner, owner_auth, f"public-source-{marker}")
        source_publication = _published(owner, owner_auth, source_case["id"])
        current = owner.get(f"/api/cases/{case['id']}").json()
        mounted_case_source = owner.post(
            f"/api/cases/{case['id']}/case-sources",
            headers={"X-CSRF-Token": owner_auth["csrfToken"]},
            json={
                "sourceCaseId": source_case["id"],
                "versionId": source_publication["version"]["id"],
                "revision": current["revision"],
            },
        )
        assert mounted_case_source.status_code == 201, mounted_case_source.text
        source_id = mounted_case_source.json()["id"]
        expected_ids = {attachment["id"], material_id, source_id}

        owner_attachments = owner.get(f"/api/cases/{case['id']}/attachments")
        owner_materials = owner.get(f"/api/cases/{case['id']}/materials")
        owner_case_sources = owner.get(f"/api/cases/{case['id']}/case-sources")
        assert owner_attachments.status_code == 200, owner_attachments.text
        assert owner_materials.status_code == 200, owner_materials.text
        assert owner_case_sources.status_code == 200, owner_case_sources.text
        assert {row["id"] for row in owner_attachments.json()} == {attachment["id"]}
        assert {row["id"] for row in owner_materials.json()} == {material_id}
        assert {row["id"] for row in owner_case_sources.json()} == {source_id}
        assert owner_materials.json()[0]["contentAvailable"] is True

        old_attachments = owner.get(
            f"/api/cases/{case['id']}/attachments", params={"versionId": version_id}
        )
        old_materials = owner.get(
            f"/api/cases/{case['id']}/materials", params={"versionId": version_id}
        )
        old_case_sources = owner.get(
            f"/api/cases/{case['id']}/case-sources", params={"versionId": version_id}
        )
        assert old_attachments.status_code == old_materials.status_code == 200
        assert old_case_sources.status_code == 200
        assert old_attachments.json() == old_materials.json() == old_case_sources.json() == []

        attachment_download = owner.get(
            f"/api/cases/{case['id']}/attachments/{attachment['id']}/content"
        )
        material_download = owner.get(f"/api/materials/{material_id}/content")
        assert attachment_download.status_code == 200
        assert attachment_download.content == attachment_text.encode()
        assert material_download.status_code == 200
        assert material_download.content == material_text.encode()

        owner_sources = owner.get(f"/api/cases/{case['id']}/sources")
        assert owner_sources.status_code == 200, owner_sources.text
        assert {row["id"] for row in owner_sources.json()["entries"]} == expected_ids
        export = owner.get(f"/api/cases/{case['id']}/export.docx")
        assert export.status_code == 200, export.text
        document = Document(io.BytesIO(export.content))
        exported_text = "\n".join(row.text for row in document.paragraphs)
        assert attachment["name"] in exported_text
        assert material_text in exported_text
        assert source_case["title"] in exported_text

        history = owner.get(f"/api/cases/{case['id']}/history")
        assert history.status_code == 200, history.text
        frozen = next(row for row in history.json()["versions"] if row["id"] == version_id)
        assert expected_ids.isdisjoint(
            {row["id"] for row in frozen["attachments"] + frozen["materials"] + frozen["caseSources"]}
        )

        other_attachments = other_admin.get(f"/api/cases/{case['id']}/attachments")
        other_materials = other_admin.get(f"/api/cases/{case['id']}/materials")
        other_case_sources = other_admin.get(f"/api/cases/{case['id']}/case-sources")
        assert other_attachments.status_code == other_materials.status_code == 200
        assert other_case_sources.status_code == 200
        assert other_attachments.json() == other_materials.json() == other_case_sources.json() == []
        other_sources = other_admin.get(f"/api/cases/{case['id']}/sources")
        assert other_sources.status_code == 200, other_sources.text
        assert expected_ids.isdisjoint(
            {row["id"] for row in other_sources.json()["entries"]}
        )

        owner_record = database.users.find_one({"id": owner_auth["user"]["id"]})
        other_record = database.users.find_one({"id": _other_auth["user"]["id"]})
        catalog = MeilisearchCatalog(
            create_reader(
                os.environ["MEILI_CONTRACT_URL"],
                os.environ["MEILI_CONTRACT_KEY_FILE"],
            )
        )
        state = MongoCatalogState(database)
        with tempfile.NamedTemporaryFile(delete=False) as cursor_key:
            cursor_key.write(uuid.uuid4().bytes)
            secret_path = cursor_key.name
        try:
            owner_deps = _tool_deps(
                database, owner_record, case["id"], None, catalog, state, store, secret_path
            )
            owner_context = SimpleNamespace(deps=owner_deps)
            owner_attachment_read = asyncio.run(
                read_source(owner_context, "attachment", attachment["id"])
            )
            owner_material_read = asyncio.run(
                read_source(owner_context, "material", material_id)
            )
            owner_case_read = asyncio.run(read_source(owner_context, "case", source_id))
            assert owner_attachment_read["status"] == "ok"
            assert owner_attachment_read["content"] == attachment_text
            assert owner_material_read["status"] == "ok"
            assert owner_material_read["content"] == material_text
            assert owner_case_read["status"] == "ok"
            assert marker in owner_case_read["content"]
            current_refs = {ref.id: ref for ref in owner_deps.sources}
            current_gate = SourceGate(database, owner_record, case["id"])
            assert all(current_gate.readable(current_refs[key]) for key in expected_ids)

            fixed_gate = SourceGate(database, owner_record, case["id"], version_id)
            assert not fixed_gate.readable(current_refs[attachment["id"]])
            assert fixed_gate.readable(current_refs[material_id])
            assert not fixed_gate.readable(current_refs[source_id])
            fixed_deps = _tool_deps(
                database, owner_record, case["id"], version_id, catalog, state, store,
                secret_path,
            )
            fixed_context = SimpleNamespace(deps=fixed_deps)
            assert asyncio.run(read_source(fixed_context, "material", material_id))["status"] == "unavailable"
            assert asyncio.run(read_source(fixed_context, "case", source_id))["status"] == "unavailable"

            other_deps = _tool_deps(
                database, other_record, case["id"], None, catalog, state, store, secret_path
            )
            other_context = SimpleNamespace(deps=other_deps)
            other_read = asyncio.run(
                read_source(other_context, "attachment", attachment["id"])
            )
            assert other_read["status"] == "unavailable"
            assert "content" not in other_read
            other_gate = SourceGate(database, other_record, case["id"])
            assert all(not other_gate.readable(current_refs[key]) for key in expected_ids)
        finally:
            os.unlink(secret_path)
    finally:
        mongo_client.close()


def test_global_search_sources_remain_readable_in_agent_history() -> None:
    owner, owner_auth = _unverified_user()
    reader, reader_auth = _unverified_user()
    marker = f"global-source-history-{uuid.uuid4().hex}"
    parent_case = _create_case(owner, owner_auth, f"parent-{marker}")
    source_case = _create_case(owner, owner_auth, f"public-case-{marker}")
    publication = _published(owner, owner_auth, source_case["id"])

    mongo_client, database = _database()
    settings = Settings.from_environment()
    store = minio_blob_store(settings)
    material_id = f"m-{uuid.uuid4().hex}"
    blob_id = f"blob-{uuid.uuid4().hex}"
    material_text = f"public-material-content-{marker}"
    store.put(blob_id, io.BytesIO(material_text.encode()), len(material_text), "text/plain")
    database.materials.insert_one(
        {
            "id": material_id,
            "title": f"public-material-{marker}",
            "summary": "",
            "source": "合成公开来源",
            "sourceUrl": "",
            "filename": "public-material.txt",
            "mediaType": "text/plain",
            "size": len(material_text),
            "accessLevel": "public",
            "status": "active",
            "createdBy": owner_auth["user"]["id"],
            "blobId": blob_id,
            "publicReferenceCount": 0,
        }
    )
    SearchOutbox(database).record([f"material:{material_id}"], session=None)
    try:
        reader_record = database.users.find_one({"id": reader_auth["user"]["id"]})
        catalog = MeilisearchCatalog(
            create_reader(
                os.environ["MEILI_CONTRACT_URL"],
                os.environ["MEILI_CONTRACT_KEY_FILE"],
            )
        )
        state = MongoCatalogState(database)
        with tempfile.NamedTemporaryFile(delete=False) as cursor_key:
            cursor_key.write(uuid.uuid4().bytes)
            secret_path = cursor_key.name
        try:
            _wait_for_search_item(
                reader, f"public-case-{marker}", "case", source_case["id"]
            )
            _wait_for_search_item(
                reader, f"public-material-{marker}", "material", material_id
            )
            deps = _tool_deps(
                database, reader_record, parent_case["id"], None, catalog, state,
                store, secret_path,
            )
            context = SimpleNamespace(deps=deps)
            case_search = _search_corpus_when_ready(
                context,
                CorpusSearchParams(
                    query=f"public-case-{marker}", kind="case",
                ),
            )
            material_search = _search_corpus_when_ready(
                context,
                CorpusSearchParams(
                    query=f"public-material-{marker}", kind="material",
                ),
            )
            case_ref = next(
                ref for ref in case_search["sources"]
                if ref["id"] == source_case["id"]
            )
            material_ref = next(
                ref for ref in material_search["sources"]
                if ref["id"] == material_id
            )
            assert case_ref["versionId"] == publication["version"]["id"]
            assert case_ref["sourceCaseId"] == source_case["id"]
            assert material_ref["kind"] == "material"

            case_read = asyncio.run(read_source(context, "case", source_case["id"]))
            material_read = asyncio.run(read_source(context, "material", material_id))
            assert case_read["status"] == material_read["status"] == "ok"
            assert marker in case_read["content"]
            assert material_read["content"] == material_text
            for result in (case_read, material_read):
                generated = result["usedSourceRef"]
                assert generated.get("location")
                gate = SourceGate(database, reader_record, parent_case["id"])
                assert gate.readable(generated)
                history = visible_parts(
                    gate,
                    [
                        {"type": "text", "text": result["content"]},
                        {"type": "tool-read_source", "output": result},
                    ],
                )
                assert history[0]["text"] == result["content"]
                assert history[1]["output"]["content"] == result["content"]
        finally:
            os.unlink(secret_path)
    finally:
        mongo_client.close()


@pytest.mark.parametrize("role", ["user", "admin"])
def test_approved_review_record_stays_version_scoped_after_reopen_and_resubmit(
    role: str,
) -> None:
    owner, owner_auth = _unverified_user(role)
    reviewer, reviewer_auth = _login("admin", "admin123")
    marker = f"{role}-approved-history-{uuid.uuid4().hex}"
    case = _create_case(owner, owner_auth, marker)
    submitted = _transition(owner, owner_auth, case["id"], "submit", case["revision"])
    old_version_id = submitted["version"]["id"]
    review = reviewer.get(f"/api/cases/{case['id']}/review")
    assert review.status_code == 200, review.text
    started = _transition(
        reviewer, reviewer_auth, case["id"], "start", review.json()["revision"]
    )
    note = reviewer.post(
        f"/api/cases/{case['id']}/annotations?versionId={old_version_id}",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={
            "quote": marker,
            "section": "正文",
            "content": f"approved-v1-guidance-{marker}",
            "source": "admin",
            "revision": started["case"]["revision"],
            "from": 1,
            "to": 1 + len(marker),
        },
    )
    assert note.status_code == 201, note.text
    review = reviewer.get(
        f"/api/cases/{case['id']}/review", params={"versionId": old_version_id}
    )
    approved = _transition(
        reviewer,
        reviewer_auth,
        case["id"],
        "approve",
        review.json()["revision"],
        submittedVersionId=old_version_id,
    )
    assert approved["case"]["publishedVersionId"] == old_version_id
    approved_cards = reviewer.get("/api/cases", params={"scope": "admin"}).json()
    published_card = next(row for row in approved_cards if row["id"] == case["id"])
    assert published_card["reviewVersionId"] == old_version_id
    assert published_card["reviewRecordStatus"] == "published"

    current = owner.get(f"/api/cases/{case['id']}").json()
    reopened = _transition(owner, owner_auth, case["id"], "reopen", current["revision"])
    changed = owner.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"title": f"{marker}-private-draft", "revision": reopened["case"]["revision"]},
    )
    assert changed.status_code == 200, changed.text
    reviewer_case = reviewer.get(f"/api/cases/{case['id']}")
    assert reviewer_case.status_code == 200, reviewer_case.text
    assert reviewer_case.json()["title"] == marker
    assert f"{marker}-private-draft" not in reviewer_case.text
    assert reviewer.get(f"/api/cases/{case['id']}/public").json()["title"] == marker
    reopened_cards = reviewer.get("/api/cases", params={"scope": "admin"}).json()
    assert case["id"] not in {row["id"] for row in reopened_cards}
    old_review_while_draft = reviewer.get(
        f"/api/cases/{case['id']}/review", params={"versionId": old_version_id}
    )
    assert old_review_while_draft.status_code == 200, old_review_while_draft.text
    assert old_review_while_draft.json()["reviewRecordStatus"] == "published"
    assert old_review_while_draft.json()["isCurrentReviewVersion"] is False
    assert old_review_while_draft.json()["availableActions"] == []
    assert f"{marker}-private-draft" not in old_review_while_draft.text
    if role == "admin":
        owner_review = owner.get(
            f"/api/cases/{case['id']}/review", params={"versionId": old_version_id}
        )
        assert owner_review.status_code == 200, owner_review.text
        assert owner_review.json()["title"] == marker

    resubmitted = _transition(
        owner,
        owner_auth,
        case["id"],
        "submit",
        changed.json()["revision"],
    )
    new_version_id = resubmitted["version"]["id"]
    assert new_version_id != old_version_id
    pending_cards = reviewer.get("/api/cases", params={"scope": "admin"}).json()
    current_cards = [row for row in pending_cards if row["id"] == case["id"]]
    assert len(current_cards) == 1
    assert current_cards[0]["reviewVersionId"] == new_version_id
    assert current_cards[0]["reviewRecordStatus"] == "pending"

    old_review = reviewer.get(
        f"/api/cases/{case['id']}/review", params={"versionId": old_version_id}
    )
    assert old_review.status_code == 200, old_review.text
    assert old_review.json()["reviewRecordStatus"] == "published"
    assert old_review.json()["reviewVersionId"] == old_version_id
    assert old_review.json()["isCurrentReviewVersion"] is False
    assert old_review.json()["availableActions"] == []
    assert old_review.json()["title"] == marker
    assert f"{marker}-private-draft" not in old_review.text
    old_annotations = reviewer.get(
        f"/api/cases/{case['id']}/annotations", params={"versionId": old_version_id}
    )
    assert old_annotations.status_code == 200, old_annotations.text
    assert [row["content"] for row in old_annotations.json()] == [
        f"approved-v1-guidance-{marker}"
    ]

    current_review = reviewer.get(f"/api/cases/{case['id']}/review")
    assert current_review.status_code == 200, current_review.text
    assert current_review.json()["submittedVersionId"] == new_version_id
    assert current_review.json()["reviewVersionId"] == new_version_id
    assert current_review.json()["reviewRecordStatus"] == "pending"
    assert current_review.json()["title"] == f"{marker}-private-draft"
    assert reviewer.get(
        f"/api/cases/{case['id']}/review/export.docx",
        params={"versionId": old_version_id},
    ).status_code == 200

    rejected_writes = [
        reviewer.post(
            f"/api/cases/{case['id']}/annotations?versionId={old_version_id}",
            headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
            json={
                "quote": marker,
                "section": "正文",
                "content": f"late-guidance-{marker}",
                "source": "admin",
                "revision": old_review.json()["revision"],
                "from": 1,
                "to": 1 + len(marker),
            },
        ),
        reviewer.post(
            f"/api/cases/{case['id']}/annotations/{note.json()['id']}/replies",
            headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
            json={"content": f"late-reply-{marker}"},
        ),
        reviewer.patch(
            f"/api/cases/{case['id']}/annotations/{note.json()['id']}/status",
            headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
            json={"status": "resolved"},
        ),
        reviewer.patch(
            f"/api/cases/{case['id']}/annotations/{note.json()['id']}",
            headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
            json={"content": f"edited-after-approval-{marker}"},
        ),
        reviewer.delete(
            f"/api/cases/{case['id']}/annotations/{note.json()['id']}",
            headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        ),
    ]
    assert [response.status_code for response in rejected_writes] == [409] * 5
    replay = reviewer.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={
            "command": "approve",
            "revision": current_review.json()["revision"],
            "submittedVersionId": old_version_id,
        },
    )
    assert replay.status_code == 409
    new_annotations = reviewer.get(
        f"/api/cases/{case['id']}/annotations", params={"versionId": new_version_id}
    )
    assert new_annotations.status_code == 200
    assert new_annotations.json() == []


def test_admin_case_owner_can_reply_and_resolve_returned_review_annotations() -> None:
    owner, owner_auth = _unverified_user("admin")
    reviewer, reviewer_auth = _unverified_user("admin")
    marker = f"admin-owner-returned-{uuid.uuid4().hex}"
    case = _create_case(owner, owner_auth, marker)
    submitted = _transition(owner, owner_auth, case["id"], "submit", case["revision"])
    version_id = submitted["version"]["id"]
    review = reviewer.get(f"/api/cases/{case['id']}/review").json()
    started = _transition(
        reviewer, reviewer_auth, case["id"], "start", review["revision"]
    )
    note = reviewer.post(
        f"/api/cases/{case['id']}/annotations?versionId={version_id}",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={
            "quote": marker,
            "section": "正文",
            "content": f"review-guidance-{marker}",
            "source": "admin",
            "revision": started["case"]["revision"],
            "from": 1,
            "to": 1 + len(marker),
        },
    )
    assert note.status_code == 201, note.text
    annotation_id = note.json()["id"]
    _transition(
        reviewer,
        reviewer_auth,
        case["id"],
        "reject",
        started["case"]["revision"],
        submittedVersionId=version_id,
        reasonTypes=["内容需要补充或修改"],
    )

    reviewer_reply = reviewer.post(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/replies",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={"content": f"other-admin-reply-{marker}"},
    )
    assert reviewer_reply.status_code == 409
    reviewer_resolve = reviewer.patch(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/status",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={"status": "resolved"},
    )
    assert reviewer_resolve.status_code == 409
    reviewer_edit = reviewer.patch(
        f"/api/cases/{case['id']}/annotations/{annotation_id}",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={"content": f"other-admin-edit-{marker}"},
    )
    assert reviewer_edit.status_code == 409

    owner_reply = owner.post(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/replies",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"content": f"owner-returned-reply-{marker}"},
    )
    assert owner_reply.status_code == 200, owner_reply.text
    owner_resolve = owner.patch(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/status",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"status": "resolved"},
    )
    assert owner_resolve.status_code == 200, owner_resolve.text
    assert f"owner-returned-reply-{marker}" in str(owner_resolve.json()["replies"])

    owner_reopen = owner.patch(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/status",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"status": "pending"},
    )
    assert owner_reopen.status_code == 409
    owner_edit = owner.patch(
        f"/api/cases/{case['id']}/annotations/{annotation_id}",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"content": f"owner-edit-review-opinion-{marker}"},
    )
    assert owner_edit.status_code == 409
    owner_delete = owner.delete(
        f"/api/cases/{case['id']}/annotations/{annotation_id}",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
    )
    assert owner_delete.status_code == 409


def test_regular_case_owner_can_reply_and_resolve_returned_review_annotations() -> None:
    owner, owner_auth = _unverified_user()
    reviewer, reviewer_auth = _unverified_user("admin")
    marker = f"user-owner-returned-{uuid.uuid4().hex}"
    case = _create_case(owner, owner_auth, marker)
    submitted = _transition(owner, owner_auth, case["id"], "submit", case["revision"])
    version_id = submitted["version"]["id"]
    review = reviewer.get(f"/api/cases/{case['id']}/review").json()
    started = _transition(
        reviewer, reviewer_auth, case["id"], "start", review["revision"]
    )
    note = reviewer.post(
        f"/api/cases/{case['id']}/annotations?versionId={version_id}",
        headers={"X-CSRF-Token": reviewer_auth["csrfToken"]},
        json={
            "quote": marker,
            "section": "正文",
            "content": f"review-guidance-{marker}",
            "source": "admin",
            "revision": started["case"]["revision"],
            "from": 1,
            "to": 1 + len(marker),
        },
    )
    assert note.status_code == 201, note.text
    _transition(
        reviewer,
        reviewer_auth,
        case["id"],
        "reject",
        started["case"]["revision"],
        submittedVersionId=version_id,
        reasonTypes=["内容需要补充或修改"],
    )

    annotation_id = note.json()["id"]
    reply = owner.post(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/replies",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"content": f"user-returned-reply-{marker}"},
    )
    assert reply.status_code == 200, reply.text
    resolved = owner.patch(
        f"/api/cases/{case['id']}/annotations/{annotation_id}/status",
        headers={"X-CSRF-Token": owner_auth["csrfToken"]},
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text
    assert f"user-returned-reply-{marker}" in str(resolved.json()["replies"])


def test_real_meilisearch_and_production_agent_source_tools_enforce_acl() -> None:
    author, author_auth = _unverified_user()
    admin, admin_auth = _unverified_user("admin")
    other, other_auth = _unverified_user()
    marker = f"private-search-{uuid.uuid4().hex}"
    material_text = f"private-material-{uuid.uuid4().hex}"
    mongo_client, database = _database()
    settings = Settings.from_environment()
    store = minio_blob_store(settings)
    material_id = f"m-{uuid.uuid4().hex}"
    blob_id = f"blob-{uuid.uuid4().hex}"
    store.put(blob_id, io.BytesIO(material_text.encode()), len(material_text), "text/plain")
    database.materials.insert_one(
        {
            "id": material_id,
            "title": material_text,
            "summary": "",
            "source": "合成私人来源",
            "sourceUrl": "",
            "filename": "private-source.txt",
            "mediaType": "text/plain",
            "size": len(material_text),
            "accessLevel": "private",
            "status": "active",
            "createdBy": author_auth["user"]["id"],
            "blobId": blob_id,
            "publicReferenceCount": 0,
        }
    )
    case = _create_case(author, author_auth, f"case-{uuid.uuid4().hex}")
    attachment = _upload_private(author, author_auth, case["id"], marker)
    campus_text = f"campus-{uuid.uuid4().hex}"
    campus_attachment = _upload_private(
        author, author_auth, case["id"], campus_text, "campus"
    )
    publication = _published(author, author_auth, case["id"], material_id)
    version_id = publication["version"]["id"]
    frozen = database.case_versions.find_one({"id": version_id, "caseId": case["id"]})
    assert any(row["id"] == attachment["id"] for row in frozen["attachments"])
    approved_material = publication["approved"]["version"]["materials"][0]
    assert approved_material["contentAvailable"] is False
    assert "summary" not in approved_material
    admin_history = admin.get(f"/api/cases/{case['id']}/history")
    assert admin_history.status_code == 200
    historical_material = admin_history.json()["versions"][0]["materials"][0]
    assert historical_material["contentAvailable"] is False
    assert "summary" not in historical_material

    material_access = author.get(f"/api/materials/{material_id}/content")
    assert material_access.status_code == 200 and material_access.content == material_text.encode()
    assert admin.get(f"/api/materials/{material_id}/content").status_code == 404
    with httpx.Client(base_url=BASE_URL) as public_client:
        public_materials = public_client.get(
            f"/api/cases/{case['id']}/materials", params={"versionId": version_id}
        )
    assert public_materials.status_code == 200
    assert public_materials.json()[0]["contentAvailable"] is False
    assert admin.get(
        f"/api/cases/{case['id']}/materials", params={"versionId": version_id}
    ).json()[0]["contentAvailable"] is False
    assert not other_auth["user"].get("campusVerified")
    other_sources = other.get(
        f"/api/cases/{case['id']}/sources", params={"versionId": version_id}
    )
    assert other_sources.status_code == 200
    other_campus = next(
        row for row in other_sources.json()["entries"]
        if row["id"] == campus_attachment["id"]
    )
    assert other_campus["contentAvailable"] is False
    assert other.get(
        f"/api/cases/{case['id']}/attachments/{campus_attachment['id']}/content",
        params={"versionId": version_id},
    ).status_code == 403
    admin_sources = admin.get(
        f"/api/cases/{case['id']}/sources", params={"versionId": version_id}
    )
    admin_campus = next(
        row for row in admin_sources.json()["entries"]
        if row["id"] == campus_attachment["id"]
    )
    assert admin_campus["contentAvailable"] is False
    assert admin.get(
        f"/api/cases/{case['id']}/attachments/{campus_attachment['id']}/content",
        params={"versionId": version_id},
    ).status_code == 403
    owner_sources = author.get(
        f"/api/cases/{case['id']}/sources", params={"versionId": version_id}
    )
    owner_campus = next(
        row for row in owner_sources.json()["entries"]
        if row["id"] == campus_attachment["id"]
    )
    assert owner_campus["contentAvailable"] is True
    owner_download = author.get(
        f"/api/cases/{case['id']}/attachments/{campus_attachment['id']}/content",
        params={"versionId": version_id},
    )
    assert owner_download.status_code == 200
    assert owner_download.content == campus_text.encode()

    deadline = time.monotonic() + 45
    owner_items = []
    while time.monotonic() < deadline:
        response = author.get(
            "/api/search", params={"q": marker, "kind": "case", "pageSize": 20}
        )
        if response.status_code == 200:
            owner_items = response.json()["items"]
            if any(item["id"] == case["id"] for item in owner_items):
                break
        time.sleep(1)
    assert any(item["id"] == case["id"] for item in owner_items)
    assert admin.get(
        "/api/search", params={"q": marker, "kind": "case", "pageSize": 20}
    ).json()["items"] == []
    other_search = other.get(
        "/api/search", params={"q": marker, "kind": "case", "pageSize": 20}
    )
    assert other_search.status_code in {200, 403}
    if other_search.status_code == 200:
        assert other_search.json()["items"] == []
    anonymous_search = httpx.get(
        f"{BASE_URL}/api/search", params={"q": marker, "kind": "case", "pageSize": 20}
    )
    assert anonymous_search.status_code == 200
    assert anonymous_search.json()["items"] == []
    campus_name = campus_attachment["name"]
    _wait_for_search_item(author, campus_name, "case", case["id"])
    for reader in (admin, other):
        denied_search = reader.get(
            "/api/search", params={"q": campus_name, "kind": "case", "pageSize": 20}
        )
        assert denied_search.status_code == 200
        assert denied_search.json()["items"] == []
    assert httpx.get(
        f"{BASE_URL}/api/search",
        params={"q": campus_name, "kind": "case", "pageSize": 20},
    ).json()["items"] == []

    try:
        owner_record = database.users.find_one({"id": author_auth["user"]["id"]})
        admin_record = database.users.find_one({"id": admin_auth["user"]["id"]})
        other_record = database.users.find_one({"id": other_auth["user"]["id"]})
        catalog = MeilisearchCatalog(
            create_reader(
                os.environ["MEILI_CONTRACT_URL"],
                os.environ["MEILI_CONTRACT_KEY_FILE"],
            )
        )
        state = MongoCatalogState(database)
        settings = Settings.from_environment()
        store = minio_blob_store(settings)
        with tempfile.NamedTemporaryFile(delete=False) as cursor_key:
            cursor_key.write(uuid.uuid4().bytes)
            secret_path = cursor_key.name
        owner_deps = _tool_deps(
            database, owner_record, case["id"], version_id, catalog, state, store,
            secret_path,
        )
        admin_deps = _tool_deps(
            database, admin_record, case["id"], version_id, catalog, state, store,
            secret_path,
        )
        other_deps = _tool_deps(
            database, other_record, case["id"], version_id, catalog, state, store,
            secret_path,
        )
        owner_rows = area_rows(database, case["id"], version_id, owner_record)
        assert any(row["id"] == attachment["id"] for row in owner_rows["attachment"])
        assert any(
            ref.kind == "attachment" and ref.id == attachment["id"]
            for ref in owner_deps.sources
        ), [ref.model_dump(by_alias=True) for ref in owner_deps.sources]
        assert any(
            ref.kind == "attachment" and ref.id == campus_attachment["id"]
            for ref in owner_deps.sources
        )
        owner_context = SimpleNamespace(deps=owner_deps)
        admin_context = SimpleNamespace(deps=admin_deps)
        other_context = SimpleNamespace(deps=other_deps)
        owner_search = _search_corpus_when_ready(
            owner_context, CorpusSearchParams(query=marker, kind="case")
        )
        admin_search = _search_corpus_when_ready(
            admin_context, CorpusSearchParams(query=marker, kind="case")
        )
        other_corpus_search = _search_corpus_when_ready(
            other_context, CorpusSearchParams(query=marker, kind="case")
        )
        assert [row["id"] for row in owner_search["sources"]] == [case["id"]]
        assert admin_search["sources"] == []
        assert other_corpus_search["sources"] == []

        owner_read = asyncio.run(read_source(owner_context, "attachment", attachment["id"]))
        owner_campus_read = asyncio.run(
            read_source(owner_context, "attachment", campus_attachment["id"])
        )
        admin_read = asyncio.run(read_source(admin_context, "attachment", attachment["id"]))
        other_read = asyncio.run(read_source(other_context, "attachment", attachment["id"]))
        assert owner_read["status"] == "ok" and owner_read["content"] == marker, owner_read
        assert owner_campus_read["status"] == "ok"
        assert owner_campus_read["content"] == campus_text
        assert admin_read["status"] == "no_access"
        assert other_read["status"] == "no_access"
        admin_campus_search = _search_corpus_when_ready(
            admin_context,
            CorpusSearchParams(query=campus_attachment["name"], kind="case"),
        )
        assert admin_campus_search["sources"] == []
        admin_campus_read = asyncio.run(
            read_source(admin_context, "attachment", campus_attachment["id"])
        )
        assert admin_campus_read["status"] == "no_access"
        owner_material_search = _search_corpus_when_ready(
            owner_context,
            CorpusSearchParams(query=material_text, kind="material"),
        )
        admin_material_search = _search_corpus_when_ready(
            admin_context,
            CorpusSearchParams(query=material_text, kind="material"),
        )
        other_material_search = _search_corpus_when_ready(
            other_context,
            CorpusSearchParams(query=material_text, kind="material"),
        )
        _assert_referenced_private_material_http_acl(
            author, admin, other, material_text, material_id, database
        )
        assert [row["id"] for row in owner_material_search["sources"]] == [material_id]
        assert owner_material_search["total"] == 1
        assert owner_material_search["counts"]["material"] == 1
        assert admin_material_search["sources"] == []
        assert admin_material_search["total"] == 0
        assert admin_material_search["counts"]["material"] == 0
        assert other_material_search["sources"] == []
        assert other_material_search["total"] == 0
        assert other_material_search["counts"]["material"] == 0
        owner_material = asyncio.run(read_source(owner_context, "material", material_id))
        admin_material = asyncio.run(read_source(admin_context, "material", material_id))
        assert owner_material["status"] == "ok" and owner_material["content"] == material_text
        assert admin_material["status"] == "no_access"

        search_client = create_client(
            os.environ["MEILI_CONTRACT_URL"],
            os.environ["MEILI_CONTRACT_KEY_FILE"],
        )
        current_catalog = database.search_catalog_generation.find_one({"_id": "catalog"})
        previous_epoch = current_catalog["indexEpoch"]
        legacy_catalog_id = f"case-{case['id']}-public"
        legacy_document = {
            "catalogId": legacy_catalog_id,
            "id": case["id"],
            "kind": "case",
            "docClass": "case-public",
            "title": "legacy projection synthetic case",
            "summary": "",
            "publishedAt": "2026-10-07",
            "versionId": version_id,
            "versionNumber": publication["version"]["number"],
            "createdBy": author_auth["user"]["id"],
            "searchableText": marker,
        }
        active_index = search_client.index(current_catalog["indexUid"])
        wait_task(
            search_client,
            active_index.add_documents([legacy_document], primary_key="catalogId"),
        )
        database.search_catalog_generation.update_one(
            {"_id": "catalog"}, {"$set": {"projectionVersion": 1}}
        )

        outbox_key = f"material:{material_id}"
        SearchOutbox(database).record([outbox_key], session=None)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            pending = database.search_outbox.find_one({"_id": outbox_key})
            generation = database.search_catalog_generation.find_one({"_id": "catalog"})
            outbox_applied = pending is None or (
                pending.get("appliedSequence", 0) >= pending.get("sequence", 1)
            )
            if (
                outbox_applied
                and generation["indexEpoch"] != previous_epoch
                and generation.get("projectionVersion") == 1
            ):
                break
            time.sleep(0.2)
        else:
            raise AssertionError("正常 outbox 更新未完成")
        assert database.search_catalog_generation.find_one({"_id": "catalog"})[
            "indexEpoch"
        ] == index_epoch(search_client, current_catalog["indexUid"])
        legacy_hits = active_index.search(
            marker,
            {"filter": 'kind = "case" AND docClass = "case-public"'},
        )["hits"]
        assert any(row.get("catalogId") == legacy_catalog_id for row in legacy_hits)

        stale_http = admin.get(
            "/api/search", params={"q": marker, "kind": "case", "pageSize": 20}
        )
        assert stale_http.status_code == 503
        with pytest.raises(RuntimeError, match="检索服务暂不可用"):
            asyncio.run(
                search_corpus(
                    admin_context, CorpusSearchParams(query=marker, kind="case")
                )
            )

        index_prefix = current_catalog["indexUid"].split("-generation-", 1)[0]
        CatalogRebuilder(database, search_client, index_prefix).rebuild()
        rebuilt_generation = database.search_catalog_generation.find_one({"_id": "catalog"})
        assert rebuilt_generation["projectionVersion"] == 2
        clean_http = admin.get(
            "/api/search", params={"q": marker, "kind": "case", "pageSize": 20}
        )
        assert clean_http.status_code == 200, clean_http.text
        assert clean_http.json()["items"] == []
        clean_tool = _search_corpus_when_ready(
            admin_context, CorpusSearchParams(query=marker, kind="case")
        )
        assert clean_tool["sources"] == []

        stale_result_marker = f"forged-stale-private-search-item-{uuid.uuid4().hex}"
        provider_config = admin.put(
            "/api/ai/settings",
            headers={"X-CSRF-Token": admin_auth["csrfToken"]},
            json={
                "mode": "custom",
                "baseUrl": "http://ai-provider:8080/v1",
                "apiKey": "e2e-api-key",
                "model": "e2e-model-a",
            },
        )
        assert provider_config.status_code == 200, provider_config.text
        stale = admin.post(
            "/api/search/summary",
            headers={"X-CSRF-Token": admin_auth["csrfToken"]},
            json={
                "id": "stale-summary",
                "trigger": "submit-message",
                "messages": [
                    {
                        "id": "stale-message",
                        "role": "user",
                        "parts": [{"type": "text", "text": campus_name}],
                    }
                ],
                "query": campus_name,
                "search": {"q": campus_name, "kind": "case"},
                "items": [{
                    "id": "private-draft",
                    "kind": "case",
                    "title": stale_result_marker,
                    "score": 100,
                }],
            },
        )
        assert stale.status_code == 200, stale.text
        assert _streamed_text(stale) == "隔离模型回答：已依据当前可见资源完成分析。"
        assert "STALE_PRIVATE_SEARCH_RESULT_REACHED_PROVIDER" not in stale.text
    finally:
        if "secret_path" in locals():
            os.unlink(secret_path)
        mongo_client.close()
