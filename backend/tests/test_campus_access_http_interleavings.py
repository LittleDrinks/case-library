from __future__ import annotations

import asyncio
import os
import socket
import uuid
from datetime import UTC, datetime
from contextlib import ExitStack, contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from threading import Event, Thread

import httpx
import pytest
import uvicorn
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel
from pymongo import MongoClient

from app.core.config import Settings
from app.main import create_app
from app.modules.agent.repository import AgentRepository
from app.modules.attachments.storage import minio_blob_store
from app.modules.auth.admin_bootstrap import bootstrap_admin
from app.modules.auth.management_service import AccountManagementService
from app.modules.auth.sessions import COOKIE_NAME
from app.modules.search.client import create_reader, index_epoch, wait_task
from app.modules.search.indexer import catalog_settings
from app.modules.search.meilisearch import MeilisearchCatalog
from app.modules.search.projection import PROJECTION_VERSION, project_catalog_documents
from app.modules.search.state import MongoCatalogState


pytestmark = pytest.mark.e2e(
    "AUTH_QUERY_MONGODB_URI",
    "OBJECT_STORE_ENDPOINT",
    "OBJECT_STORE_ACCESS_KEY_FILE",
    "OBJECT_STORE_SECRET_KEY_FILE",
    "MEILI_CONTRACT_URL",
    "MEILI_CONTRACT_KEY_FILE",
)


class _RequestPause:
    def __init__(self) -> None:
        self.entered = Event()
        self.resume = Event()

    def wait(self) -> None:
        self.entered.set()
        if not self.resume.wait(timeout=30):
            raise TimeoutError("测试调度等待恢复超时")


@pytest.fixture
def campus_http_environment(tmp_path):
    mongo = MongoClient(os.environ["AUTH_QUERY_MONGODB_URI"], serverSelectionTimeoutMS=5000)
    database_name = f"case_library_360_interleaving_{uuid.uuid4().hex}"
    try:
        database = mongo[database_name]
        admin = {
            "username": f"issue360-root-{uuid.uuid4().hex}",
            "password": f"Issue360-Root-{uuid.uuid4().hex}!a",
        }
        bootstrap_admin(database, admin["username"], "合成并发管理员", admin["password"])
        secret = tmp_path / "app-secret"
        secret.write_text("synthetic-test-secret", encoding="utf-8")
        settings = replace(
            Settings(),
            app_environment="test",
            session_cookie_secure=False,
            app_secret_file=str(secret),
            object_store_endpoint=os.environ["OBJECT_STORE_ENDPOINT"],
            object_store_bucket=f"issue360-{uuid.uuid4().hex}",
            object_store_access_key_file=os.environ["OBJECT_STORE_ACCESS_KEY_FILE"],
            object_store_secret_key_file=os.environ["OBJECT_STORE_SECRET_KEY_FILE"],
            search_url=os.environ["MEILI_CONTRACT_URL"],
            search_index_uid=f"campus360-{uuid.uuid4().hex}",
            search_api_key_file=os.environ["MEILI_CONTRACT_KEY_FILE"],
        )
        blob_store = minio_blob_store(settings)
        search_catalog = MeilisearchCatalog(
            create_reader(settings.search_url, settings.search_api_key_file)
        )

        def new_app():
            return create_app(
                database=database,
                settings=settings,
                blob_store=blob_store,
                search_catalog=search_catalog,
                catalog_state=MongoCatalogState(database),
            )

        yield database, new_app, admin
    finally:
        try:
            mongo.drop_database(database_name)
        finally:
            mongo.close()


def _clients(stack: ExitStack, base_url: str, count: int) -> list[httpx.Client]:
    return [
        stack.enter_context(httpx.Client(base_url=base_url, timeout=30))
        for _ in range(count)
    ]


def _login(client: httpx.Client, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token = client.cookies.get(COOKIE_NAME)
    assert token
    client.cookies.clear()
    return {"token": token, "csrf": response.json()["csrfToken"],
            "user": response.json()["user"]}


def _call(client: httpx.Client, session: dict, method: str, path: str, body=None):
    headers = {
        "Cookie": f"{COOKIE_NAME}={session['token']}",
        "X-CSRF-Token": session["csrf"],
    }
    return client.request(method, path, json=body, headers=headers)


def _read_secret(path: str) -> str:
    with open(path, encoding="utf-8") as secret_file:
        return secret_file.read().strip()


def _register(client: httpx.Client, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _promote_admin(client: httpx.Client, root_session: dict, username: str) -> dict:
    password = f"Issue360-Actor-{uuid.uuid4().hex}!a"
    account = _register(client, username, password)
    response = _call(
        client,
        root_session,
        "POST",
        f"/api/admin/accounts/{account['id']}/role",
        {"role": "admin", "reason": "合成事务操作者开户"},
    )
    assert response.status_code == 200, response.text
    return {"account": account, "password": password}


def _run_request_after_change(
    request, pause: _RequestPause, change_request,
):
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(request)
        try:
            assert pause.entered.wait(timeout=15), "原请求未到达身份守卫后的暂停点"
            assert not pending.done()
            change_result = change_request()
        finally:
            pause.resume.set()
        return change_result, pending.result(timeout=30)


@contextmanager
def _uvicorn_server(app):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    host, port = listener.getsockname()
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="error", access_log=False, lifespan="on")
    )
    thread = Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
    try:
        deadline = 15
        while not server.started and deadline > 0 and thread.is_alive():
            Event().wait(0.02)
            deadline -= 0.02
        assert server.started, "隔离 Uvicorn 未能启动"
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        listener.close()
        assert not thread.is_alive(), "测试启动的 Uvicorn 未能停止"


