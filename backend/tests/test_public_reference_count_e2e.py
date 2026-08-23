from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def login(username: str, password: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return client, response.json()["csrfToken"]


def create_material(database) -> dict:
    token = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    material = {
        "id": f"m-reference-{token}",
        "title": f"公开引用计数-{token}",
        "summary": "校内素材引用计数端到端验证",
        "source": "上海大学",
        "tags": ["引用计数"],
        "materialType": "政策文件",
        "authority": "original",
        "accessLevel": "campus",
        "status": "active",
        "createdBy": "u-admin-demo",
        "createdAt": now,
        "publishedAt": now,
        "publicReferenceCount": 0,
    }
    database.materials.insert_one(material)
    return material


def transition(client, csrf: str, case: dict, command: str, **extra) -> httpx.Response:
    return client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": csrf},
        json={"command": command, "revision": case["revision"], **extra},
    )


def transition_ok(client, csrf: str, case: dict, command: str, **extra) -> dict:
    response = transition(client, csrf, case, command, **extra)
    assert response.status_code == 200
    return response.json()


def create_mounted_case(client, csrf: str, material: dict) -> dict:
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": csrf},
        json={"title": f"引用 {material['title']}"},
    )
    assert created.status_code == 200
    case = created.json()
    mounted = client.post(
        f"/api/cases/{case['id']}/materials",
        headers={"X-CSRF-Token": csrf},
        json={"materialId": material["id"], "revision": case["revision"]},
    )
    assert mounted.status_code == 201
    return client.get(f"/api/cases/{case['id']}").json()


def publish(client, csrf: str, admin, admin_csrf: str, material: dict) -> dict:
    case = create_mounted_case(client, csrf, material)
    submitted = transition_ok(client, csrf, case, "submit")
    started = transition_ok(admin, admin_csrf, submitted["case"], "start")
    return transition_ok(
        admin,
        admin_csrf,
        started["case"],
        "approve",
        submittedVersionId=submitted["version"]["id"],
    )["case"]


def hide_response(task) -> httpx.Response:
    client, csrf, case = task
    return transition(client, csrf, case, "hide")


def hide_concurrently(admin, csrf: str, case: dict) -> dict:
    second, second_csrf = login("admin", "admin123")
    tasks = ((admin, csrf, case), (second, second_csrf, case))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(hide_response, tasks))
    assert sorted(response.status_code for response in responses) == [200, 409]
    second.close()
    return admin.get(f"/api/cases/{case['id']}").json()


def search_material(material: dict) -> httpx.Response:
    return httpx.get(
        f"{BASE_URL}/api/search",
        params={"q": material["title"], "kind": "material", "pageSize": 20},
    )


def search_result(response: httpx.Response, material: dict) -> dict | None:
    assert response.status_code == 200
    return next(
        (row for row in response.json()["items"] if row["id"] == material["id"]), None
    )


def await_search_state(material: dict, visible: bool) -> dict | None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = search_material(material)
        if response.status_code == 503:
            time.sleep(0.1)
            continue
        result = search_result(response, material)
        if (result is not None) is visible:
            return result
        time.sleep(0.1)
    pytest.fail("检索目录未在 10 秒内收敛")


def assert_state(database, material: dict, count: int, visible: bool) -> None:
    stored = database.materials.find_one({"id": material["id"]})
    assert stored["publicReferenceCount"] == count
    result = await_search_state(material, visible)
    assert (result is not None) is visible
    if result:
        assert result["contentAvailable"] is False
        assert "summary" not in result


def exercise_reference_lifecycle(database, material: dict) -> None:
    author, author_csrf = login("user", "user123")
    admin, admin_csrf = login("admin", "admin123")
    first = publish(author, author_csrf, admin, admin_csrf, material)
    second = publish(author, author_csrf, admin, admin_csrf, material)
    assert_state(database, material, 2, True)
    first = hide_concurrently(admin, admin_csrf, first)
    assert_state(database, material, 1, True)
    second = transition_ok(admin, admin_csrf, second, "hide")["case"]
    assert_state(database, material, 0, False)
    transition_ok(admin, admin_csrf, first, "restore")
    assert_state(database, material, 1, True)
    author.close()
    admin.close()


def test_shared_material_visibility_tracks_public_case_references() -> None:
    mongo = MongoClient(MONGO_URI)
    try:
        database = mongo.get_default_database()
        exercise_reference_lifecycle(database, create_material(database))
    finally:
        mongo.close()
