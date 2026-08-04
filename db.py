# -*- coding: utf-8 -*-
"""案例业务数据 SQLite 持久层：案例/审核留痕/批注/版本/收藏/点赞。

cases.data 存完整案例 JSON（blocks/citations/kit 等）；批注、版本、点赞人独立成表，
读取时按前端既有对象形状组装（annotations/versions/likedBy 内嵌进案例对象）。
提交前自检批注（selfcheck）由服务端在每次写入后同步，所有客户端看到同一份。
"""
import json
import os
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
"""

# 状态机：draft/pending/reviewing/published/hidden（checking 预留给机审）
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
    def seed(self, cases):
        """cases 表为空时灌入种子案例（files/cases_seed.json），返回灌入数量。"""
        with self._lock:
            if self._conn.execute("SELECT COUNT(*) c FROM cases").fetchone()["c"]:
                return 0
            for c in cases:
                self._insert_case(c)
            self._conn.commit()
            return len(cases)

    def reseed(self, cases):
        """清空业务表并重新灌入种子（管理后台「重置演示数据」）。"""
        with self._lock:
            for t in ("cases", "reviews", "annotations", "versions", "favorites", "likes"):
                self._conn.execute("DELETE FROM " + t)
            for c in cases:
                self._insert_case(c)
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
            c.setdefault("createdAt", _now())
            c["updatedAt"] = _now()
            self._insert_case(c)
            self._sync_selfchecks(c["id"])
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
        self._conn.execute(
            "INSERT INTO versions(id,caseId,actorId,label,at,data) VALUES(?,?,?,?,?,?)",
            (v["id"], cid, actor_id, label, v["at"], json.dumps(v, ensure_ascii=False)))

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
                self._conn.execute("UPDATE cases SET status='pending', submittedAt=?, updatedAt=? WHERE id=?",
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
                self._conn.execute(
                    "UPDATE cases SET status='published', publishedAt=?, updatedAt=?, data=? WHERE id=?",
                    (pub_day, now, json.dumps(data, ensure_ascii=False), cid))
                self._add_review(cid, user["id"], "approve", reason, reason_type, offline_from,
                                 self._submit_round(cid))
            elif action in ("reject", "supplement"):
                if st not in ("pending", "reviewing"):
                    return None, "案例不在审核流程中", 409
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
