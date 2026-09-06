"""Skill 平台 HTTP：管理员上传/发布、教师目录、不可变版本与权限。"""

from __future__ import annotations

import hashlib
import io
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.skill_packages import (
    EXAMPLE_PATH,
    FILES,
    INSTALL_PATH,
    SKILL_DIR,
    SKILL_MD,
    TEMPLATE_PATH,
    TEMPLATE_TEXT,
    build_package,
    build_unflagged_package,
)

ADMIN = {"username": "admin", "password": "admin123"}
TEACHER = {"username": "user", "password": "user123"}
PACKAGE_PATH = "/api/admin/skills/packages"
SKILLS_PATH = "/api/skills"
SKILL_ID = "sizheng-case-generator"


def _login(client: TestClient, account: dict) -> dict:
    response = client.post("/api/auth/login", json=account)
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _upload(client: TestClient, auth: dict, data: bytes) -> object:
    return client.post(
        PACKAGE_PATH, headers=_csrf(auth),
        files={"file": ("思政案例生成Skill包_v2.1.zip", data, "application/zip")},
    )


def _publish(client: TestClient, auth: dict, skill_id: str, version_id: str) -> object:
    return client.post(
        f"/api/admin/skills/{skill_id}/publish",
        headers=_csrf(auth), json={"versionId": version_id},
    )


def _first_version(client: TestClient, auth: dict, skill_id: str) -> dict:
    listing = client.get("/api/admin/skills", headers=_csrf(auth)).json()
    return next(row for row in listing if row["id"] == skill_id)["versions"][0]


def _login_teacher(client: TestClient) -> dict:
    return _login(client, TEACHER)


def test_teacher_cannot_upload_or_list_or_publish(client: TestClient) -> None:
    auth = _login_teacher(client)
    assert _upload(client, auth, build_package()).status_code == 403
    assert client.get("/api/admin/skills", headers=_csrf(auth)).status_code == 403
    publish = _publish(client, auth, SKILL_ID, "skillver-x")
    assert publish.status_code == 403


def test_upload_parses_metadata_manifest_and_hashes(client: TestClient) -> None:
    data = build_package()
    response = _upload(client, _login(client, ADMIN), data)
    assert response.status_code == 201, response.text
    skill, version = response.json()["skill"], response.json()["version"]
    assert skill["id"] == SKILL_ID and skill["publishedVersionId"] is None
    assert skill["name"] == SKILL_ID
    assert skill["description"].startswith("习近平文化思想课程思政案例生成技能")
    assert version["version"] == "v1"
    assert version["packageSha256"] == hashlib.sha256(data).hexdigest()
    assert version["description"].startswith("习近平文化思想课程思政案例生成技能")
    database = client.app.state.database
    stored = database.skill_versions.find_one({"id": version["id"]})
    assert {row["path"] for row in stored["files"]} == {
        TEMPLATE_PATH, EXAMPLE_PATH, INSTALL_PATH,
    }


def test_publish_then_teacher_catalog_content_and_resources(client: TestClient) -> None:
    teacher = _csrf(_login_teacher(client))
    admin = _login(client, ADMIN)
    uploaded = _upload(client, admin, build_package()).json()
    assert client.get(SKILLS_PATH, headers=teacher).json() == []
    assert _publish(client, admin, SKILL_ID, uploaded["version"]["id"]).status_code == 200
    auth = _csrf(_login_teacher(client))
    assert client.get(SKILLS_PATH, headers=auth).json() == [_expected_catalog(uploaded)]
    content = client.get(f"{SKILLS_PATH}/{SKILL_ID}/content", headers=auth).json()
    assert content["path"] == f"{SKILL_DIR}/SKILL.md"
    assert content["version"] == "v1"
    assert content["content"] == SKILL_MD.split("---\n", 2)[-1].strip("\n")
    template = client.get(
        f"{SKILLS_PATH}/{SKILL_ID}/resources/{TEMPLATE_PATH}", headers=auth
    ).json()
    assert template["content"] == TEMPLATE_TEXT
    assert len(template["sha256"]) == 64


