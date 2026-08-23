from __future__ import annotations

import os
from time import perf_counter
from typing import Callable

import httpx
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")
COLLECTIONS = (
    "sessions",
    "users",
    "cases",
    "search_catalog_generation",
    "search_control",
    "search_catalog_state",
    "search_worker_state",
    "search_outbox",
    "search_revocations",
)
PROFILE_APP_NAME = "e2e-app"
MEASURE_ATTEMPTS = 3


def _database():
    client = MongoClient(MONGO_URI)
    return client, client.get_default_database()


def _start_profile(database) -> None:
    database.command("profile", 0)
    database["system.profile"].drop()
    namespaces = [f"{database.name}.{name}" for name in COLLECTIONS]
    database.command("profile", 2, filter={"ns": {"$in": namespaces}})


def _profile_counts(database) -> tuple[dict[str, int], float, tuple[str, ...]]:
    database.command("profile", 0)
    namespaces = [f"{database.name}.{name}" for name in COLLECTIONS]
    rows = list(
        database["system.profile"].find(
            {
                "ns": {"$in": namespaces},
                "appName": PROFILE_APP_NAME,
            }
        )
    )
    counts = {name: 0 for name in COLLECTIONS}
    for row in rows:
        counts[row["ns"].rsplit(".", 1)[-1]] += 1
    catalog_rows = [
        row for row in rows if row["ns"].endswith(".search_catalog_generation")
    ]
    concerns = tuple(row["command"]["readConcern"]["level"] for row in catalog_rows)
    return counts, sum(row.get("millis", 0) for row in rows), concerns


def _measure(
    database, request: Callable[[], httpx.Response]
) -> tuple[dict, httpx.Response]:
    _start_profile(database)
    started = perf_counter()
    response = request()
    wall_ms = (perf_counter() - started) * 1000
    counts, mongo_ms, concerns = _profile_counts(database)
    assert response.status_code == 200
    metrics = {
        "mongoOps": counts,
        "wallMs": round(wall_ms, 2),
        "mongoMs": mongo_ms,
        "catalogReadConcerns": concerns,
    }
    return metrics, response


def _best_measure(
    database, request: Callable[[], httpx.Response]
) -> tuple[dict, httpx.Response]:
    samples = (_measure(database, request) for _ in range(MEASURE_ATTEMPTS))
    return min(samples, key=lambda sample: sum(sample[0]["mongoOps"].values()))


def _login(client: httpx.Client) -> httpx.Response:
    return client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )


def _collect(database, client: httpx.Client) -> dict:
    return {
        "login": _best_measure(database, lambda: _login(client))[0],
        "session": _best_measure(database, lambda: client.get("/api/auth/session"))[0],
        "case": _best_measure(database, lambda: client.get("/api/cases/c-draft-1"))[0],
    }


def _expected(**counts: int) -> dict[str, int]:
    return {name: counts.get(name, 0) for name in COLLECTIONS}


def _search_reads(database, client: httpx.Client) -> dict:
    first, response = _best_measure(
        database,
        lambda: client.get("/api/search?kind=material&pageSize=1"),
    )
    cursor = response.json()["nextCursor"]
    assert cursor
    second, _response = _best_measure(
        database,
        lambda: client.get(
            "/api/search",
            params={
                "kind": "material",
                "pageSize": 1,
                "cursor": cursor,
            },
        ),
    )
    return {"searchFirst": first, "searchCursor": second}


def test_authenticated_reads_stay_within_the_mongo_query_budget() -> None:
    mongo, database = _database()
    try:
        with httpx.Client(base_url=BASE_URL) as client:
            observed = _collect(database, client)
    finally:
        database.command("profile", 0)
        mongo.close()
    print(observed)
    expected_login = _expected(sessions=1, users=1)
    expected_session = _expected(sessions=1, users=1)
    expected_case = _expected(sessions=1, users=1, cases=1)
    assert observed["login"]["mongoOps"] == expected_login
    assert observed["session"]["mongoOps"] == expected_session
    assert observed["case"]["mongoOps"] == expected_case


def test_search_reads_use_two_catalog_snapshots() -> None:
    mongo, database = _database()
    try:
        with httpx.Client(base_url=BASE_URL) as client:
            assert _login(client).status_code == 200
            observed = _search_reads(database, client)
    finally:
        database.command("profile", 0)
        mongo.close()
    print(observed)
    expected = _expected(sessions=1, users=1, search_catalog_generation=2)
    assert observed["searchFirst"]["mongoOps"] == expected
    assert observed["searchCursor"]["mongoOps"] == expected
    assert observed["searchFirst"]["catalogReadConcerns"] == ("snapshot", "snapshot")
    assert observed["searchCursor"]["catalogReadConcerns"] == ("snapshot", "snapshot")