@pytest.mark.parametrize("change", ["force_logout", "disable", "change_password"])
def test_application_request_rechecks_after_other_public_session_changes_account(
    tmp_path, monkeypatch, campus_http_environment, change: str,
) -> None:
    database, new_app, admin_credentials = campus_http_environment
    username = f"issue360-applicant-{uuid.uuid4().hex}"
    password = f"Issue360-Applicant-{uuid.uuid4().hex}!a"
    new_password = f"Issue360-Changed-{uuid.uuid4().hex}!b"
    applicant_id: str

    with _uvicorn_server(new_app()) as base_url, ExitStack() as stack:
        applicant_client, other_session_client, admin_client = _clients(
            stack, base_url, 3
        )
        root_session = _login(
            admin_client, admin_credentials["username"], admin_credentials["password"]
        )
        applicant = _register(applicant_client, username, password)
        applicant_id = applicant["id"]
        original_session = _login(applicant_client, username, password)
        other_session = _login(other_session_client, username, password)
        pause = _RequestPause()
        original_submit = AccountManagementService.submit_campus_application

        def pause_after_http_guard(service, user, applicant_name, student_number):
            pause.wait()
            return original_submit(service, user, applicant_name, student_number)

        monkeypatch.setattr(
            AccountManagementService,
            "submit_campus_application",
            pause_after_http_guard,
        )

        def submit():
            return _call(
                applicant_client,
                original_session,
                "POST",
                "/api/auth/campus-access/applications",
                {"applicantName": "合成并发申请人", "studentNumber": f"SYN-360-{uuid.uuid4().hex[:12]}"},
            )

        def change_account():
            if change == "force_logout":
                return _call(
                    admin_client,
                    root_session,
                    "POST",
                    f"/api/admin/accounts/{applicant_id}/force-logout",
                    {"reason": "合成申请前撤销会话"},
                )
            if change == "disable":
                return _call(
                    admin_client,
                    root_session,
                    "POST",
                    f"/api/admin/accounts/{applicant_id}/status",
                    {"status": "disabled", "reason": "合成申请前停用"},
                )
            return _call(
                other_session_client,
                other_session,
                "POST",
                "/api/auth/change-password",
                {"currentPassword": password, "newPassword": new_password},
            )

        changed, response = _run_request_after_change(submit, pause, change_account)

    expected_change_status = 204 if change == "change_password" else 200
    assert changed.status_code == expected_change_status, changed.text
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "当前账号会话已变化，请重新登录后重试"
    assert database.campus_access_applications.count_documents({"userId": applicant_id}) == 0
    assert database.account_management_operations.find_one({
        "action": "campus_access_application_submit",
        "actorId": applicant_id,
        "result": "rejected",
        "detail": response.json()["detail"],
    })
    assert database.account_management_operations.count_documents({
        "action": "campus_access_application_submit",
        "actorId": applicant_id,
        "result": "success",
    }) == 0


@pytest.mark.parametrize("action", ["approve", "reject", "revoke", "legacy_revoke"])
def test_admin_campus_transaction_rechecks_actor_after_public_force_logout(
    monkeypatch, campus_http_environment, action: str,
) -> None:
    database, new_app, admin_credentials = campus_http_environment
    root_username, root_password = admin_credentials["username"], admin_credentials["password"]
    target_username = f"issue360-target-{uuid.uuid4().hex}"
    target_password = f"Issue360-Target-{uuid.uuid4().hex}!a"
    actor_username = f"issue360-actor-{uuid.uuid4().hex}"
    reason = f"合成过期权限决策-{action}"
    target_id: str
    application_id: str | None = None

    with _uvicorn_server(new_app()) as base_url, ExitStack() as stack:
        target_client, root_client, actor_client = _clients(stack, base_url, 3)
        root_session = _login(root_client, root_username, root_password)
        target = _register(target_client, target_username, target_password)
        target_id = target["id"]

        if action == "legacy_revoke":
            database.users.update_one(
                {"id": target_id},
                {"$set": {
                    "campus_verified": True,
                    "campus_access_grant_source": "legacy",
                }},
            )
            method_name = "revoke_legacy_campus_access"
            path = f"/api/admin/campus-access-users/{target_id}/revoke-legacy"
            body = {"reason": reason}
            audit_action = "campus_access_legacy_revoke"
        else:
            target_session = _login(target_client, target_username, target_password)
            submitted = _call(
                target_client,
                target_session,
                "POST",
                "/api/auth/campus-access/applications",
                {"applicantName": "合成事务目标", "studentNumber": f"SYN-360-{uuid.uuid4().hex[:12]}"},
            )
            assert submitted.status_code == 201, submitted.text
            application_id = submitted.json()["id"]
            method_name = "revoke_campus_access" if action == "revoke" else "decide_campus_application"
            if action == "revoke":
                approved = _call(
                    root_client,
                    root_session,
                    "POST",
                    f"/api/admin/campus-access-applications/{application_id}/decision",
                    {"decision": "approved", "reason": "合成撤销事务准备"},
                )
                assert approved.status_code == 200, approved.text
                path = f"/api/admin/campus-access-applications/{application_id}/revoke"
                body = {"reason": reason}
                audit_action = "campus_access_revoke"
            else:
                decision = "approved" if action == "approve" else "rejected"
                path = f"/api/admin/campus-access-applications/{application_id}/decision"
                body = {"decision": decision, "reason": reason}
                audit_action = f"campus_access_{action}"

        actor_account = _promote_admin(root_client, root_session, actor_username)
        actor_session = _login(
            actor_client, actor_username, actor_account["password"]
        )
        actor_id = actor_account["account"]["id"]
        pause = _RequestPause()
        original_method = getattr(AccountManagementService, method_name)

        def pause_after_http_guard(service, *args, **kwargs):
            pause.wait()
            return original_method(service, *args, **kwargs)

        monkeypatch.setattr(AccountManagementService, method_name, pause_after_http_guard)

        def request():
            return _call(actor_client, actor_session, "POST", path, body)

        def change_request():
            return _call(
                root_client,
                root_session,
                "POST",
                f"/api/admin/accounts/{actor_id}/force-logout",
                {"reason": "合成事务前撤销操作员会话"},
            )

        forced, response = _run_request_after_change(request, pause, change_request)

    assert forced.status_code == 200, forced.text
    assert response.status_code == 403, response.text
    assert database.account_management_operations.find_one({
        "action": audit_action,
        "actorId": actor_id,
        "targetId": target_id,
        "reason": reason,
        "result": "rejected",
    })
    assert database.account_management_operations.count_documents({
        "action": audit_action,
        "actorId": actor_id,
        "result": "success",
    }) == 0

    current_target = database.users.find_one({"id": target_id})
    if action == "legacy_revoke":
        assert current_target["campus_verified"] is True
        assert current_target["campus_access_grant_source"] == "legacy"
        assert "campus_access_revoked_at" not in current_target
    else:
        current_application = database.campus_access_applications.find_one(
            {"id": application_id}
        )
        expected_status = "approved" if action == "revoke" else "pending"
        assert current_application["status"] == expected_status
        assert current_target["campus_verified"] is (action == "revoke")


