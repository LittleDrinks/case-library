# -*- coding: utf-8 -*-
"""Neo4j 图谱库（WP7）：Chapter/Knowledge/Case/Material/Tag 五类节点，
CITES（案例→素材/知识节）、MENTIONS（素材→知识节，LLM 增强）、
BELONGS（节→章）、HAS_TAG（案例/素材→标签，src=meta 声明标签 / llm 抽取主题词）四类边。

依赖官方 pip 驱动 neo4j（.venv）；驱动缺失或 Neo4j 不可达时降级：available() 为 False，
写操作静默跳过（stderr 记一次），读接口返回 None 由 server 层转降级提示——不影响其他功能。
连接惰性建立，故障后 30s 重试。所有输出节点形状与前端 graph.js 约定一致：
{id, label, type, ref:{kind,id}}，边 {source, target, rel}（rel 取 包含/引用/涉及/标签）。
"""
import sys
import threading
import time

try:
    from neo4j import GraphDatabase
    _HAS_DRIVER = True
except ImportError:
    _HAS_DRIVER = False

# 前端类型/详情跳转 kind 映射
_TYPE = {"Chapter": "chapter", "Knowledge": "section", "Case": "case",
         "Material": "material", "Tag": "tag"}
_KIND = {"Chapter": "chapter", "Knowledge": "knowledge", "Case": "case",
         "Material": "material", "Tag": "tag"}
_REL_NAME = {"CITES": "引用", "MENTIONS": "涉及", "BELONGS": "包含", "HAS_TAG": "标签"}
# ego 入参 type → (label, 键属性)
_NODE_KEY = {"case": ("Case", "id"), "material": ("Material", "id"),
             "knowledge": ("Knowledge", "id"), "section": ("Knowledge", "id"),
             "chapter": ("Chapter", "id"), "tag": ("Tag", "name")}
_RETRY_SECONDS = 30