def _expected_catalog(uploaded: dict) -> dict:
    return {
        "id": SKILL_ID, "versionId": uploaded["version"]["id"], "version": "v1",
        "name": SKILL_ID, "description": uploaded["version"]["description"],
    }


def test_unflagged_utf8_zip_reads_chinese_paths_exactly(client: TestClient) -> None:
    data = build_unflagged_package()
    admin = _login(client, ADMIN)
    uploaded = _upload(client, admin, data).json()
    _publish(client, admin, SKILL_ID, uploaded["version"]["id"])
    auth = _csrf(_login_teacher(client))
    for relative, expected in (
        (TEMPLATE_PATH, TEMPLATE_TEXT),
        (EXAMPLE_PATH, FILES[f"{SKILL_DIR}/{EXAMPLE_PATH}"]),
    ):
        read = client.get(
            f"{SKILLS_PATH}/{SKILL_ID}/resources/{relative}", headers=auth
        )
        assert read.status_code == 200, read.text
        assert read.json()["content"] == expected


def test_invalid_packages_get_actionable_errors(client: TestClient) -> None:
    auth = _csrf(_login(client, ADMIN))
    for expected, data in _invalid_cases().items():
        response = client.post(
            PACKAGE_PATH, headers=auth,
            files={"file": ("skill.zip", data, "application/zip")},
        )
        assert response.status_code == 422, (expected, response.text)
        assert expected in response.json()["detail"]


def _invalid_cases() -> dict[str, bytes]:
    return {
        "包内缺少 SKILL.md": build_package(files={"readme.txt": "没有入口"}),
        "包内包含多个 SKILL.md": build_package(files={
            "a/SKILL.md": SKILL_MD, "b/SKILL.md": SKILL_MD,
        }),
        "name 只能包含": build_package(files={
            "sizheng_case/SKILL.md": SKILL_MD.replace(
                'name: "sizheng-case-generator"', 'name: "Sizheng Case"'
            ),
        }),
        "缺少非空 description": build_package(files={
            "sizheng-case/SKILL.md": SKILL_MD.replace(
                'description: "习近平', 'description: ""\nignored: "习近平'
            ),
        }),
        "不是有效的 ZIP 文件": b"not a zip",
    }


def test_new_upload_makes_new_version_and_keeps_old_immutable(client: TestClient) -> None:
    admin = _login(client, ADMIN)
    first = _upload(client, admin, build_package()).json()["version"]
    altered = dict(FILES)
    altered[f"{SKILL_DIR}/{TEMPLATE_PATH}"] = "# 模板规范 v2.1\n\n修订后的规范。"
    second = _upload(client, admin, build_package(altered)).json()["version"]
    assert second["version"] == "v2"
    listing = client.get("/api/admin/skills", headers=_csrf(admin)).json()
    versions = {row["version"]: row for row in listing[0]["versions"]}
    assert versions["v1"]["packageSha256"] == first["packageSha256"]
    assert versions["v2"]["packageSha256"] == second["packageSha256"]
    assert versions["v1"]["packageSha256"] != versions["v2"]["packageSha256"]
    _publish(client, admin, SKILL_ID, versions["v2"]["id"])
    auth = _csrf(_login_teacher(client))
    read = client.get(
        f"{SKILLS_PATH}/{SKILL_ID}/resources/{TEMPLATE_PATH}", headers=auth
    ).json()
    assert read["content"] == altered[f"{SKILL_DIR}/{TEMPLATE_PATH}"]
    assert read["versionId"] == versions["v2"]["id"]


