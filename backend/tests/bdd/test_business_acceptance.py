"""中文 Gherkin 业务验收测试收集器：加载步骤定义并收集 features/ 全部场景。"""
from __future__ import annotations

import importlib
from pathlib import Path

from pytest_bdd import scenarios

BDD_DIR = Path(__file__).resolve().parent

# 真实检索步骤由 test_search_sync_e2e.py 加载。
DEFERRED_STEPS = {"search_sync_steps"}

for steps in sorted((BDD_DIR / "steps").glob("*_steps.py")):
    if steps.stem in DEFERRED_STEPS:
        continue
    importlib.import_module(f"tests.bdd.steps.{steps.stem}")

# 真实检索场景不在轻量层收集。
DEFERRED_FEATURES = {"search_sync.feature"}

for feature in sorted((BDD_DIR / "features").glob("*.feature")):
    if feature.name in DEFERRED_FEATURES:
        continue
    scenarios(str(feature))
