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
from pymongo import MongoClient

from app.core.config import Settings
from app.modules.agent.case_area import area_rows, retained_sources
from app.modules.agent.deps import ToolDeps
from app.modules.agent.skills import read_source, search_corpus
from app.modules.agent.search import CorpusSearchParams
from app.modules.attachments.storage import minio_blob_store
from app.modules.search.client import create_reader
from app.modules.search.meilisearch import MeilisearchCatalog
from app.modules.search.state import MongoCatalogState

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
    return client, client["case_library_e2e"]


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
            f"/api/cases/{case_id}/agent/thread", params={"mode": "review"}
        )
        assert review_thread.status_code == 200
        thread = review_thread.json()
        assert thread["versionId"] == frozen_id
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

        started = _transition(
            admin, admin_auth, case_id, "start", submitted["case"]["revision"]
        )
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


def test_real_meilisearch_and_production_agent_source_tools_enforce_acl() -> None:
    author, author_auth = _login("user", "user123")
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
    campus_attachment = _upload_private(
        author, author_auth, case["id"], f"campus-{uuid.uuid4().hex}", "campus"
    )
    publication = _published(author, author_auth, case["id"], material_id)
    version_id = publication["version"]["id"]
    frozen = database.case_versions.find_one({"id": version_id, "caseId": case["id"]})
    assert any(row["id"] == attachment["id"] for row in frozen["attachments"])

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
    owner_campus_search = author.get(
        "/api/search", params={"q": campus_name, "kind": "case", "pageSize": 20}
    )
    assert owner_campus_search.status_code == 200
    assert any(item["id"] == case["id"] for item in owner_campus_search.json()["items"])
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
        cursor_key = tempfile.NamedTemporaryFile(delete=False)
        cursor_key.write(uuid.uuid4().bytes)
        cursor_key.close()
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
        owner_context = SimpleNamespace(deps=owner_deps)
        admin_context = SimpleNamespace(deps=admin_deps)
        other_context = SimpleNamespace(deps=other_deps)
        owner_search = asyncio.run(
            search_corpus(owner_context, CorpusSearchParams(query=marker, kind="case"))
        )
        admin_search = asyncio.run(
            search_corpus(admin_context, CorpusSearchParams(query=marker, kind="case"))
        )
        other_corpus_search = asyncio.run(
            search_corpus(other_context, CorpusSearchParams(query=marker, kind="case"))
        )
        assert [row["id"] for row in owner_search["sources"]] == [case["id"]]
        assert admin_search["sources"] == []
        assert other_corpus_search["sources"] == []

        owner_read = asyncio.run(read_source(owner_context, "attachment", attachment["id"]))
        admin_read = asyncio.run(read_source(admin_context, "attachment", attachment["id"]))
        other_read = asyncio.run(read_source(other_context, "attachment", attachment["id"]))
        assert owner_read["status"] == "ok" and owner_read["content"] == marker, owner_read
        assert admin_read["status"] == "no_access"
        assert other_read["status"] == "no_access"
        admin_campus_search = asyncio.run(
            search_corpus(
                admin_context,
                CorpusSearchParams(query=campus_attachment["name"], kind="case"),
            )
        )
        assert admin_campus_search["sources"] == []
        admin_campus_read = asyncio.run(
            read_source(admin_context, "attachment", campus_attachment["id"])
        )
        assert admin_campus_read["status"] == "no_access"
        owner_material_search = asyncio.run(
            search_corpus(
                owner_context,
                CorpusSearchParams(query=material_text, kind="material"),
            )
        )
        admin_material_search = asyncio.run(
            search_corpus(
                admin_context,
                CorpusSearchParams(query=material_text, kind="material"),
            )
        )
        assert [row["id"] for row in owner_material_search["sources"]] == [material_id]
        assert admin_material_search["sources"] == []
        owner_material = asyncio.run(read_source(owner_context, "material", material_id))
        admin_material = asyncio.run(read_source(admin_context, "material", material_id))
        assert owner_material["status"] == "ok" and owner_material["content"] == material_text
        assert admin_material["status"] == "no_access"

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