def test_publish_unknown_version_and_missing_resources_fail(client: TestClient) -> None:
    admin = _login(client, ADMIN)
    assert _publish(client, admin, SKILL_ID, "skillver-none").status_code == 404
    _upload(client, admin, build_package())
    assert _publish(client, admin, SKILL_ID, "skillver-none").status_code == 404
    version = _first_version(client, admin, SKILL_ID)
    _publish(client, admin, SKILL_ID, version["id"])
    auth = _csrf(_login_teacher(client))
    assert client.get(
        f"{SKILLS_PATH}/{SKILL_ID}/resources/references/missing.md", headers=auth
    ).status_code == 404
    assert client.get(
        f"{SKILLS_PATH}/unknown-skill/content", headers=auth
    ).status_code == 404


def test_resource_read_rejects_traversal_and_binary(client: TestClient) -> None:
    admin = _login(client, ADMIN)
    payload = build_package()
    _upload(client, admin, payload)
    version = _first_version(client, admin, SKILL_ID)
    _publish(client, admin, SKILL_ID, version["id"])
    auth = _csrf(_login_teacher(client))
    assert client.get(
        f"{SKILLS_PATH}/{SKILL_ID}/resources/..%2F..%2Fetc%2Fpasswd", headers=auth
    ).status_code == 404


def _non_string_frontmatter_cases() -> dict[str, str]:
    """非法样例：数字/布尔/列表/对象一律拒绝，纯空白视为缺失。"""

    def frontmatter(
        name: str = 'name: "sizheng-case-generator"',
        description: str = 'description: "简要描述"',
    ) -> str:
        return f"{name}\n{description}"

    return {
        "name 必须是字符串，收到数字": frontmatter(name="name: 123"),
        "name 必须是字符串，收到布尔值": frontmatter(name="name: true"),
        "name 必须是字符串，收到列表": frontmatter(name="name: [sizheng-case-generator]"),
        "description 必须是字符串，收到数字": frontmatter(description="description: 20240901"),
        "description 必须是字符串，收到对象": frontmatter(description="description: {zh: 简介}"),
        "缺少非空 name": frontmatter(name='name: "   "'),
        "缺少非空 description": frontmatter(description='description: "\\n \\t"'),
    }


def test_frontmatter_rejects_non_string_metadata(client: TestClient) -> None:
    """name/description 必须是真实非空字符串，不做类型强转。"""
    auth = _csrf(_login(client, ADMIN))
    for expected, raw in _non_string_frontmatter_cases().items():
        response = client.post(
            PACKAGE_PATH, headers=auth,
            files={"file": ("skill.zip", _package_with_raw_frontmatter(raw), "application/zip")},
        )
        assert response.status_code == 422, (expected, response.text)
        assert expected in response.json()["detail"], expected


def _package_with_raw_frontmatter(frontmatter: str) -> bytes:
    body = SKILL_MD.split("---\n", 2)[-1]
    text = f"---\n{frontmatter}\n---{body}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{SKILL_DIR}/SKILL.md", text)
        archive.writestr(f"{SKILL_DIR}/{TEMPLATE_PATH}", TEMPLATE_TEXT)
    return buffer.getvalue()


