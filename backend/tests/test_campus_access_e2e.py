from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from io import BytesIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
MONGODB_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def _opener():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def _request(opener, method: str, path: str, body=None, csrf: str = ""):
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = Request(f"{BASE_URL}{path}", payload, headers, method=method)
    try:
        with opener.open(request) as response:
            content = response.read()
            return response.status, json.loads(content) if content else None
    except HTTPError as error:
        content = error.read()
        if not content:
            return error.code, None
        try:
            return error.code, json.loads(content)
        except json.JSONDecodeError:
            return error.code, content.decode()


def _event_text(opener, path: str) -> tuple[int, str]:
    request = Request(f"{BASE_URL}{path}")
    try:
        with opener.open(request) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def _login(opener, username: str, password: str) -> dict:
    status, payload = _request(
        opener,
        "POST",
        "/api/auth/login",
        {"username": username, "password": password},
    )
    assert status == 200
    return payload


def _submit(opener, csrf: str, name: str, student_number: str):
    return _request(
        opener,
        "POST",
        "/api/auth/campus-access/applications",
        {"applicantName": name, "studentNumber": student_number},
        csrf,
    )


def _admin_action(admin, csrf: str, application_id: str, action: str, body: dict):
    return _request(
        admin,
        "POST",
        f"/api/admin/campus-access-applications/{application_id}/{action}",
        body,
        csrf,
    )


def _run_concurrently(first, second):
    start = Barrier(3)

    def request_after_barrier(request):
        start.wait(timeout=10)
        return request()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_result = executor.submit(request_after_barrier, first)
        second_result = executor.submit(request_after_barrier, second)
        start.wait(timeout=10)
        return first_result.result(timeout=30), second_result.result(timeout=30)


def test_real_http_and_mongodb_preserve_application_approval_revocation_history() -> None:
    username = f"issue360-http-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    student_numbers = [f"SYN-360-{uuid.uuid4().hex[:12]}" for _ in range(3)]
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = client.get_default_database()
    prior_operation_count = database.account_management_operations.count_documents({})

    try:
        anonymous = _opener()
        registered_status, registered = _request(
            anonymous,
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registered_status == 201
        assert registered["campusVerified"] is False
        assert registered["name"] == username

        applicant = _opener()
        applicant_session = _login(applicant, username, password)
        applicant_id = applicant_session["user"]["id"]
        assert applicant_session["user"]["name"] == username
        assert applicant_session["user"]["campusVerified"] is False
        initial_status, initial = _request(applicant, "GET", "/api/auth/campus-access")
        assert initial_status == 200
        assert initial["currentStatus"] == "not_applied"

        first_status, first = _submit(
            applicant, applicant_session["csrfToken"], "合成姓名甲", student_numbers[0]
        )
        assert first_status == 201
        assert first["identitySource"] == "self_reported"
        assert first["status"] == "pending"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False

        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        admin_id = admin_session["user"]["id"]
        queue_status, queue = _request(
            admin,
            "GET",
            f"/api/admin/campus-access-applications?q={username}&status=pending",
        )
        assert queue_status == 200
        assert [item["id"] for item in queue["items"]] == [first["id"]]
        rejected_status, rejected = _admin_action(
            admin,
            admin_session["csrfToken"],
            first["id"],
            "decision",
            {"decision": "rejected", "reason": "合成资料待补充"},
        )
        assert rejected_status == 200
        assert rejected["status"] == "rejected"
        assert rejected["history"][-1]["reason"] == "合成资料待补充"

        applicant_session = _login(applicant, username, password)
        status, rejected_status_view = _request(applicant, "GET", "/api/auth/campus-access")
        assert status == 200
        assert rejected_status_view["campusVerified"] is False
        assert rejected_status_view["applications"][0]["id"] == first["id"]

        second_status, second = _submit(
            applicant, applicant_session["csrfToken"], "合成姓名乙", student_numbers[1]
        )
        assert second_status == 201
        assert second["id"] != first["id"]
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False

        admin_session = _login(admin, "admin", "admin123")
        approved_status, approved = _admin_action(
            admin,
            admin_session["csrfToken"],
            second["id"],
            "decision",
            {"decision": "approved", "reason": "合成身份核验通过"},
        )
        assert approved_status == 200
        assert approved["status"] == "approved"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is True

        revoked_status, revoked = _admin_action(
            admin,
            admin_session["csrfToken"],
            second["id"],
            "revoke",
            {"reason": "合成资格复核后撤销"},
        )
        assert revoked_status == 200
        assert revoked["status"] == "revoked"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False
        assert database.users.find_one({"id": applicant_id})["campus_access_revoked_at"]

        applicant_session = _login(applicant, username, password)
        third_status, third = _submit(
            applicant, applicant_session["csrfToken"], "合成姓名丙", student_numbers[2]
        )
        assert third_status == 201
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["currentStatus"] == "pending"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1]["campusVerified"] is False
        assert database.users.find_one({"id": applicant_id})["campus_access_revoked_at"]

        admin_session = _login(admin, "admin", "admin123")
        approved_again_status, approved_again = _admin_action(
            admin,
            admin_session["csrfToken"],
            third["id"],
            "decision",
            {"decision": "approved", "reason": "合成再次人工核验通过"},
        )
        assert approved_again_status == 200
        assert approved_again["status"] == "approved"

        stale_status, stale_result = _admin_action(
            admin,
            admin_session["csrfToken"],
            third["id"],
            "decision",
            {"decision": "rejected", "reason": "合成过期重复决定"},
        )
        assert stale_status == 409
        assert stale_result["detail"] == "申请已处理，不能重复决定"

        final_status, final = _request(applicant, "GET", "/api/auth/campus-access")
        assert final_status == 200
        assert final["campusVerified"] is True
        assert final["currentStatus"] == "approved"
        assert final["applications"][0]["status"] == "approved"
        assert final["applications"][0]["history"][-1]["result"] == "rejected"
        assert final["applications"][0]["history"][-1]["reason"] == "合成过期重复决定"
        assert final["applications"][0]["history"][-1]["actorUsername"] == "admin"
        assert [item["id"] for item in final["applications"]] == [
            third["id"],
            second["id"],
            first["id"],
        ]
        assert final["applications"][1]["status"] == "revoked"
        assert final["applications"][1]["history"][-1]["reason"] == "合成资格复核后撤销"
        assert final["applications"][2]["status"] == "rejected"
        assert final["applications"][2]["history"][-1]["reason"] == "合成资料待补充"
        assert "campus_access_revoked_at" not in database.users.find_one({"id": applicant_id})
        assert database.users.find_one({"id": applicant_id})["name"] == username
        assert database.campus_access_applications.count_documents({"userId": applicant_id}) == 3
        assert database.account_management_operations.count_documents({}) == prior_operation_count + 8
        operations = list(
            database.account_management_operations.find(
                {"campusApplicationId": {"$in": [first["id"], second["id"], third["id"]]}}
            )
        )
        assert len(operations) == 8
        assert sum(operation["result"] == "success" for operation in operations) == 7
        assert sum(operation["result"] == "rejected" for operation in operations) == 1
        assert all(operation["targetId"] == applicant_id for operation in operations)
        assert all(
            operation["actorId"] == applicant_id
            if operation["action"] == "campus_access_application_submit"
            else operation["actorId"] == admin_id
            for operation in operations
        )
        assert {
            operation["reason"]
            for operation in operations
            if operation["action"] != "campus_access_application_submit"
        } == {
            "合成资料待补充",
            "合成身份核验通过",
            "合成资格复核后撤销",
            "合成再次人工核验通过",
            "合成过期重复决定",
        }
        failed_repeat = next(
            operation
            for operation in operations
            if operation["reason"] == "合成过期重复决定"
        )
        assert failed_repeat["actorId"] == admin_id
        assert failed_repeat["result"] == "rejected"
    finally:
        client.close()


