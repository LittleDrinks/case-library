#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
思政教学案例智能平台 — 服务端

职责：
1. 托管 app/ 下的前端；
2. /api/ai/chat      —— OpenAI 兼容 Chat 接口服务端代理（API Key 只存在服务端，支持 SSE 流式）；
3. /api/web-search   —— Tavily 联网检索（密钥只存在服务端）；
4. /api/fetch-url    —— 公开 URL 采集（生成可引用的内容副本，原始 URL 保留）；
5. /api/export-docx  —— 将案例及成套教学材料导出为 .docx（页脚注入追踪元数据）；
6. /api/auth/login   —— 演示登录：账号 ID 换 HMAC token（12h，无密码，ADR 0009）；
7. /api/files        —— 资料文件库：列表/上传/下载/删除，文件落盘 files/，按密级服务端强制；
   上传 md/txt/docx 自动抽取纯文本，GET /api/files/{fid}/text 在线查看；
8. /api/knowledge    —— 知识库在线导入（admin，markdown 按 # 章/### 节解析）与公开查询；
9. /api/constants    —— 健康检查与能力开关；
10. /api/search      —— 服务端语料检索（BM25 + 中文 bigram，惰性索引，按用户密级过滤素材）；
11. /api/ai/agent    —— 统一 AI 入口（MoA 多智能体编排：主Agent/资料管理员/写作手/内容审校员，SSE）。

