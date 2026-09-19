"""中文 Gherkin 业务验收测试收集器：加载步骤定义并收集 features/ 全部场景。"""
from __future__ import annotations

import importlib
from pathlib import Path

from pytest_bdd import scenarios

BDD_DIR = Path(__file__).resolve().parent

# 真实资源层（真实 Meilisearch + e2e-app HTTP）与浏览器层（Playwright）步骤
# 分别由 test_search_sync_e2e.py 与浏览器 e2e 模块自行加载；轻量层不导入。
DEFERRED_STEPS = {"search_sync_steps", "browser_steps"}

for steps in sorted((BDD_DIR / "steps").glob("*_steps.py")):
    if steps.stem in DEFERRED_STEPS:
        continue
    importlib.import_module(f"tests.bdd.steps.{steps.stem}")

# search_sync.feature 绑定真实资源层（test_search_sync_e2e），
# browser_workbench.feature 绑定浏览器层（Playwright e2e 模块），
# 均不在轻量层收集。
DEFERRED_FEATURES = {"search_sync.feature", "browser_workbench.feature"}

for feature in sorted((BDD_DIR / "features").glob("*.feature")):
    if feature.name in DEFERRED_FEATURES:
        continue
    scenarios(str(feature))