@pytest.mark.parametrize(
    ("action", "decision", "actor_change"),
    [
        ("decision", "approved", "role"),
        ("decision", "approved", "status"),
        ("decision", "rejected", "role"),
        ("decision", "rejected", "status"),
        ("revoke", None, "role"),
        ("revoke", None, "status"),
    ],
)
def test_real_http_serializes_campus_action_with_admin_change(
    action: str, decision: str | None, actor_change: str
) -> None:
    applicant_username = f"issue360-race-applicant-{uuid.uuid4().hex}"
    applicant_password = f"Issue360-{uuid.uuid4().hex}!a"
    actor_username = f"issue360-race-admin-{uuid.uuid4().hex}"
    actor_password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()

    try:
        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        applicant_registration, applicant_user = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": applicant_username, "password": applicant_password},
        )
        assert applicant_registration == 201
        applicant = _opener()
        applicant_session = _login(applicant, applicant_username, applicant_password)
        submitted_status, application = _submit(
            applicant,
            applicant_session["csrfToken"],
            "合成并发申请人",
            student_number,
        )
        assert submitted_status == 201

        actor_registration_status, actor_user = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": actor_username, "password": actor_password},
        )
        assert actor_registration_status == 201
        promoted_status, _promoted = _request(
            admin,
            "POST",
            f"/api/admin/accounts/{actor_user['id']}/role",
            {"role": "admin", "reason": "合成并发管理员初始化"},
            admin_session["csrfToken"],
        )
        assert promoted_status == 200
        actor = _opener()
        actor_session = _login(actor, actor_username, actor_password)
        actor_access_status, actor_access = _request(actor, "GET", "/api/auth/campus-access")
        assert actor_access_status == 200
        assert actor_access["campusVerified"] is False

        if action == "revoke":
            approved_status, approved = _admin_action(
                admin,
                admin_session["csrfToken"],
                application["id"],
                "decision",
                {"decision": "approved", "reason": "合成并发撤销准备"},
            )
            assert approved_status == 200
            assert approved["status"] == "approved"

        campus_body = (
            {"reason": "合成并发资格撤销"}
            if action == "revoke"
            else {"decision": decision, "reason": "合成并发申请决定"}
        )
        expected_action = (
            "campus_access_revoke"
            if action == "revoke"
            else f"campus_access_{'approve' if decision == 'approved' else 'reject'}"
        )
        actor_reason = "合成并发操作者角色变化" if actor_change == "role" else "合成并发操作者停用"

        def perform_campus_action():
            return _admin_action(
                actor,
                actor_session["csrfToken"],
                application["id"],
                action,
                campus_body,
            )

        def change_actor():
            suffix, body = (
                ("role", {"role": "user", "reason": actor_reason})
                if actor_change == "role"
                else ("status", {"status": "disabled", "reason": actor_reason})
            )
            return _request(
                admin,
                "POST",
                f"/api/admin/accounts/{actor_user['id']}/{suffix}",
                body,
                admin_session["csrfToken"],
            )

        (campus_status, campus_result), (change_status, changed_actor) = (
            _run_concurrently(perform_campus_action, change_actor)
        )
        assert change_status == 200
        assert changed_actor["role"] == ("user" if actor_change == "role" else "admin")
        assert changed_actor["status"] == ("active" if actor_change == "role" else "disabled")
        assert campus_status in {200, 401, 403}

        stored_application = database.campus_access_applications.find_one(
            {"id": application["id"]}
        )
        resulting_status = (
            "revoked"
            if action == "revoke" and campus_status == 200
            else "approved"
            if action == "revoke"
            else decision
            if campus_status == 200
            else "pending"
        )
        assert stored_application["status"] == resulting_status
        assert database.users.find_one({"id": applicant_user["id"]})[
            "campus_verified"
        ] is (resulting_status == "approved")
        current_status, current_access = _request(
            applicant, "GET", "/api/auth/campus-access"
        )
        assert current_status == 200
        assert current_access["campusVerified"] is (resulting_status == "approved")

        campus_operations = list(
            database.account_management_operations.find(
                {
                    "campusApplicationId": application["id"],
                    "action": expected_action,
                }
            )
        )
        if campus_status == 200:
            assert any(
                operation["actorId"] == actor_user["id"]
                and operation["result"] == "success"
                for operation in campus_operations
            )
        else:
            assert not any(operation["result"] == "success" for operation in campus_operations)
        manager_action = "account_role_change" if actor_change == "role" else "account_status_change"
        assert database.account_management_operations.find_one(
            {
                "action": manager_action,
                "targetId": actor_user["id"],
                "reason": actor_reason,
                "result": "success",
            }
        )
    finally:
        mongo.close()