仅依赖标准库 + python-docx。运行：python3 server.py [port]
"""
import base64
import hashlib
import hmac
import json
import math
import os
import queue
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "app")


def load_env(path):
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


ENV = load_env(os.path.join(ROOT, ".env"))
AI_BASE_URL = ENV.get("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = ENV.get("AI_API_KEY", "")
AI_MODELS = [m.strip() for m in ENV.get("AI_MODELS", "").split(",") if m.strip()]
AI_DEFAULT_MODEL = ENV.get("AI_DEFAULT_MODEL", "qwen-plus")
AI_TIMEOUT = int(ENV.get("AI_TIMEOUT_SECONDS", "60") or 60)
AI_REVIEW_ENABLED = ENV.get("AI_REVIEW_ENABLED", "").lower() in ("1", "true", "yes")
TAVILY_API_KEY = ENV.get("TAVILY_API_KEY", "")
# MoA 多智能体编排模型（.env 可选覆盖；未配置时用以下默认值。写作手主候选 = AI_DEFAULT_MODEL）
MOA_MODEL_ORCHESTRATOR = ENV.get("MOA_MODEL_ORCHESTRATOR", "") or "qwen-plus"
MOA_MODEL_LIBRARIAN = ENV.get("MOA_MODEL_LIBRARIAN", "") or "qwen-plus"
MOA_MODEL_WRITER_ALT = ENV.get("MOA_MODEL_WRITER_ALT", "") or "qwen-plus"
# 注意：模型网关对大小写敏感，R1 的可用名是小写 "deepseek-r1"（大写会被 400 拒绝）
MOA_MODEL_REVIEWER = ENV.get("MOA_MODEL_REVIEWER", "") or "deepseek-r1"

UA = "CaseLibrary/1.0 (+shanghai-university-sizheng-case-library)"

# ------------------------------------------------------------ 演示鉴权与文件库（ADR 0009）
APP_SECRET = ENV.get("APP_SECRET", "")
FILES_DIR = os.path.join(ROOT, "files")
INDEX_FILE = os.path.join(FILES_DIR, "index.json")
USERS_FILE = os.path.join(FILES_DIR, "users.json")
KNOWLEDGE_FILE = os.path.join(FILES_DIR, "knowledge.json")
TOKEN_TTL_SECONDS = 12 * 3600
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LEVEL_NAMES = ["公开", "校内", "受限"]
_INDEX_LOCK = threading.Lock()


def _b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(uid):
    payload = _b64url(json.dumps(
        {"uid": uid, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        separators=(",", ":")).encode("utf-8"))
    sig = _b64url(hmac.new(APP_SECRET.encode("utf-8"), payload.encode("ascii"),
                           hashlib.sha256).digest())
    return payload + "." + sig


def read_token(tok):
    """校验 HMAC token，返回 uid；无效/过期返回 None。"""
    if not APP_SECRET or not tok or "." not in tok:
        return None
    payload, sig = tok.rsplit(".", 1)
    want = _b64url(hmac.new(APP_SECRET.encode("utf-8"), payload.encode("ascii"),
                            hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return None
    try:
        data = json.loads(_b64url_decode(payload))
    except Exception:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("uid")


def load_users():
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return {u["id"]: u for u in json.load(f)}
    except Exception:
        return {}


def auth_user(handler):
    """从 Authorization: Bearer 解析登录用户；未登录返回 None（按公开级看待）。"""
    ah = handler.headers.get("Authorization") or ""
    uid = read_token(ah[7:].strip()) if ah.startswith("Bearer ") else None
    return load_users().get(uid) if uid else None


def req_max_level(user):
    return user["maxLevel"] if user else 0


def load_index():
    try:
        with open(INDEX_FILE, encoding="utf-8") as f:
            return json.load(f).get("files", [])
    except Exception:
        return []


def save_index(entries):
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"files": entries}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, INDEX_FILE)


def entry_to_material(e):
    """上传文件条目 → 前端素材记录（种子素材的记录在 app/data.js，不走这里）。"""
    return {
        "id": e["materialId"], "fileId": e["id"], "uploaded": True,
        "title": e.get("title") or e["name"], "kind": "文档", "tags": ["教师上传"],
        "source": "教师上传 · " + (e.get("byName") or e.get("by") or ""),
        "sourceUrl": "", "publishedAt": e.get("at", ""), "collectedAt": e.get("at", ""),
        "level": e["level"], "credibility": "normal",
        "scope": "全体教师", "status": "正常",
        "summary": e.get("summary") or "", "excerpt": "",
        "textPath": e.get("textPath"),
    }


def api_login(payload):
    if not APP_SECRET:
        return {"ok": False, "error": "服务端未配置 APP_SECRET"}
    users = load_users()
    if not users:
        return {"ok": False, "error": "服务端缺少 files/users.json，请先运行 tools/build_data.py"}
    uid = (payload.get("userId") or "").strip()
    u = users.get(uid)
    if not u:
        return {"ok": False, "error": "账号不存在"}
    return {"ok": True, "token": make_token(uid), "user": u}


def api_files_list(user):
    ml = req_max_level(user)
    entries = [e for e in load_index() if e.get("level", 0) <= ml]
    return {
        "ok": True,
        "files": {e["id"]: {"name": e["name"], "size": e.get("size", 0), "textPath": e.get("textPath")} for e in entries},
        "materials": [entry_to_material(e) for e in entries if not e.get("seed")],
    }


def extract_upload_text(full_path, ext):
    """按扩展名抽取纯文本（md/txt 直接读，docx 用 python-docx）；
    不支持的类型或抽取失败返回 None，不影响上传本身。"""
    ext = ext.lower()
    try:
        if ext in (".md", ".markdown", ".txt"):
            with open(full_path, encoding="utf-8") as f:
                return f.read()
        if ext == ".docx":
            from docx import Document
            doc = Document(full_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return None
    return None


def api_file_upload(user, payload):
    if not user:
        return {"ok": False, "error": "未登录或登录已过期，请重新切换账号"}, 401
    if not user.get("admin"):
        return {"ok": False, "error": "仅案例管理员可上传资料文件"}, 403
    title = (payload.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "请填写素材标题"}, 400
    try:
        level = int(payload.get("level"))
    except Exception:
        level = -1
    if level not in (0, 1, 2):
        return {"ok": False, "error": "密级取值无效"}, 400
    name = os.path.basename((payload.get("filename") or "").strip()) or "file.bin"
    try:
        raw = base64.b64decode(payload.get("dataBase64") or "")
    except Exception:
        return {"ok": False, "error": "文件内容编码无效"}, 400
    if not raw:
        return {"ok": False, "error": "文件为空"}, 400
    if len(raw) > MAX_UPLOAD_BYTES:
        return {"ok": False, "error": "文件超过 20MB 上限"}, 400

    fid = "f-up-" + uuid.uuid4().hex[:12]
    ext = re.sub(r"[^A-Za-z0-9.]", "", os.path.splitext(name)[1])[:10]
    rel = "up/" + fid + ext
    os.makedirs(os.path.join(FILES_DIR, "up"), exist_ok=True)
    with open(os.path.join(FILES_DIR, rel), "wb") as f:
        f.write(raw)
    entry = {
        "id": fid, "materialId": "m-up-" + uuid.uuid4().hex[:12],
        "name": name, "path": rel, "size": len(raw), "level": level,
        "seed": False, "title": title,
        "summary": (payload.get("summary") or "").strip(),
        "by": user["id"], "byName": user.get("name", ""),
        "at": time.strftime("%Y-%m-%d %H:%M"),
    }
    # 在线文本抽取：成功则落盘 up/{fid}.txt 并在索引条目上记录 textPath
    text = extract_upload_text(os.path.join(FILES_DIR, rel), ext)
    if text and text.strip():
        text_rel = "up/" + fid + ".txt"
        with open(os.path.join(FILES_DIR, text_rel), "w", encoding="utf-8") as f:
            f.write(text)
        entry["textPath"] = text_rel
    with _INDEX_LOCK:
        entries = load_index()
        entries.append(entry)
        save_index(entries)
    mark_search_dirty()
    return {"ok": True, "material": entry_to_material(entry)}, 200


def find_entry(fid):
    for e in load_index():
        if e.get("id") == fid:
            return e
    return None


FILE_CTYPES = {
    ".md": "text/markdown; charset=utf-8", ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".zip": "application/zip", ".rar": "application/vnd.rar",
}


def api_file_download(user, fid):
    e = find_entry(fid)
    if not e:
        return None, {"ok": False, "error": "文件不存在"}, 404
    level = e.get("level", 0)
    if level > req_max_level(user):
        return None, {"ok": False, "error":
                      "该文件密级为「%s」，超出你的授权范围" % LEVEL_NAMES[level]}, 403
    full = os.path.join(FILES_DIR, e["path"])
    if not os.path.isfile(full):
        return None, {"ok": False, "error": "文件已丢失（索引在、实体不在）"}, 404
    with open(full, "rb") as f:
        data = f.read()
    ctype = FILE_CTYPES.get(os.path.splitext(e["name"])[1].lower(),
                            "application/octet-stream")
    return (data, ctype, e["name"]), None, 200


def api_file_text(user, fid):
    """在线文本：鉴权与密级检查与文件下载一致。"""
    e = find_entry(fid)
    if not e:
        return {"ok": False, "error": "文件不存在"}, 404
    level = e.get("level", 0)
    if level > req_max_level(user):
        return {"ok": False, "error":
                "该文件密级为「%s」，超出你的授权范围" % LEVEL_NAMES[level]}, 403
    tp = e.get("textPath")
    if not tp:
        return {"ok": False, "error":
                "该文件没有可在线查看的文本（仅 md/txt/docx 上传时自动抽取）"}, 404
    full = os.path.join(FILES_DIR, tp)
    if not os.path.isfile(full):
        return {"ok": False, "error": "文本副本已丢失（索引在、实体不在）"}, 404
    with open(full, encoding="utf-8") as f:
        return {"ok": True, "text": f.read()}, 200


def api_file_delete(user, fid):
    if not user:
        return {"ok": False, "error": "未登录或登录已过期，请重新切换账号"}, 401
    if not user.get("admin"):
        return {"ok": False, "error": "仅案例管理员可删除资料文件"}, 403
    with _INDEX_LOCK:
        entries = load_index()
        e = next((x for x in entries if x.get("id") == fid), None)
        if not e:
            return {"ok": False, "error": "文件不存在"}, 404
        if e.get("seed"):
            return {"ok": False, "error": "种子素材不能删除，只能停用"}, 403
        save_index([x for x in entries if x.get("id") != fid])
    try:
        os.remove(os.path.join(FILES_DIR, e["path"]))
    except OSError:
        pass
    if e.get("textPath"):
        try:
            os.remove(os.path.join(FILES_DIR, e["textPath"]))
        except OSError:
            pass
    mark_search_dirty()
    return {"ok": True}, 200


def api_file_patch(user, fid, payload):
    """调整文件密级（仅 admin）。种子条目重建后会回到 build_data.py 默认值。"""
    if not user:
        return {"ok": False, "error": "未登录或登录已过期，请重新切换账号"}, 401
    if not user.get("admin"):
        return {"ok": False, "error": "仅案例管理员可调整文件密级"}, 403
    try:
        level = int(payload.get("level"))
    except Exception:
        level = -1
    if level not in (0, 1, 2):
        return {"ok": False, "error": "密级取值无效"}, 400
    with _INDEX_LOCK:
        entries = load_index()
        e = next((x for x in entries if x.get("id") == fid), None)
        if not e:
            return {"ok": False, "error": "文件不存在"}, 404
        e["level"] = level
        save_index(entries)
    mark_search_dirty()
    return {"ok": True}, 200


# ---------------------------------------------------------------- 知识库在线导入
def load_knowledge():
    try:
        with open(KNOWLEDGE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_knowledge(sources):
    tmp = KNOWLEDGE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=1)
    os.replace(tmp, KNOWLEDGE_FILE)


def _md_clean(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_knowledge_markdown(source_id, markdown):
    """与 tools/build_data.py 教材解析同规则：# 为章、### 为节；
    产出 chapters/sections（节含 id/title/text），id 以 sourceId 为前缀保证跨来源唯一。"""
    chapters, sections = [], []
    ch, sec, buf = None, None, []

    def flush():
        nonlocal buf
        body = _md_clean("\n".join(buf))
        buf = []
        if sec is not None:
            sections.append({
                "id": "%s-%02d-%02d" % (source_id, ch["index"], sec["index"]),
                "chapterId": ch["id"],
                "chapter": ch["title"],
                "index": sec["index"],
                "title": sec["title"],
                "text": body,
                "chars": len(body),
            })
        elif ch is not None and body:
            ch["intro"] = (ch.get("intro") or "") + body + "\n"

    for ln in markdown.splitlines():
        m1 = re.match(r"^#\s+(.+)$", ln)
        m3 = re.match(r"^###\s+(.+)$", ln)
        if m1:
            flush()
            ch = {"id": "%s-c%02d" % (source_id, len(chapters) + 1),
                  "index": len(chapters) + 1, "title": m1.group(1).strip()}
            chapters.append(ch)
            sec = None
        elif m3 and ch is not None:
            flush()
            sec = {"index": sum(1 for s in sections if s["chapterId"] == ch["id"]) + 1,
                   "title": m3.group(1).strip()}
        else:
            buf.append(ln)
    flush()
    for c in chapters:
        c["intro"] = _md_clean(c.get("intro") or "")
        c["sections"] = ["%s-%02d-%02d" % (source_id, c["index"], s["index"])
                         for s in sections if s["chapterId"] == c["id"]]
    return chapters, sections


def api_knowledge_import(user, payload):
    """导入 markdown 教材为知识来源（仅 admin）；同名来源覆盖而非追加。"""
    if not user:
        return {"ok": False, "error": "未登录或登录已过期，请重新切换账号"}, 401
    if not user.get("admin"):
        return {"ok": False, "error": "仅案例管理员可导入知识库"}, 403
    name = (payload.get("name") or "").strip()
    markdown = payload.get("markdown") or ""
    if not name:
        return {"ok": False, "error": "缺少知识来源名称 name"}, 400
    if not markdown.strip():
        return {"ok": False, "error": "缺少 markdown 内容"}, 400
    with _INDEX_LOCK:
        sources = load_knowledge()
        old = next((s for s in sources if s.get("name") == name), None)
        source_id = old["sourceId"] if old else "kn-%d-%s" % (
            int(time.time()), uuid.uuid4().hex[:4])
        chapters, sections = parse_knowledge_markdown(source_id, markdown)
        entry = {
            "sourceId": source_id, "name": name,
            "source": (payload.get("source") or "").strip(),
            "importedAt": time.strftime("%Y-%m-%d %H:%M"),
            "by": user["id"], "byName": user.get("name", ""),
            "chapters": chapters, "sections": sections,
        }
        sources = [s for s in sources if s.get("name") != name] + [entry]
        save_knowledge(sources)
    mark_search_dirty()
    return {"ok": True, "sourceId": source_id, "name": name,
            "chapters": len(chapters), "sections": len(sections)}, 200


# ------------------------------------------------------------ 服务端检索索引（BM25）
_SEARCH_LOCK = threading.Lock()
_SEARCH_STATE = {"version": 0, "built_version": -1, "index": None}
BOOK_MD = os.path.join(FILES_DIR, "seed", "book", "zrbjf-2025.md")
LEARN_DIR = os.path.join(FILES_DIR, "seed", "learn")
BM25_K1, BM25_B = 1.5, 0.75


def mark_search_dirty():
    """语料变化（上传/删除/调整密级/知识导入）后置脏，下次检索时惰性重建索引。"""
    with _SEARCH_LOCK:
        _SEARCH_STATE["version"] += 1


def _tokenize(text):
    """中文按字符 bigram 分词，非中文（字母/数字）按词。"""
    tokens = []
    for part in re.findall(r"[a-z0-9]+|[㐀-䶿一-鿿]+", (text or "").lower()):
        if re.match(r"^[a-z0-9]+$", part):
            tokens.append(part)
        elif len(part) == 1:
            tokens.append(part)
        else:
            tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
    return tokens


def _build_search_index():
    """收集四类语料并构建 Okapi BM25 索引。
    doc: {id, cls(knowledge|material), title, chapter, source, text, level, credibility}"""
    docs = []

    def add(cls, doc_id, title, chapter, text, source="", level=0, credibility=""):
        text = (text or "").strip()
        if not doc_id or not text:
            return
        docs.append({
            "id": doc_id, "cls": cls, "title": (title or doc_id).strip(),
            "chapter": (chapter or "").strip(), "source": source, "text": text,
            "level": level, "credibility": credibility,
        })

    # 1) 教材：与知识库导入同规则（# 章 / ### 节）切节
    try:
        with open(BOOK_MD, encoding="utf-8") as f:
            _chapters, sections = parse_knowledge_markdown("book-zrbjf-2025", f.read())
        for s in sections:
            add("knowledge", s["id"], s["title"], s["chapter"], s["text"])
    except OSError:
        pass

    # 2) 学习资料：每期一条（标题 + 正文前 800 字），全员可见
    entries_by_path = {e.get("path"): e for e in load_index()}
    if os.path.isdir(LEARN_DIR):
        for name in sorted(os.listdir(LEARN_DIR)):
            if not name.startswith("lr-") or not name.endswith(".md"):
                continue
            try:
                with open(os.path.join(LEARN_DIR, name), encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                continue
            entry = entries_by_path.get("seed/learn/" + name) or {}
            title = os.path.splitext(entry.get("name") or name)[0]
            body = re.sub(r"^#+.*$", "", raw, flags=re.M)
            body = re.sub(r"\s+", " ", body).strip()[:800]
            add("knowledge", entry.get("materialId") or os.path.splitext(name)[0],
                title, "学习资料", title + "。" + body)

    # 3) 运行时导入的知识条目（无 knowledge.json 时跳过）
    for src in load_knowledge():
        for s in src.get("sections") or []:
            add("knowledge", s.get("id"), s.get("title"),
                "%s / %s" % (src.get("name") or "知识库", s.get("chapter") or ""),
                s.get("text"))

    # 4) 教师上传抽取文本（files/up/*.txt），元数据来自 files/index.json，按密级过滤
    for e in load_index():
        tp = e.get("textPath")
        if not tp:
            continue
        try:
            with open(os.path.join(FILES_DIR, tp), encoding="utf-8") as f:
                text = f.read(30000)
        except OSError:
            continue
        add("material", e.get("materialId") or e.get("id"),
            e.get("title") or e.get("name"), "",
            text, source="教师上传 · " + (e.get("byName") or e.get("by") or ""),
            level=e.get("level", 0), credibility=e.get("credibility") or "normal")

    tf = [Counter(_tokenize(d["title"] + "\n" + d["text"])) for d in docs]
    dl = [sum(c.values()) for c in tf]
    df = Counter()
    for c in tf:
        for t in c:
            df[t] += 1
    avgdl = (sum(dl) / len(dl)) if dl else 0.0
    return {"docs": docs, "tf": tf, "dl": dl, "df": df, "avgdl": avgdl, "n": len(docs)}


def get_search_index():
    """惰性构建索引；版本戳被置脏后在下次调用时重建。"""
    with _SEARCH_LOCK:
        if (_SEARCH_STATE["index"] is not None
                and _SEARCH_STATE["built_version"] == _SEARCH_STATE["version"]):
            return _SEARCH_STATE["index"]
        idx = _build_search_index()
        _SEARCH_STATE["index"] = idx
        _SEARCH_STATE["built_version"] = _SEARCH_STATE["version"]
        return idx


def _make_snippet(text, q_tokens, width=60):
    """命中位置前后各约 width 字；未命中（经由其他词命中）取开头。"""
    flat = re.sub(r"\s+", " ", text)
    pos = -1
    for t in q_tokens:
        p = flat.lower().find(t)
        if 0 <= p and (pos < 0 or p < pos):
            pos = p
    if pos < 0:
        pos = 0
    return flat[max(0, pos - width):pos + width + 2].strip()


def search_corpus(q, max_level=0, kinds=None, limit=8):
    """BM25 统一打分，分 knowledge / materials 两类返回；materials 按用户密级过滤。"""
    empty = {"knowledge": [], "materials": []}
    q_tokens = _tokenize(q)
    idx = get_search_index()
    if not q_tokens or not idx["n"]:
        return empty
    if kinds:
        kinds = {"material" if k in ("material", "materials") else k for k in kinds}
        kinds = {k for k in kinds if k in ("knowledge", "material")} or None
    avgdl = idx["avgdl"] or 1.0
    scored = []
    for i, d in enumerate(idx["docs"]):
        if kinds and d["cls"] not in kinds:
            continue
        if d["cls"] == "material" and d["level"] > max_level:
            continue
        c, dl = idx["tf"][i], idx["dl"][i] or 1
        score = 0.0
        for t in q_tokens:
            n = idx["df"].get(t, 0)
            f = c.get(t, 0)
            if not n or not f:
                continue
            idf = math.log(1 + (idx["n"] - n + 0.5) / (n + 0.5))
            score += idf * (f * (BM25_K1 + 1)) / (f + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        if score > 0:
            scored.append((score, i))
    scored.sort(key=lambda x: -x[0])
    knowledge, materials = [], []
    for score, i in scored:
        d = idx["docs"][i]
        if d["cls"] == "knowledge" and len(knowledge) < limit:
            knowledge.append({
                "id": d["id"], "title": d["title"], "chapter": d["chapter"],
                "snippet": _make_snippet(d["text"], q_tokens), "score": round(score, 3),
            })
        elif d["cls"] == "material" and len(materials) < limit:
            materials.append({
                "id": d["id"], "title": d["title"], "source": d["source"],
                "snippet": _make_snippet(d["text"], q_tokens), "score": round(score, 3),
                "level": d["level"], "credibility": d["credibility"],
            })
        if len(knowledge) >= limit and len(materials) >= limit:
            break
    return {"knowledge": knowledge, "materials": materials}


def api_search(user, payload):
    q = (payload.get("q") or "").strip()
    if not q:
        return {"ok": False, "error": "缺少检索词 q"}, 400
    try:
        limit = min(max(int(payload.get("limit") or 8), 1), 50)
    except Exception:
        limit = 8
    kinds = payload.get("kinds")
    if isinstance(kinds, str):
        kinds = [k.strip() for k in kinds.split(",")]
    if not isinstance(kinds, list):
        kinds = None
    res = search_corpus(q, max_level=req_max_level(user), kinds=kinds, limit=limit)
    return {"ok": True, "q": q,
            "knowledge": res["knowledge"], "materials": res["materials"]}, 200


# ---------------------------------------------------------------- AI 代理
def ai_chat(payload):
    """转发 OpenAI 兼容 chat 请求到真实模型服务。密钥不离开服务端。"""
    if not AI_BASE_URL or not AI_API_KEY:
        return {"ok": False, "error": "服务端未配置 AI_BASE_URL / AI_API_KEY"}
    body = {
        "model": payload.get("model") or AI_DEFAULT_MODEL,
        "messages": payload.get("messages") or [],
        "temperature": payload.get("temperature", 0.7),
        "stream": False,
    }
    # 模型只允许 .env 白名单内的取值
    if AI_MODELS and body["model"] not in AI_MODELS:
        body["model"] = AI_DEFAULT_MODEL
    if payload.get("max_tokens"):
        body["max_tokens"] = int(payload["max_tokens"])
    req = urllib.request.Request(
        AI_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + AI_API_KEY,
        },
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        return {"ok": False, "error": "模型服务 HTTP %s: %s" % (e.code, detail)}
    except Exception as e:  # 超时/网络错误
        return {"ok": False, "error": "模型调用失败: %s" % e}
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return {
        "ok": True,
        "content": msg.get("content", ""),
        "model": data.get("model", body["model"]),
        "usage": data.get("usage", {}),
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


# ------------------------------------------------------------ URL 临时抓取
def _is_public_host(host):
    """基础 SSRF 防护：仅允许公网 http/https。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        ip = info[4][0]
        if ip.startswith(("127.", "10.", "0.", "169.254.", "192.168.", "::1")):
            return False
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                if 16 <= second <= 31:
                    return False
            except Exception:
                return False
    return True


