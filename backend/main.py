#!/usr/bin/env python3
"""FastAPI entry point for the case library."""

import hashlib
import os
import sys
import time
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(__file__))

from case_processor import process_new_case
from database import (
    count_cases,
    create_case,
    create_user,
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


def get_current_user(headers):
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if not auth_header:
        return None

    try:
        token = auth_header.replace("Bearer ", "").replace("bearer ", "")
        username = token.split("_")[0]
        return get_user_by_username(username)
    except Exception as exc:
        print(f"Failed to resolve current user: {exc}")
        return None


init_db()
search_engine = CaseSearchEngine()

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
UPLOAD_DIR = os.path.join(ROOT_DIR, "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if password_hash != user["password"]:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = f"{user['username']}_{int(time.time())}"
    return {
        "success": True,
        "data": {
            "id": user["id"],
            "username": user["username"],
            "role": user.get("role", "user"),
            "token": token,
        },
    }


@app.post("/api/auth/register")
async def register(username: str = Form(...), password: str = Form(...)):
    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="用户名长度不能少于3位")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于6位")

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user_id = create_user(username, password_hash, "user")

    return {
        "success": True,
        "message": "注册成功",
        "data": {"id": user_id, "username": username, "role": "user"},
    }


@app.get("/api/cases")
async def list_cases(
    status: Optional[str] = "approved",
    offset: int = 0,
    limit: int = 50,
    author: Optional[str] = None,
    request: Request = None,
):
    current_user = get_current_user(dict(request.headers)) if request else None

    if author and current_user:
        if current_user.get("role") != "admin" and current_user.get("username") != author:
            raise HTTPException(status_code=403, detail="无权查看该用户案例")

    cases = get_all_cases(status, offset, limit, author)
    return {"success": True, "data": cases, "total": count_cases(status, author)}


@app.get("/api/cases/{case_id}")
async def get_case_detail(case_id: int, increment_view: bool = True):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    if increment_view:
        increment_view_count(case_id)

    return {"success": True, "data": case}


@app.post("/api/cases")
async def create_new_case(
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(""),
    department: str = Form(""),
    type: str = Form("TYPE_A"),
    theme: str = Form("铸魂育人"),
    status: str = Form("pending_review"),
    auto_process: bool = Form(False),
):
    type = type or "TYPE_A"
    theme = theme or "铸魂育人"

    if auto_process:
        case_ids = process_new_case(content, title, author, department, type, theme)
        return {"success": True, "message": "案例创建成功", "case_ids": case_ids}

    case_id = create_case(
        {
            "title": title,
            "type": type,
            "theme": theme,
            "content": content,
            "author": author,
            "department": department,
            "status": status,
        }
    )
    return {"success": True, "message": "案例创建成功", "case_id": case_id}


async def _update_existing_case_impl(
    case_id: int,
    title: Optional[str],
    content: Optional[str],
    author: Optional[str],
    department: Optional[str],
    type: Optional[str],
    theme: Optional[str],
    status: Optional[str],
    updated_by: str,
    change_reason: str,
):
    case_data = {}
    for field, value in {
        "title": title,
        "content": content,
        "author": author,
        "department": department,
        "type": type,
        "theme": theme,
        "status": status,
    }.items():
        if value is not None and value != "":
            case_data[field] = value

    if not update_case(case_id, case_data, updated_by, change_reason):
        raise HTTPException(status_code=404, detail="案例更新失败")

    return {"success": True, "message": "案例更新成功"}


@app.put("/api/cases/{case_id}")
async def update_existing_case(
    case_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    type: Optional[str] = Form(None),
    theme: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    updated_by: str = Form("system"),
    change_reason: str = Form(""),
):
    return await _update_existing_case_impl(
        case_id, title, content, author, department, type, theme, status, updated_by, change_reason
    )


@app.post("/api/cases/{case_id}")
async def update_existing_case_post_compat(
    case_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    type: Optional[str] = Form(None),
    theme: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    updated_by: str = Form("system"),
    change_reason: str = Form(""),
):
    return await _update_existing_case_impl(
        case_id, title, content, author, department, type, theme, status, updated_by, change_reason
    )


@app.delete("/api/cases/{case_id}")
async def delete_case_endpoint(case_id: int):
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
async def submit_case_for_review(case_id: int):
    if not submit_for_review(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True, "message": "案例已提交审核"}


@app.post("/api/cases/{case_id}/like")
async def like_case(case_id: int):
    if not increment_like_count(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True, "message": "点赞成功"}


@app.post("/api/cases/{case_id}/unlike")
async def unlike_case(case_id: int):
    if not decrement_like_count(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True, "message": "取消点赞成功"}


@app.get("/api/search")
async def search_cases_endpoint(q: str, status: Optional[str] = "approved"):
    results = search_engine.search(q, status)
    return {"success": True, "data": results, "query": q}


@app.get("/api/search/advanced")
async def advanced_search(
    type: Optional[str] = None,
    theme: Optional[str] = None,
    status: str = "approved",
    keyword: Optional[str] = None,
    limit: int = 50,
):
    results = search_engine.advanced_filter(
        type_filter=type,
        theme_filter=theme,
        status_filter=status,
        keyword_filter=keyword,
        limit=limit,
    )
    return {"success": True, "data": results}


@app.get("/api/recommendations/{case_id}")
async def get_recommendations_endpoint(case_id: int, limit: int = 5):
    return {"success": True, "data": search_engine.get_recommendations(case_id, limit)}


@app.get("/api/trending")
async def get_trending_cases(limit: int = 10):
    return {"success": True, "data": search_engine.get_trending(limit)}


@app.get("/api/latest")
async def get_latest_cases(limit: int = 10):
    return {"success": True, "data": search_engine.get_latest(limit)}


@app.post("/api/reviews/{case_id}")
async def review_case_endpoint(
    case_id: int,
    reviewer: str = Form(...),
    comment: str = Form(...),
    status: str = Form(...),
):
    if not review_case(case_id, reviewer, comment, status):
        raise HTTPException(status_code=400, detail="审核失败")
    return {"success": True, "message": "审核完成"}


@app.get("/api/reviews/{case_id}")
async def get_case_reviews(case_id: int):
    return {"success": True, "data": get_reviews(case_id)}


@app.get("/api/versions/{case_id}")
async def get_case_version_history(case_id: int):
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
                "approved_pending_deploy": "已通过",
                "needs_revision": "需修改",
                "deleted": "已删除",
            },
        },
    }


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def read_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{path:path}")
async def catch_all(path: str):
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
