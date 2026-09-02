from __future__ import annotations

import json

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel


def _agent():
    from app.modules.agent.runtime import agent

    return agent


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _message(text: str) -> dict:
    return {
        "id": "product-message",
        "role": "user",
        "parts": [{"type": "text", "text": text}],
    }


def _body(text: str, **fields) -> dict:
    return {
        "id": "product-chat",
        "trigger": "submit-message",
        "messages": [_message(text)],
        **fields,
    }


def _headers(auth: dict) -> dict[str, str]:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _model(answer: str) -> TestModel:
    return TestModel(custom_output_text=answer)


def _text_deltas(response) -> str:
    return "".join(
        json.loads(line[6:]).get("delta", "")
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"type":"text-delta"' in line
    )


def test_case_ai_uses_production_agent_and_vercel_stream(client: TestClient) -> None:
    auth = _login(client)
    payload = _body(
        "请给出课堂建议",
        mode="chat",
        instruction="请给出课堂建议",
        context={"revision": 1},
    )
    with _agent().override(model=_model("工作台回答")):
        response = client.post(
            "/api/cases/c-draft-1/ai/chat", headers=_headers(auth), json=payload
        )
    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert _text_deltas(response) == "工作台回答"


def test_search_summary_uses_production_agent_and_vercel_stream(client: TestClient) -> None:
    auth = _login(client)
    payload = _body(
        "如何教学",
        query="如何教学",
        items=[{"kind": "case", "id": "c-draft-1", "title": "案例"}],
    )
    with _agent().override(model=_model("检索摘要")):
        response = client.post(
            "/api/search/summary", headers=_headers(auth), json=payload
        )
    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert _text_deltas(response) == "检索摘要"


def test_product_ai_requires_the_latest_message_to_match_request(client: TestClient) -> None:
    auth = _login(client)
    payload = _body(
        "其他问题",
        mode="chat",
        instruction="请求问题",
        context={"revision": 1},
    )
    response = client.post(
        "/api/cases/c-draft-1/ai/chat", headers=_headers(auth), json=payload
    )
    assert response.status_code == 422
