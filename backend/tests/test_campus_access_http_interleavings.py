from __future__ import annotations

import os
import socket
import uuid
from contextlib import ExitStack, contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event, Thread

import httpx
import pytest
import uvicorn
from pymongo import MongoClient

from app.core.config import Settings
from app.main import create_app
from app.modules.agent.repository import AgentRepository
from app.modules.attachments.storage import minio_blob_store
from app.modules.auth.admin_bootstrap import bootstrap_admin
from app.modules.auth.management_service import AccountManagementService
from app.modules.auth.sessions import COOKIE_NAME
from app.modules.search.client import create_reader
from app.modules.search.meilisearch import MeilisearchCatalog
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
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on")
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
    monkeypatch, campus_http_environment, change: str,
) -> None:
    from app.modules.agent import routes as agent_routes

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

        pause = _RequestPause()
        original_factory = agent_routes._event_access_check

        def pause_after_first_sse_chunk(database, user, conversation, thread):
            access_check = original_factory(database, user, conversation, thread)
            checks = 0

            def scheduled_check():
                nonlocal checks
                checks += 1
                if checks == 2:
                    pause.wait()
                return access_check()

            return scheduled_check

        monkeypatch.setattr(agent_routes, "_event_access_check", pause_after_first_sse_chunk)
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
                assert pause.entered.wait(timeout=15), (
                    "SSE 未在客户端收到首段后进入调度点"
                )
                assert not pending.done()
                changed = change_account()
                expected_status = 204 if change == "change_password" else 200
                assert changed.status_code == expected_status, changed.text
                append_second_chunk()
            finally:
                database.agent_runs.update_one(
                    {"id": run.id}, {"$set": {"status": "completed"}}
                )
                pause.resume.set()
            pending.result(timeout=30)

        assert stream_status == [200]
        assert first_marker in "\n".join(received)
        assert second_marker not in "\n".join(received)
    assert database.agent_run_streams.find_one({"_id": run.id})["sources"] == []