def test_duplicate_resource_paths_rejected_before_any_write(client: TestClient) -> None:
    """ZIP 允许同名成员；清单记首个哈希、按名读取却命中末个内容，必须整体拒绝。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{SKILL_DIR}/SKILL.md", SKILL_MD)
        archive.writestr(f"{SKILL_DIR}/{TEMPLATE_PATH}", TEMPLATE_TEXT)
        archive.writestr(f"{SKILL_DIR}/{TEMPLATE_PATH}", "# 后写入的同名内容")
    auth = _csrf(_login(client, ADMIN))
    response = client.post(
        PACKAGE_PATH, headers=auth,
        files={"file": ("dup.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 422, response.text
    assert "重复资源路径" in response.json()["detail"]
    database = client.app.state.database
    assert database.skill_versions.count_documents({}) == 0
    assert database.skills.count_documents({}) == 0
    assert client.app.state.blob_store.objects == {}


def test_concurrent_uploads_allocate_distinct_versions(client: TestClient) -> None:
    """并发上传同一 Skill：版本号原子分配，各得唯一 vN，无 DuplicateKeyError 漏出。"""
    admin = _login(client, ADMIN)

    def upload(index: int):
        files = dict(FILES)
        files[f"{SKILL_DIR}/{TEMPLATE_PATH}"] = f"# 模板规范 并发-{index}"
        return _upload(client, admin, build_package(files))

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(upload, range(6)))
    assert all(response.status_code == 201 for response in responses)
    versions = sorted(
        response.json()["version"]["version"] for response in responses
    )
    assert versions == [f"v{index}" for index in range(1, 7)]
    listing = client.get("/api/admin/skills", headers=_csrf(admin)).json()[0]
    assert len(listing["versions"]) == 6


def test_late_finishing_upload_never_regresses_latest(
    client: TestClient, monkeypatch
) -> None:
    """并发完成乱序：v1 迟到完成不得把 latestVersionId 从 v2 倒退回 v1。"""
    from app.modules.skills import service

    database = client.app.state.database
    second, late = _upload_out_of_order(client, monkeypatch, service)
    assert late.status_code == 201
    assert second["version"]["version"] == "v2"
    assert second["skill"]["latestVersionId"] == second["version"]["id"]
    skill = database.skills.find_one({"id": SKILL_ID})
    assert skill["latestVersionNumber"] == 2
    assert skill["latestVersionId"] == second["version"]["id"]


def _upload_out_of_order(client: TestClient, monkeypatch, service) -> tuple[dict, object]:
    """v1 卡在版本落库前，v2 完成并指向最新后再放行 v1 完成写库。"""
    release = threading.Event()
    original_insert = service._insert_version

    def gated_insert(db, package, number, now):
        if number == 1:
            release.wait(timeout=10)
        return original_insert(db, package, number, now)

    monkeypatch.setattr(service, "_insert_version", gated_insert)
    admin = _login(client, ADMIN)
    late_package = build_package(_altered_files("迟到-v1"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        late = pool.submit(_upload, client, admin, late_package)
        _wait_for_reserved_number(client.app.state.database, 1)
        second = _upload(client, admin, build_package(_altered_files("抢先-v2"))).json()
        release.set()
    return second, late.result()


def _altered_files(note: str) -> dict[str, str]:
    files = dict(FILES)
    files[f"{SKILL_DIR}/{TEMPLATE_PATH}"] = f"# 模板规范 {note}"
    return files


def _wait_for_reserved_number(database, number: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        skill = database.skills.find_one({"id": SKILL_ID})
        if skill and skill.get("versionCounter", 0) >= number:
            return
        time.sleep(0.01)
    raise AssertionError("版本号未被预留")


def test_republish_same_version_keeps_published_at(client: TestClient) -> None:
    """重复发布同一版本幂等：publishedAt 不被改写；换发新版本才更新。"""
    admin = _login(client, ADMIN)
    first = _upload(client, admin, build_package()).json()["version"]
    _publish(client, admin, SKILL_ID, first["id"])
    published_at = _published_at(client, admin)
    time.sleep(0.02)
    again = _publish(client, admin, SKILL_ID, first["id"])
    assert again.status_code == 200
    assert _published_at(client, admin) == published_at
    assert again.json()["skill"]["publishedVersionId"] == first["id"]
    second = _upload(
        client, admin, build_package(_altered_files("新-v2"))
    ).json()["version"]
    _publish(client, admin, SKILL_ID, second["id"])
    assert _published_at(client, admin) != published_at


def _published_at(client: TestClient, auth: dict) -> str | None:
    listing = client.get("/api/admin/skills", headers=_csrf(auth)).json()
    return next(row for row in listing if row["id"] == SKILL_ID)["publishedAt"]