@pytest.mark.parametrize("change", ["force_logout", "disable", "change_password"])
def test_open_source_less_sse_stops_after_public_account_change(
    campus_http_environment, change: str,
) -> None:
    database, new_app, admin_credentials = campus_http_environment
    username = f"issue360-sse-user-{uuid.uuid4().hex}"
    password = f"Issue360-Sse-{uuid.uuid4().hex}!a"
    new_password = f"Issue360-SseChanged-{uuid.uuid4().hex}!b"
    first_marker = f"合成首段-{uuid.uuid4().hex}"
    second_marker = f"合成撤销后段-{uuid.uuid4().hex}"

    app = new_app()
    with _uvicorn_server(app) as base_url, ExitStack() as stack:
        user_client, second_session_client, admin_client = _clients(
            stack, base_url, 3
        )
        root_session = _login(
            admin_client, admin_credentials["username"], admin_credentials["password"]
        )
        user = _register(user_client, username, password)
        original_session = _login(user_client, username, password)
        second_session = _login(second_session_client, username, password)
        case_response = _call(
            user_client,
            original_session,
            "POST",
            "/api/cases",
            {"title": "合成无来源 SSE", "document": {"type": "doc", "content": [{"type": "paragraph"}]}},
        )
        assert case_response.status_code == 200, case_response.text
        case_id = case_response.json()["id"]
        thread_response = _call(
            user_client,
            original_session,
            "POST",
            f"/api/cases/{case_id}/agent/threads",
            {"title": "合成无来源流"},
        )
        assert thread_response.status_code == 201, thread_response.text

        repository = AgentRepository(database)
        thread = repository.thread_by_id(thread_response.json()["id"])
        run = repository.start_run(
            thread,
            user["id"],
            [{"type": "text", "text": "合成流输入"}],
            {},
            f"assistant-{uuid.uuid4().hex}",
        )
        database.agent_run_streams.insert_one({
            "_id": run.id,
            "chunks": [{"type": "text-delta", "id": run.assistant_message_id, "delta": first_marker}],
            "sources": [],
        })

        event_path = f"/api/cases/{case_id}/agent/thread/{thread.id}/events"

        def change_account():
            if change == "force_logout":
                return _call(
                    admin_client,
                    root_session,
                    "POST",
                    f"/api/admin/accounts/{user['id']}/force-logout",
                    {"reason": "合成 SSE 前撤销会话"},
                )
            if change == "disable":
                return _call(
                    admin_client,
                    root_session,
                    "POST",
                    f"/api/admin/accounts/{user['id']}/status",
                    {"status": "disabled", "reason": "合成 SSE 前停用"},
                )
            return _call(
                second_session_client,
                second_session,
                "POST",
                "/api/auth/change-password",
                {"currentPassword": password, "newPassword": new_password},
            )

        def append_second_chunk():
            database.agent_run_streams.update_one(
                {"_id": run.id},
                {"$push": {"chunks": {
                    "type": "text-delta",
                    "id": run.assistant_message_id,
                    "delta": second_marker,
                }}},
            )
            database.agent_runs.update_one(
                {"id": run.id}, {"$set": {"status": "completed"}}
            )

        headers = {
            "Cookie": f"{COOKIE_NAME}={original_session['token']}",
            "X-CSRF-Token": original_session["csrf"],
        }
        first_received = Event()
        received: list[str] = []
        stream_status: list[int] = []

        def read_stream():
            with user_client.stream("GET", event_path, headers=headers) as stream:
                stream_status.append(stream.status_code)
                assert stream.status_code == 200, stream.text
                for line in stream.iter_lines():
                    received.append(line)
                    if first_marker in line:
                        first_received.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(read_stream)
            try:
                assert first_received.wait(timeout=15), "客户端未收到 SSE 首段"
                assert not pending.done()
                changed = change_account()
                expected_status = 204 if change == "change_password" else 200
                assert changed.status_code == expected_status, changed.text
                append_second_chunk()
            finally:
                database.agent_runs.update_one(
                    {"id": run.id}, {"$set": {"status": "completed"}}
                )
            pending.result(timeout=30)

        assert stream_status == [200]
        assert first_marker in "\n".join(received)
        assert second_marker not in "\n".join(received)
    assert database.agent_run_streams.find_one({"_id": run.id})["sources"] == []


