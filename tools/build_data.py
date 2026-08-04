#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 assets/ 初期资料生成前端数据 app/data.js 与服务端文件库 files/：

- assets/《自然辩证法概论（2025版）》.md  → 知识库（章/节，含正文）+ 教材素材（真实文件）
- examples/*.docx                     → 已发布案例（信息卡 + 章节正文）
- assets/学习资料md.rar                → 中心组学习资料素材（69 期全文落盘 files/seed/learn/）

同时生成服务端运行所需：
- files/index.json        种子文件索引（保留已有的上传条目）
- files/users.json        演示账号（从 app/seed.js 抽取，供服务端鉴权）
- files/materials_seed.json 素材登记种子（app/seed.js extraMaterials 8 条 + 学习资料 69 期，
  服务端首启灌入 SQLite materials 表；教材是知识不是素材，不入库，ADR 0011）

运行：python3 tools/build_data.py
"""
import html
import json
import os
import re
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "app", "data.js")

BOOK_FILE = os.path.join(ROOT, "assets", "《自然辩证法概论（2025版）》.md")
BOOK_TITLE = "《自然辩证法概论（2025版）》"
EXAMPLES_DIR = os.path.join(ROOT, "examples")
LEARN_RAR = os.path.join(ROOT, "assets", "学习资料md.rar")
SEED_JS = os.path.join(ROOT, "app", "seed.js")
FILES_DIR = os.path.join(ROOT, "files")
INDEX_FILE = os.path.join(FILES_DIR, "index.json")
USERS_FILE = os.path.join(FILES_DIR, "users.json")
CASES_SEED_FILE = os.path.join(FILES_DIR, "cases_seed.json")
MATERIALS_SEED_FILE = os.path.join(FILES_DIR, "materials_seed.json")
EXCERPT_ISSUES = 69      # 最新多少期保留内容副本（检索摘录用，全文一律落盘）
EXCERPT_CHARS = 800      # 每期副本截取长度


def clean(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ------------------------------------------------------------ 教材知识库
def parse_book():
    with open(BOOK_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    chapters, sections = [], []
    ch, sec, buf = None, None, []

    def flush():
        nonlocal buf
        body = clean("\n".join(buf))
        buf = []
        if sec is not None:
            sections.append({
                "id": "kn-%02d-%02d" % (ch["index"], sec["index"]),
                "chapterId": ch["id"],
                "chapter": ch["title"],
                "index": sec["index"],
                "title": sec["title"],
                "text": body,
                "chars": len(body),
            })
        elif ch is not None and body:
            ch["intro"] = (ch.get("intro") or "") + body + "\n"

    for ln in lines:
        m1 = re.match(r"^#\s+(.+)$", ln)
        m3 = re.match(r"^###\s+(.+)$", ln)
        if m1:
            flush()
            ch = {"id": "kc-%02d" % (len(chapters) + 1), "index": len(chapters) + 1,
                  "title": m1.group(1).strip()}
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
        c["intro"] = clean(c.get("intro") or "")
        c["sections"] = ["kn-%02d-%02d" % (c["index"], s["index"])
                         for s in sections if s["chapterId"] == c["id"]]
    return chapters, sections


# ------------------------------------------------------------ 示例案例
CARD_KEYS = ["案例题目", "作者", "报送单位", "学段", "应用课程", "理论知识点", "案例概述"]


def docx_lines(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    # 正则剥标签不会解码 XML 实体，需显式还原（&amp; → & 等），否则前端二次转义成 &amp;
    xml = html.unescape(xml)
    return [ln.strip() for ln in xml.splitlines() if ln.strip()]


def parse_case_docx(path):
    lines = docx_lines(path)
    card, sections = {}, []
    cur = None
    i = 0
    # 信息卡：键名单独成行，下一行为值
    while i < len(lines):
        ln = lines[i]
        if ln in CARD_KEYS and i + 1 < len(lines):
            card[ln] = lines[i + 1]
            i += 2
            continue
        m = re.match(r"^([一二三四五六七八九十]+)、(.+)$", ln)
        if m:
            cur = {"title": m.group(2).strip(), "paras": []}
            sections.append(cur)
        elif cur is not None:
            cur["paras"].append(ln)
        i += 1
    # 剥掉 docx 尾部的「附录/素材来源/参考文献」：这些来源信息由平台引用体系表达（ADR 0005/0011）
    for s in sections:
        cut = next((j for j, p in enumerate(s["paras"])
                    if re.match(r"^附录\s*$", p) or re.match(r"^参考文献", p)), None)
        if cut is not None:
            del s["paras"][cut:]
    return {
        "sourceFile": os.path.basename(path),
        "title": card.get("案例题目", lines[0] if lines else "未命名"),
        "author": card.get("作者", ""),
        "org": card.get("报送单位", ""),
        "stage": card.get("学段", ""),
        "courses": [c.strip() for c in re.split(r"[、，,]", card.get("应用课程", "")) if c.strip()],
        "theoryPoints": [t.strip() for t in re.split(r"[、，,]", card.get("理论知识点", "")) if t.strip()],
        "summary": card.get("案例概述", ""),
        "sections": [{"title": s["title"], "paras": s["paras"]} for s in sections],
    }


# ------------------------------------------------------------ 中心组学习资料
def issue_key(name):
    m = re.search(r"总第(\d+)期", name)
    return int(m.group(1)) if m else 0


def read_rar(path):
    """用系统 libarchive（ctypes）读取 RAR5 归档，返回 {文件名: 文本}。"""
    import ctypes
    lib = ctypes.CDLL("libarchive.so.13")
    vp = ctypes.c_void_p
    lib.archive_read_new.restype = vp
    lib.archive_read_open_filename.argtypes = [vp, ctypes.c_char_p, ctypes.c_size_t]
    lib.archive_read_next_header.argtypes = [vp, ctypes.POINTER(vp)]
    lib.archive_entry_pathname.restype = ctypes.c_char_p
    lib.archive_entry_size.restype = ctypes.c_longlong
    lib.archive_read_data.argtypes = [vp, vp, ctypes.c_size_t]
    lib.archive_read_data.restype = ctypes.c_ssize_t
    lib.archive_read_free.argtypes = [vp]
    for fn in ("archive_read_support_filter_all", "archive_read_support_format_all"):
        getattr(lib, fn).argtypes = [vp]

    a = lib.archive_read_new()
    lib.archive_read_support_filter_all(a)
    lib.archive_read_support_format_all(a)
    if lib.archive_read_open_filename(a, os.fsencode(path), 10240) != 0:
        lib.archive_read_free(a)
        raise RuntimeError("libarchive 无法打开归档: %s" % path)
    out, e = {}, vp()
    while lib.archive_read_next_header(a, ctypes.byref(e)) == 0:
        name = (lib.archive_entry_pathname(e) or b"").decode("utf-8", "ignore")
        size = lib.archive_entry_size(e)
        if not name.endswith(".md") or size <= 0:
            continue
        buf = ctypes.create_string_buffer(size)
        got = lib.archive_read_data(a, buf, size)
        if got > 0:
            out[name] = buf.raw[:got].decode("utf-8", "ignore")
    lib.archive_read_free(a)
    return out


def parse_learn_docs():
    docs, entries = [], []
    out_dir = os.path.join(FILES_DIR, "seed", "learn")
    os.makedirs(out_dir, exist_ok=True)
    for name, text in read_rar(LEARN_RAR).items():
        year = "2026" if name.startswith("2026") else "2025"
        base = os.path.basename(name)
        title = re.sub(r"\.md$", "", base)
        docs.append({"title": title, "year": year,
                     "issue": issue_key(base), "chars": len(text),
                     "name": base, "text": clean(text)})
    docs.sort(key=lambda d: -d["issue"])
    for i, d in enumerate(docs):
        d["id"] = "lr-%03d" % (i + 1)
        d["fileId"] = "f-" + d["id"]
        rel = os.path.join("seed", "learn", d["id"] + ".md")
        with open(os.path.join(FILES_DIR, rel), "w", encoding="utf-8") as f:
            f.write(d["text"])
        entries.append({
            "id": d["fileId"], "materialId": d["id"], "name": d["name"],
            "path": rel.replace(os.sep, "/"), "size": os.path.getsize(os.path.join(FILES_DIR, rel)),
            "level": 1, "seed": True,
        })
        if i < EXCERPT_ISSUES:
            d["excerpt"] = d["text"][:EXCERPT_CHARS]
        d.pop("text", None)
        d.pop("name", None)
    return docs, entries


# ------------------------------------------------------------ 教材素材（真实文件）
def assign_file_secs(text, sections):
    """按 ADR 0010 派生切片规则计算每个知识节（### 标题）的文件结构路径（如 "2.1.1"），
    与前端 U.chunkMd 严格同规则：出现的标题级别按 # 数排序为第 1..K 层，
    路径 = 各级序号拼接（缺层不占位）；### 节仅计首个 # 章之后的（与 parse_book 一致）。"""
    lines = text.splitlines()
    levels = sorted({len(re.match(r"^(#{1,3})\s+", l).group(1))
                     for l in lines if re.match(r"^#{1,3}\s+", l)})
    ranks = {h: i + 1 for i, h in enumerate(levels)}
    counters = [0, 0, 0, 0]
    sec_i = 0
    seen_chapter = False
    out = {}
    for ln in lines:
        m = re.match(r"^(#{1,3})\s+", ln)
        if not m:
            continue
        r = ranks[len(m.group(1))]
        counters[r] += 1
        for i in range(r + 1, 4):
            counters[i] = 0
        if re.match(r"^#\s+", ln):
            seen_chapter = True
        elif re.match(r"^###\s+", ln) and seen_chapter and sec_i < len(sections):
            out[sections[sec_i]["id"]] = ".".join(str(n) for n in counters[1:r + 1] if n > 0)
            sec_i += 1
    return out


def make_book_file(chapters, sections):
    """教材 = 知识，不是素材（ADR 0011）：产出教材文件信息（data.js bookFile）与
    files 索引条目；索引锚点指向知识来源 ks-zr，教材不进入素材库。"""
    with open(BOOK_FILE, encoding="utf-8") as f:
        text = f.read()
    rel = os.path.join("seed", "book", "zrbjf-2025.md")
    os.makedirs(os.path.dirname(os.path.join(FILES_DIR, rel)), exist_ok=True)
    with open(os.path.join(FILES_DIR, rel), "w", encoding="utf-8") as f:
        f.write(text)
    book_file = {
        "fileId": "f-book-zrdb", "title": BOOK_TITLE,
        "summary": "教材全文原始文件。内容已按章/节导入知识库（%d 章 %d 节），按标题树派生切片，可在线预览与下载。"
                   % (len(chapters), len(sections)),
    }
    entry = {
        "id": book_file["fileId"], "materialId": "ks-zr",
        "name": BOOK_TITLE + ".md", "path": rel.replace(os.sep, "/"),
        "size": os.path.getsize(os.path.join(FILES_DIR, rel)),
        "level": 0, "seed": True,
    }
    return book_file, entry


# ------------------------------------------------------------ 种子案例（服务端 SQLite 首启灌库用）
SNAP_KEYS = ["title", "summary", "theoryPoints", "blocks", "citations", "kit",
             "typeId", "audience", "course", "author", "org", "stageText", "applyCourses"]


def sections_to_blocks(sections):
    blocks = []
    for s in sections or []:
        if s.get("title"):
            blocks.append({"kind": "h2", "text": s["title"]})
        blocks.extend({"kind": "p", "text": p} for p in s.get("paras", []))
    return blocks


def strip_junk_blocks(case):
    """剥掉 docx 尾部的附录/素材来源/参考文献块（现由引用体系表达，ADR 0011）。"""
    blocks = case.get("blocks") or []
    cut = next((i for i, b in enumerate(blocks)
                if (b.get("text") or "").strip() == "附录"), -1)
    if cut < 0:
        return
    junk = re.compile(r"^(附录|素材来源|参考文献|\[\d+\]|$)")
    if all(junk.match((b.get("text") or "").strip()) for b in blocks[cut:]):
        case["blocks"] = blocks[:cut]


def extract_seed_cases():
    """用 node 从 app/seed.js 提取 draftCases/publishedMeta/extraMaterials（JS 对象字面量，正则不可靠）。"""
    script = ("global.window={};require(%s);"
              "console.log(JSON.stringify({drafts:window.SEED.draftCases,meta:window.SEED.publishedMeta,"
              "materials:window.SEED.extraMaterials}));"
              % json.dumps(SEED_JS))
    try:
        out = subprocess.run(["node", "-e", script], check=True,
                             capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError("需要 node 提取 app/seed.js 种子数据: %s" % e)
    return json.loads(out.stdout)


def write_cases_seed(imported, drafts, meta):
    """组装完整案例对象（与前端既有形状一致），输出 files/cases_seed.json。"""
    out = []
    for c in imported:
        prefix = next((p for p in meta if c["sourceFile"].startswith(p)), None)
        m = meta.get(prefix, {})
        case = {
            "id": "c-" + c["sourceFile"][:2],
            "title": c["title"], "typeId": m.get("typeId", "ct-general"),
            "audience": m.get("audience", "ug"),
            "course": (c["courses"] or [""])[0], "purpose": "案例申报",
            "ownerId": "u-admin", "status": "published",
            "author": c["author"], "org": c["org"], "summary": c["summary"],
            "theoryPoints": c["theoryPoints"], "applyCourses": c["courses"],
            "stageText": c["stage"],
            "blocks": sections_to_blocks(c["sections"]),
            "citations": list(m.get("citations", [])),
            "kit": {"design": "", "discussion": [], "ppt": [], "reflist": []},
            "annotations": [], "likes": m.get("likes", 0),
            "createdAt": "2026-05-20 10:00",
            "updatedAt": m.get("publishedAt", "2026-06-02"),
            "publishedAt": m.get("publishedAt", "2026-06-02"),
            "sourceFile": c["sourceFile"],
        }
        strip_junk_blocks(case)
        case["publishedSnapshot"] = {k: case[k] for k in SNAP_KEYS if k in case}
        case["versions"] = [{
            "id": "v-pub", "label": "公开版 v1", "at": case["publishedAt"] + " 09:00",
            "note": "审核通过，发布为公开版本", "snapshot": case["publishedSnapshot"],
        }]
        out.append(case)
    for d in drafts:
        d = json.loads(json.dumps(d))  # 深拷贝，避免污染 seed.js 原对象
        if not d.get("blocks"):
            d["blocks"] = sections_to_blocks(d.pop("sections", []))
        for a in d.get("annotations", []):
            a.setdefault("replies", [])
        d["citations"] = [{"target": r} if isinstance(r, str) else r
                          for r in d.get("citations", [])]
        d["kit"] = dict({"design": "", "discussion": [], "ppt": [], "reflist": []},
                        **(d.get("kit") or {}))
        out.append(d)
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(CASES_SEED_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return len(out)


# ------------------------------------------------------------ 素材登记种子（服务端 SQLite 首启灌库用）
# 信源等级映射（S 级暂空，由管理员定）：credibility high→A / normal→B / low→C
GRADE_BY_CRED = {"high": "A", "normal": "B", "low": "C"}
GRADE_REASON = {
    "high": "按可信度自动定级：权威来源 → A",
    "normal": "按可信度自动定级：一般来源 → B",
    "low": "按可信度自动定级：待核实 → C",
}


def material_row(m):
    """统一补齐素材行字段（与 db.py materials 表对应）。"""
    cred = m.get("credibility", "normal")
    return {
        "id": m["id"], "title": m["title"], "kind": m.get("kind", ""),
        "tags": m.get("tags") or [], "source": m.get("source", ""),
        "sourceUrl": m.get("sourceUrl", ""), "level": m.get("level", 0),
        "credibility": cred,
        "grade": m.get("grade") or GRADE_BY_CRED.get(cred, ""),
        "gradeReason": m.get("gradeReason") or GRADE_REASON.get(cred, ""),
        "publishedAt": m.get("publishedAt", ""), "collectedAt": m.get("collectedAt", ""),
        "status": m.get("status", "正常"),
        "summary": m.get("summary", ""), "excerpt": m.get("excerpt", ""),
        "fileId": m.get("fileId", ""), "scope": m.get("scope", ""),
        "citedCount": 0, "lastCitedAt": "",
        "createdAt": m.get("collectedAt", ""), "updatedAt": m.get("collectedAt", ""),
    }


def write_materials_seed(extra, learn):
    """8 条登记素材（seed.js extraMaterials）+ 69 期学习资料 → files/materials_seed.json。"""
    rows = [material_row(m) for m in extra]
    for d in learn:
        rows.append(material_row({
            "id": d["id"], "title": d["title"], "kind": "资料包", "fileId": d["fileId"],
            "source": "上海大学党委宣传部 · 中心组学习资料",
            "publishedAt": d["year"] + " 年（总第%d期）" % d["issue"],
            "collectedAt": "2026-07-18", "level": 1, "credibility": "high",
            "scope": "校内教师",
            "summary": "校党委中心组学习资料，%s 年出版，全文约 %d 千字。"
                       % (d["year"], round(d["chars"] / 1000)),
            "excerpt": d.get("excerpt", ""),
        }))
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(MATERIALS_SEED_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return len(rows)


# ------------------------------------------------------------ 服务端运行文件
def write_index(seed_entries):
    """种子条目整体重建；已存在的上传条目（seed=false）原样保留。"""
    os.makedirs(FILES_DIR, exist_ok=True)
    existing = []
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                existing = json.load(f).get("files", [])
        except Exception:
            existing = []
    kept = [e for e in existing if not e.get("seed")]
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"files": seed_entries + kept}, f, ensure_ascii=False, indent=1)
    return len(kept)


def write_users():
    """从 app/seed.js 抽取演示账号（id/name/maxLevel/admin），供服务端鉴权。"""
    with open(SEED_JS, encoding="utf-8") as f:
        src = f.read()
    block = src.split("users: [", 1)[1].split("audienceNames", 1)[0]
    users = []
    for chunk in re.split(r"\{\s*id: \"", block)[1:]:
        users.append({
            "id": chunk.split('"', 1)[0],
            "name": re.search(r'name: "([^"]*)"', chunk).group(1),
            "maxLevel": int(re.search(r"maxLevel: (\d)", chunk).group(1)),
            "admin": bool(re.search(r"admin:\s*true", chunk)),
        })
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=1)
    return users


def main():
    chapters, sections = parse_book()
    cases = [parse_case_docx(os.path.join(EXAMPLES_DIR, fn))
             for fn in sorted(os.listdir(EXAMPLES_DIR)) if fn.endswith(".docx")]
    learn, learn_entries = parse_learn_docs()
    book_file, book_entry = make_book_file(chapters, sections)
    with open(BOOK_FILE, encoding="utf-8") as f:
        secs_map = assign_file_secs(f.read(), sections)
    for s in sections:
        s["fileSec"] = secs_map.get(s["id"])
    kept_uploads = write_index(learn_entries + [book_entry])
    users = write_users()
    seed_cases = extract_seed_cases()
    n_cases = write_cases_seed(cases, seed_cases["drafts"], seed_cases["meta"])
    n_materials = write_materials_seed(seed_cases["materials"], learn)

    data = {
        "book": {"title": BOOK_TITLE, "edition": "2025版",
                 "chapters": len(chapters), "sections": len(sections)},
        "chapters": chapters,
        "knowledge": sections,
        "importedCases": cases,
        "bookFile": book_file,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// 由 tools/build_data.py 从项目素材自动生成，请勿手工编辑\n")
        f.write("window.RAWDATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")
    size = os.path.getsize(OUT)
    print("生成 %s（%.1f KB）：知识 %d 节 / %d 章，案例 %d 篇，学习资料 %d 期（全文落盘 %d 期 + 教材）"
          % (OUT, size / 1024, len(sections), len(chapters), len(cases),
             len(learn), len(learn_entries)))
    print("files/index.json：种子 %d 条，保留上传 %d 条；files/users.json：账号 %d 个"
          % (len(learn_entries) + 1, kept_uploads, len(users)))
    print("files/cases_seed.json：种子案例 %d 篇（服务端首启灌入 SQLite）" % n_cases)
    print("files/materials_seed.json：种子素材 %d 条（服务端首启灌入 SQLite）" % n_materials)


if __name__ == "__main__":
    main()