class Graph(object):
    def __init__(self, uri, user, password):
        self._err_logged = False
        self._down_until = 0.0
        self._lock = threading.Lock()
        self.gen = 0  # 重建代次：LLM 增强线程据此丢弃过期写入
        self._driver = None
        if not (_HAS_DRIVER and uri and password):
            return
        try:
            self._driver = GraphDatabase.driver(
                uri, auth=(user, password),
                connection_acquisition_timeout=5, max_transaction_retry_time=3)
        except Exception as e:
            sys.stderr.write("[graph] Neo4j 驱动初始化失败：%s\n" % e)

    @property
    def configured(self):
        return self._driver is not None

    def _fail(self, e):
        self._down_until = time.time() + _RETRY_SECONDS
        if not self._err_logged:
            self._err_logged = True
            sys.stderr.write("[graph] Neo4j 不可达，图谱功能降级（%s）；恢复后自动重连\n" % e)

    def available(self):
        if not self._driver or time.time() < self._down_until:
            return False
        try:
            with self._driver.session() as s:
                s.run("RETURN 1").consume()
            self._err_logged = False
            return True
        except Exception as e:
            self._fail(e)
            return False

    def _run(self, cypher, **params):
        """单语句写/读（自动降级：异常返回 None）。"""
        if not self._driver or time.time() < self._down_until:
            return None
        try:
            with self._lock, self._driver.session() as s:
                return list(s.run(cypher, **params))
        except Exception as e:
            self._fail(e)
            return None

    # ------------------------------------------------------------ 灌库
    def rebuild(self, data):
        """全量重建（启动/管理后台/reseed 后）；data 见 server._graph_snapshot。
        返回各标签节点计数，不可用时返回 None。"""
        if not self.available():
            return None
        with self._lock:
            self.gen += 1
            stmts = [
                "MATCH (n) DETACH DELETE n",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Chapter) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Knowledge) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Case) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Material) REQUIRE n.id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Tag) REQUIRE n.name IS UNIQUE",
                # 章 / 节（教材骨架）
                """UNWIND $rows AS r MERGE (n:Chapter {id:r.id})
                   SET n.title=r.title, n.index=r.index""",
                """UNWIND $rows AS r MERGE (n:Knowledge {id:r.id})
                   SET n.title=r.title, n.chapter=r.chapter, n.index=r.index,
                       n.fileSec=r.fileSec, n.snippet=r.snippet""",
                """UNWIND $rows AS r MATCH (k:Knowledge {id:r.id}), (c:Chapter {id:r.chapterId})
                   MERGE (k)-[:BELONGS]->(c)""",
                # 案例（CITES 目标含发布快照引用，server 侧已并集）
                """UNWIND $rows AS r MERGE (n:Case {id:r.id})
                   SET n.title=r.title, n.status=r.status, n.typeId=r.typeId,
                       n.ownerId=r.ownerId, n.summary=r.summary""",
                """UNWIND $rows AS r MATCH (c:Case {id:r.cid}), (k:Knowledge {id:r.tid})
                   MERGE (c)-[:CITES]->(k)""",
                """UNWIND $rows AS r MATCH (c:Case {id:r.cid}), (m:Material {id:r.tid})
                   MERGE (c)-[:CITES]->(m)""",
                """UNWIND $rows AS r MERGE (t:Tag {name:r.tag})
                   WITH t, r MATCH (c:Case {id:r.cid}) MERGE (c)-[:HAS_TAG {src:'meta'}]->(t)""",
                # 素材
                """UNWIND $rows AS r MERGE (n:Material {id:r.id})
                   SET n.title=r.title, n.kind=r.kind, n.grade=r.grade, n.status=r.status,
                       n.level=r.level, n.summary=r.summary, n.citedCount=r.citedCount""",
                """UNWIND $rows AS r MERGE (t:Tag {name:r.tag})
                   WITH t, r MATCH (m:Material {id:r.mid}) MERGE (m)-[:HAS_TAG {src:'meta'}]->(t)""",
            ]
            args = [
                {}, {}, {}, {}, {}, {},
                {"rows": data["chapters"]},
                {"rows": data["sections"]},
                {"rows": data["sections"]},
                {"rows": data["cases"]},
                {"rows": [x for c in data["cases"] for x in
                          ({"cid": c["id"], "tid": t} for t in c["knTargets"])]},
                {"rows": [x for c in data["cases"] for x in
                          ({"cid": c["id"], "tid": t} for t in c["matTargets"])]},
                {"rows": [x for c in data["cases"] for x in
                          ({"cid": c["id"], "tag": t} for t in c["tags"])]},
                {"rows": data["materials"]},
                {"rows": [x for m in data["materials"] for x in
                          ({"mid": m["id"], "tag": t} for t in m["tags"])]},
            ]
            try:
                with self._driver.session() as s:
                    for cypher, params in zip(stmts, args):
                        s.run(cypher, **params).consume()
            except Exception as e:
                self._fail(e)
                return None
        return self.counts()

    def counts(self):
        rows = self._run(
            "MATCH (n) UNWIND labels(n) AS lb RETURN lb, count(*) AS c")
        if rows is None:
            return None
        out = {r["lb"]: r["c"] for r in rows}
        rels = self._run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c")
        if rels:
            out.update({"rel:" + r["t"]: r["c"] for r in rels})
        return out

    # ------------------------------------------------------------ 增量同步
    def sync_case(self, c):
        """案例写入后整点刷新：MERGE 节点 + 重挂其 CITES/HAS_TAG 出边。"""
        self._run(
            """MERGE (n:Case {id:$id})
               SET n.title=$title, n.status=$status, n.typeId=$typeId,
                   n.ownerId=$ownerId, n.summary=$summary
               WITH n OPTIONAL MATCH (n)-[r:CITES|HAS_TAG]->() DELETE r""",
            id=c["id"], title=c.get("title", ""), status=c.get("status", ""),
            typeId=c.get("typeId", ""), ownerId=c.get("ownerId", ""),
            summary=c.get("summary", ""))
        for t in c.get("knTargets") or []:
            self._run("MATCH (c:Case {id:$cid}), (k:Knowledge {id:$tid}) MERGE (c)-[:CITES]->(k)",
                      cid=c["id"], tid=t)
        for t in c.get("matTargets") or []:
            self._run("MATCH (c:Case {id:$cid}), (m:Material {id:$tid}) MERGE (c)-[:CITES]->(m)",
                      cid=c["id"], tid=t)
        for t in c.get("tags") or []:
            self._run(
                """MERGE (t:Tag {name:$tag})
                   WITH t MATCH (c:Case {id:$cid}) MERGE (c)-[:HAS_TAG {src:'meta'}]->(t)""",
                cid=c["id"], tag=t)
        self._gc_tags()

    def delete_case(self, cid):
        self._run("MATCH (n:Case {id:$id}) DETACH DELETE n", id=cid)
        self._gc_tags()

    def sync_material(self, m):
        """素材写入后整点刷新：MERGE 节点 + 重挂声明标签（保留 LLM 抽取的 MENTIONS/主题词）。"""
        self._run(
            """MERGE (n:Material {id:$id})
               SET n.title=$title, n.kind=$kind, n.grade=$grade, n.status=$status,
                   n.level=$level, n.summary=$summary, n.citedCount=$citedCount
               WITH n OPTIONAL MATCH (n)-[r:HAS_TAG {src:'meta'}]->() DELETE r""",
            id=m["id"], title=m.get("title", ""), kind=m.get("kind", ""),
            grade=m.get("grade", ""), status=m.get("status", ""),
            level=int(m.get("level") or 0),
            summary=m.get("summary", ""), citedCount=int(m.get("citedCount") or 0))
        for t in m.get("tags") or []:
            self._run(
                """MERGE (t:Tag {name:$tag})
                   WITH t MATCH (m:Material {id:$mid}) MERGE (m)-[:HAS_TAG {src:'meta'}]->(t)""",
                mid=m["id"], tag=t)
        self._gc_tags()

    def delete_material(self, mid):
        self._run("MATCH (n:Material {id:$id}) DETACH DELETE n", id=mid)
        self._gc_tags()

    def add_mentions(self, mid, kn_ids, topics, gen=None):
        """LLM 实体增强落边（可重入）：替换该素材的 MENTIONS 与 llm 主题词。
        gen 非空且落后于当前重建代次时丢弃（重建期间不写旧数据）。"""
        if gen is not None and gen != self.gen:
            return
        self._run(
            """MATCH (m:Material {id:$mid})
               OPTIONAL MATCH (m)-[r:MENTIONS]->() DELETE r
               WITH m OPTIONAL MATCH (m)-[r2:HAS_TAG {src:'llm'}]->() DELETE r2""",
            mid=mid)
        for kid in kn_ids or []:
            self._run("MATCH (m:Material {id:$mid}), (k:Knowledge {id:$kid})"
                      " MERGE (m)-[:MENTIONS]->(k)", mid=mid, kid=kid)
        for t in topics or []:
            self._run(
                """MERGE (t:Tag {name:$tag})
                   WITH t MATCH (m:Material {id:$mid}) MERGE (m)-[:HAS_TAG {src:'llm'}]->(t)""",
                mid=mid, tag=t)

    def _gc_tags(self):
        """清孤儿 Tag（标签随案例/素材删除而失去全部挂接时）。"""
        self._run("MATCH (t:Tag) WHERE NOT (t)<-[:HAS_TAG]-() DELETE t")

    # ------------------------------------------------------------ 查询
    @staticmethod
    def _node_out(n, center=None):
        lb = next((x for x in n.labels if x in _TYPE), "Tag")
        nid = n.get("id") or n.get("name")
        kind = "self" if center and nid == center else _KIND[lb]
        out = {"id": nid, "label": n.get("title") or nid, "type": _TYPE[lb],
               "ref": {"kind": kind, "id": nid}}
        if lb == "Case":  # server 按 status/ownerId 做可见性过滤
            out["status"] = n.get("status") or ""
            out["ownerId"] = n.get("ownerId") or ""
        elif lb == "Material":  # server 按密级过滤
            out["level"] = n.get("level") or 0
        return out

    @staticmethod
    def _rel_out(r, a_nid, b_nid):
        return {"source": a_nid, "target": b_nid, "rel": _REL_NAME.get(r.type, r.type)}

    def _subgraph(self, cypher, center=None, **params):
        """路径查询 → {nodes, links}（按 id 去重）。"""
        rows = self._run(cypher, **params)
        if rows is None:
            return None
        nodes, links, seen_e = {}, [], set()
        for row in rows:
            p = row["p"]
            pn = list(p.nodes)
            for n in pn:
                o = self._node_out(n, center)
                nodes[o["id"]] = o
            for i, r in enumerate(p.relationships):
                a = pn[i].get("id") or pn[i].get("name")
                b = pn[i + 1].get("id") or pn[i + 1].get("name")
                key = (a, b, r.type)
                if key not in seen_e:
                    seen_e.add(key)
                    links.append(self._rel_out(r, a, b))
        return {"nodes": list(nodes.values()), "links": links}

    def ego(self, ntype, nid, hops=2):
        """以某节点为中心的两跳子图。"""
        label, key = _NODE_KEY.get(ntype, (None, None))
        if not label:
            return None
        hops = min(max(int(hops or 2), 1), 3)
        return self._subgraph(
            "MATCH p=(n:%s {%s:$id})-[*1..%d]-(m) RETURN p LIMIT 400" % (label, key, hops),
            center=nid, id=nid)

    def overview(self):
        """全库轻量图（ADR 0004）：教材骨架（章/节）+ 案例 + 节级引用边；素材经 ego 按需展开。"""
        return self._subgraph(
            """MATCH p=(k:Knowledge)-[:BELONGS]->(c:Chapter) RETURN p
               UNION MATCH p=(c:Case)-[:CITES]->(k:Knowledge) RETURN p
               UNION MATCH p=(c:Case) WHERE NOT (c)-[:CITES]->(:Knowledge) RETURN p""")

    def reverse(self, kn=None, tag=None):
        """知识点/标签反查：直接关联的案例与素材 + 两跳路径（知识点→案例→素材）。"""
        if kn:
            center_rows = self._run("MATCH (n:Knowledge {id:$id}) RETURN n", id=kn)
            sub = self._subgraph(
                """MATCH p=(k:Knowledge {id:$id})<-[:CITES]-(c:Case) RETURN p
                   UNION MATCH p=(k:Knowledge {id:$id})<-[:MENTIONS]-(m:Material) RETURN p
                   UNION MATCH p=(k:Knowledge {id:$id})<-[:CITES]-(c:Case)-[:CITES]->(m:Material) RETURN p""",
                center=kn, id=kn)
        elif tag:
            center_rows = self._run("MATCH (n:Tag {name:$id}) RETURN n", id=tag)
            sub = self._subgraph(
                """MATCH p=(t:Tag {name:$id})<-[:HAS_TAG]-(c:Case) RETURN p
                   UNION MATCH p=(t:Tag {name:$id})<-[:HAS_TAG]-(m:Material) RETURN p
                   UNION MATCH p=(t:Tag {name:$id})<-[:HAS_TAG]-(c:Case)-[:CITES]->(m:Material) RETURN p""",
                center=tag, id=tag)
        else:
            return None
        if not center_rows or sub is None:
            return None
        center = self._node_out(center_rows[0]["n"], center=(kn or tag))
        nodes = [n for n in sub["nodes"] if n["id"] != center["id"]]
        nodes.insert(0, center)
        return {
            "node": next((n for n in nodes if n["id"] == (kn or tag)), None),
            "cases": [n for n in nodes if n["type"] == "case"],
            "materials": [n for n in nodes if n["type"] == "material"],
            "nodes": nodes, "links": sub["links"],
        }

    def neighborhood(self, ids):
        """QA 召回：种子节点一跳子图 + 证据属性（title/summary/snippet）。"""
        rows = self._run(
            """MATCH (n) WHERE n.id IN $ids OR n.name IN $ids
               OPTIONAL MATCH p=(n)-[*1..1]-(m)
               WITH collect(p) AS ps, collect(DISTINCT n) AS centers
               RETURN ps, [c IN centers | properties(c)] AS centerProps""",
            ids=list(ids))
        if not rows:
            return None
        nodes, links, seen_e = {}, [], set()
        props = {}
        for cp in rows[0]["centerProps"]:
            nid = cp.get("id") or cp.get("name")
            props[nid] = cp
        for p in rows[0]["ps"] or []:
            if p is None:
                continue
            pn = list(p.nodes)
            for n in pn:
                o = self._node_out(n)
                nodes[o["id"]] = o
                props.setdefault(o["id"], dict(n))
            for i, r in enumerate(p.relationships):
                a = pn[i].get("id") or pn[i].get("name")
                b = pn[i + 1].get("id") or pn[i + 1].get("name")
                key = (a, b, r.type)
                if key not in seen_e:
                    seen_e.add(key)
                    links.append(self._rel_out(r, a, b))
        return {"nodes": list(nodes.values()), "links": links, "props": props}
