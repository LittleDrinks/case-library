#!/usr/bin/env python3
"""FastAPI entry point for the case library."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))

from case_processor import process_new_case
from database import (
    authenticate_user,
    change_user_password,
    count_cases,
    create_case,
    decrement_like_count,
    delete_case,
    get_all_cases,
    get_case,
    get_case_versions,
    get_reviews,
    get_statistics,
    get_user_by_username,
    increment_like_count,
    increment_view_count,
    init_db,
    review_case,
    set_case_hidden,
    submit_for_review,
    update_case,
)
from search_engine import CaseSearchEngine

app = FastAPI(title="Case Library API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"success": False, "detail": str(exc)})


AUTH_SECRET = os.getenv("AUTH_SECRET")
if not AUTH_SECRET:
    AUTH_SECRET = secrets.token_urlsafe(32)
    print(
        "WARNING: AUTH_SECRET is not set. A random secret was generated for this "
        "process; tokens will be invalidated on restart. Set AUTH_SECRET in production."
    )
_AUTH_SECRET_BYTES = AUTH_SECRET.encode("utf-8")
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL", str(7 * 24 * 3600)))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def create_auth_token(username: str) -> str:
    now = int(time.time())
    payload = {"u": username, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_AUTH_SECRET_BYTES, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def verify_auth_token(token: str) -> str | None:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            _AUTH_SECRET_BYTES, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    username = payload.get("u")
    if not isinstance(username, str) or not username:
        return None
    return username


def get_current_user(headers):
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    username = verify_auth_token(parts[1].strip())
    if not username:
        return None
    user = get_user_by_username(username)
    if user and user.get("status") == "active":
        return user
    return None


def get_case_owner_username(case: dict) -> str:
    return case.get("owner_username") or case.get("author") or ""


def _ensure_case_history_visible(case_id: int, current_user: dict | None) -> dict:
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    is_admin = bool(current_user and current_user.get("role") == "admin")
    is_owner = bool(current_user and current_user.get("username") == get_case_owner_username(case))
    if is_admin or is_owner:
        return case
    if case.get("status") == "approved" and not case.get("is_hidden"):
        return case
    raise HTTPException(status_code=403, detail="无权查看该案例的历史记录")


init_db()
search_engine = CaseSearchEngine()

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOAD_DIR = ROOT_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_auth_token(user["username"])
    return {
        "success": True,
        "data": {
            "id": user["id"],
            "username": user["username"],
            "role": user.get("role", "normal"),
            "nickname": user.get("nickname", ""),
            "must_change_password": bool(user.get("must_change_password", False)),
            "status": user.get("status", "active"),
            "token": token,
        },
    }


@app.post("/api/auth/change-password")
async def change_password(
    username: str = Form(...),
    old_password: str = Form(...),
    new_password: str = Form(...),
):
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码长度不能少于8位")
    if not change_user_password(username, old_password, new_password):
        raise HTTPException(status_code=400, detail="用户名或原密码错误")
    return {"success": True, "message": "密码修改成功"}


@app.get("/api/cases")
async def list_cases(
    request: Request,
    status: str | None = "approved",
    offset: int = 0,
    limit: int = 50,
    author: str | None = None,
):
    current_user = get_current_user(dict(request.headers))
    if status == "draft" and not author:
        if not current_user:
            raise HTTPException(status_code=401, detail="请先登录")
        author = current_user.get("username")

    if author:
        if not current_user:
            raise HTTPException(status_code=401, detail="请先登录")
        if current_user.get("role") != "admin" and current_user.get("username") != author:
            raise HTTPException(status_code=403, detail="无权查看该用户案例")
        if status == "draft" and current_user.get("username") != author:
            raise HTTPException(status_code=403, detail="无权查看该用户草稿")

    is_admin = bool(current_user and current_user.get("role") == "admin")
    is_self_view = bool(author and current_user and current_user.get("username") == author)
    is_public_library = (status == "approved") and not author
    include_hidden = (is_admin or is_self_view) and not is_public_library

    return {
        "success": True,
        "data": get_all_cases(status, offset, limit, author, include_hidden=include_hidden),
        "total": count_cases(status, author, include_hidden=include_hidden),
    }


@app.get("/api/cases/{case_id}")
async def get_case_detail(case_id: int, request: Request, increment_view: bool = True):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    current_user = get_current_user(dict(request.headers))
    owner_username = get_case_owner_username(case)
    is_admin = bool(current_user and current_user.get("role") == "admin")
    is_owner = bool(current_user and current_user.get("username") == owner_username)

    if case.get("status") == "draft" and not is_owner:
        raise HTTPException(status_code=403, detail="无权查看该草稿")

    if case.get("is_hidden") and not (is_admin or is_owner):
        raise HTTPException(status_code=404, detail="案例不存在")

    if increment_view and not increment_view_count(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")

    return {"success": True, "data": case}


@app.post("/api/cases")
async def create_new_case(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    department: str = Form(""),
    type: str = Form("TYPE_A"),
    theme: str = Form("铸魂育人"),
    status: str = Form("pending_review"),
    auto_process: bool = Form(False),
):
    current_user = get_current_user(dict(request.headers))
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    if status not in ("draft", "pending_review"):
        raise HTTPException(status_code=400, detail="非法的初始状态")

    owner_username = current_user.get("username", "")
    author = current_user.get("nickname") or owner_username

    case_type = type or "TYPE_A"
    case_theme = theme or "铸魂育人"

    if auto_process:
        case_ids = process_new_case(
            content, title, author, department, case_type, case_theme, owner_username
        )
        return {"success": True, "message": "案例创建成功", "case_ids": case_ids}

    case_id = create_case(
        {
            "title": title,
            "type": case_type,
            "theme": case_theme,
            "content": content,
            "author": author,
            "owner_username": owner_username,
            "department": department,
            "status": status,
        }
    )
    return {"success": True, "message": "案例创建成功", "case_id": case_id}


async def _update_existing_case_impl(
    case_id: int,
    title: str | None,
    content: str | None,
    author: str | None,
    department: str | None,
    type: str | None,
    theme: str | None,
    change_reason: str,
    current_user: dict | None,
):
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    existing_case = get_case(case_id)
    if not existing_case:
        raise HTTPException(status_code=404, detail="案例不存在")
    owner_username = get_case_owner_username(existing_case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权修改该案例")
    if existing_case.get("status") == "draft" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权修改该草稿")

    case_data = {}
    for field, value in {
        "title": title,
        "content": content,
        "author": author,
        "department": department,
        "type": type,
        "theme": theme,
    }.items():
        if value is not None and value != "":
            case_data[field] = value

    updated_by = current_user.get("username", "")
    if not update_case(case_id, case_data, updated_by, change_reason):
        if get_case(case_id):
            raise HTTPException(status_code=400, detail="案例没有实际变更")
        raise HTTPException(status_code=404, detail="案例不存在")

    return {"success": True, "message": "案例更新成功"}


@app.put("/api/cases/{case_id}")
async def update_existing_case(
    case_id: int,
    request: Request,
    title: str | None = Form(None),
    content: str | None = Form(None),
    author: str | None = Form(None),
    department: str | None = Form(None),
    type: str | None = Form(None),
    theme: str | None = Form(None),
    change_reason: str = Form(""),
):
    current_user = get_current_user(dict(request.headers))
    return await _update_existing_case_impl(
        case_id, title, content, author, department, type, theme, change_reason, current_user
    )


@app.post("/api/cases/{case_id}")
async def update_existing_case_post_compat(
    case_id: int,
    request: Request,
    title: str | None = Form(None),
    content: str | None = Form(None),
    author: str | None = Form(None),
    department: str | None = Form(None),
    type: str | None = Form(None),
    theme: str | None = Form(None),
    change_reason: str = Form(""),
):
    current_user = get_current_user(dict(request.headers))
    return await _update_existing_case_impl(
        case_id, title, content, author, department, type, theme, change_reason, current_user
    )


@app.delete("/api/cases/{case_id}")
async def delete_case_endpoint(case_id: int, request: Request):
    current_user = get_current_user(dict(request.headers))
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    owner_username = get_case_owner_username(case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权删除该案例")
    if case.get("status") == "draft" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权删除该草稿")

    result = delete_case(case_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail="案例不存在")

    return {
        "success": True,
        "message": "案例删除成功",
        "deleted_stats": {
            "was_in_library": result.get("was_in_library", False),
            "view_count": result.get("view_count", 0),
            "like_count": result.get("like_count", 0),
            "type": result.get("type"),
            "theme": result.get("theme"),
        },
    }


@app.post("/api/cases/{case_id}/submit")
async def submit_case_for_review(case_id: int, request: Request):
    current_user = get_current_user(dict(request.headers))
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    case = get_case(case_id, include_deleted=True)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    owner_username = get_case_owner_username(case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权提交该案例")

    if not submit_for_review(case_id):
        raise HTTPException(status_code=400, detail="案例状态不允许提交审核")
    return {"success": True, "message": "案例已提交审核"}


@app.post("/api/cases/{case_id}/like")
async def like_case(case_id: int):
    if not increment_like_count(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True, "message": "点赞成功"}


@app.post("/api/cases/{case_id}/unlike")
async def unlike_case(case_id: int):
    if not decrement_like_count(case_id):
        if get_case(case_id):
            raise HTTPException(status_code=400, detail="点赞数已经为0")
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True, "message": "取消点赞成功"}


@app.get("/api/search")
async def search_cases_endpoint(q: str, status: str | None = "approved"):
    return {"success": True, "data": search_engine.search(q, status), "query": q}


@app.get("/api/search/advanced")
async def advanced_search(
    type: str | None = None,
    theme: str | None = None,
    status: str = "approved",
    keyword: str | None = None,
    limit: int = 50,
):
    return {
        "success": True,
        "data": search_engine.advanced_filter(
            type_filter=type,
            theme_filter=theme,
            status_filter=status,
            keyword_filter=keyword,
            limit=limit,
        ),
    }


@app.get("/api/recommendations/{case_id}")
async def get_recommendations_endpoint(case_id: int, limit: int = 5):
    return {"success": True, "data": search_engine.get_recommendations(case_id, limit)}


@app.get("/api/trending")
async def get_trending_cases(limit: int = 10):
    return {"success": True, "data": search_engine.get_trending(limit)}


@app.get("/api/latest")
async def get_latest_cases(limit: int = 10):
    return {"success": True, "data": search_engine.get_latest(limit)}


@app.post("/api/cases/{case_id}/visibility")
async def toggle_case_visibility(
    case_id: int,
    request: Request,
    hidden: bool = Form(...),
):
    current_user = get_current_user(dict(request.headers))
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可以隐藏或展示案例")

    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")

    if not set_case_hidden(case_id, hidden):
        raise HTTPException(status_code=400, detail="操作失败")

    return {
        "success": True,
        "message": "案例已隐藏" if hidden else "案例已展示",
        "is_hidden": bool(hidden),
    }


@app.post("/api/reviews/{case_id}")
async def review_case_endpoint(
    case_id: int,
    request: Request,
    comment: str = Form(...),
    status: str = Form(...),
):
    current_user = get_current_user(dict(request.headers))
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可以审核案例")
    reviewer = current_user.get("username", "")
    if not review_case(case_id, reviewer, comment, status):
        raise HTTPException(status_code=400, detail="审核失败")
    return {"success": True, "message": "审核完成"}


@app.get("/api/reviews/{case_id}")
async def get_case_reviews(case_id: int, request: Request):
    current_user = get_current_user(dict(request.headers))
    _ensure_case_history_visible(case_id, current_user)
    return {"success": True, "data": get_reviews(case_id)}


@app.get("/api/versions/{case_id}")
async def get_case_version_history(case_id: int, request: Request):
    current_user = get_current_user(dict(request.headers))
    _ensure_case_history_visible(case_id, current_user)
    return {"success": True, "data": get_case_versions(case_id)}


@app.get("/api/statistics")
async def get_statistics_endpoint():
    return {"success": True, "data": get_statistics()}


@app.get("/api/constants")
async def get_constants():
    return {
        "success": True,
        "data": {
            "case_types": {
                "TYPE_A": "思政课教学案例",
                "TYPE_B": "课程思政共享资源案例",
                "TYPE_C": "实践育人案例",
            },
            "themes": ["强国建设", "实践育人", "数字赋能", "铸魂育人"],
            "statuses": {
                "draft": "草稿",
                "pending_review": "待审核",
                "approved": "已通过",
                "needs_revision": "已驳回",
            },
        },
    }


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def read_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{path:path}")
async def catch_all(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
