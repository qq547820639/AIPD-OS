"""Generic Lineage（v5.8.1 Commit 9）。

跨域 lineage：Idea → Claim → EvidenceRelation → Evidence → Insight →
ProductPrinciple → Requirement → Feature…… 统一用 :class:`LineageService`
读写，**复用 canonical ``dependencies`` 表**（本来就是通用有向边存储：
source_type/source_id/target_type/target_id/relation + tenant/project scope；
migration v6 补 created_at / provenance / version_no），不新造第二套
graph persistence。

- :class:`LineageNodeRef`：node_type / node_id / tenant_id / project_id / version；
- :class:`LineageEdge`：source / target / relation_type / created_at / provenance；
- :class:`LineageService`：add_edge（scope 校验 + 环检测 + audit）、outgoing /
  incoming（tenant+project scoped）、path（BFS 最短路径，深度限制防环）。

relation_type 全集：derived_from / supported_by / contradicted_by /
translated_to / satisfies / validated_by / supersedes（+ 既有 dependencies
的 legacy 值 affects / needs_external / blocked_by_external）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from aipd_os.state.db import AIPDStateDB, now_iso

# 通用 lineage 关系类型（含既有 dependencies 的 legacy relation 值）
LINEAGE_RELATION_TYPES = frozenset({
    "derived_from",
    "supported_by",
    "contradicted_by",
    "translated_to",
    "satisfies",
    "validated_by",
    "supersedes",
    # legacy dependencies relations（v1 表既有用法）
    "affects",
    "needs_external",
    "blocked_by_external",
})

# path() 的默认深度限制（防环）
DEFAULT_MAX_DEPTH = 10


@dataclass(frozen=True)
class LineageNodeRef:
    """lineage 图中的节点引用（跨域通用）。"""

    node_type: str
    node_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "node_id": self.node_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "version": self.version,
        }


@dataclass
class LineageEdge:
    """一条有向 lineage 边。"""

    edge_id: str
    source: LineageNodeRef
    target: LineageNodeRef
    relation_type: str
    created_at: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    version_no: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "relation_type": self.relation_type,
            "created_at": self.created_at,
            "provenance": self.provenance,
            "version_no": self.version_no,
        }


class LineageScopeError(ValueError):
    """跨 tenant/project 的 lineage 边拒绝。"""


class LineageRelationError(ValueError):
    """非法 relation_type。"""


class LineageCycleError(Exception):
    """新增边会形成环（拒绝）。"""


class LineageService:
    """dependencies 表之上的通用 lineage 读写（tenant+project scoped）。"""

    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _check_scope(source: LineageNodeRef, target: LineageNodeRef) -> None:
        if (source.tenant_id, source.project_id) != (target.tenant_id,
                                                     target.project_id):
            raise LineageScopeError(
                f"lineage edge crosses scope: source "
                f"tenant={source.tenant_id}/project={source.project_id} vs target "
                f"tenant={target.tenant_id}/project={target.project_id}")

    @staticmethod
    def _encode_id(node: LineageNodeRef) -> str:
        """持久化 node_id；version 存在时编码为 ``{node_id}@{version}``。"""
        if node.version:
            return f"{node.node_id}@{node.version}"
        return node.node_id

    @staticmethod
    def _decode_id(stored: str) -> tuple[str, str | None]:
        """解析持久化 node_id → (node_id, version)。"""
        if stored and "@" in stored:
            node_id, version = stored.rsplit("@", 1)
            if node_id and version:
                return node_id, version
        return stored, None

    @staticmethod
    def _node_eq(a: LineageNodeRef, b: LineageNodeRef) -> bool:
        return (a.node_type, a.node_id, a.version, a.tenant_id, a.project_id) == \
            (b.node_type, b.node_id, b.version, b.tenant_id, b.project_id)

    def _row_to_edge(self, row: Any) -> LineageEdge:
        d = dict(row)
        try:
            provenance = json.loads(d.get("provenance") or "{}")
        except (ValueError, TypeError):
            provenance = {}
        src_id, src_ver = self._decode_id(d["source_id"])
        tgt_id, tgt_ver = self._decode_id(d["target_id"])
        return LineageEdge(
            edge_id=str(d["dependency_id"]),
            source=LineageNodeRef(
                node_type=d["source_type"], node_id=src_id,
                tenant_id=d["tenant_id"], project_id=d["project_id"],
                version=src_ver),
            target=LineageNodeRef(
                node_type=d["target_type"], node_id=tgt_id,
                tenant_id=d["tenant_id"], project_id=d["project_id"],
                version=tgt_ver),
            relation_type=d["relation"],
            created_at=d.get("created_at") or None,
            provenance=provenance,
            version_no=int(d.get("version_no", 1)),
        )

    # ------------------------------------------------------------- write
    def add_edge(self, source: LineageNodeRef, target: LineageNodeRef,
                 relation_type: str,
                 provenance: dict[str, Any] | None = None,
                 actor: str = "system") -> LineageEdge:
        """新增 lineage 边（幂等；scope 校验 + 环检测 + audit + version）。

        - 同 (source, target, relation_type, scope) 已存在 → 返回现有边；
        - 新增边若使图成环 → :class:`LineageCycleError` 拒绝；
        - audit（action=lineage.add_edge）。
        """
        self._check_scope(source, target)
        if relation_type not in LINEAGE_RELATION_TYPES:
            raise LineageRelationError(
                f"invalid lineage relation_type {relation_type!r}; "
                f"expected one of {sorted(LINEAGE_RELATION_TYPES)}")
        # 环检测：若 target 已可达 source，加 source→target 会成环
        if self._reachable(target, source, depth=DEFAULT_MAX_DEPTH):
            raise LineageCycleError(
                f"adding edge {source.node_type}:{source.node_id}"
                f"{('@'+source.version) if source.version else ''} -> "
                f"{target.node_type}:{target.node_id}"
                f"{('@'+target.version) if target.version else ''} "
                f"would create a cycle")
        ts = now_iso()
        prov_json = json.dumps(provenance or {}, ensure_ascii=False, sort_keys=True)
        with self._db.connect() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO dependencies(project_id,tenant_id,source_type,"
                "source_id,target_type,target_id,relation,created_at,provenance,"
                "version_no) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (source.project_id, source.tenant_id, source.node_type,
                 self._encode_id(source), target.node_type,
                 self._encode_id(target), relation_type,
                 ts, prov_json, 1))
            row = c.execute(
                "SELECT * FROM dependencies WHERE project_id=? AND tenant_id=? "
                "AND source_type=? AND source_id=? AND target_type=? AND target_id=? "
                "AND relation=?",
                (source.project_id, source.tenant_id, source.node_type,
                 self._encode_id(source), target.node_type,
                 self._encode_id(target), relation_type)).fetchone()
        edge = self._row_to_edge(row)
        if cur.rowcount == 1:
            # 本次真正插入 → audit
            self._db.add_audit(actor, "lineage.add_edge", source.project_id,
                               source.tenant_id, before=None, after=edge.to_dict())
        return edge

    # ------------------------------------------------------------- query
    def outgoing(self, node: LineageNodeRef) -> list[LineageEdge]:
        """node 的出边（source=node）。"""
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM dependencies WHERE project_id=? AND tenant_id=? "
                "AND source_type=? AND source_id=? ORDER BY dependency_id",
                (node.project_id, node.tenant_id, node.node_type,
                 self._encode_id(node))).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def incoming(self, node: LineageNodeRef) -> list[LineageEdge]:
        """node 的入边（target=node）。"""
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM dependencies WHERE project_id=? AND tenant_id=? "
                "AND target_type=? AND target_id=? ORDER BY dependency_id",
                (node.project_id, node.tenant_id, node.node_type,
                 self._encode_id(node))).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def edges(self, tenant_id: str, project_id: str) -> list[LineageEdge]:
        """scope 内全部 lineage 边。"""
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM dependencies WHERE project_id=? AND tenant_id=? "
                "ORDER BY dependency_id", (project_id, tenant_id)).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def path(self, source: LineageNodeRef, target: LineageNodeRef,
             max_depth: int = DEFAULT_MAX_DEPTH) -> list[LineageEdge] | None:
        """BFS 最短路径（source→target）；不存在或超深度 → None。

        BFS 天然防环（visited 集合）。
        """
        self._check_scope(source, target)
        if self._node_eq(source, target):
            return []
        from collections import deque
        # BFS：queue of (node, path_edges)
        queue: deque[tuple[LineageNodeRef, list[LineageEdge]]] = deque()
        queue.append((source, []))
        visited = {self._node_key(source)}
        while queue:
            current, path_edges = queue.popleft()
            if len(path_edges) >= max_depth:
                continue
            for edge in self.outgoing(current):
                nxt = edge.target
                key = self._node_key(nxt)
                if key in visited:
                    continue
                new_path = path_edges + [edge]
                if self._node_eq(nxt, target):
                    return new_path
                visited.add(key)
                queue.append((nxt, new_path))
        return None

    @staticmethod
    def _node_key(node: LineageNodeRef) -> tuple:
        return (node.node_type, node.node_id, node.version,
                node.tenant_id, node.project_id)

    def _reachable(self, from_node: LineageNodeRef, to_node: LineageNodeRef,
                   depth: int = DEFAULT_MAX_DEPTH) -> bool:
        """from_node 是否可达 to_node（BFS，防环）。"""
        return self.path(from_node, to_node, max_depth=depth) is not None


__all__ = [
    "LINEAGE_RELATION_TYPES",
    "DEFAULT_MAX_DEPTH",
    "LineageNodeRef",
    "LineageEdge",
    "LineageService",
    "LineageScopeError",
    "LineageRelationError",
    "LineageCycleError",
]
