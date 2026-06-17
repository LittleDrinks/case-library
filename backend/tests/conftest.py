from __future__ import annotations

import os

import pytest
from pymongo import TEXT

SAFE_TEST_DB_PREFIXES = (
    "case_library_test_",
    "case_library_prompt_inj_",
    "case_library_security_unit_",
)
MONGO_CLEANUP_MODULES = {
    "backend.tests.integration.test_submit_flow",
    "backend.tests.unit.test_ai_review_service",
    "backend.tests.unit.test_database_repository_helpers",
    "backend.tests.unit.test_prompt_injection",
    "backend.tests.unit.test_public_search_helpers",
    "backend.tests.unit.test_security_dependencies",
}
CONTRACT_HELPER_TESTS = {
    "assert_paragraph_contracts",
    "assert_public_serialization_uses_review_snapshot",
    "assert_structured_ai_review_contract",
}


def _is_safe_test_db_name(db_name: str | None) -> bool:
    if not db_name:
        return False
    return any(
        db_name.startswith(prefix) and len(db_name) > len(prefix)
        for prefix in SAFE_TEST_DB_PREFIXES
    )


def pytest_pycollect_makeitem(collector, name, obj):
    module_name = getattr(getattr(collector, "module", None), "__name__", "")
    if module_name == "backend.tests.unit.test_contract_helpers" and name in CONTRACT_HELPER_TESTS:
        return pytest.Function.from_parent(collector, name=name, callobj=obj)
    return None


@pytest.fixture(autouse=True)
def clean_active_mongo_database(monkeypatch, request):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:18080,http://localhost:18080",
    )

    module_name = getattr(request.module, "__name__", "")
    configured_db_name = os.environ.get("MONGODB_DB_NAME")
    if module_name not in MONGO_CLEANUP_MODULES:
        yield
        return

    if not _is_safe_test_db_name(configured_db_name):
        raise RuntimeError(
            f"{module_name} must set MONGODB_DB_NAME to a safe test database prefix"
        )

    from backend.db.connection import get_db, get_mongo_client

    db_name = get_db().name
    if not _is_safe_test_db_name(db_name):
        raise RuntimeError(f"Refusing to clean unsafe MongoDB database: {db_name!r}")

    get_mongo_client().drop_database(db_name)
    get_db().cases.create_index(
        [("title", TEXT), ("content", TEXT), ("source_material", TEXT), ("keywords", TEXT)],
        name="cases_text_idx",
        default_language="none",
    )

    yield

    get_mongo_client().drop_database(db_name)
