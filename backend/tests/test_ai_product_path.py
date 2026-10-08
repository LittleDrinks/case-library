from __future__ import annotations

import json

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from starlette.responses import Response

import app.modules.search.ai_routes as summary_routes
from app.modules.search.meilisearch import CatalogPage


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
    return TestModel(custom_output_text=answer, call_tools=[])


def _text_deltas(response) -> str:
    return "".join(
        json.loads(line[6:]).get("delta", "")
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"type":"text-delta"' in line
    )


def test_search_summary_uses_production_agent_and_vercel_stream(client: TestClient) -> None:
    auth = _login(client)
    payload = _body(
        "如何教学",
        query="如何教学",
        search={"q": "如何教学"},
    )
    with _agent().override(model=_model("检索摘要")):
        response = client.post(
            "/api/search/summary", headers=_headers(auth), json=payload
        )
    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert _text_deltas(response) == "检索摘要"


def test_search_summary_requeries_instead_of_using_client_items(client, monkeypatch) -> None:
    auth = _login(client)
    requested = []
    instructions_seen = []

    class CurrentSearchCatalog:
        def search(self, search_request):
            requested.append(search_request)
            return CatalogPage(
                [{"id": "visible-case", "kind": "case", "title": "当前可见案例", "score": 5}],
                None,
                False,
                False,
            )

    def capture_summary(_adapter, _selection, _settings, instructions, _lease):
        instructions_seen.append(instructions)

        async def empty_stream():
            if False:
                yield None

        return empty_stream()

    monkeypatch.setattr(summary_routes, "stream_summary", capture_summary)
    monkeypatch.setattr(
        summary_routes,
        "summary_response",
        lambda _adapter, _stream: Response(status_code=204),
    )
    client.app.state.search_catalog = CurrentSearchCatalog()
    query = "当前可见的课堂案例"
    stale_marker = "客户端伪造的私人草稿结果"
    payload = _body(
        query,
        query=query,
        search={"q": query, "kind": "case"},
        items=[{"id": "private-draft", "kind": "case", "title": stale_marker}],
    )

    response = client.post("/api/search/summary", headers=_headers(auth), json=payload)

    assert response.status_code == 204
    assert len(requested) == 1
    assert requested[0].q == query and requested[0].principal.user_id == auth["user"]["id"]
    assert requested[0].principal.verified is auth["user"]["campusVerified"]
    assert "当前可见案例" in instructions_seen[0]
    assert stale_marker not in instructions_seen[0]
