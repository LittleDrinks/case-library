"""真实 MongoDB replica set 上的 Skill 并发上传验收：版本号原子分配，各得唯一 vN。

原为 mongomock 层用例，迁移至此因 mongomock 4.3.0 的 find_one_and_update
非原子实现（find→update→find）会使并发版本分配产生假阳性失败；
真实 MongoDB 的 findOneAndUpdate 单文档原子操作不受影响，断言原样保留。
走既有 E2E 应用（e2e-app，CASE_LIBRARY_E2E_URL），经 HTTP 公共接口上传。
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from tests.skill_packages import FILES, SKILL_DIR, TEMPLATE_PATH, build_package

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL")
SKILL_ID = "sizheng-case-generator"


def test_concurrent_uploads_allocate_distinct_versions_on_replica_set() -> None:
    with httpx.Client(base_url=BASE_URL) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == 200
        csrf = response.json()["csrfToken"]
        # 独立 skill 命名空间：并发多次运行互不污染，也无需清理既有数据。
        scope = f"{SKILL_ID}-{uuid.uuid4().hex[:8]}"

        def upload(index: int) -> httpx.Response:
            files = dict(FILES)
            files[f"{SKILL_DIR}/SKILL.md"] = files[f"{SKILL_DIR}/SKILL.md"].replace(
                f'name: "{SKILL_ID}"', f'name: "{scope}"'
            )
            # 证明替换真实发生：若包内元数据不含原 name，replace 会静默空操作。
            assert f'name: "{scope}"' in files[f"{SKILL_DIR}/SKILL.md"]
            files[f"{SKILL_DIR}/{TEMPLATE_PATH}"] = f"# 模板规范 并发-{index}"
            return client.post(
                "/api/admin/skills/packages",
                headers={"X-CSRF-Token": csrf},
                files={"file": (f"并发-{index}.zip", build_package(files), "application/zip")},
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(upload, index) for index in range(6)]
            responses = [future.result(timeout=30) for future in futures]
        assert all(response.status_code == 201 for response in responses)
        versions = sorted(
            response.json()["version"]["version"] for response in responses
        )
        assert versions == [f"v{index}" for index in range(1, 7)]
        listing_response = client.get(
            "/api/admin/skills", headers={"X-CSRF-Token": csrf}
        )
        assert listing_response.status_code == 200, listing_response.text
        skill = next(
            row for row in listing_response.json() if row["id"] == scope
        )
        assert len(skill["versions"]) == 6
        assert skill["latestVersionNumber"] == 6
        assert skill["latestVersionId"] == next(
            response.json()["version"]["id"]
            for response in responses
            if response.json()["version"]["version"] == "v6"
        )