def test_real_http_audit_insert_failure_rolls_back_campus_approval() -> None:
    username = f"issue360-audit-failure-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()
    collection_name = "account_management_operations"
    collection_options = database.command(
        "listCollections", filter={"name": collection_name}
    )["cursor"]["firstBatch"][0].get("options", {})
    original_validator = collection_options.get("validator", {})
    original_validation_level = collection_options.get("validationLevel", "strict")
    original_validation_action = collection_options.get("validationAction", "error")

    try:
        registration_status, registered = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registration_status == 201
        applicant = _opener()
        applicant_session = _login(applicant, username, password)
        submitted_status, application = _submit(
            applicant,
            applicant_session["csrfToken"],
            "合成审计回滚申请人",
            student_number,
        )
        assert submitted_status == 201
        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        prior_application_operations = database.account_management_operations.count_documents(
            {"campusApplicationId": application["id"]}
        )

        database.command(
            "collMod",
            collection_name,
            validator={"action": {"$ne": "campus_access_approve"}},
            validationLevel="strict",
            validationAction="error",
        )
        failed_status, failed_result = _admin_action(
            admin,
            admin_session["csrfToken"],
            application["id"],
            "decision",
            {"decision": "approved", "reason": "合成审计拒写回滚"},
        )
        assert failed_status == 500
        assert failed_result is not None
        assert database.campus_access_applications.find_one(
            {"id": application["id"]}
        )["status"] == "pending"
        assert database.users.find_one({"id": registered["id"]})[
            "campus_verified"
        ] is False
        assert database.account_management_operations.count_documents(
            {"campusApplicationId": application["id"]}
        ) == prior_application_operations
    finally:
        database.command(
            "collMod",
            collection_name,
            validator=original_validator,
            validationLevel=original_validation_level,
            validationAction=original_validation_action,
        )
        mongo.close()