@pytest.mark.parametrize(
    ("source_type", "change"),
    [
        ("material", "revoke"),
        ("material", "force_logout"),
        ("attachment", "revoke"),
        ("attachment", "force_logout"),
    ],
)
def test_campus_download_stream_stops_after_http_revocation(
    monkeypatch, campus_http_environment, source_type: str, change: str,
) -> None:
    database, new_app, admin_credentials = campus_http_environment
    applicant_name = f"issue360-stream-{uuid.uuid4().hex}"
    applicant_password = f"Issue360-Stream-{uuid.uuid4().hex}!a"
    first_marker = b"issue360-first-download-chunk"
    second_marker = b"issue360-revoked-download-chunk"
    first_chunk = first_marker + b"x" * (1024 * 1024 - len(first_marker))
    payload = first_chunk + second_marker + b"y" * (1024 * 1024)
    blob_id = f"issue360-stream-{uuid.uuid4().hex}"
    entered = Event()
    resume = Event()
    closed = Event()
    response_closed = Event()
    response_released = Event()
    app = new_app()
    store = None
    bucket_created = False

    with _uvicorn_server(app) as base_url, ExitStack() as stack:
        applicant_client, admin_client = _clients(stack, base_url, 2)
        root_session = _login(
            admin_client, admin_credentials["username"], admin_credentials["password"]
        )
        _register(applicant_client, applicant_name, applicant_password)
        applicant_session = _login(
            applicant_client, applicant_name, applicant_password
        )
        application = _call(
            applicant_client,
            applicant_session,
            "POST",
            "/api/auth/campus-access/applications",
            {
                "applicantName": "合成下载测试申请人",
                "studentNumber": f"SYN-360-{uuid.uuid4().hex[:12]}",
            },
        )
        assert application.status_code == 201, application.text
        decision = _call(
            admin_client,
            root_session,
            "POST",
            f"/api/admin/campus-access-applications/{application.json()['id']}/decision",
            {"decision": "approved", "reason": "合成下载流测试批准"},
        )
        assert decision.status_code == 200, decision.text

        store = app.state.blob_store
        bucket_created = store.client.bucket_exists(store.bucket)
        store.put(blob_id, BytesIO(payload), len(payload), "text/plain")
        original_get_object = store.client.get_object

        class TrackedResponse:
            def __init__(self, response):
                self.response = response

            def stream(self, *args, **kwargs):
                return self.response.stream(*args, **kwargs)

            def close(self):
                self.response.close()
                response_closed.set()

            def release_conn(self):
                self.response.release_conn()
                response_released.set()

        def tracked_get_object(*args, **kwargs):
            return TrackedResponse(original_get_object(*args, **kwargs))

        monkeypatch.setattr(store.client, "get_object", tracked_get_object)

        if source_type == "material":
            source_id = f"issue360-material-{uuid.uuid4().hex}"
            database.materials.insert_one({
                "id": source_id,
                "title": "合成校内流素材",
                "accessLevel": "campus",
                "status": "active",
                "blobId": blob_id,
                "createdBy": "issue360-other-owner",
                "filename": "synthetic-stream.txt",
                "mediaType": "text/plain",
                "size": len(payload),
            })
            path = f"/api/materials/{source_id}/content"
        else:
            case_id = f"issue360-case-{uuid.uuid4().hex}"
            version_id = f"issue360-version-{uuid.uuid4().hex}"
            attachment_id = f"issue360-attachment-{uuid.uuid4().hex}"
            database.cases.insert_one({
                "id": case_id,
                "ownerId": "issue360-other-owner",
                "publicationStatus": "public",
                "workflowStatus": "published",
                "publishedVersionId": version_id,
            })
            database.case_versions.insert_one({
                "id": version_id,
                "caseId": case_id,
                "number": 1,
                "kind": "submission",
                "title": "合成公开案例",
                "document": {"type": "doc", "content": []},
                "attachments": [{
                    "id": attachment_id,
                    "caseId": case_id,
                    "name": "合成校内附件.txt",
                    "accessLevel": "campus",
                    "blobId": blob_id,
                    "mediaType": "text/plain",
                    "size": len(payload),
                    "createdAt": datetime.now(UTC).isoformat(),
                }],
            })
            path = f"/api/cases/{case_id}/attachments/{attachment_id}/content"

        original_open = store.open

        def scheduled_open(current_blob_id):
            source = original_open(current_blob_id)

            def chunks():
                try:
                    yield next(source)
                    entered.set()
                    if not resume.wait(timeout=30):
                        raise TimeoutError("下载流测试未收到恢复信号")
                    yield from source
                finally:
                    source.close()
                    closed.set()

            return chunks()

        monkeypatch.setattr(store, "open", scheduled_open)
        response_headers = {
            "Cookie": f"{COOKIE_NAME}={applicant_session['token']}"
        }
        try:
            with applicant_client.stream("GET", path, headers=response_headers) as response:
                assert response.status_code == 200
                chunks = response.iter_raw()
                first = next(chunks)
                assert first_marker in first
                assert entered.wait(timeout=15), "MinIO iterator 未到达分块暂停点"
                assert second_marker not in first
                if change == "revoke":
                    changed = _call(
                        admin_client,
                        root_session,
                        "POST",
                        f"/api/admin/campus-access-applications/{application.json()['id']}/revoke",
                        {"reason": "合成下载过程中撤销资格"},
                    )
                else:
                    changed = _call(
                        admin_client,
                        root_session,
                        "POST",
                        f"/api/admin/accounts/{applicant_session['user']['id']}/force-logout",
                        {"reason": "合成下载过程中撤销会话"},
                    )
                assert changed.status_code == 200, changed.text
                resume.set()
                remainder = b"".join(chunks)
                assert second_marker not in remainder
                assert closed.wait(timeout=10), "撤权后未关闭 MinIO 响应"
                assert response_closed.is_set(), "MinIO get_object response 未关闭"
                assert response_released.is_set(), "MinIO get_object 连接未释放"
        finally:
            resume.set()
            store.remove(blob_id)
            if not bucket_created and store.client.bucket_exists(store.bucket):
                store.client.remove_bucket(store.bucket)


