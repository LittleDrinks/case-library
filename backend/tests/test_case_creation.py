from __future__ import annotations

from fastapi.testclient import TestClient

from app.modules.cases import template

GENERAL_SECTIONS = (
    (2, "（一）建设目标"),
    (2, "（二）主要内容设计"),
    (2, "（三）方法与策略"),
    (2, "（四）评价与成效"),
    (2, "（五）特色与创新"),
)
STANDARD_SECTIONS = (
    (1, "一、教学说明（800字左右）"),
    (2, "（一）教学目的"),
    (2, "（二）阅读思考题（2～3个）"),
    (2, "（三）教学安排"),
    (2, "（四）注意事项"),
    (1, "二、文本内容（2500字左右）"),
    (1, "三、附件"),
)
GENERAL_METADATA = {
    "audience": "ug",
    "stageText": "本科思政",
    "typeId": "ct-figure",
    "typeName": "人物传记类",
    "templateId": "tpl-general-v1",
    "templateVersion": 1,
    "templateName": "通用案例结构",
}


def _auth(
    client: TestClient, username: str = "user", password: str = "user123"
) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    return response.json()


def _selection(template_id: str = "tpl-general-v1") -> dict:
    return {"stageId": "ug", "typeId": "ct-figure", "templateId": template_id}


def _create(client: TestClient, headers: dict, body: dict | None = None) -> dict:
    response = client.post("/api/cases", headers=headers, json=body or _selection())
    assert response.status_code == 200
    return response.json()


def _document(sections: tuple[tuple[int, str], ...]) -> dict:
    content = []
    for level, title in sections:
        content.extend([
            {
                "type": "heading",
                "attrs": {"level": level},
                "content": [{"type": "text", "text": title}],
            },
            {"type": "paragraph", "content": []},
        ])
    return {"type": "doc", "content": content}


def _test_template(
    template_id: str, *, enabled: bool, stage_ids: tuple[str, ...]
) -> dict:
    return {
        "id": template_id,
        "version": 1,
        "name": "测试模板",
        "stageIds": stage_ids,
        "typeIds": ("ct-figure",),
        "sections": ({"level": 2, "title": "测试小节"},),
        "enabled": enabled,
    }


def _with_unavailable_templates(monkeypatch) -> None:
    additions = (
        _test_template("tpl-disabled-test", enabled=False, stage_ids=("ug",)),
        _test_template("tpl-grad-test", enabled=True, stage_ids=("grad",)),
    )
    monkeypatch.setattr(template, "TEMPLATES", (*template.TEMPLATES, *additions))


def _assert_unavailable(client: TestClient, headers: dict, body: dict) -> None:
    response = client.post("/api/cases", headers=headers, json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": "模板不可用"}


def _submit(client: TestClient, headers: dict, case: dict) -> dict:
    response = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers=headers,
        json={"command": "submit", "revision": case["revision"]},
    )
    assert response.status_code == 200
    return response.json()


def _save_title(client: TestClient, headers: dict, case: dict) -> dict:
    response = client.patch(
        f"/api/cases/{case['id']}",
        headers=headers,
        json={"title": "停用后仍可编辑", "revision": case["revision"]},
    )
    assert response.status_code == 200
    return response.json()


def _approve(client: TestClient, case: dict, version_id: str) -> None:
    admin = _auth(client, "admin", "admin123")
    start = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={"command": "start", "revision": case["revision"]},
    ).json()
    approved = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": admin["csrfToken"]},
        json={
            "command": "approve",
            "revision": start["case"]["revision"],
            "submittedVersionId": version_id,
        },
    )
    assert approved.status_code == 200


def test_catalog_requires_login_and_hides_template_definitions(client: TestClient) -> None:
    assert client.get("/api/case-creation-catalog").status_code == 401
    assert client.post("/api/cases", json=_selection()).status_code == 401
    _auth(client)
    catalog = client.get("/api/case-creation-catalog").json()
    assert [stage["id"] for stage in catalog["stages"]] == ["grad", "ug", "embed"]
    assert [case_type["id"] for case_type in catalog["caseTypes"]] == [
        "ct-general",
        "ct-policy",
        "ct-figure",
        "ct-thought",
        "ct-school",
        "ct-tech",
        "ct-society",
    ]
    fields = {"id", "version", "name", "stageIds", "typeIds", "sectionTitles"}
    assert all(set(row) == fields for row in catalog["templates"])


def test_templates_materialize_exact_documents_and_metadata(client: TestClient) -> None:
    auth = _auth(client)
    headers = {"X-CSRF-Token": auth["csrfToken"]}
    general = _create(client, headers)
    standard = _create(client, headers, _selection("tpl-teaching-standard-v1"))
    assert general["document"] == _document(GENERAL_SECTIONS)
    assert standard["document"] == _document(STANDARD_SECTIONS)
    assert {key: general[key] for key in GENERAL_METADATA} == GENERAL_METADATA
    assert general["title"] == "未命名案例"
    assert general["ownerId"] == auth["user"]["id"]
    assert general["revision"] == 1


def test_creation_contract_rejects_old_and_unavailable_requests(
    client: TestClient, monkeypatch
) -> None:
    auth = _auth(client)
    headers = {"X-CSRF-Token": auth["csrfToken"]}
    database = client.app.state.database
    before = database.cases.count_documents({})
    old_request = {"title": "旧请求", "document": _document(GENERAL_SECTIONS)}
    assert client.post("/api/cases", headers=headers, json=old_request).status_code == 422
    assert client.post(
        "/api/cases", headers=headers, json=_selection() | {"title": "不接受"}
    ).status_code == 422
    _with_unavailable_templates(monkeypatch)
    _assert_unavailable(client, headers, _selection("tpl-missing"))
    _assert_unavailable(client, headers, _selection("tpl-grad-test"))
    _assert_unavailable(client, headers, _selection("tpl-disabled-test"))
    assert database.cases.count_documents({}) == before


def test_template_metadata_is_snapshotted_and_disabling_does_not_block_lifecycle(
    client: TestClient, monkeypatch
) -> None:
    auth = _auth(client)
    headers = {"X-CSRF-Token": auth["csrfToken"]}
    case = _create(client, headers)
    monkeypatch.setattr(template, "TEMPLATES", ())
    assert client.get(f"/api/cases/{case['id']}").json()["templateId"] == "tpl-general-v1"
    submitted = _submit(client, headers, _save_title(client, headers, case))
    metadata = submitted["version"]["metadata"]
    assert {key: metadata[key] for key in GENERAL_METADATA} == GENERAL_METADATA
    _approve(client, submitted["case"], submitted["version"]["id"])
    client.cookies.clear()
    published = client.get(f"/api/cases/{case['id']}").json()
    assert published["workflowStatus"] == "published"
