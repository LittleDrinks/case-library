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


def _pieces(payload: dict) -> tuple[list[str], float]:
    prompt = json.dumps(payload, ensure_ascii=False)
    slow = "慢速测试" in prompt
    cancel = "取消测试" in prompt
    candidate = CANDIDATE_SECOND if "第二条" in prompt else CANDIDATE
    answer = (
        json.dumps(candidate, ensure_ascii=False)
        if "writing_candidate" in prompt
        else ANSWER
    )
    return list(answer), 1.0 if cancel else 0.12 if slow else 0.005


def _interrupted(payload: dict) -> bool:
    """重试语义：首次请求的用户文本只出现一次；重试 Run 的模型上下文包含两份。"""
    prompt = json.dumps(payload, ensure_ascii=False)
    if "重试测试" in prompt:
        return prompt.count("重试测试") == 1
    return "上游中断测试" in prompt


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
        if not _send_pieces(handler, payload):
            return
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        return


def _structured(handler, payload: dict) -> None:
    schema = json.dumps(payload.get("response_format", {}), ensure_ascii=False)
    if "annotation_candidates" in schema:
        content = {"kind": "annotation_candidates", "items": [{
            "quote": "原文", "section": "小节", "content": "建议", "category": "theory"
        }]}
    else:
        candidate = CANDIDATE_SECOND if "第二条" in json.dumps(payload, ensure_ascii=False) else CANDIDATE
        content = {"kind": "writing_candidate", **candidate}
    _json(handler, 200, {"id": "structured-id", "object": "chat.completion", "created": 1,
        "model": payload.get("model", ""), "choices": [{"index": 0, "message": {
            "role": "assistant", "content": json.dumps(content, ensure_ascii=False), "refusal": None
        }, "logprobs": None, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


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
        if payload.get("response_format"):
            return _structured(self, payload)
        if payload.get("stream") is not True:
            return _json(self, 422, {"error": "invalid request"})
        _stream(self, payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