@pytest.mark.parametrize("source_type", ["public_material", "owner_attachment"])
def test_public_download_and_attachment_owner_remain_accessible(
    campus_http_environment, source_type: str,
) -> None:
    database, new_app, _admin_credentials = campus_http_environment
    app = new_app()
    marker = f"issue360-allowed-download-{uuid.uuid4().hex}".encode()
    blob_id = f"issue360-allowed-download-{uuid.uuid4().hex}"

    with _uvicorn_server(app) as base_url, ExitStack() as stack:
        client = _clients(stack, base_url, 1)[0]
        store = app.state.blob_store
        bucket_created = store.client.bucket_exists(store.bucket)
        payload = marker + b" synthetic public or owner content"
        store.put(blob_id, BytesIO(payload), len(payload), "text/plain")
        try:
            if source_type == "public_material":
                source_id = f"issue360-public-material-{uuid.uuid4().hex}"
                database.materials.insert_one({
                    "id": source_id,
                    "title": "合成公开下载素材",
                    "accessLevel": "public",
                    "status": "active",
                    "blobId": blob_id,
                    "createdBy": "issue360-public-owner",
                    "filename": "synthetic-public.txt",
                    "mediaType": "text/plain",
                    "size": len(payload),
                })
                response = client.get(f"/api/materials/{source_id}/content")
            else:
                username = f"issue360-owner-{uuid.uuid4().hex}"
                password = f"Issue360-Owner-{uuid.uuid4().hex}!a"
                account = _register(client, username, password)
                owner_session = _login(client, username, password)
                case_id = f"issue360-owner-case-{uuid.uuid4().hex}"
                attachment_id = f"issue360-owner-attachment-{uuid.uuid4().hex}"
                database.cases.insert_one({
                    "id": case_id,
                    "ownerId": account["id"],
                    "publicationStatus": "private",
                    "workflowStatus": "draft",
                })
                database.attachments.insert_one({
                    "id": attachment_id,
                    "caseId": case_id,
                    "name": "合成作者私人附件.txt",
                    "accessLevel": "private",
                    "blobId": blob_id,
                    "mediaType": "text/plain",
                    "size": len(payload),
                    "searchText": "合成作者私人附件",
                    "createdAt": datetime.now(UTC),
                })
                response = client.get(
                    f"/api/cases/{case_id}/attachments/{attachment_id}/content",
                    headers={"Cookie": f"{COOKIE_NAME}={owner_session['token']}"},
                )
            assert response.status_code == 200, response.text
            assert marker in response.content
        finally:
            store.remove(blob_id)
            if not bucket_created and store.client.bucket_exists(store.bucket):
                store.client.remove_bucket(store.bucket)


