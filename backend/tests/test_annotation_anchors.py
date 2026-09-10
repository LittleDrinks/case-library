from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from app.modules.agent import writes
from app.modules.agent.models import ArtifactTarget
from app.modules.agent.repository import AgentRepository

HEADING = "一、教学说明"


def utf16_size(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def document(*paragraphs: str) -> dict:
    content = [{
        "type": "heading",
        "attrs": {"level": 1},
        "content": [{"type": "text", "text": HEADING}],
    }]
    content.extend(
        {"type": "paragraph", **({"content": [{"type": "text", "text": text}]} if text else {})}
        for text in paragraphs
    )
    return {"type": "doc", "content": content}


def paragraph_start(*prior: str) -> int:
    return utf16_size(HEADING) + 3 + sum(utf16_size(text) + 2 for text in prior)


def annotation_payload(case: dict, text: str, prior: tuple[str, ...] = ()) -> dict:
    start = paragraph_start(*prior)
    return {
        "from": start,
        "to": start + utf16_size(text),
        "quote": text,
        "section": HEADING,
        "quoteHash": hashlib.sha256(text.encode()).hexdigest(),
        "revision": case["revision"],
        "content": "请补充教学依据。",
        "source": "manual",
    }


def create_case(client: TestClient, auth: dict, *paragraphs: str) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "锚点测试", "document": document(*paragraphs)},
    )
    assert response.status_code == 200
    return response.json()


def create_annotation(client: TestClient, auth: dict, case: dict, payload: dict) -> dict:
    response = client.post(
        f"/api/cases/{case['id']}/annotations",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def replace_step(start: int, end: int, text: str = "") -> dict:
    step = {"stepType": "replace", "from": start, "to": end}
    if text:
        step["slice"] = {"content": [{"type": "text", "text": text}]}
    return step


def save_document(client: TestClient, auth: dict, case: dict, next_document: dict, steps: list[dict]):
    return client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"revision": case["revision"], "document": next_document, "steps": steps},
    )


def annotation(client: TestClient, case: dict) -> dict:
    return client.get(f"/api/cases/{case['id']}/annotations").json()[0]


def agent_run(client: TestClient, auth: dict, case: dict, target: ArtifactTarget):
    database = client.app.state.database
    repository = AgentRepository(database)
    thread = repository.default_thread(case["id"], auth["user"]["id"])
    run = repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "直接写入"}], {},
        "assistant-anchor-test", base_revision=case["revision"], target=target,
        write_authorized=True,
    )
    return database, thread, run


def test_anchor_follows_verified_position_mapping_and_survives_refresh(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "目标正文")
    start = paragraph_start()
    create_annotation(client, auth, case, annotation_payload(case, "目标正文"))

    saved = save_document(
        client, auth, case, document("前置目标正文"), [replace_step(start, start, "前置")]
    )

    assert saved.status_code == 200
    row = annotation(client, saved.json())
    assert row["from"] == start + 2
    assert row["to"] == start + 2 + len("目标正文")
    assert row["anchorState"] == "active"
    assert row["revision"] == saved.json()["revision"]


def test_changed_target_keeps_discussion_but_cannot_keep_anchor(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "目标正文")
    start = paragraph_start()
    create_annotation(client, auth, case, annotation_payload(case, "目标正文"))

    saved = save_document(
        client, auth, case, document("改写正文"), [replace_step(start, start + len("目标正文"), "改写正文")]
    )

    assert saved.status_code == 200
    row = annotation(client, saved.json())
    assert row["quote"] == "目标正文"
    assert row["anchorState"] == "changed"
    assert "from" not in row and "to" not in row


def test_deleted_target_keeps_original_quote_and_is_marked_deleted(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "目标正文")
    start = paragraph_start()
    create_annotation(client, auth, case, annotation_payload(case, "目标正文"))

    saved = save_document(
        client, auth, case, document(""), [replace_step(start, start + len("目标正文"))]
    )

    assert saved.status_code == 200
    row = annotation(client, saved.json())
    assert row["quote"] == "目标正文"
    assert row["anchorState"] == "deleted"
    assert "from" not in row and "to" not in row


def test_duplicate_quotes_follow_their_position_not_another_match(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "相同文字", "相同文字")
    payload = annotation_payload(case, "相同文字", ("相同文字",))
    create_annotation(client, auth, case, payload)

    saved = save_document(
        client,
        auth,
        case,
        document("前置相同文字", "相同文字"),
        [replace_step(paragraph_start(), paragraph_start(), "前置")],
    )

    assert saved.status_code == 200
    row = annotation(client, saved.json())
    assert row["from"] == paragraph_start("相同文字") + 2
    assert row["quote"] == "相同文字"
    assert row["anchorState"] == "active"


def test_forged_steps_cannot_rebind_an_annotation(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "目标正文")
    start = paragraph_start()
    create_annotation(client, auth, case, annotation_payload(case, "目标正文"))

    response = save_document(
        client, auth, case, document("前置目标正文"), [replace_step(start + 2, start + 2, "前置")]
    )

    assert response.status_code == 409
    current = client.get(f"/api/cases/{case['id']}").json()
    assert current["document"] == document("目标正文")
    assert annotation(client, case)["anchorState"] == "active"


def test_changed_document_without_steps_is_refused(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "目标正文")
    response = save_document(client, auth, case, document("前置目标正文"), [])
    assert response.status_code == 409
    assert client.get(f"/api/cases/{case['id']}").json()["document"] == document("目标正文")


def test_utf16_emoji_anchor_uses_native_positions(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "A😀B")
    start = paragraph_start()
    payload = annotation_payload(case, "😀")
    payload.update({"from": start + 1, "to": start + 3})
    create_annotation(client, auth, case, payload)
    saved = save_document(
        client, auth, case, document("前A😀B"), [replace_step(start, start, "前")],
    )
    assert saved.status_code == 200
    row = annotation(client, saved.json())
    assert row["from"] == start + 2 and row["to"] == start + 4
    assert row["quote"] == "😀" and row["anchorState"] == "active"


def test_agent_write_and_undo_reconcile_active_anchor(client: TestClient) -> None:
    auth = login(client)
    case = create_case(client, auth, "第一段", "第二段")
    create_annotation(client, auth, case, annotation_payload(case, "第二段", ("第一段",)))
    target_start = paragraph_start()
    target = ArtifactTarget(from_pos=target_start, to_pos=target_start + len("第一段"), quote="第一段")
    database, thread, run = agent_run(client, auth, case, target)
    record = writes.apply_write(
        database, case["id"], run.id, "selection",
        [{"type": "paragraph", "text": "更长的第一段"}], auth["user"],
    )
    moved = annotation(client, case)
    assert moved["anchorState"] == "active"
    assert moved["from"] == paragraph_start("更长的第一段")
    writes.undo_write(database, case["id"], thread.id, record["id"], auth["user"])
    assert annotation(client, case)["from"] == paragraph_start("第一段")