def test_real_http_history_snapshot_and_sse_recheck_revoked_campus_access() -> None:
    username = f"issue360-history-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()

    try:
        anonymous = _opener()
        registration_status, registered = _request(
            anonymous,
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registration_status == 201
        applicant = _opener()
        session = _login(applicant, username, password)
        submitted_status, application = _submit(
            applicant, session["csrfToken"], "合成历史申请人", student_number
        )
        assert submitted_status == 201
        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        approved_status, approved = _admin_action(
            admin,
            admin_session["csrfToken"],
            application["id"],
            "decision",
            {"decision": "approved", "reason": "合成历史回放资格批准"},
        )
        assert approved_status == 200 and approved["status"] == "approved"

        case_status, case = _request(
            applicant,
            "POST",
            "/api/cases",
            {"title": f"合成校内来源历史 {uuid.uuid4().hex}"},
            session["csrfToken"],
        )
        assert case_status == 200
        thread_status, thread = _request(
            applicant,
            "POST",
            f"/api/cases/{case['id']}/agent/threads",
            {"title": "合成来源历史"},
            session["csrfToken"],
        )
        assert thread_status == 201

        material_id = f"m-issue360-history-{uuid.uuid4().hex}"
        database.materials.insert_one(
            {
                "id": material_id,
                "status": "active",
                "title": "合成校内来源",
                "accessLevel": "campus",
                "createdBy": admin_session["user"]["id"],
            }
        )
        message_id = f"message-issue360-history-{uuid.uuid4().hex}"
        run_id = f"run-issue360-history-{uuid.uuid4().hex}"
        marker = f"合成校内历史内容-{uuid.uuid4().hex}"
        source = {
            "kind": "material",
            "id": material_id,
            "title": "合成校内来源",
            "location": f"material:{material_id}",
        }
        database.agent_messages.insert_one(
            {
                "id": message_id,
                "threadId": thread["id"],
                "runId": run_id,
                "messageSeq": 0,
                "role": "assistant",
                "metadata": {},
                "parts": [
                    {
                        "type": "tool-read_source",
                        "output": {"status": "ok", "usedSourceRef": source},
                    },
                    {"type": "text", "text": marker},
                ],
                "createdAt": datetime.now(UTC),
            }
        )
        database.agent_thread_events.insert_one(
            {
                "id": f"event-issue360-history-{uuid.uuid4().hex}",
                "threadId": thread["id"],
                "eventSeq": 1,
                "type": "message.created",
                "runId": run_id,
                "payload": {"messageId": message_id},
                "createdAt": datetime.now(UTC),
            }
        )
        database.agent_threads.update_one(
            {"id": thread["id"]}, {"$set": {"eventSeq": 1}}
        )

        snapshot_status, snapshot = _request(
            applicant, "GET", f"/api/cases/{case['id']}/agent/threads/{thread['id']}"
        )
        assert snapshot_status == 200
        assert marker in json.dumps(snapshot, ensure_ascii=False)
        replay_status, replay = _event_text(
            applicant, f"/api/cases/{case['id']}/agent/thread/{thread['id']}/events"
        )
        assert replay_status == 200 and marker in replay

        revoked_status, revoked = _admin_action(
            admin,
            admin_session["csrfToken"],
            application["id"],
            "revoke",
            {"reason": "合成历史回放资格撤销"},
        )
        assert revoked_status == 200 and revoked["status"] == "revoked"

        snapshot_status, snapshot = _request(
            applicant, "GET", f"/api/cases/{case['id']}/agent/threads/{thread['id']}"
        )
        assert snapshot_status == 200
        assert marker not in json.dumps(snapshot, ensure_ascii=False)
        assert "该回答引用的来源当前不可读，相关内容已隐藏" in json.dumps(
            snapshot, ensure_ascii=False
        )
        replay_status, replay = _event_text(
            applicant, f"/api/cases/{case['id']}/agent/thread/{thread['id']}/events"
        )
        assert replay_status == 200
        assert marker not in replay
        assert "该回答引用的来源当前不可读，相关内容已隐藏" in replay
        assert database.users.find_one({"id": registered["id"]})[
            "campus_access_revoked_at"
        ]
    finally:
        mongo.close()


@pytest.mark.e2e(
    "CASE_LIBRARY_E2E_URL",
    "AUTH_QUERY_MONGODB_URI",
    "OBJECT_STORE_ENDPOINT",
    "OBJECT_STORE_BUCKET",
    "OBJECT_STORE_ACCESS_KEY_FILE",
    "OBJECT_STORE_SECRET_KEY_FILE",
    "MEILI_CONTRACT_URL",
    "MEILI_CONTRACT_KEY_FILE",
)
def test_real_http_campus_revoke_rechecks_next_tool_and_review_output() -> None:
    import meilisearch
    from app.modules.agent.deps import ToolDeps
    from app.modules.agent.models import SourceRef
    from app.modules.agent.repository import AgentRepository
    from app.modules.agent.search import CorpusSearchParams
    from app.modules.agent.service import _reader_accessible
    from app.modules.agent.skills import read_source as read_source_tool
    from app.modules.agent.skills import search_corpus as search_corpus_tool
    from app.modules.attachments.storage import MinioBlobStore
    from app.modules.search.client import create_reader, index_epoch, wait_task
    from app.modules.search.indexer import catalog_settings
    from app.modules.search.meilisearch import MeilisearchCatalog
    from app.modules.search.outbox import CatalogTarget
    from app.modules.search.projection import project_catalog_documents
    from app.modules.search.state import CatalogSnapshot
    from minio import Minio

    username = f"issue360-tool-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()
    blob_id = f"issue360-{uuid.uuid4().hex}"
    material_id = f"m-{blob_id}"
    material_title = f"合成校内当前资格来源-{uuid.uuid4().hex}"
    material_summary = f"合成校内摘要-{uuid.uuid4().hex}"
    endpoint = os.environ["OBJECT_STORE_ENDPOINT"]
    bucket = os.environ["OBJECT_STORE_BUCKET"]
    access_key = Path(os.environ["OBJECT_STORE_ACCESS_KEY_FILE"]).read_text(
        encoding="utf-8"
    ).strip()
    secret_key = Path(os.environ["OBJECT_STORE_SECRET_KEY_FILE"]).read_text(
        encoding="utf-8"
    ).strip()
    client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=os.getenv("OBJECT_STORE_SECURE", "").lower()
        in {"1", "true", "yes", "on"},
    )
    store = MinioBlobStore(client, bucket)
    material_text = f"合成校内来源正文-{uuid.uuid4().hex}"
    meili_key = Path(os.environ["MEILI_CONTRACT_KEY_FILE"]).read_text(
        encoding="utf-8"
    ).strip()
    meili_client = meilisearch.Client(os.environ["MEILI_CONTRACT_URL"], meili_key)
    index_uid = f"campus_access_{uuid.uuid4().hex}"
    index_created = False
    catalog = None
    catalog_state = None
    blob_written = False

    def tool_deps(user: dict, source: SourceRef, case_id: str, thread_id: str, run_id: str):
        return ToolDeps(
            database=database,
            case_id=case_id,
            thread_id=thread_id,
            run_id=run_id,
            user=user,
            catalog=catalog,
            catalog_state=catalog_state,
            secret_path="",
            store=store,
            hits=[source],
        )

    try:
        store.put(
            blob_id, BytesIO(material_text.encode()), len(material_text.encode()),
            "text/plain",
        )
        blob_written = True
        database.materials.insert_one({
            "id": material_id,
            "status": "active",
            "title": material_title,
            "summary": material_summary,
            "source": "合成资料",
            "excerpt": "合成校内素材摘录",
            "materialType": "文档",
            "authority": "original",
            "tags": ["合成"],
            "publicReferenceCount": 1,
            "filename": "campus.txt",
            "mediaType": "text/plain",
            "size": len(material_text.encode()),
            "blobId": blob_id,
            "accessLevel": "campus",
            "createdBy": "u-issue360-synthetic-owner",
        })
        wait_task(
            meili_client,
            meili_client.create_index(index_uid, {"primaryKey": "catalogId"}),
        )
        index_created = True
        index = meili_client.index(index_uid)
        wait_task(meili_client, index.update_settings(catalog_settings()))
        projected = project_catalog_documents(
            "material",
            {
                "id": material_id,
                "status": "active",
                "title": material_title,
                "summary": material_summary,
                "source": "合成资料",
                "excerpt": "合成校内素材摘录",
                "materialType": "文档",
                "authority": "original",
                "tags": ["合成"],
                "publicReferenceCount": 1,
                "blobId": blob_id,
                "accessLevel": "campus",
                "createdBy": "u-issue360-synthetic-owner",
            },
        )
        wait_task(meili_client, index.add_documents(projected))
        target = CatalogTarget(
            f"campus-access-{uuid.uuid4().hex}",
            index_uid,
            index_epoch(meili_client, index_uid),
        )
        snapshot = CatalogSnapshot(target, 0, ())
        catalog = MeilisearchCatalog(
            create_reader(
                os.environ["MEILI_CONTRACT_URL"],
                os.environ["MEILI_CONTRACT_KEY_FILE"],
            )
        )
        catalog_state = SimpleNamespace(read=lambda: snapshot)

        anonymous = _opener()
        registered_status, registered = _request(
            anonymous,
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registered_status == 201
        applicant = _opener()
        applicant_session = _login(applicant, username, password)
        applicant_id = registered["id"]
        assert applicant_session["user"]["id"] == applicant_id
        submitted_status, application = _submit(
            applicant, applicant_session["csrfToken"], "合成工具申请人", student_number
        )
        assert submitted_status == 201

        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        case_id = f"c-review360-{uuid.uuid4().hex}"
        thread_id = f"t-review360-{uuid.uuid4().hex}"
        run_id = f"r-review360-{uuid.uuid4().hex}"
        submitted_version_id = f"v-review360-{uuid.uuid4().hex}"
        database.cases.insert_one({
            "id": case_id,
            "workflowStatus": "reviewing",
            "submittedVersionId": submitted_version_id,
        })
        database.agent_threads.insert_one({"id": thread_id, "caseId": case_id})
        database.agent_runs.insert_one({
            "id": run_id,
            "threadId": thread_id,
            "userId": applicant_id,
            "submittedVersionId": submitted_version_id,
        })

        promoted_status, promoted = _request(
            admin,
            "POST",
            f"/api/admin/accounts/{applicant_id}/role",
            {"role": "admin", "reason": "合成审核员角色准备"},
            admin_session["csrfToken"],
        )
        assert promoted_status == 200 and promoted["role"] == "admin"
        current_applicant = database.users.find_one({"id": applicant_id})
        token_version = current_applicant["token_version"]
        assert current_applicant["campus_verified"] is False
        assert current_applicant["id"] == registered["id"]
        assert current_applicant["name"] == username
        source = SourceRef(kind="material", id=material_id, title=material_title)
        deps = tool_deps(current_applicant, source, case_id, thread_id, run_id)
        context = SimpleNamespace(
            review=True,
            case={"id": case_id, "versionId": None},
            run=SimpleNamespace(id=run_id, user_id=applicant_id),
            repository=AgentRepository(database),
            deps=deps,
        )
        pending_search = asyncio.run(
            search_corpus_tool(
                SimpleNamespace(deps=deps),
                CorpusSearchParams(query=material_title, kind="material"),
            )
        )
        assert pending_search["sources"][0]["contentAvailable"] is False
        assert pending_search["sources"][0]["snippet"] == material_title
        assert material_summary not in json.dumps(pending_search, ensure_ascii=False)
        pending_read = asyncio.run(
            read_source_tool(SimpleNamespace(deps=deps), "material", material_id)
        )
        assert pending_read["status"] == "no_access"

        approved_status, approved = _admin_action(
            admin, admin_session["csrfToken"], application["id"], "decision",
            {"decision": "approved", "reason": "合成工具取材核验通过"},
        )
        assert approved_status == 200 and approved["status"] == "approved"
        approved_search = asyncio.run(
            search_corpus_tool(
                SimpleNamespace(deps=deps),
                CorpusSearchParams(query=material_title, kind="material"),
            )
        )
        assert approved_search["sources"][0]["contentAvailable"] is True
        assert approved_search["sources"][0]["snippet"] == material_summary
        assert material_summary in json.dumps(approved_search, ensure_ascii=False)
        first_read = asyncio.run(
            read_source_tool(SimpleNamespace(deps=deps), "material", material_id)
        )
        assert first_read["status"] == "ok"
        assert material_text in first_read["content"]
        assert _reader_accessible(context) is True

        revoked_status, revoked = _admin_action(
            admin, admin_session["csrfToken"], application["id"], "revoke",
            {"reason": "合成审核中校内资格撤销"},
        )
        assert revoked_status == 200 and revoked["status"] == "revoked"
        revoked_search = asyncio.run(
            search_corpus_tool(
                SimpleNamespace(deps=deps),
                CorpusSearchParams(query=material_title, kind="material"),
            )
        )
        assert revoked_search["sources"][0]["contentAvailable"] is False
        assert revoked_search["sources"][0]["snippet"] == material_title
        assert material_summary not in json.dumps(revoked_search, ensure_ascii=False)
        denied_read = asyncio.run(
            read_source_tool(SimpleNamespace(deps=deps), "material", material_id)
        )
        assert denied_read["status"] == "no_access"
        assert "content" not in denied_read
        assert _reader_accessible(context) is False
        assert database.users.find_one({"id": applicant_id})["role"] == "admin"

        applicant_session = _login(applicant, username, password)
        pending_status, reapplication = _submit(
            applicant, applicant_session["csrfToken"], "合成工具再次申请人",
            student_number + "-R",
        )
        assert pending_status == 201
        pending_read = asyncio.run(
            read_source_tool(SimpleNamespace(deps=deps), "material", material_id)
        )
        assert pending_read["status"] == "no_access"
        pending_search = asyncio.run(
            search_corpus_tool(
                SimpleNamespace(deps=deps),
                CorpusSearchParams(query=material_title, kind="material"),
            )
        )
        assert pending_search["sources"][0]["contentAvailable"] is False
        assert pending_search["sources"][0]["snippet"] == material_title
        assert material_summary not in json.dumps(pending_search, ensure_ascii=False)
        approved_again_status, approved_again = _admin_action(
            admin, admin_session["csrfToken"], reapplication["id"], "decision",
            {"decision": "approved", "reason": "合成再次人工核验通过"},
        )
        assert approved_again_status == 200 and approved_again["status"] == "approved"
        restored_search = asyncio.run(
            search_corpus_tool(
                SimpleNamespace(deps=deps),
                CorpusSearchParams(query=material_title, kind="material"),
            )
        )
        assert restored_search["sources"][0]["contentAvailable"] is True
        assert restored_search["sources"][0]["snippet"] == material_summary
        assert material_summary in json.dumps(restored_search, ensure_ascii=False)
        restored_read = asyncio.run(
            read_source_tool(SimpleNamespace(deps=deps), "material", material_id)
        )
        assert restored_read["status"] == "ok"
        assert material_text in restored_read["content"]

        force_logout_status, _force_logout = _request(
            admin,
            "POST",
            f"/api/admin/accounts/{applicant_id}/force-logout",
            {"reason": "合成过期 Run 会话撤销"},
            admin_session["csrfToken"],
        )
        assert force_logout_status == 200
        expired_read = asyncio.run(
            read_source_tool(SimpleNamespace(deps=deps), "material", material_id)
        )
        assert expired_read == {"status": "no_access", "detail": "当前账号不可读取来源"}
        with pytest.raises(RuntimeError, match="当前账号不可继续检索"):
            asyncio.run(
                search_corpus_tool(
                    SimpleNamespace(deps=deps),
                    CorpusSearchParams(query=material_title, kind="material"),
                )
            )
        assert _reader_accessible(context) is False
        assert database.users.find_one({"id": applicant_id})["status"] == "active"
        assert database.users.find_one({"id": applicant_id})["token_version"] > token_version
        assert _request(applicant, "GET", "/api/auth/campus-access")[0] == 401
    finally:
        try:
            if blob_written:
                store.remove(blob_id)
        finally:
            try:
                if index_created:
                    wait_task(meili_client, meili_client.delete_index(index_uid))
            finally:
                database.materials.delete_one({"id": material_id})
                mongo.close()


@pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")
def test_real_http_legacy_source_migration_keeps_explicit_revocation_after_restart() -> None:
    from app.core.database import _mark_legacy_campus_grant, initialize

    username = f"issue360-legacy-{uuid.uuid4().hex}"
    password = f"Issue360-{uuid.uuid4().hex}!a"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()

    try:
        anonymous = _opener()
        registered_status, registered = _request(
            anonymous,
            "POST",
            "/api/auth/register",
            {"username": username, "password": password},
        )
        assert registered_status == 201
        user_id = registered["id"]
        database.users.update_one(
            {"id": user_id},
            {"$set": {"campus_verified": True}, "$unset": {
                "campus_access_grant_source": "",
                "campus_access_granted_by_application_id": "",
            }},
        )
        stale_migration_row = database.users.find_one({"id": user_id})

        admin = _opener()
        admin_session = _login(admin, "admin", "admin123")
        promoted_status, promoted = _request(
            admin,
            "POST",
            f"/api/admin/accounts/{user_id}/role",
            {"role": "admin", "reason": "合成既有资格账号角色提升"},
            admin_session["csrfToken"],
        )
        assert promoted_status == 200 and promoted["role"] == "admin"

        initialize(database)
        legacy = database.users.find_one({"id": user_id})
        assert legacy["campus_verified"] is True
        assert legacy["campus_access_grant_source"] == "legacy"
        assert legacy["id"] == user_id and legacy["name"] == username
        assert database.campus_access_applications.count_documents({"userId": user_id}) == 0
        grant_status, grants = _request(
            admin, "GET", f"/api/admin/campus-access-legacy-grants?q={username}"
        )
        assert grant_status == 200
        assert grants["items"] == [{
            "userId": user_id, "username": username, "role": "admin",
            "grantSource": "legacy",
        }]

        revoke_status, revoked = _request(
            admin,
            "POST",
            f"/api/admin/campus-access-users/{user_id}/revoke-legacy",
            {"reason": "合成旧系统资格明确撤销"},
            admin_session["csrfToken"],
        )
        assert revoke_status == 200 and revoked["campusVerified"] is False
        revoked_at = revoked["revokedAt"]
        applicant = _opener()
        applicant_session = _login(applicant, username, password)
        pending_status, pending = _submit(
            applicant, applicant_session["csrfToken"], "合成旧系统资格重申",
            f"SYN-360-{uuid.uuid4().hex[:12]}",
        )
        assert pending_status == 201 and pending["status"] == "pending"
        assert _request(applicant, "GET", "/api/auth/campus-access")[1][
            "campusVerified"
        ] is False
        _mark_legacy_campus_grant(database, stale_migration_row)
        initialize(database)

        current = database.users.find_one({"id": user_id})
        assert current["campus_verified"] is False
        assert current["campus_access_grant_source"] == "legacy"
        assert current["campus_access_revoked_at"] == revoked_at
        assert current["role"] == "admin"
        assert current["id"] == user_id and current["name"] == username
        assert database.campus_access_applications.count_documents({"userId": user_id}) == 1
        assert database.campus_access_applications.find_one({"userId": user_id})[
            "status"
        ] == "pending"
        operation = database.account_management_operations.find_one({
            "action": "campus_access_legacy_revoke", "targetId": user_id,
        })
        assert operation["reason"] == "合成旧系统资格明确撤销"
        assert "campusApplicationId" not in operation
    finally:
        mongo.close()


@pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")
@pytest.mark.parametrize("action", ["approve", "reject", "revoke", "legacy_revoke"])
def test_real_http_force_logout_prevents_stale_campus_decision_transaction(action: str) -> None:
    from app.modules.auth.management_service import (
        AccountManagementError,
        AccountManagementService,
    )

    actor_username = f"issue360-stale-session-admin-{uuid.uuid4().hex}"
    actor_password = f"Issue360-{uuid.uuid4().hex}!a"
    target_username = f"issue360-stale-session-target-{uuid.uuid4().hex}"
    target_password = f"Issue360-{uuid.uuid4().hex}!a"
    student_number = f"SYN-360-{uuid.uuid4().hex[:12]}"
    reason = f"合成过期资格操作员{action}"
    mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    database = mongo.get_default_database()

    try:
        super_admin = _opener()
        super_session = _login(super_admin, "admin", "admin123")
        actor_registration_status, actor_user = _request(
            _opener(),
            "POST",
            "/api/auth/register",
            {"username": actor_username, "password": actor_password},
        )
        assert actor_registration_status == 201
        promoted_status, _promoted = _request(
            super_admin,
            "POST",
            f"/api/admin/accounts/{actor_user['id']}/role",
            {"role": "admin", "reason": "合成过期会话管理员初始化"},
            super_session["csrfToken"],
        )
        assert promoted_status == 200
        actor = _opener()
        actor_session = _login(actor, actor_username, actor_password)
        stale_actor = database.users.find_one({"id": actor_user["id"]})

        if action == "legacy_revoke":
            target_status, target = _request(
                _opener(),
                "POST",
                "/api/auth/register",
                {"username": target_username, "password": target_password},
            )
            assert target_status == 201
            target_id = target["id"]
            database.users.update_one(
                {"id": target_id},
                {"$set": {
                    "campus_verified": True,
                    "campus_access_grant_source": "legacy",
                }},
            )
            http_path = f"/api/admin/campus-access-users/{target_id}/revoke-legacy"
            http_body = {"reason": reason}
            operation = "campus_access_legacy_revoke"
            before = database.users.find_one({"id": target_id})
        else:
            target_registration_status, target = _request(
                _opener(),
                "POST",
                "/api/auth/register",
                {"username": target_username, "password": target_password},
            )
            assert target_registration_status == 201
            target_id = target["id"]
            applicant = _opener()
            applicant_session = _login(applicant, target_username, target_password)
            submitted_status, application = _submit(
                applicant,
                applicant_session["csrfToken"],
                "合成过期会话申请人",
                student_number,
            )
            assert submitted_status == 201
            if action == "revoke":
                approved_status, _approved = _admin_action(
                    super_admin,
                    super_session["csrfToken"],
                    application["id"],
                    "decision",
                    {"decision": "approved", "reason": "合成过期会话撤销准备"},
                )
                assert approved_status == 200
                decision = "approved"
            else:
                decision = "approved" if action == "approve" else "rejected"
            http_path = (
                f"/api/admin/campus-access-applications/{application['id']}/revoke"
                if action == "revoke"
                else f"/api/admin/campus-access-applications/{application['id']}/decision"
            )
            http_body = (
                {"reason": reason}
                if action == "revoke"
                else {"decision": decision, "reason": reason}
            )
            operation = f"campus_access_{action}"
            before = {
                "application": database.campus_access_applications.find_one(
                    {"id": application["id"]}
                ),
                "user": database.users.find_one({"id": target_id}),
            }

        assert stale_actor["role"] == "admin"
        logout_status, _logged_out = _request(
            super_admin,
            "POST",
            f"/api/admin/accounts/{actor_user['id']}/force-logout",
            {"reason": "合成先撤销旧资格管理员会话"},
            super_session["csrfToken"],
        )
        assert logout_status == 200

        stale_http_status, _stale_response = _request(
            actor, "POST", http_path, http_body, actor_session["csrfToken"]
        )
        assert stale_http_status == 401

        service = AccountManagementService(database)
        with pytest.raises(AccountManagementError) as error:
            if action == "legacy_revoke":
                service.revoke_legacy_campus_access(stale_actor, target_id, reason)
            elif action == "revoke":
                service.revoke_campus_access(stale_actor, application["id"], reason)
            else:
                service.decide_campus_application(
                    stale_actor, application["id"], decision, reason
                )
        assert error.value.status_code == 403

        operation_row = database.account_management_operations.find_one({
            "actorId": actor_user["id"], "action": operation,
            "targetId": target_id, "reason": reason, "result": "rejected",
        })
        assert operation_row
        if action == "legacy_revoke":
            after = database.users.find_one({"id": target_id})
            assert after["campus_verified"] is before["campus_verified"] is True
            assert after["campus_access_grant_source"] == "legacy"
            assert "campus_access_revoked_at" not in after
        else:
            after_application = database.campus_access_applications.find_one(
                {"id": application["id"]}
            )
            after_user = database.users.find_one({"id": target_id})
            expected_status = "approved" if action == "revoke" else "pending"
            assert after_application["status"] == expected_status
            assert after_user["campus_verified"] is (action == "revoke")
            assert after_application["status"] == before["application"]["status"]
            assert after_user["campus_verified"] == before["user"]["campus_verified"]
    finally:
        mongo.close()