@pytest.mark.parametrize(
    ("result_access", "change", "cursor_mode"),
    [
        ("campus", "revoke", None),
        ("campus", "force_logout", None),
        ("public", None, None),
        (None, None, None),
        ("public", None, "basic-page-two"),
        ("public", None, "campus-page-two"),
    ],
)
def test_search_summary_rechecks_current_session_and_search_results(
    campus_http_environment,
    result_access: str | None,
    change: str | None,
    cursor_mode: str | None,
) -> None:
    import meilisearch

    database, new_app, admin_credentials = campus_http_environment
    app = new_app()
    query = f"issue360-summary-{uuid.uuid4().hex}"
    first_marker = f"issue360-summary-first-{uuid.uuid4().hex}"
    second_marker = f"issue360-summary-second-{uuid.uuid4().hex}"
    model_resumed = Event()
    first_chunk_sent = Event()
    prompt_messages: list[str] = []
    meili_key_file = os.environ["MEILI_CONTRACT_KEY_FILE"]
    meili_admin = meilisearch.Client(
        os.environ["MEILI_CONTRACT_URL"],
        open(meili_key_file, encoding="utf-8").read().strip(),
    )
    index_uid = f"issue360-summary-{uuid.uuid4().hex}"
    generation = f"issue360-summary-generation-{uuid.uuid4().hex}"
    index_created = False

    async def stream_model(messages, _info):
        prompt_messages.append(str(messages))
        yield first_marker
        first_chunk_sent.set()
        if not await asyncio.to_thread(model_resumed.wait, 30):
            raise TimeoutError("摘要事件调度未收到恢复信号")
        yield second_marker

    app.state.agent = Agent(
        model=FunctionModel(stream_function=stream_model),
        output_type=str,
        name="issue360-summary-stream-scheduler",
    )
    wait_task(
        meili_admin,
        meili_admin.create_index(index_uid, {"primaryKey": "catalogId"}),
    )
    index_created = True
    index = meili_admin.index(index_uid)
    wait_task(meili_admin, index.update_settings(catalog_settings()))
    documents = [{
        "catalogId": "catalog-meta",
        "docClass": "catalog-meta",
        "generation": generation,
        "projectionVersion": PROJECTION_VERSION,
    }]
    material_id = f"issue360-summary-material-{uuid.uuid4().hex}"
    materials = []
    material_count = 22 if cursor_mode else 1
    if result_access:
        for position in range(material_count):
            material_id = f"issue360-summary-material-{uuid.uuid4().hex}"
            material = {
                "id": material_id,
                "title": f"{query} 合成条目 {position:02d}",
                "summary": f"合成摘要内容 {uuid.uuid4().hex}",
                "accessLevel": "public" if cursor_mode else result_access,
                "status": "active",
                "createdBy": "issue360-summary-owner",
                "publicReferenceCount": 1,
                "publishedAt": "2026-10-08",
                "tags": [],
                "materialType": "文档",
                "authority": "original",
            }
            materials.append(material)
            database.materials.insert_one(material)
            documents.extend(project_catalog_documents("material", material))
    wait_task(meili_admin, index.add_documents(documents))
    epoch = index_epoch(meili_admin, index_uid)
    database.search_catalog_generation.update_one(
        {"_id": "catalog"},
        {"$set": {
            "generation": generation,
            "indexUid": index_uid,
            "indexEpoch": epoch,
            "projectionVersion": PROJECTION_VERSION,
            "retiredIndexUids": [],
        }},
        upsert=True,
    )
    database.search_control.update_one(
        {"_id": "catalog"}, {"$set": {"sequence": 0}}, upsert=True
    )
    database.search_worker_state.update_one(
        {"_id": "catalog"},
        {"$set": {
            "worker": "issue360-summary-e2e",
            "updatedAt": datetime.now(UTC),
            "status": "healthy",
            "indexUid": index_uid,
            "indexEpoch": epoch,
        }},
        upsert=True,
    )

    try:
        with _uvicorn_server(app) as base_url, ExitStack() as stack:
            applicant_client, admin_client = _clients(stack, base_url, 2)
            root_session = _login(
                admin_client,
                admin_credentials["username"],
                admin_credentials["password"],
            )
            applicant_name = f"issue360-summary-user-{uuid.uuid4().hex}"
            applicant_password = f"Issue360-Summary-{uuid.uuid4().hex}!a"
            _register(applicant_client, applicant_name, applicant_password)
            applicant_session = _login(
                applicant_client, applicant_name, applicant_password
            )
            application = None
            if result_access == "campus" or cursor_mode == "campus-page-two":
                application = _call(
                    applicant_client,
                    applicant_session,
                    "POST",
                    "/api/auth/campus-access/applications",
                    {
                        "applicantName": "合成摘要申请人",
                        "studentNumber": f"SYN-360-{uuid.uuid4().hex[:12]}",
                    },
                )
                assert application.status_code == 201, application.text
                approved = _call(
                    admin_client,
                    root_session,
                    "POST",
                    f"/api/admin/campus-access-applications/{application.json()['id']}/decision",
                    {"decision": "approved", "reason": "合成摘要测试批准"},
                )
                assert approved.status_code == 200, approved.text

            cursor = None
            page_summary_candidates: list[str] = []
            if cursor_mode:
                first_page = applicant_client.get(
                    "/api/search",
                    params={"q": query, "kind": "material", "pageSize": 20},
                    headers={"Cookie": f"{COOKIE_NAME}={applicant_session['token']}"},
                )
                assert first_page.status_code == 200, first_page.text
                cursor = first_page.json()["nextCursor"]
                assert cursor, "真实检索未返回下一页游标"
                second_page = applicant_client.get(
                    "/api/search",
                    params={
                        "q": query,
                        "kind": "material",
                        "pageSize": 20,
                        "cursor": cursor,
                    },
                    headers={"Cookie": f"{COOKIE_NAME}={applicant_session['token']}"},
                )
                assert second_page.status_code == 200, second_page.text
                assert second_page.json()["page"] == 2
                assert "campusDependency" not in second_page.json()["items"][0]
                page_ids = {
                    item["id"] for item in second_page.json()["items"]
                }
                page_summary_candidates = [
                    material["summary"]
                    for material in materials
                    if material["id"] in page_ids
                ]
                assert page_summary_candidates

            payload = {
                "id": f"issue360-summary-chat-{uuid.uuid4().hex}",
                "trigger": "submit-message",
                "messages": [{
                    "id": f"issue360-summary-message-{uuid.uuid4().hex}",
                    "role": "user",
                    "parts": [{"type": "text", "text": query}],
                }],
                "query": query,
                "search": {
                    "q": query,
                    "kind": "material",
                    **({"cursor": cursor, "pageSize": 20} if cursor else {}),
                },
            }
            headers = {
                "Cookie": f"{COOKIE_NAME}={applicant_session['token']}",
                "X-CSRF-Token": applicant_session["csrf"],
            }
            received: list[str] = []
            with applicant_client.stream(
                "POST", "/api/search/summary", headers=headers, json=payload
            ) as response:
                assert response.status_code == 200, response.read().decode(errors="replace")
                lines = response.iter_lines()
                for line in lines:
                    received.append(line)
                    if first_marker in line:
                        break
                else:
                    raise AssertionError("摘要流未输出首个合成事件")
                assert first_chunk_sent.wait(timeout=10)
                assert first_marker in "\n".join(received)
                expected_summaries = (
                    page_summary_candidates if cursor_mode else [
                        material["summary"] for material in materials
                    ]
                )
                if expected_summaries:
                    assert any(
                        summary in prompt_messages[0]
                        for summary in expected_summaries
                    )

                if change == "revoke":
                    revoked = _call(
                        admin_client,
                        root_session,
                        "POST",
                        f"/api/admin/campus-access-applications/{application.json()['id']}/revoke",
                        {"reason": "合成摘要期间撤销资格"},
                    )
                    assert revoked.status_code == 200, revoked.text
                elif change == "force_logout":
                    forced = _call(
                        admin_client,
                        root_session,
                        "POST",
                        f"/api/admin/accounts/{applicant_session['user']['id']}/force-logout",
                        {"reason": "合成摘要期间撤销会话"},
                    )
                    assert forced.status_code == 200, forced.text

                model_resumed.set()
                received.extend(lines)
            output = "\n".join(received)
            if change:
                assert second_marker not in output
            else:
                assert second_marker in output
    finally:
        model_resumed.set()
        if index_created:
            wait_task(meili_admin, meili_admin.delete_index(index_uid))


