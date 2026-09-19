"""中文 Gherkin 业务验收夹具：复用既有确定性测试基座（mongomock + TestClient）。"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (  # noqa: F401  复用既有夹具组件
    MemoryBlobStore,
    EmptySearchCatalog,
    ReadyCatalogState,
    _test_database,
)

from app.core.config import Settings
from app.main import create_app

# pytest 只为收集到的 conftest/测试模块注册 fixture；步骤定义模块被普通 import 时
# 其 fixture 不进入 fixturemanager。这里在模块级把步骤模块的 stepdef fixture 对象
# 并入本 conftest 的 globals，使其随 conftest 一起注册且对本目录树可见。
# 真实检索步骤由 test_search_sync_e2e.py 加载。
STEPS_DIR = Path(__file__).resolve().parent / "steps"
DEFERRED_STEPS = {"search_sync_steps"}

for _steps in sorted(STEPS_DIR.glob("*_steps.py")):
    if _steps.stem in DEFERRED_STEPS:
        continue
    _module = importlib.import_module(f"tests.bdd.steps.{_steps.stem}")
    for _name, _value in vars(_module).items():
        if _name.startswith("pytestbdd_stepdef"):
            globals()[_name] = _value


@pytest.fixture
def client(tmp_path) -> TestClient:
    database = _test_database()
    secret = tmp_path / "app-secret"
    secret.write_text("test-app-secret", encoding="utf-8")
    settings = Settings(
        app_environment="test",
        enable_demo_seed=True,
        session_cookie_secure=False,
        app_secret_file=str(secret),
    )
    app = create_app(
        database=database,
        settings=settings,
        blob_store=MemoryBlobStore(),
        search_catalog=EmptySearchCatalog(),
        catalog_state=ReadyCatalogState(database),
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def ctx(client):
    """场景共享上下文：会话、案例、版本、批注等业务对象的中转站。"""
    return {"client": client, "sessions": {}, "cases": {}, "memo": {}}