def fetch_url(payload):
    url = (payload.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return {"ok": False, "error": "仅支持 http/https 链接"}
    host = urllib.parse.urlparse(url).hostname or ""
    if not _is_public_host(host):
        return {"ok": False, "error": "该地址不允许抓取（非公网地址）"}
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            final_url = resp.geturl()
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read(1024 * 1024)  # 最多 1MB
    except Exception as e:
        # 链接进入来源台账，但状态为失败
        return {"ok": False, "error": "抓取失败: %s" % e, "url": url}
    if "text" not in ctype and "html" not in ctype and "json" not in ctype:
        return {"ok": False, "error": "非文本页面（%s），请上传资料包补充内容" % ctype,
                "url": url, "finalUrl": final_url, "contentType": ctype}
    html = raw.decode("utf-8", "ignore")
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    # 粗提取正文：去脚本/样式/标签
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;|&gt;|&quot;|&#39;", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 8]
    text = "\n".join(lines)[:8000]
    return {"ok": True, "url": url, "finalUrl": final_url, "title": title,
            "text": text, "contentType": ctype}


# --------------------------------------------------------------- 联网检索
def web_search(payload):
    """Tavily 检索公开网络资源，供素材采集选用。密钥不离开服务端。"""
    if not TAVILY_API_KEY:
        return {"ok": False, "error": "服务端未配置 TAVILY_API_KEY"}
    query = (payload.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "缺少检索词"}
    body = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": min(int(payload.get("max_results") or 6), 10),
        "include_answer": False,
        "include_raw_content": False,
    }
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        return {"ok": False, "error": "检索服务 HTTP %s: %s" % (e.code, detail)}
    except Exception as e:
        return {"ok": False, "error": "检索失败: %s" % e}
    results = [{
        "title": r.get("title", ""), "url": r.get("url", ""),
        "content": (r.get("content") or "")[:1200],
        "score": r.get("score", 0),
    } for r in (data.get("results") or [])]
    return {"ok": True, "query": query, "results": results}


