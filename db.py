# -*- coding: utf-8 -*-
"""案例业务数据 SQLite 持久层：案例/审核留痕/批注/版本/收藏/点赞 + 素材登记。

cases.data 存完整案例 JSON（blocks/citations/kit 等）；批注、版本、点赞人独立成表，
读取时按前端既有对象形状组装（annotations/versions/likedBy 内嵌进案例对象）。
提交前自检批注（selfcheck）由服务端在每次写入后同步，所有客户端看到同一份。

materials 表是素材登记的唯一权威（WP2，ADR 0003/0011）：种子来自 files/materials_seed.json；
citedCount/lastCitedAt 由案例写入时统一重算（_sync_material_usage）；
「待淘汰」是派生态（30 天未被引且未豁免），不落库，读取时计算（ADR 0003）。
"""
import difflib
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY,
  ownerId TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  title TEXT NOT NULL DEFAULT '',
  likes INTEGER NOT NULL DEFAULT 0,
  createdAt TEXT, updatedAt TEXT, submittedAt TEXT, publishedAt TEXT,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews(
  id TEXT PRIMARY KEY,
  caseId TEXT NOT NULL,
  actorId TEXT NOT NULL,
  action TEXT NOT NULL,
  reason TEXT DEFAULT '',
  reasonType TEXT DEFAULT '',
  offlineFrom TEXT DEFAULT '',
  round INTEGER DEFAULT 0,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reviews_case ON reviews(caseId);
CREATE TABLE IF NOT EXISTS annotations(
  id TEXT NOT NULL,
  caseId TEXT NOT NULL,
  kind TEXT DEFAULT '',
  status TEXT DEFAULT 'pending',
  authorId TEXT DEFAULT '',
  at TEXT,
  data TEXT NOT NULL,
  PRIMARY KEY(id, caseId)
);
CREATE INDEX IF NOT EXISTS ix_annos_case ON annotations(caseId);
CREATE TABLE IF NOT EXISTS versions(
  id TEXT NOT NULL,
  caseId TEXT NOT NULL,
  actorId TEXT DEFAULT '',
  label TEXT DEFAULT '',
  at TEXT,
  data TEXT NOT NULL,
  PRIMARY KEY(id, caseId)
);
CREATE INDEX IF NOT EXISTS ix_versions_case ON versions(caseId);
CREATE TABLE IF NOT EXISTS favorites(
  userId TEXT NOT NULL, caseId TEXT NOT NULL, at TEXT,
  PRIMARY KEY(userId, caseId)
);
CREATE TABLE IF NOT EXISTS likes(
  userId TEXT NOT NULL, caseId TEXT NOT NULL, at TEXT,
  PRIMARY KEY(userId, caseId)
);
CREATE TABLE IF NOT EXISTS materials(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  kind TEXT DEFAULT '',
  tags TEXT DEFAULT '[]',
  source TEXT DEFAULT '',
  sourceUrl TEXT DEFAULT '',
  level INTEGER NOT NULL DEFAULT 0,
  credibility TEXT DEFAULT 'normal',
  grade TEXT DEFAULT '',
  gradeReason TEXT DEFAULT '',
  publishedAt TEXT DEFAULT '',
  collectedAt TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '候选',
  summary TEXT DEFAULT '',
  excerpt TEXT DEFAULT '',
  fileId TEXT DEFAULT '',
  citedCount INTEGER NOT NULL DEFAULT 0,
  lastCitedAt TEXT DEFAULT '',
  scope TEXT DEFAULT '',
  exempt INTEGER NOT NULL DEFAULT 0,
  createdAt TEXT, updatedAt TEXT
);
CREATE TABLE IF NOT EXISTS mat_favorites(
  userId TEXT NOT NULL, materialId TEXT NOT NULL, at TEXT,
  PRIMARY KEY(userId, materialId)
);
CREATE TABLE IF NOT EXISTS watch_sources(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  keywords TEXT DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  lastRunAt TEXT DEFAULT '',
  lastItemCount INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS watch_items(
  id TEXT PRIMARY KEY,
  sourceId TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  summary TEXT DEFAULT '',
  publishedAt TEXT DEFAULT '',
  fingerprint TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '待审',
  materialId TEXT DEFAULT '',
  fetchedAt TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_watch_items_source ON watch_items(sourceId);
CREATE TABLE IF NOT EXISTS contributions(
  id TEXT PRIMARY KEY,
  userId TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT DEFAULT '{}',
  status TEXT NOT NULL DEFAULT '待审',
  reviewedBy TEXT DEFAULT '',
  at TEXT
);
CREATE TABLE IF NOT EXISTS user_prefs(
  userId TEXT PRIMARY KEY,
  length TEXT DEFAULT '',
  style TEXT DEFAULT '',
  bannedWords TEXT DEFAULT '',
  themes TEXT DEFAULT '',
  updatedAt TEXT
);
"""

# 素材状态：候选（入库闸，待 admin 确认）/正常/停用/来源失效；「待淘汰」为派生态不落库
MAT_STATUSES = ("候选", "正常", "停用", "来源失效")
MAT_GRADES = ("S", "A", "B", "C")
DORMANT_DAYS = 30  # 满 30 天未被引用且未豁免 → 待淘汰（ADR 0003）

# 盯源候选卡与教师贡献的状态机（WP5）
WATCH_ITEM_STATUSES = ("待审", "已入库", "已忽略")
CONTRIB_KINDS = ("link", "kn_link")
CONTRIB_STATUSES = ("待审", "通过", "驳回")

# 状态机：draft → checking（机审，提交后自动进入）→ pending → reviewing → published/hidden；
# 退回/要求补充回 draft。机审（词库规则 + LLM 反例审校）由服务端在 submit 后异步执行，
# 结果以 kind=risk 批注呈现，reviews 留痕 action=checking。
# 结构化退回理由（reject/supplement 必选）：
REASON_TYPES = ("fact_error", "citation_unsupported", "forced_mapping",
                "over_praise", "wording", "other")
SNAP_KEYS = ["title", "summary", "theoryPoints", "blocks", "citations", "kit",
             "typeId", "audience", "course", "author", "org", "stageText", "applyCourses"]

SELFCHECK_NAMES = [
    ("ck-title", "标题已填写（非默认标题）"),
    ("ck-paras", "正文段落不少于 3 段"),
    ("ck-emptyh2", "没有空标题（每个标题下都有正文）"),
    ("ck-cite", "至少 1 处引用（理论或素材有着落）"),
    ("ck-len", "正文不少于 600 字"),
    ("ck-risk", "无待处理的风险提示批注"),
]


def _now():
    return time.strftime("%Y-%m-%d %H:%M")


def _uid(prefix):
    return "%s-%s" % (prefix, uuid.uuid4().hex[:10])


def snapshot_of(c):
    return {k: c[k] for k in SNAP_KEYS if k in c}


class CaseDB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------ 种子
    def seed(self, cases, materials=None):
        """cases/materials 表为空时灌入种子（files/cases_seed.json、files/materials_seed.json）。"""
        with self._lock:
            n = 0
            if not self._conn.execute("SELECT COUNT(*) c FROM cases").fetchone()["c"]:
                for c in cases:
                    self._insert_case(c)
                n = len(cases)
            if materials and not self._conn.execute(
                    "SELECT COUNT(*) c FROM materials").fetchone()["c"]:
                for m in materials:
                    self._insert_material(m)
            self._conn.commit()
            self._sync_material_usage()
            self._conn.commit()
            return n

    def reseed(self, cases, materials=None):
        """清空业务表并重新灌入种子（管理后台「重置演示数据」）。"""
        with self._lock:
            for t in ("cases", "reviews", "annotations", "versions", "favorites", "likes",
                      "mat_favorites", "watch_items", "contributions"):
                self._conn.execute("DELETE FROM " + t)
            if materials is not None:
                self._conn.execute("DELETE FROM materials")
                for m in materials:
                    self._insert_material(m)
            for c in cases:
                self._insert_case(c)
            self._conn.commit()
            self._sync_material_usage()
            self._conn.commit()
            return len(cases)

    def _insert_case(self, c):
        c = dict(c)
        annos = c.pop("annotations", []) or []
        versions = c.pop("versions", []) or []
        c.pop("likedBy", None)
        likes = c.pop("likes", 0) or 0
        self._conn.execute(
            "INSERT INTO cases(id,ownerId,status,title,likes,createdAt,updatedAt,submittedAt,publishedAt,data)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (c["id"], c.get("ownerId", ""), c.get("status", "draft"), c.get("title", ""),
             likes, c.get("createdAt"), c.get("updatedAt"),
             c.get("submittedAt"), c.get("publishedAt"),
             json.dumps(c, ensure_ascii=False)))
        for a in annos:
            a.setdefault("replies", [])
            self._conn.execute(
                "INSERT INTO annotations(id,caseId,kind,status,authorId,at,data) VALUES(?,?,?,?,?,?,?)",
                (a.get("id") or _uid("an"), c["id"], a.get("kind", ""), a.get("status", "pending"),
                 a.get("authorId", ""), a.get("createdAt", ""),
                 json.dumps(a, ensure_ascii=False)))
        for v in versions:
            self._conn.execute(
                "INSERT INTO versions(id,caseId,actorId,label,at,data) VALUES(?,?,?,?,?,?)",
                (v.get("id") or _uid("v"), c["id"], v.get("actorId", ""), v.get("label", ""),
                 v.get("at", ""), json.dumps(v, ensure_ascii=False)))

    # ------------------------------------------------------------ 组装
    def _case_obj(self, row):
        c = json.loads(row["data"])
        for k in ("id", "ownerId", "status", "title", "likes",
                  "createdAt", "updatedAt", "submittedAt", "publishedAt"):
            if row[k] is not None:
                c[k] = row[k]
        cid = row["id"]
        c["likedBy"] = [r["userId"] for r in self._conn.execute(
            "SELECT userId FROM likes WHERE caseId=? ORDER BY at", (cid,))]
        c["annotations"] = [json.loads(r["data"]) for r in self._conn.execute(
            "SELECT data FROM annotations WHERE caseId=? ORDER BY rowid", (cid,))]
        c["versions"] = [json.loads(r["data"]) for r in self._conn.execute(
            "SELECT data FROM versions WHERE caseId=? ORDER BY rowid", (cid,))]
        return c

    @staticmethod
    def _visible(row, user):
        if row["status"] == "published":
            return True
        return bool(user) and (user.get("admin") or row["ownerId"] == user["id"])

    def list_cases(self, user, status=None, owner_id=None):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM cases ORDER BY updatedAt DESC").fetchall()
            out = []
            for r in rows:
                if not self._visible(r, user):
                    continue
                if status and r["status"] != status:
                    continue
                if owner_id and r["ownerId"] != owner_id:
                    continue
                out.append(self._case_obj(r))
            return out

    def get_case(self, cid, user):
        with self._lock:
            r = self._conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
            if not r or not self._visible(r, user):
                return None
            return self._case_obj(r)

    def _row(self, cid):
        return self._conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()

    # ------------------------------------------------------------ 案例写入
    def create_case(self, user, c):
        with self._lock:
            if self._row(c.get("id") or ""):
                return None, "案例 id 已存在"
            c = dict(c)
            c["ownerId"] = user["id"]
            c["status"] = "draft"
            meta = c.setdefault("meta", {})  # AI 生成标识：origin/modelVersions/reviewedBy
            meta.setdefault("origin", "human")
            meta.setdefault("modelVersions", [])
            meta.setdefault("reviewedBy", "")
            c.setdefault("createdAt", _now())
            c["updatedAt"] = _now()
            self._insert_case(c)
            self._sync_selfchecks(c["id"])
            self._sync_material_usage()
            self._conn.commit()
            return self._case_obj(self._row(c["id"])), None

    def update_case(self, user, cid, patch):
        """整体覆盖内容字段（blocks/citations/kit 等）；状态/归属只能走流转接口。"""
        with self._lock:
            r = self._row(cid)
            if not r:
                return None, "案例不存在"
            if r["ownerId"] != user["id"]:
                return None, "仅作者本人可编辑"
            # 合并到既有数据：状态/归属/计数/发布快照等只能由服务端流转逻辑改写
            data = json.loads(r["data"])
            for k, v in patch.items():
                if k in ("id", "ownerId", "status", "likes", "likedBy", "annotations",
                         "versions", "publishedSnapshot", "createdAt", "submittedAt",
                         "publishedAt"):
                    continue
                data[k] = v
            data["updatedAt"] = _now()
            self._conn.execute(
                "UPDATE cases SET title=?, updatedAt=?, data=? WHERE id=?",
                (data.get("title", ""), data["updatedAt"],
                 json.dumps(data, ensure_ascii=False), cid))
            self._sync_selfchecks(cid)
            self._sync_material_usage()
            self._conn.commit()
            return self._case_obj(r), None

    def delete_case(self, user, cid):
        with self._lock:
            r = self._row(cid)
            if not r:
                return "案例不存在"
            if not (user.get("admin") or r["ownerId"] == user["id"]):
                return "仅作者本人或管理员可删除"
            for t in ("cases", "reviews", "annotations", "versions", "favorites", "likes"):
                self._conn.execute("DELETE FROM %s WHERE %s=?" % (
                    t, "id" if t == "cases" else "caseId"), (cid,))
            self._sync_material_usage()
            self._conn.commit()
            return None

    # ------------------------------------------------------------ 审核流转
    def _submit_round(self, cid):
        return self._conn.execute(
            "SELECT COUNT(*) c FROM versions WHERE caseId=? AND label LIKE '提交版%'", (cid,)
        ).fetchone()["c"]

    def _add_review(self, cid, actor_id, action, reason="", reason_type="",
                    offline_from="", rnd=0):
        self._conn.execute(
            "INSERT INTO reviews(id,caseId,actorId,action,reason,reasonType,offlineFrom,round,at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (_uid("rv"), cid, actor_id, action, reason, reason_type, offline_from, rnd, _now()))

    def _add_version(self, cid, actor_id, label, note="", snapshot=None):
        v = {"id": _uid("v"), "label": label, "at": _now(), "note": note}
        if snapshot is not None:
            v["snapshot"] = snapshot
            ds = self._diff_summary(cid, snapshot)
            if ds:
                v["diffSummary"] = ds
        self._conn.execute(
            "INSERT INTO versions(id,caseId,actorId,label,at,data) VALUES(?,?,?,?,?,?)",
            (v["id"], cid, actor_id, label, v["at"], json.dumps(v, ensure_ascii=False)))

    @staticmethod
    def _block_lines(blocks):
        return [str(b.get("text") or "") for b in blocks or []]

    def _diff_summary(self, cid, new_snap):
        """与上一版快照的 blocks 文本 diff 统计：增/删/改行数 + 变更块 id（b+块序号）。
        首个带快照的版本没有上一版，返回 None。"""
        prev = None
        for r in self._conn.execute(
                "SELECT data FROM versions WHERE caseId=? ORDER BY rowid DESC", (cid,)):
            x = json.loads(r["data"])
            if x.get("snapshot"):
                prev = x
                break
        if not prev:
            return None
        old = self._block_lines(prev["snapshot"].get("blocks"))
        new = self._block_lines(new_snap.get("blocks"))
        added = removed = changed = 0
        ids = []

        def nlines(texts):
            return sum(t.count("\n") + 1 for t in texts)

        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, old, new, autojunk=False).get_opcodes():
            if tag == "insert":
                added += nlines(new[j1:j2])
                ids += ["b%d" % j for j in range(j1, j2)]
            elif tag == "delete":
                removed += nlines(old[i1:i2])
            elif tag == "replace":
                changed += max(nlines(old[i1:i2]), nlines(new[j1:j2]))
                ids += ["b%d" % j for j in range(j1, j2)]
        return {"vs": prev.get("id", ""), "added": added,
                "removed": removed, "changed": changed, "blocks": ids}

    def transition(self, user, cid, action, reason="", reason_type="", offline_from=""):
        """submit/withdraw 限作者本人；start/approve/reject/supplement/hide/unhide 限 admin。"""
        with self._lock:
            r = self._row(cid)
            if not r:
                return None, "案例不存在", 404
            c = self._case_obj(r)
            is_owner = r["ownerId"] == user["id"]
            if action in ("submit", "withdraw") and not is_owner:
                return None, "仅作者本人可提交/撤回", 403
            if action in ("start", "approve", "reject", "supplement", "hide", "unhide") \
                    and not user.get("admin"):
                return None, "仅案例管理员可审核", 403
            st = r["status"]
            now = _now()
            if action == "submit":
                if st != "draft":
                    return None, "仅草稿可提交审核", 409
                n = self._submit_round(cid) + 1
                self._add_version(cid, user["id"], "提交版 v%d" % n, "提交审核", snapshot_of(c))
                # 先进 checking：服务端异步机审完成后转 pending（见 machine_check_apply）
                self._conn.execute("UPDATE cases SET status='checking', submittedAt=?, updatedAt=? WHERE id=?",
                                   (now, now, cid))
                self._add_review(cid, user["id"], "submit", rnd=n)
            elif action == "withdraw":
                if st != "pending":
                    return None, "仅待审状态可撤回（管理员开始审核后不可撤回）", 409
                self._add_version(cid, user["id"], "撤回", "审核开始前撤回提交")
                self._conn.execute("UPDATE cases SET status='draft', updatedAt=? WHERE id=?", (now, cid))
                self._add_review(cid, user["id"], "withdraw", rnd=self._submit_round(cid))
            elif action == "start":
                if st != "pending":
                    return None, "仅待审案例可开始审核", 409
                self._conn.execute("UPDATE cases SET status='reviewing', updatedAt=? WHERE id=?", (now, cid))
                self._add_review(cid, user["id"], "start", rnd=self._submit_round(cid))
            elif action == "approve":
                if st not in ("pending", "reviewing"):
                    return None, "案例不在审核流程中", 409
                pub_day = now[:10]
                snap = snapshot_of(c)
                self._add_version(cid, user["id"],
                                  "公开版 v%d" % max(1, self._submit_round(cid)),
                                  "审核通过并发布" + (reason and "：" + reason or ""), snap)
                data = json.loads(r["data"])
                data["publishedSnapshot"] = snap
                meta = data.setdefault("meta", {})
                meta["reviewedBy"] = user.get("name") or user["id"]
                self._conn.execute(
                    "UPDATE cases SET status='published', publishedAt=?, updatedAt=?, data=? WHERE id=?",
                    (pub_day, now, json.dumps(data, ensure_ascii=False), cid))
                self._add_review(cid, user["id"], "approve", reason, reason_type, offline_from,
                                 self._submit_round(cid))
            elif action in ("reject", "supplement"):
                if st not in ("pending", "reviewing"):
                    return None, "案例不在审核流程中", 409
                if reason_type not in REASON_TYPES:
                    return None, "退回/要求补充必须选择退回类型 reasonType（%s）" % "/".join(REASON_TYPES), 400
                self._add_version(cid, user["id"],
                                  "退回" if action == "reject" else "要求补充", reason)
                self._conn.execute("UPDATE cases SET status='draft', updatedAt=? WHERE id=?", (now, cid))
                self._add_review(cid, user["id"], action, reason, reason_type, offline_from,
                                 self._submit_round(cid))
            elif action == "hide":
                self._conn.execute("UPDATE cases SET status='hidden', updatedAt=? WHERE id=?", (now, cid))
                self._add_review(cid, user["id"], "hide", reason, reason_type, offline_from,
                                 self._submit_round(cid))
            elif action == "unhide":
                if st != "hidden":
                    return None, "案例当前不是隐藏状态", 409
                self._conn.execute("UPDATE cases SET status='published', updatedAt=? WHERE id=?", (now, cid))
                self._add_review(cid, user["id"], "unhide", reason)
            else:
                return None, "未知操作: " + action, 400
            self._sync_selfchecks(cid)
            self._sync_material_usage()
            self._conn.commit()
            return self._case_obj(self._row(cid)), None, 200

    def list_reviews(self, limit=50, case_id=None):
        with self._lock:
            sql = "SELECT * FROM reviews"
            args = ()
            if case_id:
                sql += " WHERE caseId=?"
                args = (case_id,)
            rows = self._conn.execute(
                sql + " ORDER BY at DESC, rowid DESC LIMIT ?", args + (limit,)).fetchall()
            return [self._review_obj(r) for r in rows]

    @staticmethod
    def _review_obj(r):
        return {"id": r["id"], "caseId": r["caseId"], "action": r["action"],
                "opinion": r["reason"], "reasonType": r["reasonType"],
                "offlineFrom": r["offlineFrom"], "by": r["actorId"],
                "at": r["at"], "round": r["round"]}

    # ------------------------------------------------------------ 机审（WP4）
    def get_case_data(self, cid):
        """机审等后台流程用的原始读取（不做可见性过滤）。"""
        with self._lock:
            r = self._row(cid)
            return json.loads(r["data"]) if r else None

    def machine_check_apply(self, cid, annotations, note, model=""):
        """机审落库（submit 后由服务端异步调用）：命中项写 kind=risk 批注、
        reviews 留痕 action=checking，状态 checking → pending；
        机审用过的模型记入 meta.modelVersions。"""
        with self._lock:
            r = self._row(cid)
            if not r or r["status"] != "checking":
                return None, "案例不在机审中"
            data = json.loads(r["data"])
            if model:
                mv = data.setdefault("meta", {}).setdefault("modelVersions", [])
                if model not in mv:
                    mv.append(model)
            now = _now()
            for a in annotations:
                a = dict(a)
                a.setdefault("id", _uid("an"))
                a.setdefault("kind", "risk")
                a.setdefault("status", "pending")
                a.setdefault("section", 0)
                a.setdefault("quote", "")
                a.setdefault("lowRisk", False)
                a.setdefault("createdAt", now)
                a.setdefault("replies", [])
                self._conn.execute(
                    "INSERT INTO annotations(id,caseId,kind,status,authorId,at,data)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (a["id"], cid, "risk", "pending", "", a["createdAt"],
                     json.dumps(a, ensure_ascii=False)))
            self._conn.execute(
                "UPDATE cases SET status='pending', updatedAt=?, data=? WHERE id=?",
                (now, json.dumps(data, ensure_ascii=False), cid))
            self._add_review(cid, "system", "checking", note, rnd=self._submit_round(cid))
            self._sync_selfchecks(cid)
            self._conn.commit()
            return self._case_obj(self._row(cid)), None

    def review_ledger(self, limit=200):
        """被退回表达台账（组织资产）：reject/supplement 留痕按 reasonType 聚合，附关联批注。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reviews WHERE action IN ('reject','supplement') AND reasonType!=''"
                " ORDER BY at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
            items, by_type = [], {}
            for r in rows:
                cr = self._row(r["caseId"])
                title = json.loads(cr["data"]).get("title", "") if cr else "（已删除）"
                annos = [{
                    "kind": a.get("kind", ""), "quote": a.get("quote", ""),
                    "text": a.get("text", ""),
                } for a in (json.loads(x["data"]) for x in self._conn.execute(
                        "SELECT data FROM annotations WHERE caseId=?"
                        " AND kind IN ('risk','admin') ORDER BY rowid DESC LIMIT 3",
                        (r["caseId"],)))]
                items.append({"id": r["id"], "caseId": r["caseId"], "caseTitle": title,
                              "action": r["action"], "reasonType": r["reasonType"],
                              "reason": r["reason"], "by": r["actorId"],
                              "at": r["at"], "round": r["round"], "annotations": annos})
                by_type[r["reasonType"]] = by_type.get(r["reasonType"], 0) + 1
            return {"items": items, "byType": by_type}

    # ------------------------------------------------------------ 批注
    def add_annotation(self, user, cid, anno):
        with self._lock:
            if not self._row(cid):
                return None, "案例不存在"
            a = dict(anno)
            a.setdefault("id", _uid("an"))
            a.setdefault("kind", "admin" if user.get("admin") else "author")
            a.setdefault("status", "pending")
            a.setdefault("createdAt", _now())
            a.setdefault("replies", [])
            a["authorId"] = user["id"]
            a.setdefault("author", user.get("name", ""))
            self._conn.execute(
                "INSERT INTO annotations(id,caseId,kind,status,authorId,at,data) VALUES(?,?,?,?,?,?,?)",
                (a["id"], cid, a.get("kind", ""), a["status"], user["id"], a["createdAt"],
                 json.dumps(a, ensure_ascii=False)))
            self._sync_selfchecks(cid)
            self._conn.commit()
            return a, None

    def patch_annotation(self, user, aid, patch):
        """status 流转与回复线程；回复（reopen=true）会重开已解决的批注。"""
        with self._lock:
            r = self._conn.execute("SELECT * FROM annotations WHERE id=?", (aid,)).fetchone()
            if not r:
                return None, "批注不存在"
            a = json.loads(r["data"])
            if patch.get("status"):
                a["status"] = patch["status"]
            if patch.get("section") is not None:
                a["section"] = patch["section"]
            reply = patch.get("reply")
            if reply and (reply.get("text") or "").strip():
                a.setdefault("replies", []).append({
                    "id": _uid("rp"), "by": user["id"], "byName": user.get("name", ""),
                    "text": reply["text"].strip(), "at": _now(),
                })
                if reply.get("reopen"):
                    a["status"] = "pending"
            a["resolved"] = a.get("status") == "resolved"
            self._conn.execute("UPDATE annotations SET status=?, data=? WHERE id=?",
                               (a.get("status", "pending"), json.dumps(a, ensure_ascii=False), aid))
            self._sync_selfchecks(r["caseId"])
            self._conn.commit()
            return a, None

    # ------------------------------------------------------------ 版本
    def save_version(self, user, cid, label):
        with self._lock:
            r = self._row(cid)
            if not r:
                return None, "案例不存在"
            if r["ownerId"] != user["id"]:
                return None, "仅作者本人可存版本"
            label = (label or "").strip() or "手动存档"
            self._add_version(cid, user["id"], label, "手动保存版本",
                              snapshot_of(self._case_obj(r)))
            self._conn.commit()
            row = self._conn.execute(
                "SELECT data FROM versions WHERE caseId=? ORDER BY rowid DESC LIMIT 1", (cid,)
            ).fetchone()
            return json.loads(row["data"]), None

    def rollback(self, user, cid, vid):
        with self._lock:
            r = self._row(cid)
            if not r:
                return None, "案例不存在"
            if r["ownerId"] != user["id"]:
                return None, "仅作者本人可回滚"
            vr = self._conn.execute(
                "SELECT data FROM versions WHERE id=? AND caseId=?", (vid, cid)).fetchone()
            v = json.loads(vr["data"]) if vr else None
            if not v or not v.get("snapshot"):
                return None, "该版本没有可用快照，不能作为回滚目标"
            c = self._case_obj(r)
            self._add_version(cid, user["id"], "回滚前自动快照",
                              "恢复到「%s」前的自动存档" % v.get("label", ""), snapshot_of(c))
            data = json.loads(r["data"])
            for k, val in v["snapshot"].items():
                data[k] = val
            data["updatedAt"] = _now()
            self._conn.execute("UPDATE cases SET title=?, updatedAt=?, data=? WHERE id=?",
                               (data.get("title", ""), data["updatedAt"],
                                json.dumps(data, ensure_ascii=False), cid))
            self._sync_selfchecks(cid)
            self._sync_material_usage()
            self._conn.commit()
            return self._case_obj(self._row(cid)), None

    # ------------------------------------------------------------ 收藏与点赞
    def set_favorite(self, user, cid, on):
        with self._lock:
            if not self._row(cid):
                return "案例不存在"
            if on:
                self._conn.execute(
                    "INSERT OR IGNORE INTO favorites(userId,caseId,at) VALUES(?,?,?)",
                    (user["id"], cid, _now()))
            else:
                self._conn.execute(
                    "DELETE FROM favorites WHERE userId=? AND caseId=?", (user["id"], cid))
            self._conn.commit()
            return None

    def list_favorites(self, user):
        with self._lock:
            return [r["caseId"] for r in self._conn.execute(
                "SELECT caseId FROM favorites WHERE userId=? ORDER BY at DESC", (user["id"],))]

    def set_like(self, user, cid, on):
        with self._lock:
            r = self._row(cid)
            if not r:
                return None, "案例不存在"
            if on:
                self._conn.execute(
                    "INSERT OR IGNORE INTO likes(userId,caseId,at) VALUES(?,?,?)",
                    (user["id"], cid, _now()))
                self._conn.execute("UPDATE cases SET likes=likes+1 WHERE id=?", (cid,))
            else:
                cur = self._conn.execute(
                    "DELETE FROM likes WHERE userId=? AND caseId=?", (user["id"], cid))
                if cur.rowcount:
                    self._conn.execute(
                        "UPDATE cases SET likes=MAX(0, likes-1) WHERE id=?", (cid,))
            self._conn.commit()
            row = self._row(cid)
            return {"likes": row["likes"],
                    "likedBy": [x["userId"] for x in self._conn.execute(
                        "SELECT userId FROM likes WHERE caseId=?", (cid,))]}, None

    # ------------------------------------------------------------ 提交前自检（未过项即批注）
    def _sync_selfchecks(self, cid):
        c = json.loads(self._row(cid)["data"])
        blocks = c.get("blocks") or []
        paras = [b for b in blocks if b.get("kind") == "p" and (b.get("text") or "").strip()]
        chars = sum(len(b["text"]) for b in paras)
        empty_h2 = False
        for i, b in enumerate(blocks):
            if b.get("kind") == "h2" and (b.get("text") or "").strip():
                nxt = next((x for x in blocks[i + 1:]
                            if x.get("kind") == "h2" or (x.get("text") or "").strip()), None)
                if nxt is None or nxt.get("kind") == "h2":
                    empty_h2 = True
                    break
        annos = [json.loads(r["data"]) for r in self._conn.execute(
            "SELECT data FROM annotations WHERE caseId=?", (cid,))]
        results = {
            "ck-title": bool((c.get("title") or "").strip()) and c.get("title") != "未命名案例",
            "ck-paras": len(paras) >= 3,
            "ck-emptyh2": not empty_h2,
            "ck-cite": len(c.get("citations") or []) >= 1,
            "ck-len": chars >= 600,
            "ck-risk": not any(a.get("kind") == "risk" and a.get("status") == "pending"
                               for a in annos),
        }
        names = dict(SELFCHECK_NAMES)
        for ck_id, ok in results.items():
            existing = next((a for a in annos
                             if a.get("kind") == "selfcheck" and a.get("checkId") == ck_id), None)
            if not ok and not existing:
                a = {"id": _uid("an"), "kind": "selfcheck", "checkId": ck_id,
                     "status": "pending", "section": 0, "quote": "",
                     "text": "提交前自检未通过：" + names[ck_id],
                     "author": "系统自检", "lowRisk": False,
                     "createdAt": _now(), "replies": []}
                self._conn.execute(
                    "INSERT INTO annotations(id,caseId,kind,status,authorId,at,data)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (a["id"], cid, "selfcheck", "pending", "", a["createdAt"],
                     json.dumps(a, ensure_ascii=False)))
            elif ok and existing and existing.get("status") == "pending":
                existing["status"] = "resolved"
                self._conn.execute("UPDATE annotations SET status='resolved', data=? WHERE id=?",
                                   (json.dumps(existing, ensure_ascii=False), existing["id"]))

    # ------------------------------------------------------------ 检索语料
    def cases_for_index(self):
        """检索索引用的轻量案例字段（不做可见性过滤，查询时按用户过滤）。"""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM cases").fetchall()
            out = []
            for r in rows:
                c = json.loads(r["data"])
                text = "\n".join([
                    c.get("title", ""), c.get("summary", ""),
                    " ".join(c.get("theoryPoints") or []),
                    " ".join((b.get("text") or "") for b in (c.get("blocks") or [])),
                ]).strip()
                out.append({"id": r["id"], "title": c.get("title", ""),
                            "status": r["status"], "ownerId": r["ownerId"], "text": text})
            return out

    # ============================================================ 素材登记（WP2）
    MAT_COLS = ["id", "title", "kind", "tags", "source", "sourceUrl", "level",
                "credibility", "grade", "gradeReason", "publishedAt", "collectedAt",
                "status", "summary", "excerpt", "fileId", "citedCount", "lastCitedAt",
                "scope", "exempt", "createdAt", "updatedAt"]

    def _insert_material(self, m):
        vals = []
        for k in self.MAT_COLS:
            v = m.get(k)
            if k == "tags":
                v = json.dumps(m.get("tags") or [], ensure_ascii=False)
            elif k in ("level", "citedCount", "exempt"):
                v = int(v or 0)
            elif v is None:
                v = "" if k not in ("createdAt", "updatedAt") else None
            vals.append(v)
        self._conn.execute(
            "INSERT INTO materials(%s) VALUES(%s)"
            % (",".join(self.MAT_COLS), ",".join("?" * len(self.MAT_COLS))),
            vals)

    @staticmethod
    def _dormant(m):
        """待淘汰（派生态，ADR 0003）：从未被引且入库满 30 天，且未被管理员豁免。"""
        if m["status"] != "正常" or m["citedCount"] > 0 or m["exempt"]:
            return False
        born = m["collectedAt"] or m["publishedAt"] or ""
        try:
            t = time.mktime(time.strptime(born[:10], "%Y-%m-%d"))
        except Exception:
            return False
        return (time.time() - t) > DORMANT_DAYS * 86400

    def _mat_obj(self, row):
        m = {k: row[k] for k in self.MAT_COLS if k != "tags"}
        m["tags"] = json.loads(row["tags"] or "[]")
        m["dormant"] = self._dormant(m)
        m["uploaded"] = m["fileId"].startswith("f-up-")
        return m

    def _mat_row(self, mid):
        return self._conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()

    def _mat_visible(self, row, user):
        if user and user.get("admin"):
            return True
        if row["status"] in ("候选", "停用"):
            return False
        return row["level"] <= (user["maxLevel"] if user else 0)

    def list_materials(self, user, status=None, kind=None, grade=None, q=None):
        """status 取 候选/正常/停用/来源失效/待淘汰（派生）；grade 支持 S/A/B/C 与「未定级」。"""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM materials ORDER BY collectedAt DESC, rowid").fetchall()
            out = []
            for r in rows:
                if not self._mat_visible(r, user):
                    continue
                m = self._mat_obj(r)
                if status:
                    if status == "待淘汰":
                        if not m["dormant"]:
                            continue
                    elif m["status"] != status:
                        continue
                if kind and m["kind"] != kind:
                    continue
                if grade:
                    want = "" if grade == "未定级" else grade
                    if m["grade"] != want:
                        continue
                if q:
                    hay = m["title"] + m["source"] + m["summary"] + " ".join(m["tags"])
                    if q not in hay:
                        continue
                out.append(m)
            return out

    def get_material(self, mid, user):
        with self._lock:
            r = self._mat_row(mid)
            if not r or not self._mat_visible(r, user):
                return None
            return self._mat_obj(r)

    def get_material_raw(self, mid):
        """不做可见性过滤的素材读取（服务端内部：引用证据迁移/兜底回填用）。"""
        with self._lock:
            r = self._mat_row(mid)
            return self._mat_obj(r) if r else None

    def migrate_citation_evidence(self, resolve):
        """启动迁移（WP3）：案例 citations（含发布快照）缺 evidence 的 best-effort 回填。
        resolve(target) -> dict(sec/snippet/capturedAt 等） 或 None；返回回填条数。
        resolve 可能回调本库（get_material_raw），故在锁外执行，仅写入时持锁。"""
        with self._lock:
            rows = [(r["id"], r["data"]) for r in
                    self._conn.execute("SELECT id, data FROM cases").fetchall()]
        n, updates = 0, []
        for cid, raw in rows:
            data = json.loads(raw)
            changed = False
            holders = [data]
            if isinstance(data.get("publishedSnapshot"), dict):
                holders.append(data["publishedSnapshot"])
            for holder in holders:
                for ref in holder.get("citations") or []:
                    if not isinstance(ref, dict) or ref.get("evidence"):
                        continue
                    ev = resolve(ref.get("target") or "")
                    if not ev:
                        continue
                    ref["evidence"] = ev
                    changed = True
                    n += 1
            if changed:
                updates.append((json.dumps(data, ensure_ascii=False), cid))
        if updates:
            with self._lock:
                for d, cid in updates:
                    self._conn.execute("UPDATE cases SET data=? WHERE id=?", (d, cid))
                self._conn.commit()
        return n

    def find_material_by_url(self, url):
        """URL 查重（入库闸，ADR 0003）。"""
        if not url:
            return None
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM materials WHERE sourceUrl=? AND sourceUrl!=''", (url,)).fetchone()
            return self._mat_obj(r) if r else None

    def create_material(self, user, m, status="候选"):
        """采集入库：新素材默认落「候选」，admin 确认（改状态）后才进检索语料（入库闸）；
        admin 上传真实文件直通 status='正常'（文件已在库内，管理员即入库闸）。"""
        with self._lock:
            m = dict(m)
            m.setdefault("id", _uid("m"))
            if self._mat_row(m["id"]):
                return None, "素材 id 已存在"
            m["status"] = status if status in MAT_STATUSES else "候选"
            now = _now()
            m.setdefault("collectedAt", now[:10])
            m["createdAt"] = now
            m["updatedAt"] = now
            self._insert_material(m)
            self._conn.commit()
            return self._mat_obj(self._mat_row(m["id"])), None

    # admin 可改的治理字段；非 admin 仅允许「重新采集」刷新内容副本
    MAT_ADMIN_FIELDS = ("title", "kind", "tags", "source", "sourceUrl", "level",
                        "credibility", "grade", "gradeReason", "publishedAt",
                        "collectedAt", "status", "summary", "excerpt", "scope", "exempt")
    MAT_REFETCH_FIELDS = ("title", "excerpt", "collectedAt")

    def update_material(self, user, mid, patch):
        with self._lock:
            r = self._mat_row(mid)
            if not r:
                return None, "素材不存在"
            admin = bool(user and user.get("admin"))
            allowed = self.MAT_ADMIN_FIELDS if admin else self.MAT_REFETCH_FIELDS
            sets, vals = [], []
            for k, v in (patch or {}).items():
                if k not in allowed:
                    continue
                if k == "status" and v not in MAT_STATUSES:
                    return None, "状态取值无效"
                if k == "grade" and v and v not in MAT_GRADES:
                    return None, "信源等级取值无效"
                if k == "level" and v not in (0, 1, 2):
                    return None, "密级取值无效"
                if k == "tags":
                    v = json.dumps(v or [], ensure_ascii=False)
                if k in ("level", "exempt"):
                    v = int(v or 0)
                sets.append("%s=?" % k)
                vals.append(v)
            if not sets:
                return None, "没有可更新的字段" if not admin else "没有可更新的字段"
            sets.append("updatedAt=?")
            vals.append(_now())
            vals.append(mid)
            self._conn.execute("UPDATE materials SET %s WHERE id=?" % ",".join(sets), vals)
            self._conn.commit()
            return self._mat_obj(self._mat_row(mid)), None

    def batch_update_materials(self, user, ids, patch):
        """批量治理（admin）：调密级/停用恢复/豁免淘汰/确认候选入库等。"""
        if not (user and user.get("admin")):
            return None, "仅案例管理员可批量操作"
        out = []
        for mid in ids or []:
            m, _e = self.update_material(user, mid, patch)
            if m:
                out.append(m)
        return out, None

    def delete_material_by_file(self, file_id):
        """上传文件删除时联动删除素材行（文件库是上传素材的实体来源）。"""
        with self._lock:
            cur = self._conn.execute("DELETE FROM materials WHERE fileId=?", (file_id,))
            self._conn.execute("DELETE FROM mat_favorites WHERE materialId NOT IN (SELECT id FROM materials)")
            self._conn.commit()
            return cur.rowcount

    def mark_materials_failed(self, ids):
        """来源健康检查失败的素材标「来源失效」（不停用、不删除）。"""
        with self._lock:
            n = 0
            for mid in ids:
                cur = self._conn.execute(
                    "UPDATE materials SET status='来源失效', updatedAt=? WHERE id=? AND status!='停用'",
                    (_now(), mid))
                n += cur.rowcount
            self._conn.commit()
            return n

    # ------------------------------------------------------------ 素材使用度
    def _sync_material_usage(self):
        """citedCount/lastCitedAt 全量重算：「被用」= 进入案例引用清单（含发布快照，ADR 0003）。
        在每次案例写入后调用，所有客户端看到同一份。"""
        if not self._conn.execute("SELECT COUNT(*) c FROM materials").fetchone()["c"]:
            return
        usage = {}
        for r in self._conn.execute("SELECT data, updatedAt FROM cases").fetchall():
            c = json.loads(r["data"])
            sets = [c.get("citations") or []]
            snap = c.get("publishedSnapshot") or {}
            if snap.get("citations"):
                sets.append(snap["citations"])
            for s in sets:
                for ref in s:
                    t = ref.get("target") if isinstance(ref, dict) else ref
                    if not t:
                        continue
                    at = (isinstance(ref, dict) and ref.get("at")) or c.get("updatedAt") or r["updatedAt"] or ""
                    cnt, last = usage.get(t, (0, ""))
                    usage[t] = (cnt + 1, max(last, at))
        # 未被任何案例引用的素材清零（案例删引用/删除后计数要回落）
        self._conn.execute("UPDATE materials SET citedCount=0, lastCitedAt=''")
        for mid, (cnt, last) in usage.items():
            self._conn.execute(
                "UPDATE materials SET citedCount=?, lastCitedAt=? WHERE id=?", (cnt, last, mid))

    # ------------------------------------------------------------ 素材收藏
    def set_mat_favorite(self, user, mid, on):
        with self._lock:
            if not self._mat_row(mid):
                return "素材不存在"
            if on:
                self._conn.execute(
                    "INSERT OR IGNORE INTO mat_favorites(userId,materialId,at) VALUES(?,?,?)",
                    (user["id"], mid, _now()))
            else:
                self._conn.execute(
                    "DELETE FROM mat_favorites WHERE userId=? AND materialId=?",
                    (user["id"], mid))
            self._conn.commit()
            return None

    def list_mat_favorites(self, user):
        with self._lock:
            return [r["materialId"] for r in self._conn.execute(
                "SELECT materialId FROM mat_favorites WHERE userId=? ORDER BY at DESC",
                (user["id"],))]

    # ------------------------------------------------------------ 推荐与最近引用
    def recommend_materials(self, user, case_id, limit=12):
        """工作台无输入推荐（ADR 0004 方向）：共享标签/理论点 + 同类型案例引用 + 共引关系打分，
        排除已引用与不可见素材。"""
        with self._lock:
            cr = self._row(case_id)
            if not cr or not self._visible(cr, user):
                return None, "案例不存在或无权查看"
            c = json.loads(cr["data"])
            cited = {ref.get("target") for ref in (c.get("citations") or [])
                     if isinstance(ref, dict) and ref.get("target")}
            cited_kn = {t for t in cited if t.startswith("kn-")}
            words = set(c.get("theoryPoints") or []) | set(c.get("tags") or [])
            # 教师贡献的知识点-素材关联（admin 通过的 kn_link）：本案例引用了该 kn 节时加分
            kn_links = {}
            for lr in self._conn.execute(
                    "SELECT payload FROM contributions WHERE kind='kn_link' AND status='通过'"):
                try:
                    lp = json.loads(lr["payload"])
                except Exception:
                    continue
                if lp.get("knId") and lp.get("materialId"):
                    kn_links.setdefault(lp["materialId"], set()).add(lp["knId"])
            score = {}
            for r in self._conn.execute("SELECT data FROM cases WHERE id!=?", (case_id,)).fetchall():
                x = json.loads(r["data"])
                refs = [ref.get("target") for ref in (x.get("citations") or [])
                        if isinstance(ref, dict) and ref.get("target")]
                mats = [t for t in refs if t and not t.startswith("kn-")]
                if not mats:
                    continue
                same_type = x.get("typeId") == c.get("typeId")
                # 共引：与本案例引用过同一素材，或同一教材节（共享 kn 节）
                co = bool(cited & set(mats)) or bool(cited_kn & set(refs))
                for t in mats:
                    if t in cited:
                        continue
                    s = 0
                    if co:
                        s += 2
                    if same_type:
                        s += 1  # 同类型案例引用过
                    if s:
                        score[t] = score.get(t, 0) + s
            rows = self._conn.execute("SELECT * FROM materials").fetchall()
            out = []
            for r in rows:
                if r["id"] in cited or not self._mat_visible(r, user) or r["status"] != "正常":
                    continue
                m = self._mat_obj(r)
                s = score.get(r["id"], 0)
                if cited_kn & kn_links.get(r["id"], set()):
                    s += 3  # 已确认的知识点-素材关联
                overlap = words & set(m["tags"])
                s += 2 * len(overlap)
                hay = m["title"] + m["summary"]
                s += sum(1 for w in words if w and w in hay)  # 理论点命中标题/摘要
                if s <= 0:
                    continue
                s += min(m["citedCount"], 10) * 0.2
                out.append((s, m))
            out.sort(key=lambda e: -e[0])
            return [m for _s, m in out[:limit]], None

    def recent_cited_materials(self, user, uid, limit=12):
        """最近引用：从本人案例的引用清单派生（按引用时间倒序去重）。"""
        if uid != user["id"] and not user.get("admin"):
            return None, "仅本人或管理员可查看"
        with self._lock:
            seen, order = set(), []
            rows = self._conn.execute(
                "SELECT data, updatedAt FROM cases WHERE ownerId=? ORDER BY updatedAt DESC",
                (uid,)).fetchall()
            for r in rows:
                c = json.loads(r["data"])
                refs = list(c.get("citations") or [])
                refs.reverse()  # 列表尾部是最新挂接
                for ref in refs:
                    t = ref.get("target") if isinstance(ref, dict) else ref
                    if not t or t.startswith("kn-") or t in seen:
                        continue
                    mr = self._mat_row(t)
                    if not mr or not self._mat_visible(mr, user):
                        continue
                    seen.add(t)
                    order.append(self._mat_obj(mr))
                    if len(order) >= limit:
                        return order, None
            return order, None

    def materials_for_index(self):
        """检索语料：仅 status=正常 的素材进索引（候选只可在管理台检索，入库闸）。"""
        with self._lock:
            return [self._mat_obj(r) for r in self._conn.execute(
                "SELECT * FROM materials WHERE status='正常'").fetchall()]

    # ============================================================ 盯源（WP5）
    def seed_watch_sources(self, sources):
        """预置盯源（空表时灌入；只配置不保证可达）。"""
        with self._lock:
            if self._conn.execute("SELECT COUNT(*) c FROM watch_sources").fetchone()["c"]:
                return 0
            for s in sources:
                self._conn.execute(
                    "INSERT INTO watch_sources(id,name,url,keywords,enabled) VALUES(?,?,?,?,1)",
                    (_uid("ws"), s.get("name", ""), s.get("url", ""),
                     json.dumps(s.get("keywords") or [], ensure_ascii=False)))
            self._conn.commit()
            return len(sources)

    @staticmethod
    def _source_obj(r):
        return {"id": r["id"], "name": r["name"], "url": r["url"],
                "keywords": json.loads(r["keywords"] or "[]"),
                "enabled": bool(r["enabled"]), "lastRunAt": r["lastRunAt"],
                "lastItemCount": r["lastItemCount"]}

    def list_watch_sources(self):
        with self._lock:
            return [self._source_obj(r) for r in self._conn.execute(
                "SELECT * FROM watch_sources ORDER BY rowid").fetchall()]

    def create_watch_source(self, s):
        with self._lock:
            name = (s.get("name") or "").strip()
            url = (s.get("url") or "").strip()
            if not name or not url:
                return None, "缺少来源名称 name 或栏目链接 url"
            if self._conn.execute("SELECT 1 FROM watch_sources WHERE url=?", (url,)).fetchone():
                return None, "该栏目链接已在盯源列表中"
            sid = _uid("ws")
            self._conn.execute(
                "INSERT INTO watch_sources(id,name,url,keywords,enabled) VALUES(?,?,?,?,?)",
                (sid, name, url,
                 json.dumps(s.get("keywords") or [], ensure_ascii=False),
                 1 if s.get("enabled", True) else 0))
            self._conn.commit()
            r = self._conn.execute("SELECT * FROM watch_sources WHERE id=?", (sid,)).fetchone()
            return self._source_obj(r), None

    def update_watch_source(self, sid, patch):
        with self._lock:
            if not self._conn.execute("SELECT 1 FROM watch_sources WHERE id=?", (sid,)).fetchone():
                return None, "盯源不存在"
            sets, vals = [], []
            for k in ("name", "url"):
                if k in patch and str(patch[k]).strip():
                    sets.append("%s=?" % k)
                    vals.append(str(patch[k]).strip())
            if "keywords" in patch:
                sets.append("keywords=?")
                vals.append(json.dumps(patch["keywords"] or [], ensure_ascii=False))
            if "enabled" in patch:
                sets.append("enabled=?")
                vals.append(1 if patch["enabled"] else 0)
            if not sets:
                return None, "没有可更新的字段"
            vals.append(sid)
            self._conn.execute("UPDATE watch_sources SET %s WHERE id=?" % ",".join(sets), vals)
            self._conn.commit()
            r = self._conn.execute("SELECT * FROM watch_sources WHERE id=?", (sid,)).fetchone()
            return self._source_obj(r), None

    def delete_watch_source(self, sid):
        with self._lock:
            cur = self._conn.execute("DELETE FROM watch_sources WHERE id=?", (sid,))
            self._conn.execute("DELETE FROM watch_items WHERE sourceId=?", (sid,))
            self._conn.commit()
            return cur.rowcount

    def mark_watch_run(self, sid, count):
        with self._lock:
            self._conn.execute(
                "UPDATE watch_sources SET lastRunAt=?, lastItemCount=? WHERE id=?",
                (_now(), count, sid))
            self._conn.commit()

    # ------------------------------------------------------------ 盯源候选卡
    @staticmethod
    def _fingerprint(title):
        """内容指纹：标题去空白小写后的 md5（同事件重复报道的第一道去重）。"""
        norm = re.sub(r"\s+", "", (title or "").lower())
        return hashlib.md5(norm.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _watch_item_obj(r):
        return {"id": r["id"], "sourceId": r["sourceId"], "title": r["title"],
                "url": r["url"], "summary": r["summary"], "publishedAt": r["publishedAt"],
                "fingerprint": r["fingerprint"], "status": r["status"],
                "materialId": r["materialId"], "fetchedAt": r["fetchedAt"]}

    def add_watch_items(self, source_id, items):
        """候选卡落库：URL + 标题指纹双重去重（对 watch_items 与 materials.sourceUrl）。"""
        added = 0
        with self._lock:
            for it in items or []:
                url = (it.get("url") or "").strip()
                title = (it.get("title") or "").strip()
                if not url or not title:
                    continue
                fp = self._fingerprint(title)
                if self._conn.execute(
                        "SELECT 1 FROM watch_items WHERE url=? OR fingerprint=? LIMIT 1",
                        (url, fp)).fetchone():
                    continue
                if self._conn.execute(
                        "SELECT 1 FROM materials WHERE sourceUrl=? AND sourceUrl!='' LIMIT 1",
                        (url,)).fetchone():
                    continue
                self._conn.execute(
                    "INSERT INTO watch_items(id,sourceId,title,url,summary,publishedAt,"
                    "fingerprint,status,fetchedAt) VALUES(?,?,?,?,?,?,?,'待审',?)",
                    (_uid("wi"), source_id, title, url, it.get("summary") or "",
                     (it.get("publishedAt") or "")[:10], fp, _now()))
                added += 1
            self._conn.commit()
        return added

    def list_watch_items(self, status=None, limit=300):
        with self._lock:
            sql = "SELECT * FROM watch_items"
            args = ()
            if status:
                sql += " WHERE status=?"
                args = (status,)
            rows = self._conn.execute(
                sql + " ORDER BY fetchedAt DESC, rowid DESC LIMIT ?", args + (limit,)).fetchall()
            return [self._watch_item_obj(r) for r in rows]

    def get_watch_item(self, iid):
        with self._lock:
            r = self._conn.execute("SELECT * FROM watch_items WHERE id=?", (iid,)).fetchone()
            return self._watch_item_obj(r) if r else None

    def set_watch_item(self, iid, status, material_id=""):
        if status not in WATCH_ITEM_STATUSES:
            return None, "候选卡状态取值无效"
        with self._lock:
            cur = self._conn.execute(
                "UPDATE watch_items SET status=?, materialId=? WHERE id=?",
                (status, material_id, iid))
            self._conn.commit()
            if not cur.rowcount:
                return None, "候选卡不存在"
            r = self._conn.execute("SELECT * FROM watch_items WHERE id=?", (iid,)).fetchone()
            return self._watch_item_obj(r), None

    # ============================================================ 众筹贡献（WP5）
    @staticmethod
    def _contrib_obj(r):
        return {"id": r["id"], "userId": r["userId"], "kind": r["kind"],
                "payload": json.loads(r["payload"] or "{}"), "status": r["status"],
                "reviewedBy": r["reviewedBy"], "at": r["at"]}

    def create_contribution(self, user, kind, payload):
        if kind not in CONTRIB_KINDS:
            return None, "贡献类型取值无效（%s）" % "/".join(CONTRIB_KINDS)
        with self._lock:
            cid = _uid("cb")
            self._conn.execute(
                "INSERT INTO contributions(id,userId,kind,payload,status,at) VALUES(?,?,?,?,'待审',?)",
                (cid, user["id"], kind, json.dumps(payload or {}, ensure_ascii=False), _now()))
            self._conn.commit()
            r = self._conn.execute("SELECT * FROM contributions WHERE id=?", (cid,)).fetchone()
            return self._contrib_obj(r), None

    def list_contributions(self, user):
        """先审后发：普通用户仅见本人贡献与状态，admin 见全量。"""
        with self._lock:
            if user.get("admin"):
                rows = self._conn.execute(
                    "SELECT * FROM contributions ORDER BY at DESC, rowid DESC LIMIT 300").fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM contributions WHERE userId=? ORDER BY at DESC, rowid DESC LIMIT 300",
                    (user["id"],)).fetchall()
            return [self._contrib_obj(r) for r in rows]

    def review_contribution(self, user, cid, action, reason=""):
        """admin 审核贡献：link 通过 → 走入库闸落素材「候选」（URL 查重沿用）；
        kn_link 通过 → 关联生效（体现在 recommend_materials 打分里）；驳回记 reviewNote。"""
        if not user.get("admin"):
            return None, "仅案例管理员可审核贡献", 403
        if action not in ("approve", "reject"):
            return None, "未知审核动作", 400
        with self._lock:
            r = self._conn.execute("SELECT * FROM contributions WHERE id=?", (cid,)).fetchone()
            if not r:
                return None, "贡献不存在", 404
            if r["status"] != "待审":
                return None, "该贡献已审核过", 409
            row = dict(r)
        p = json.loads(row["payload"] or "{}")
        material = None
        if action == "approve" and row["kind"] == "link":
            dup = self.find_material_by_url(p.get("url") or "")
            if dup:
                material = dup  # 链接已在库中，直接关联既有素材
            else:
                grade = p.get("grade") if p.get("grade") in MAT_GRADES else "B"
                material, e = self.create_material(user, {
                    "title": p.get("title") or p.get("url"),
                    "kind": "链接",
                    "source": p.get("source") or "教师贡献",
                    "sourceUrl": p["url"],
                    "publishedAt": (p.get("publishedAt") or "")[:10] or _now()[:10],
                    "grade": grade,
                    "gradeReason": p.get("gradeReason")
                                   or "教师贡献链接（建议 %s 级），管理员确认定级" % grade,
                    "summary": p.get("summary") or "",
                    "credibility": "normal",
                }, status="候选")
                if e:
                    return None, "入库失败：" + e, 409
            p["materialId"] = material["id"]
        if action == "reject" and reason:
            p["reviewNote"] = reason
        with self._lock:
            self._conn.execute(
                "UPDATE contributions SET status=?, reviewedBy=?, payload=? WHERE id=?",
                ("通过" if action == "approve" else "驳回",
                 user.get("name") or user["id"],
                 json.dumps(p, ensure_ascii=False), cid))
            self._conn.commit()
            r = self._conn.execute("SELECT * FROM contributions WHERE id=?", (cid,)).fetchone()
            return (self._contrib_obj(r), material), None, 200

    # ------------------------------------------------------------ 我的生成偏好（WP4b）
    PREF_KEYS = ("length", "style", "bannedWords", "themes")

    def get_prefs(self, user_id):
        """教师显式填写的生成偏好；未填写时四个字段均为空串。"""
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM user_prefs WHERE userId=?", (user_id,)).fetchone()
            out = {k: (r[k] or "") if r else "" for k in self.PREF_KEYS}
            out["updatedAt"] = (r["updatedAt"] or "") if r else ""
            return out

    def set_prefs(self, user_id, prefs):
        """整体覆盖（PUT 语义）；四项全空即清空（删行）。偏好只来自教师亲手填写。"""
        vals = {k: str((prefs or {}).get(k) or "").strip()[:200] for k in self.PREF_KEYS}
        with self._lock:
            if any(vals.values()):
                self._conn.execute(
                    "INSERT OR REPLACE INTO user_prefs(userId,length,style,bannedWords,themes,updatedAt)"
                    " VALUES(?,?,?,?,?,?)",
                    (user_id, vals["length"], vals["style"], vals["bannedWords"],
                     vals["themes"], _now()))
            else:
                self._conn.execute("DELETE FROM user_prefs WHERE userId=?", (user_id,))
            self._conn.commit()
        return self.get_prefs(user_id)

    # ------------------------------------------------------------ 我的影响力
    def my_impact(self, user):
        """被引用/被改编数据页（从简）：素材贡献被引次数 + 案例被收藏/被点赞聚合。"""
        with self._lock:
            case_ids = [r["id"] for r in self._conn.execute(
                "SELECT id FROM cases WHERE ownerId=?", (user["id"],))]
            likes = favs = 0
            if case_ids:
                marks = ",".join("?" * len(case_ids))
                likes = self._conn.execute(
                    "SELECT COUNT(*) c FROM likes WHERE caseId IN (%s)" % marks,
                    case_ids).fetchone()["c"]
                favs = self._conn.execute(
                    "SELECT COUNT(*) c FROM favorites WHERE caseId IN (%s)" % marks,
                    case_ids).fetchone()["c"]
            rows = self._conn.execute(
                "SELECT kind, status, payload FROM contributions WHERE userId=?",
                (user["id"],)).fetchall()
            mat_ids, by_status = [], {}
            for r in rows:
                by_status[r["status"]] = by_status.get(r["status"], 0) + 1
                if r["kind"] == "link" and r["status"] == "通过":
                    mid = (json.loads(r["payload"] or "{}")).get("materialId")
                    if mid:
                        mat_ids.append(mid)
            cited = 0
            for mid in mat_ids:
                mr = self._mat_row(mid)
                if mr:
                    cited += mr["citedCount"]
            return {"caseLikes": likes, "caseFavorites": favs,
                    "materialsCited": cited, "contributedMaterials": len(mat_ids),
                    "contributions": by_status}
