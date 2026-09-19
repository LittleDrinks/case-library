"""真实资源上的检索同步中文场景：发布→outbox消费→真实 Meili→公开搜索。

经既有 e2e-app HTTP 公共接口执行发布/下线（该服务由隔离 Compose 注入
SEARCH_SYNC_E2E_URL 指向真实 Mongo 副本集、Meilisearch 与常驻 search-worker），
以公开搜索实际结果的有限轮询为准。本模块只读 SEARCH_SYNC_E2E_URL 一个变量。

步骤 fixture 注册：pytest 只为收集到的测试模块/conftest 注册 fixture，
普通 import 步骤模块不生效；这里把步骤模块的 stepdef fixture 并入本模块
globals，与 tests/bdd/conftest.py 的合并机制一致（pytest-bdd 8 的步骤
装饰器会在定义模块内生成 pytestbdd_stepdef_* fixture，合并即真实注册）。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from pytest_bdd import scenarios

pytestmark = pytest.mark.e2e("SEARCH_SYNC_E2E_URL")

BDD_DIR = Path(__file__).resolve().parent

_steps_module = importlib.import_module("tests.bdd.steps.search_sync_steps")
for _name, _value in vars(_steps_module).items():
    if _name.startswith("pytestbdd_stepdef"):
        globals()[_name] = _value


@pytest.fixture
def ctx():
    """检索同步步骤只经 HTTP 访问 e2e-app，不需要进程内应用实例。"""
    return {"cases": {}, "memo": {}}


scenarios(str(BDD_DIR / "features" / "search_sync.feature"))