def test_case_summary_tracks_exact_campus_dependencies_across_pages(
    campus_http_environment,
) -> None:
    import meilisearch

    database, new_app, admin_credentials = campus_http_environment
    app = new_app()
    query = f"issue360-case-summary-{uuid.uuid4().hex}"
    meili_key_file = os.environ["MEILI_CONTRACT_KEY_FILE"]
    meili_admin = meilisearch.Client(
        os.environ["MEILI_CONTRACT_URL"], _read_secret(meili_key_file)
    )
    index_uid = f"issue360-case-summary-{uuid.uuid4().hex}"
    generation = f"issue360-case-summary-generation-{uuid.uuid4().hex}"
    index_created = False
    wait_events = [Event(), Event()]
    started_events = [Event(), Event()]
    first_markers = [
        f"issue360-case-summary-first-{uuid.uuid4().hex}",
        f"issue360-case-summary-page-two-first-{uuid.uuid4().hex}",
    ]
    second_markers = [
        f"issue360-case-summary-second-{uuid.uuid4().hex}",
        f"issue360-case-summary-page-two-second-{uuid.uuid4().hex}",
    ]
    prompts: list[str] = []
    campus_case_ids: set[str] = set()

    async def stream_model(messages, _info):
        call_index = len(prompts)
        prompts.append(str(messages))
        yield first_markers[call_index]
        started_events[call_index].set()
        if not await asyncio.to_thread(wait_events[call_index].wait, 30):
            raise TimeoutError("案例摘要事件调度未收到恢复信号")
        yield second_markers[call_index]

    app.state.agent = Agent(
        model=FunctionModel(stream_function=stream_model),
        output_type=str,
        name="issue360-case-summary-scheduler",
    )
    wait_task(
        meili_admin,
        meili_admin.create_index(index_uid, {"primaryKey": "catalogId"}),
    )
    index_created = True
    index = meili_admin.index(index_uid)
    wait_task(meili_admin, index.update_settings(catalog_settings()))
    documents = [{
        "catalogId": "catalog-meta",
        "docClass": "catalog-meta",
        "generation": generation,
        "projectionVersion": PROJECTION_VERSION,
    }]
    expected_public_ids = set()
    for position in range(12):
        case_id = f"issue360-campus-case-{uuid.uuid4().hex}"
        campus_case_ids.add(case_id)
        version_id = f"issue360-campus-case-version-{uuid.uuid4().hex}"
        database.cases.insert_one({
            "id": case_id,
            "ownerId": f"issue360-case-owner-{position}",
            "publicationStatus": "public",
            "workflowStatus": "published",
            "publishedVersionId": version_id,
            "publishedAt": "2026-10-09",
        })
        version = {
            "id": version_id,
            "caseId": case_id,
            "number": 1,
            "kind": "submission",
            "title": f"zz synthetic case {position:02d}",
            "summary": "合成公开案例摘要",
            "metadata": {},
            "document": {"type": "doc", "content": []},
            "attachments": [{
                "id": f"issue360-campus-attachment-{uuid.uuid4().hex}",
                "name": "合成校内索引词.txt",
                "accessLevel": "campus",
                "searchText": query,
            }],
        }
        database.case_versions.insert_one(version)
        documents.extend(project_catalog_documents(
            "case",
            version,
            {"ownerId": f"issue360-case-owner-{position}", "publishedAt": "2026-10-09"},
        ))

    for position in range(24):
        case_id = f"issue360-public-case-{uuid.uuid4().hex}"
        version_id = f"issue360-public-case-version-{uuid.uuid4().hex}"
        expected_public_ids.add(case_id)
        owner_id = f"issue360-public-case-owner-{position}"
        database.cases.insert_one({
            "id": case_id,
            "ownerId": owner_id,
            "publicationStatus": "public",
            "workflowStatus": "published",
            "publishedVersionId": version_id,
            "publishedAt": "2026-10-08",
        })
        version = {
            "id": version_id,
            "caseId": case_id,
            "number": 1,
            "kind": "submission",
            "title": f"zz synthetic case {position:02d}",
            "summary": "合成公开案例摘要",
            "metadata": {},
            "document": {
                "type": "doc",
                "content": [{
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": f"合成校内索引词.txt {query}",
                    }],
                }],
            },
            "attachments": [],
        }
        database.case_versions.insert_one(version)
        documents.extend(project_catalog_documents(
            "case", version, {"ownerId": owner_id, "publishedAt": "2026-10-08"}
        ))

    wait_task(meili_admin, index.add_documents(documents))

    def publish_catalog_health() -> None:
        current_epoch = index_epoch(meili_admin, index_uid)
        database.search_catalog_generation.update_one(
            {"_id": "catalog"},
            {"$set": {
                "generation": generation,
                "indexUid": index_uid,
                "indexEpoch": current_epoch,
                "projectionVersion": PROJECTION_VERSION,
                "retiredIndexUids": [],
            }, "$unset": {"stale": "", "rebuild": ""}},
            upsert=True,
        )
        database.search_control.update_one(
            {"_id": "catalog"}, {"$setOnInsert": {"sequence": 0}}, upsert=True
        )
        database.search_worker_state.update_one(
            {"_id": "catalog"},
            {"$set": {
                "worker": "issue360-case-summary-e2e",
                "updatedAt": datetime.now(UTC),
                "status": "healthy",
                "indexUid": index_uid,
                "indexEpoch": current_epoch,
            }},
            upsert=True,
        )

    try:
        with _uvicorn_server(app) as base_url, ExitStack() as stack:
            publish_catalog_health()
            applicant_client, admin_client = _clients(stack, base_url, 2)
            root_session = _login(
                admin_client,
                admin_credentials["username"],
                admin_credentials["password"],
            )
            username = f"issue360-case-summary-user-{uuid.uuid4().hex}"
            password = f"Issue360-Case-Summary-{uuid.uuid4().hex}!a"
            _register(applicant_client, username, password)
            user_session = _login(applicant_client, username, password)

            def summarize(
                cursor: str | None,
                marker_index: int,
                page_size: int | None = None,
                revoke_after_first_event: bool = False,
            ) -> None:
                publish_catalog_health()
                search = {"q": query, "kind": "case"}
                if cursor:
                    search.update({"cursor": cursor, "pageSize": page_size or 20})
                payload = {
                    "id": f"issue360-case-summary-chat-{uuid.uuid4().hex}",
                    "trigger": "submit-message",
                    "messages": [{
                        "id": f"issue360-case-summary-message-{uuid.uuid4().hex}",
                        "role": "user",
                        "parts": [{"type": "text", "text": query}],
                    }],
                    "query": query,
                    "search": search,
                }
                headers = {
                    "Cookie": f"{COOKIE_NAME}={user_session['token']}",
                    "X-CSRF-Token": user_session["csrf"],
                }
                received = []
                with applicant_client.stream(
                    "POST", "/api/search/summary", headers=headers, json=payload
                ) as response:
                    assert response.status_code == 200, response.read().decode(errors="replace")
                    lines = response.iter_lines()
                    for line in lines:
                        received.append(line)
                        if first_markers[marker_index] in line:
                            break
                    else:
                        raise AssertionError("案例摘要流未输出首个合成事件")
                    assert started_events[marker_index].wait(timeout=10)
                    if revoke_after_first_event:
                        revoked = _call(
                            admin_client,
                            root_session,
                            "POST",
                            f"/api/admin/campus-access-applications/{application_id}/revoke",
                            {"reason": "合成公开案例摘要期间撤销资格"},
                        )
                        assert revoked.status_code == 200, revoked.text
                    wait_events[marker_index].set()
                    received.extend(lines)
                assert second_markers[marker_index] in "\n".join(received)

            publish_catalog_health()
            basic_page = applicant_client.get(
                "/api/search",
                params={"q": query, "kind": "case", "pageSize": 100},
                headers={"Cookie": f"{COOKIE_NAME}={user_session['token']}"},
            )
            assert basic_page.status_code == 200, basic_page.text
            assert basic_page.json()["items"]
            assert all(item["id"] in expected_public_ids for item in basic_page.json()["items"])
            basic_ids = [item["id"] for item in basic_page.json()["items"]]
            assert len(basic_ids) == len(expected_public_ids)
            basic_ranks = {case_id: rank for rank, case_id in enumerate(basic_ids)}
            summarize(None, 0)

            application = _call(
                applicant_client,
                user_session,
                "POST",
                "/api/auth/campus-access/applications",
                {
                    "applicantName": "合成案例摘要申请人",
                    "studentNumber": f"SYN-360-{uuid.uuid4().hex[:12]}",
                },
            )
            assert application.status_code == 201, application.text
            approved = _call(
                admin_client,
                root_session,
                "POST",
                f"/api/admin/campus-access-applications/{application.json()['id']}/decision",
                {"decision": "approved", "reason": "合成案例分页摘要测试批准"},
            )
            assert approved.status_code == 200, approved.text
            application_id = application.json()["id"]

            cursor = None
            observed_campus = False
            selected_cursor = None
            observed_order = []
            for position in range(len(campus_case_ids) + len(expected_public_ids)):
                publish_catalog_health()
                params = {"q": query, "kind": "case", "pageSize": 1}
                if cursor:
                    params["cursor"] = cursor
                page = applicant_client.get(
                    "/api/search",
                    params=params,
                    headers={"Cookie": f"{COOKIE_NAME}={user_session['token']}"},
                )
                assert page.status_code == 200, page.text
                page_items = page.json()["items"]
                if not page_items:
                    break
                item_id = page_items[0]["id"]
                if item_id in campus_case_ids:
                    observed_campus = True
                    observed_order.append("campus")
                elif item_id in expected_public_ids:
                    observed_order.append("public")
                else:
                    observed_order.append("other")
                if item_id in expected_public_ids and basic_ranks[item_id] != position:
                    selected_cursor = cursor
                    break
                cursor = page.json()["nextCursor"]
                if not cursor:
                    break
            assert observed_campus, "获批检索未命中合成校内案例"
            assert selected_cursor, f"未找到因校内命中产生位移的公开案例页: {observed_order}"
            summarize(selected_cursor, 1, page_size=1, revoke_after_first_event=True)
            assert len(prompts) == 2
    finally:
        wait_events[0].set()
        wait_events[1].set()
        if index_created:
            wait_task(meili_admin, meili_admin.delete_index(index_uid))