# ------------------------------------------------------------ MoA 多智能体编排（/api/ai/agent）
INTENT_ROUTES = {
    "find-theory": "librarian", "find-material": "librarian",
    "draft": "writer", "polish": "writer", "adapt": "writer", "section-draft": "writer",
    "review": "reviewer",
}

ORCHESTRATOR_PROMPT = (
    "你是思政教学案例平台的主 Agent，只负责判断用户请求应交给哪个角色处理。"
    "只输出严格 JSON（不要输出任何其他内容）："
    "{\"route\":\"librarian|writer|reviewer\",\"reason\":\"一句话理由\"}。"
    "路由规则：查找理论依据、查找/关联素材、整理来源出处 → librarian；"
    "起草、润色、改写、续写章节等文本生成 → writer；"
    "审校、核查理论准确性/事实与引用/语言规范/风险 → reviewer。"
)

LIBRARIAN_PROMPT = (
    "你是思政教学案例平台的「资料管理员」，擅长素材关联和来源整理。"
    "你可以使用两个工具：search_corpus（检索本地语料：教材《自然辩证法概论》、学习资料、"
    "知识条目、教师上传素材）和 fetch_url（抓取公开网页）。"
    "每一轮只输出一个严格 JSON，不要输出任何其他文字：\n"
    "{\"action\":\"search_corpus\",\"args\":{\"q\":\"检索词\"}}\n"
    "或 {\"action\":\"fetch_url\",\"args\":{\"url\":\"https://...\"}}\n"
    "或 {\"action\":\"final\",\"content\":\"最终答复\"}\n"
    "规则：需要资料时先用 search_corpus（可换检索词多次检索）；信息足够后立即输出 final。"
    "final 的 content 用中文，分条列出推荐内容（标题/章节/来源），引用教材或素材用〔n〕编号标注，"
    "不要编造语料中不存在的条目。"
)

