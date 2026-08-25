from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = "e2e-api-key"
MODELS = ["e2e-model-a", "e2e-model-b"]
ANSWER = "隔离模型回答：已依据当前可见资源完成分析。"
CANDIDATE = {
    "text": "候选修订正文：教学目标、课堂任务与评价依据保持一致。",
    "reason": "让教学目标与课堂任务形成对应关系",
}
CANDIDATE_SECOND = {
    "text": "第二条候选正文：课堂任务、评价量规与教学目标逐项对应。",
    "reason": "补充可观察的课堂评价依据",
}


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


def _prompt(payload: dict) -> str:
    return "\n".join(message.get("content", "") for message in payload.get("messages", []))


def _context_line(prompt: str) -> str:
    return next((line for line in prompt.splitlines() if line.startswith("〔")), "")


def _answer(prompt: str) -> str:
    if "writing_candidate" in prompt:
        candidate = CANDIDATE_SECOND if "第二条" in prompt else CANDIDATE
        return json.dumps(candidate, ensure_ascii=False)
    context = _context_line(prompt)
    answer = f"{ANSWER}\n检索上下文：{context}" if context else ANSWER
    return f"过期回答：{answer}" if "慢速测试" in prompt else answer


def _pieces(payload: dict) -> tuple[list[str], float]:
    prompt = _prompt(payload)
    slow = "慢速测试" in prompt
    return list(_answer(prompt)), 0.12 if slow else 0.005


def _interrupted(payload: dict) -> bool:
    return "上游中断测试" in _prompt(payload)


def _send_pieces(handler, payload: dict) -> bool:
    pieces, delay = _pieces(payload)
    for index, piece in enumerate(pieces):
        handler.wfile.write(_event(piece))
        handler.wfile.flush()
        time.sleep(delay)
        if index == 2 and _interrupted(payload):
            return False
    return True


def _stream(handler, payload: dict) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()
    try:
        if not _send_pieces(handler, payload):
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
        if payload.get("model") not in MODELS or payload.get("stream") is not True:
            return _json(self, 422, {"error": "invalid request"})
        _stream(self, payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
