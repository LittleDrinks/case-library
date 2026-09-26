from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "e2e-api-key"
MODELS = ["e2e-model-a", "e2e-model-b"]
ANSWER = "隔离模型回答：已依据当前可见资源完成分析。"


def _json(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _authorized(handler) -> bool:
    return handler.headers.get("Authorization") == f"Bearer {API_KEY}"


def _body(handler) -> dict:
    size = min(int(handler.headers.get("Content-Length", "0")), 128 * 1024)
    return json.loads(handler.rfile.read(size))


def _event(text: str) -> bytes:
    payload = {"choices": [{"delta": {"content": text}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _pieces(payload: dict) -> tuple[list[str], float]:
    prompt = json.dumps(payload, ensure_ascii=False)
    slow = "慢速测试" in prompt
    cancel = "取消测试" in prompt
    return list(ANSWER), 1.0 if cancel else 0.12 if slow else 0.005


def _interrupted(payload: dict) -> bool:
    """重试语义：首次请求的用户文本只出现一次；重试 Run 的模型上下文包含两份。"""
    prompt = json.dumps(payload, ensure_ascii=False)
    if "重试测试" in prompt:
        return prompt.count("重试测试") == 1
    return "上游中断测试" in prompt


def _pending_tool_round(payload: dict) -> bool:
    """最后一条 user 消息之后是否尚无 tool 结果（即本轮首次请求）。"""
    messages = payload.get("messages", [])
    last_user = max(i for i, m in enumerate(messages) if m.get("role") == "user")
    return not any(m.get("role") == "tool" for m in messages[last_user + 1:])


def _current_user_text(payload: dict) -> str:
    for message in reversed(payload.get("messages", [])):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return ""
    return ""


def _available_tools(payload: dict) -> set[str]:
    return {
        item.get("function", {}).get("name", "")
        for item in payload.get("tools", [])
    }


def _blank_draft_call(payload: dict) -> bool:
    return (
        "请完整生成全文" in _current_user_text(payload)
        and "write_document" in _available_tools(payload)
        and _pending_tool_round(payload)
    )


def _revision_call(payload: dict) -> bool:
    text = _current_user_text(payload)
    return (
        any(
            phrase in text
            for phrase in ("写入正文", "直接写入", "直接修改", "提出修改建议")
        )
        and "propose_revision" in _available_tools(payload)
        and _pending_tool_round(payload)
    )


def _revision_event(long_reason: bool = False) -> bytes:
    arguments = json.dumps({
        "start": 1,
        "end": 1 + len("当前案例测试正文"),
        "replacement": "通过建议应用的新正文",
        "reason": "补充可核对的背景事实并说明其与本段论点的关系。 " * (100 if long_reason else 1),
    }, ensure_ascii=False)
    payload = {"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "revision-call", "type": "function",
        "function": {"name": "propose_revision", "arguments": arguments},
    }]}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _blank_draft_event() -> bytes:
    arguments = json.dumps({
        "blocks": [
            {"type": "heading", "level": 1, "text": "AI完整稿"},
            {"type": "paragraph", "text": "AI生成正文"},
        ],
        "summary": "为新建空稿生成初稿",
    }, ensure_ascii=False)
    payload = {"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "blank-draft-call", "type": "function",
        "function": {"name": "write_document", "arguments": arguments},
    }]}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _tool_finish_event() -> bytes:
    return b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'


def _send_pieces(handler, payload: dict) -> bool:
    pieces, delay = _pieces(payload)
    for piece in pieces:
        handler.wfile.write(_event(piece))
        handler.wfile.flush()
        time.sleep(delay)
    return True


def _stream(handler, payload: dict) -> None:
    if _interrupted(payload):
        return _json(handler, 502, {"error": {"message": "upstream failed"}})
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()
    try:
        if _blank_draft_call(payload):
            for event in (_blank_draft_event(), _tool_finish_event()):
                handler.wfile.write(event)
                handler.wfile.flush()
        elif _revision_call(payload):
            for event in (_revision_event("长理由" in _current_user_text(payload)), _tool_finish_event()):
                handler.wfile.write(event)
                handler.wfile.flush()
        elif not _send_pieces(handler, payload):
            return
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        return


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            return _json(self, 200, {"ok": True})
        if self.path == "/v1/models" and _authorized(self):
            return _json(self, 200, {"data": [{"id": item} for item in MODELS]})
        _json(self, 401, {"error": "unauthorized"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions" or not _authorized(self):
            return _json(self, 401, {"error": "unauthorized"})
        try:
            payload = _body(self)
        except (ValueError, json.JSONDecodeError):
            return _json(self, 400, {"error": "invalid request"})
        if payload.get("model") not in MODELS:
            return _json(self, 422, {"error": "invalid request"})
        if payload.get("stream") is not True:
            return _json(self, 422, {"error": "invalid request"})
        _stream(self, payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