WRITER_PROMPT = (
    "你是思政教学案例平台的「写作手」，擅长教学案例文本的起草、润色与改写。"
    "根据用户意图和案例上下文直接输出成稿文本本身，不要解释、不要加任何前后缀。"
    "保持思政教学语言规范、理论表述准确；引用素材用〔n〕标注。"
)

REVIEWER_PROMPT = (
    "你是思政教学案例平台的「内容审校员」。按标准清单逐条审校用户给出的文本："
    "理论准确性、事实与引用一致性、语言规范、风险与待人工确认。"
    "只输出严格 JSON 数组，不要输出任何其他内容："
    "[{\"standard\":\"标准名\",\"status\":\"pass|risk|confirm\",\"note\":\"一句话说明\",\"ref\":\"〔n〕可选\"}]。"
    "status 含义：pass=通过，risk=有风险需修改，confirm=需人工确认。"
)

MOA_AGENT_META = {
    "orchestrator": {"label": "主Agent", "skill": "意图识别与任务分派"},
    "librarian": {"label": "资料管理员", "skill": "素材关联和来源整理"},
    "writer": {"label": "写作手", "skill": "双候选写作（起草/润色/改写）"},
    "reviewer": {"label": "内容审校员", "skill": "理论/事实/语言/风险逐项审校"},
}


def llm_call(model, messages, temperature=0.7, max_tokens=None):
    """非流式 LLM 调用（服务端内部编排用；模型来自服务端配置，不走客户端白名单）。
    返回 (content, error)。"""
    body = {"model": model, "messages": messages,
            "temperature": temperature, "stream": False}
    if max_tokens:
        body["max_tokens"] = int(max_tokens)
    req = urllib.request.Request(
        AI_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + AI_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        return None, "模型服务 HTTP %s: %s" % (e.code, detail)
    except Exception as e:
        return None, "模型调用失败: %s" % e
    msg = ((data.get("choices") or [{}])[0]).get("message") or {}
    return msg.get("content") or "", None


def llm_stream_call(model, messages, on_delta, temperature=0.7, max_tokens=None):
    """流式 LLM 调用：每个增量文本回调 on_delta。返回 (full_text, error)。"""
    body = {"model": model, "messages": messages,
            "temperature": temperature, "stream": True}
    if max_tokens:
        body["max_tokens"] = int(max_tokens)
    req = urllib.request.Request(
        AI_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + AI_API_KEY},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=AI_TIMEOUT)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        return None, "模型服务 HTTP %s: %s" % (e.code, detail)
    except Exception as e:
        return None, "模型调用失败: %s" % e
    full = []
    try:
        for raw_line in resp:
            line = raw_line.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            delta = ((obj.get("choices") or [{}])[0]).get("delta") or {}
            piece = delta.get("content") or ""
            if piece:
                full.append(piece)
                try:
                    on_delta(piece)
                except Exception:
                    pass
    except Exception as e:
        return ("".join(full) or None), "流式传输中断: %s" % e
    finally:
        resp.close()
    return "".join(full), None


