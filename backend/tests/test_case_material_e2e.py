from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL")


def login(username: str, password: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return client, response.json()["csrfToken"]


def create_case(client, csrf: str) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": csrf},
        json={"title": f"素材关系 {uuid.uuid4().hex}"},
    )
    assert response.status_code == 200
    return response.json()


def mount(client, csrf: str, case: dict, material_id: str) -> httpx.Response:
    return client.post(
        f"/api/cases/{case['id']}/materials",
        headers={"X-CSRF-Token": csrf},
        json={"materialId": material_id, "revision": case["revision"]},
    )


def current(client, case_id: str) -> dict:
    return client.get(f"/api/cases/{case_id}").json()


def transition(client, csrf: str, case: dict, command: str, **extra) -> dict:
    response = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": csrf},
        json={"command": command, "revision": case["revision"], **extra},
    )
    assert response.status_code == 200
    return response.json()


def remove(client, csrf: str, case: dict, material_id: str) -> None:
    response = client.delete(
        f"/api/cases/{case['id']}/materials/{material_id}",
        headers={"X-CSRF-Token": csrf},
        params={"revision": case["revision"]},
    )
    assert response.status_code == 204


def publish(author, csrf: str, case: dict) -> dict:
    submitted = transition(author, csrf, case, "submit")
    admin, admin_csrf = login("admin", "admin123")
    started = transition(admin, admin_csrf, submitted["case"], "start")
    return transition(
        admin,
        admin_csrf,
        started["case"],
        "approve",
        submittedVersionId=submitted["version"]["id"],
    )


def ids(response: httpx.Response) -> set[str]:
    assert response.status_code == 200
    return {row["id"] for row in response.json()}


def views(response: httpx.Response) -> dict[str, dict]:
    assert response.status_code == 200
    return {row["id"]: row for row in response.json()}


def assert_public_permissions(response: httpx.Response) -> None:
    public = views(response)
    assert set(public) == {"m-kcsz", "m-zrjs"}
    assert public["m-kcsz"]["contentAvailable"] is True
    restricted = public["m-zrjs"]
    assert set(restricted) == {
        "id",
        "title",
        "accessLevel",
        "contentAvailable",
        "hasFile",
    }
    assert restricted["accessLevel"] == "campus"
    assert restricted["contentAvailable"] is False
    assert restricted["hasFile"] is False


def test_material_snapshot_rollback_and_public_permissions() -> None:
    author, csrf = login("user", "user123")
    case = create_case(author, csrf)
    assert mount(author, csrf, case, "m-kcsz").status_code == 201
    case = current(author, case["id"])
    assert mount(author, csrf, case, "m-zrjs").status_code == 201
    case = current(author, case["id"])
    snapshot = transition(author, csrf, case, "snapshot")
    remove(author, csrf, snapshot["case"], "m-kcsz")
    case = current(author, case["id"])
    rolled = transition(
        author, csrf, case, "rollback", targetId=snapshot["snapshot"]["id"]
    )
    published = publish(author, csrf, rolled["case"])
    path = f"/api/cases/{case['id']}/materials"
    assert_public_permissions(httpx.get(f"{BASE_URL}{path}"))
    assert ids(author.get(path)) == {"m-kcsz", "m-zrjs"}
    assert published["case"]["publicationStatus"] == "public"


def test_concurrent_material_mount_has_one_revision_winner() -> None:
    first, csrf = login("user", "user123")
    second, second_csrf = login("user", "user123")
    case = create_case(first, csrf)
    tasks = ((first, csrf, "m-kcsz"), (second, second_csrf, "m-kxjsh"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = pool.map(lambda task: mount(task[0], task[1], case, task[2]), tasks)
    assert sorted(response.status_code for response in responses) == [201, 409]