def _extract_json(text, want_array=False):
    """从模型输出中提取第一个 JSON 对象/数组并解析；失败返回 None。"""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start = text.find("[" if want_array else "{")
    if start < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except Exception:
        return None


def _chunk_text(text, size=24):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _moa_tool_search(q, max_level):
    """资料管理员工具：本地 BM25 检索（按请求用户密级过滤素材）。"""
    res = search_corpus(q, max_level=max_level, limit=6)
    lines = []
    for i, it in enumerate(res["knowledge"], 1):
        lines.append("〔k%d〕%s / %s：%s"
                     % (i, it["chapter"] or "知识条目", it["title"], it["snippet"]))
    for i, it in enumerate(res["materials"], 1):
        lv = LEVEL_NAMES[it["level"]] if 0 <= it["level"] < len(LEVEL_NAMES) else str(it["level"])
        lines.append("〔m%d〕素材《%s》（%s，密级：%s，可信度：%s）：%s"
                     % (i, it["title"], it["source"], lv, it["credibility"], it["snippet"]))
    total = len(res["knowledge"]) + len(res["materials"])
    text = "\n".join(lines) if lines else "未检索到相关内容"
    return text[:4000], "命中 %d 条" % total


def _moa_tool_fetch(url):
    """资料管理员工具：复用 /api/fetch-url 的网页抓取。"""
    if not url:
        return "缺少 url", "缺少 url"
    r = fetch_url({"url": url})
    if not r.get("ok"):
        return "抓取失败：" + (r.get("error") or ""), "抓取失败"
    text = "网页《%s》（%s）内容摘录：\n%s" % (
        r.get("title") or "", r.get("finalUrl") or url, (r.get("text") or "")[:3000])
    return text, "抓取成功：%s" % (r.get("title") or url)[:40]


def _moa_history(payload):
    """对话历史：沿用 chat 的 [{role,content}]，服务端截断（最近 6 条、单条 1500 字）。"""
    msgs = []
    for h in (payload.get("history") or [])[-6:]:
        if not isinstance(h, dict) or h.get("role") not in ("user", "assistant"):
            continue
        content = (h.get("content") or "")[:1500]
        if content:
            msgs.append({"role": h["role"], "content": content})
    return msgs


def _moa_user_text(payload):
    """把 text + caseContext + selection 拼成给模型的用户消息。"""
    parts = []
    ctx = payload.get("caseContext") or {}
    if ctx.get("title"):
        parts.append("案例标题：" + str(ctx["title"]))
    if ctx.get("sectionTitle"):
        parts.append("当前章节：" + str(ctx["sectionTitle"]))
    if ctx.get("sectionText"):
        parts.append("章节全文：\n" + str(ctx["sectionText"])[:3000])
    elif ctx.get("bodyExcerpt"):
        parts.append("案例内容摘要：\n" + str(ctx["bodyExcerpt"])[:1500])
    citations = ctx.get("citations") or []
    if citations:
        lines = ["已关联的引用素材："]
        for i, c in enumerate(citations[:20], 1):
            if isinstance(c, dict):
                lines.append("〔%d〕%s — %s" % (i, c.get("title", ""), c.get("source", "")))
            else:
                lines.append("〔%d〕%s" % (i, c))
        parts.append("\n".join(lines))
    if payload.get("selection"):
        parts.append("用户选中的文段：\n" + str(payload["selection"])[:1500])
    parts.append("用户请求：" + (payload.get("text") or ""))
    return "\n\n".join(p for p in parts if p)


def _moa_classify(user_text):
    """无 intentHint 时由编排模型轻量分类；解析失败回落 writer。"""
    content, err = llm_call(MOA_MODEL_ORCHESTRATOR, [
        {"role": "system", "content": ORCHESTRATOR_PROMPT},
        {"role": "user", "content": user_text[:2000]},
    ], temperature=0.1)
    if content:
        obj = _extract_json(content)
        if isinstance(obj, dict) and obj.get("route") in ("librarian", "writer", "reviewer"):
            return obj["route"], str(obj.get("reason") or "")
    sys.stderr.write("[moa] 分类失败（%s），回落 writer\n" % (err or "JSON 解析失败"))
    return "writer", "分类失败，按写作处理"


# --------------------------------------------------------------- docx 导出
def export_docx(payload):
    """导出成套教学材料。payload:
    title, meta{author,audience,caseType,course,mode,statusNote,footerNote},
    parts[{heading,markdown}], refs[{title,source}]
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    import io

    title = payload.get("title") or "未命名案例"
    meta = payload.get("meta") or {}
    parts = payload.get("parts") or []
    refs = payload.get("refs") or []

    def add_markdown(doc, markdown):
        for line in markdown.splitlines():
            raw = line.rstrip()
            if not raw.strip():
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", raw)
            if m:
                doc.add_heading(re.sub(r"\*\*", "", m.group(2)), level=min(len(m.group(1)) + 1, 4))
                continue
            if re.match(r"^\s*[-*]\s+", raw):
                doc.add_paragraph(re.sub(r"^\s*[-*]\s+", "", raw), style="List Bullet")
                continue
            if re.match(r"^\s*\d+\.\s+", raw):
                doc.add_paragraph(re.sub(r"^\s*\d+\.\s+", "", raw), style="List Number")
                continue
            if raw.startswith(">"):
                p = doc.add_paragraph(raw.lstrip("> ").strip())
                p.paragraph_format.left_indent = Pt(18)
                continue
            text = re.sub(r"\[cite:[^\]]+\]", "", raw)
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
            text = re.sub(r"`([^`]+)`", r"\1", text)
            doc.add_paragraph(text)

    doc = Document()
    doc.add_heading(title, level=0)
    info = doc.add_paragraph()
    info.add_run(
        "作者：%s    教学对象：%s    案例类型：%s    课程：%s    版本：%s"
        % (meta.get("author", "-"), meta.get("audience", "-"), meta.get("caseType", "-"),
           meta.get("course", "-"), meta.get("mode", "-"))
    ).font.size = Pt(9)

    for part in parts:
        heading = (part.get("heading") or "").strip()
        if heading:
            doc.add_heading(heading, level=1)
        add_markdown(doc, part.get("markdown") or "")

    if refs:
        doc.add_heading("引用与素材清单", level=1)
        for i, r in enumerate(refs, 1):
            doc.add_paragraph("[%d] %s — %s" % (i, r.get("title", ""), r.get("source", "")),
                              style="List Number")

    # 页脚追踪元数据：状态、生成时间、使用范围提示
    footer_note = meta.get("footerNote") or (
        "上海大学思政教学案例智能平台 · 生成时间：%s · 状态：%s"
        % (time.strftime("%Y-%m-%d %H:%M"), meta.get("statusNote", "未定"))
    )
    for section in doc.sections:
        p = section.footer.paragraphs[0]
        p.text = footer_note
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.size = Pt(8)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), title


# --------------------------------------------------------------- HTTP 处理
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[app] %s - %s\n" % (self.address_string(), fmt % args))

    # 工具 ------------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # 路由 ------------------------------------------------------------
    def _sse_chunk(self, data):
        """写一个 chunked 编码块并立即 flush。"""
        self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
        self.wfile.flush()

    # MoA SSE 帧 -----------------------------------------------------
    def _sse_begin(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _sse_frame(self, obj):
        """逐帧 data: {json}\n\n，与前端契约一致。"""
        self._sse_chunk(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))

    def _sse_end(self):
        try:
            self.wfile.write(b"0\r\n\r\n")  # chunked 结束标记
            self.wfile.flush()
        except Exception:
            pass

    def _sse_role(self, agent, model):
        meta = MOA_AGENT_META[agent]
        self._sse_frame({"type": "role", "agent": agent, "label": meta["label"],
                         "model": model, "skill": meta["skill"]})

    def _ai_agent(self, payload):
        """统一 AI 入口：主Agent 分派 → 资料管理员/写作手（双候选）/内容审校员。"""
        if not AI_BASE_URL or not AI_API_KEY:
            return self._send_json({"ok": False, "error": "服务端未配置 AI_BASE_URL / AI_API_KEY"})
        ctx = payload.get("caseContext") or {}
        if not ((payload.get("text") or "").strip()
                or payload.get("selection") or ctx.get("sectionText")):
            return self._send_json({"ok": False, "error": "缺少请求内容 text"}, 400)
        max_level = req_max_level(auth_user(self))
        self._sse_begin()
        try:
            hint = (payload.get("intentHint") or "").strip()
            route = INTENT_ROUTES.get(hint)
            user_text = _moa_user_text(payload)
            if not route:
                self._sse_role("orchestrator", MOA_MODEL_ORCHESTRATOR)
                route, _reason = _moa_classify(user_text)
            history = _moa_history(payload)
            if route == "librarian":
                self._agent_librarian(user_text, history, max_level)
            elif route == "reviewer":
                self._agent_reviewer(user_text, history)
            else:
                self._agent_writer(user_text, history)
            self._sse_frame({"type": "done"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self._sse_frame({"type": "error", "message": "编排失败: %s" % e})
            except Exception:
                pass
        finally:
            self._sse_end()

    def _agent_librarian(self, user_text, history, max_level):
        """资料管理员：内部 JSON contract 工具循环（≤3 次工具调用后强制 final）。"""
        model = MOA_MODEL_LIBRARIAN
        self._sse_role("librarian", model)
        msgs = ([{"role": "system", "content": LIBRARIAN_PROMPT}] + history
                + [{"role": "user", "content": user_text}])
        final_text, last_content, tool_calls = None, "", 0
        for _round in range(4):
            content, err = llm_call(model, msgs, temperature=0.3)
            if err:
                self._sse_frame({"type": "error", "message": err})
                return
            last_content = content or last_content
            obj = _extract_json(content)
            action = obj.get("action") if isinstance(obj, dict) else None
            if action in ("search_corpus", "fetch_url") and tool_calls < 3:
                tool_calls += 1
                args = obj.get("args") or {}
                if action == "search_corpus":
                    q = (args.get("q") or "").strip()
                    tool_text, summary = (_moa_tool_search(q, max_level) if q
                                          else ("检索词为空", "检索词为空"))
                else:
                    tool_text, summary = _moa_tool_fetch((args.get("url") or "").strip())
                self._sse_frame({"type": "tool", "agent": "librarian",
                                 "tool": action, "args": args, "summary": summary})
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user",
                             "content": "工具结果：\n" + tool_text + "\n\n请继续（输出下一个 JSON）。"})
                continue
            if action == "final":
                final_text = str(obj.get("content") or "").strip() or (content or "")
                break
            nudge = ("工具调用已达上限，" if action in ("search_corpus", "fetch_url")
                     else "输出无法解析，") + "请立即输出最终答复 JSON：{\"action\":\"final\",\"content\":\"...\"}"
            msgs.append({"role": "assistant", "content": content or ""})
            msgs.append({"role": "user", "content": nudge})
        if final_text is None:
            final_text = last_content or "（资料管理员未能形成结论，请换个问法重试）"
        for piece in _chunk_text(final_text):
            self._sse_frame({"type": "token", "agent": "librarian",
                             "which": "main", "text": piece})
        self._sse_frame({"type": "result", "kind": "text", "text": final_text})

    def _agent_writer(self, user_text, history):
        """写作手：ThreadPoolExecutor 并行双候选（主=默认模型，备=MOA_MODEL_WRITER_ALT）。"""
        self._sse_role("writer", AI_DEFAULT_MODEL)
        msgs = ([{"role": "system", "content": WRITER_PROMPT}] + history
                + [{"role": "user", "content": user_text}])
        q = queue.Queue()

        def job(which, model):
            full, err = llm_stream_call(
                model, msgs, on_delta=lambda p: q.put(("token", which, p)))
            q.put(("end", which, model, full, err))

        results, ended = {}, 0
        with ThreadPoolExecutor(max_workers=2) as ex:
            ex.submit(job, "main", AI_DEFAULT_MODEL)
            ex.submit(job, "alt", MOA_MODEL_WRITER_ALT)
            while ended < 2:
                item = q.get()
                if item[0] == "token":
                    self._sse_frame({"type": "token", "agent": "writer",
                                     "which": item[1], "text": item[2]})
                else:
                    _, which, model, full, err = item
                    results[which] = {
                        "model": model,
                        "text": full if full is not None else "（该候选生成失败：%s）" % err,
                    }
                    ended += 1
        fallback = {"model": "", "text": ""}
        self._sse_frame({"type": "result", "kind": "candidates",
                         "main": results.get("main") or fallback,
                         "alt": results.get("alt") or fallback})

    def _agent_reviewer(self, user_text, history):
        """内容审校员：按标准清单输出严格 JSON 数组；解析失败包成单条 confirm。"""
        self._sse_role("reviewer", MOA_MODEL_REVIEWER)
        msgs = ([{"role": "system", "content": REVIEWER_PROMPT}] + history
                + [{"role": "user", "content": user_text}])
        content, err = llm_call(MOA_MODEL_REVIEWER, msgs, temperature=0.2)
        if err:
            self._sse_frame({"type": "error", "message": err})
            return
        arr = _extract_json(content, want_array=True)
        items = []
        if isinstance(arr, list):
            for it in arr:
                if not isinstance(it, dict):
                    continue
                status = it.get("status")
                item = {
                    "standard": str(it.get("standard") or "未命名标准"),
                    "status": status if status in ("pass", "risk", "confirm") else "confirm",
                    "note": str(it.get("note") or ""),
                }
                if it.get("ref"):
                    item["ref"] = str(it["ref"])
                items.append(item)
        if not items:
            items = [{"standard": "审校结果解析", "status": "confirm",
                      "note": (content or "").strip() or "审校结果为空，需人工复核"}]
        self._sse_frame({"type": "result", "kind": "review", "items": items})

    def _ai_chat_stream(self, payload):
        """stream:true 的 /api/ai/chat：上游 SSE 帧逐行透传（chunked 编码）。"""
        if not AI_BASE_URL or not AI_API_KEY:
            return self._send_json({"ok": False, "error": "服务端未配置 AI_BASE_URL / AI_API_KEY"})
        body = {
            "model": payload.get("model") or AI_DEFAULT_MODEL,
            "messages": payload.get("messages") or [],
            "temperature": payload.get("temperature", 0.7),
            "stream": True,
        }
        # 模型只允许 .env 白名单内的取值
        if AI_MODELS and body["model"] not in AI_MODELS:
            body["model"] = AI_DEFAULT_MODEL
        if payload.get("max_tokens"):
            body["max_tokens"] = int(payload["max_tokens"])
        req = urllib.request.Request(
            AI_BASE_URL + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + AI_API_KEY,
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=AI_TIMEOUT)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:500]
            return self._send_json({"ok": False, "error": "模型服务 HTTP %s: %s" % (e.code, detail)})
        except Exception as e:  # 超时/网络错误
            return self._send_json({"ok": False, "error": "模型调用失败: %s" % e})
        # 上游正常，开始 SSE 流
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", "ignore").rstrip("\r\n")
                if not line:
                    continue
                self._sse_chunk((line + "\n\n").encode("utf-8"))
        except Exception as e:
            # 流开始后才出错：以错误帧告知客户端再结束
            try:
                self._sse_chunk(("data: " + json.dumps(
                    {"error": "流式传输中断: %s" % e}, ensure_ascii=False) + "\n\n"
                ).encode("utf-8"))
            except Exception:
                pass
        finally:
            resp.close()
            try:
                self.wfile.write(b"0\r\n\r\n")  # chunked 结束标记
                self.wfile.flush()
            except Exception:
                pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/constants":
            return self._send_json({
                "ok": True, "service": "sizheng-case-library",
                "aiConfigured": bool(AI_BASE_URL and AI_API_KEY),
                "models": AI_MODELS,
                "defaultModel": AI_DEFAULT_MODEL,
                "reviewEnabled": AI_REVIEW_ENABLED,
                "webSearch": bool(TAVILY_API_KEY),
                "filesAuth": bool(APP_SECRET),
            })
        if path == "/api/files":
            return self._send_json(api_files_list(auth_user(self)))
        if path == "/api/knowledge":
            return self._send_json(load_knowledge())
        if path.startswith("/api/files/"):
            rest = path[len("/api/files/"):]
            if rest.endswith("/text"):
                fid = urllib.parse.unquote(rest[:-len("/text")])
                res, status = api_file_text(auth_user(self), fid)
                return self._send_json(res, status)
            fid = urllib.parse.unquote(path.rsplit("/", 1)[1])
            found, err, status = api_file_download(auth_user(self), fid)
            if err:
                return self._send_json(err, status)
            data, ctype, name = found
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition",
                             "inline; filename*=UTF-8''" + urllib.parse.quote(name))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return self._serve_static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        payload = self._read_json()
        if path == "/api/auth/login":
            return self._send_json(api_login(payload))
        if path == "/api/files":
            res, status = api_file_upload(auth_user(self), payload)
            return self._send_json(res, status)
        if path == "/api/knowledge/import":
            res, status = api_knowledge_import(auth_user(self), payload)
            return self._send_json(res, status)
        if path == "/api/ai/chat":
            if payload.get("stream"):
                return self._ai_chat_stream(payload)
            return self._send_json(ai_chat(payload))
        if path == "/api/search":
            res, status = api_search(auth_user(self), payload)
            return self._send_json(res, status)
        if path == "/api/ai/agent":
            return self._ai_agent(payload)
        if path == "/api/web-search":
            return self._send_json(web_search(payload))
        if path == "/api/fetch-url":
            return self._send_json(fetch_url(payload))
        if path == "/api/export-docx":
            try:
                data, title = export_docx(payload)
            except Exception as e:
                return self._send_json({"ok": False, "error": "导出失败: %s" % e}, 500)
            fname = urllib.parse.quote(title + ".docx")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + fname)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return self._send_json({"ok": False, "error": "not found"}, 404)

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/files/"):
            fid = urllib.parse.unquote(path.rsplit("/", 1)[1])
            res, status = api_file_delete(auth_user(self), fid)
            return self._send_json(res, status)
        return self._send_json({"ok": False, "error": "not found"}, 404)

    def do_PATCH(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/files/"):
            fid = urllib.parse.unquote(path.rsplit("/", 1)[1])
            res, status = api_file_patch(auth_user(self), fid, self._read_json())
            return self._send_json(res, status)
        return self._send_json({"ok": False, "error": "not found"}, 404)

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        safe = os.path.normpath(path).lstrip("/")
        if safe.startswith(".."):
            return self._send_json({"ok": False, "error": "forbidden"}, 403)
        full = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(full):
            full = os.path.join(STATIC_DIR, "index.html")  # SPA 兜底
        ctype = "text/html"
        if full.endswith(".js"):
            ctype = "application/javascript"
        elif full.endswith(".css"):
            ctype = "text/css"
        elif full.endswith(".svg"):
            ctype = "image/svg+xml"
        elif full.endswith(".png"):
            ctype = "image/png"
        elif full.endswith(".json"):
            ctype = "application/json"
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            return self._send_json({"ok": False, "error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text", "application/javascript")) else ""))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(ENV.get("PROTOTYPE_PORT", "8080") or 8080)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("服务已启动: http://127.0.0.1:%d  (AI: %s, model=%s, 文件库: %s, 种子文件 %d 个)"
          % (port, "已配置" if (AI_BASE_URL and AI_API_KEY) else "未配置", AI_DEFAULT_MODEL,
             "鉴权开启" if APP_SECRET else "未配置 APP_SECRET", len(load_index())))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
