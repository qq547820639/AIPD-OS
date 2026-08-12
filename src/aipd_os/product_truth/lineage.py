"""显式依赖图与血缘图。

每条 truth 记录通过 ``add_edge(upstream_id, downstream_id)`` 建立显式依赖；
``downstream_of`` / ``upstream_of`` 提供邻接查询；``compute_affected`` 沿下游
深度优先遍历并带环检测（不无限递归）。图结构持久化在 ``truth_lineage`` 表。

作用域：边与 truth 记录一样带 ``tenant_id`` / ``project_id``（默认
``'default'``）。构造器缺省继承 store 的 scope；方法级参数可覆盖。

v5.8.2 Commit 7（Generic/ProductTruth lineage 收敛）：本类升级为
**canonical LineageService 的兼容 facade** ——
- 提供 ``canonical_db``（AIPDStateDB 实例）时：``add_edge`` 采用
  **canonical-write**（先写 ``state.lineage.LineageService`` → dependencies
  表，node_type="product_truth"；成功后再写 truth_lineage 兼容表）；
- 查询保持旧 API（从 truth_lineage 读，双写后新旧数据均可见）；
- ``remove_edge`` 在 canonical 侧 soft-retire（历史保留），truth_lineage 侧
  保持原删除语义；
- 未提供 canonical_db 时行为与 v5.7 完全一致（纯 truth_lineage）。
v5.9 及以后的新域（Insight/Opportunity/Requirement/Feature…）只走 canonical
LineageService，**不得**再建第三套 lineage 表。
"""
from __future__ import annotations

from typing import Any

from .store import ProductTruthStore


class CycleDetectedError(Exception):
    """检测到依赖环。"""


class LineageGraph:
    """基于 ProductTruthStore 的显式依赖 / 血缘图（带 tenant/project 作用域）。

    :param canonical_db: 可选 AIPDStateDB 实例 —— 提供后启用 canonical-write
        （state.lineage.LineageService → dependencies 表）。
    """

    def __init__(self, store: ProductTruthStore,
                 tenant_id: str | None = None,
                 project_id: str | None = None,
                 canonical_db: Any = None):
        self._store = store
        self.tenant_id = tenant_id or store.tenant_id
        self.project_id = project_id or store.project_id
        self._canonical_db = canonical_db

    def _scope(self, tenant_id: str | None,
               project_id: str | None) -> tuple[str, str]:
        return (tenant_id or self.tenant_id, project_id or self.project_id)

    # ------------------------------------------------------ canonical helpers
    def _canonical_lineage(self) -> Any:
        """懒构造 canonical LineageService（仅 canonical_db 存在时可用）。"""
        from aipd_os.state.lineage import LineageService
        return LineageService(self._canonical_db)

    @staticmethod
    def _canonical_node(record_id: str, tenant: str, project: str) -> Any:
        from aipd_os.state.lineage import LineageNodeRef
        return LineageNodeRef(node_type="product_truth", node_id=record_id,
                              tenant_id=tenant, project_id=project)

    # ------------------------------------------------------------- 边操作
    def add_edge(self, upstream_id: str, downstream_id: str,
                 relation: str = "affects", tenant_id: str | None = None,
                 project_id: str | None = None) -> None:
        tenant, project = self._scope(tenant_id, project_id)
        # 自环直接拒绝
        if upstream_id == downstream_id:
            raise CycleDetectedError(
                f"self-loop edge {upstream_id} -> {downstream_id} is not allowed")
        # v5.8.2 Commit 7：canonical-write 先行（权威；含全图环检测）。
        # canonical 写失败 → 不写 truth_lineage（保持一致）；
        # canonical 环异常统一转 CycleDetectedError（facade 兼容旧 API）。
        if self._canonical_db is not None:
            from aipd_os.state.lineage import LineageCycleError
            lineage = self._canonical_lineage()
            try:
                lineage.add_edge(
                    self._canonical_node(upstream_id, tenant, project),
                    self._canonical_node(downstream_id, tenant, project),
                    relation,
                    provenance={"source": "product_truth.lineage_graph",
                                "relation": relation},
                    actor="system")
            except LineageCycleError as exc:
                raise CycleDetectedError(
                    f"adding edge {upstream_id} -> {downstream_id} "
                    f"creates a cycle (canonical lineage): {exc}") from exc
        with self._store.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO truth_lineage"
                "(tenant_id,project_id,upstream_id,downstream_id,relation,created_at) "
                "VALUES(?,?,?,?,?,datetime('now'))",
                (tenant, project, upstream_id, downstream_id, relation))
        # 新增边后若立即形成环则回滚本次边；图本身仍保持无环。
        if self._has_cycle_all(tenant, project):
            with self._store.connect() as c:
                c.execute(
                    "DELETE FROM truth_lineage WHERE tenant_id=? AND project_id=? "
                    "AND upstream_id=? AND downstream_id=?",
                    (tenant, project, upstream_id, downstream_id))
            if self._canonical_db is not None:
                self._canonical_lineage().retire_edge(
                    self._canonical_edge_id(upstream_id, downstream_id,
                                            relation, tenant, project),
                    actor="system",
                    reason="product_truth truth_lineage cycle detected; "
                           "canonical edge rolled back")
            raise CycleDetectedError(
                f"adding edge {upstream_id} -> {downstream_id} creates a cycle")

    def _canonical_edge_id(self, upstream_id: str, downstream_id: str,
                           relation: str, tenant: str, project: str) -> str | None:
        """查找 canonical 侧同键 active 边 id（无则 None）。"""
        lineage = self._canonical_lineage()
        for e in lineage.outgoing(self._canonical_node(upstream_id, tenant,
                                                       project)):
            if e.target.node_id == downstream_id and \
                    e.target.node_type == "product_truth" and \
                    e.relation_type == relation:
                return e.edge_id
        return None

    def remove_edge(self, upstream_id: str, downstream_id: str,
                    tenant_id: str | None = None,
                    project_id: str | None = None) -> None:
        tenant, project = self._scope(tenant_id, project_id)
        with self._store.connect() as c:
            c.execute(
                "DELETE FROM truth_lineage WHERE tenant_id=? AND project_id=? "
                "AND upstream_id=? AND downstream_id=?",
                (tenant, project, upstream_id, downstream_id))
        # canonical 侧 soft-retire（保留历史，不物理删除）
        if self._canonical_db is not None:
            for edge in self._canonical_lineage().outgoing(
                    self._canonical_node(upstream_id, tenant, project)):
                if edge.target.node_id == downstream_id and \
                        edge.target.node_type == "product_truth":
                    self._canonical_lineage().retire_edge(
                        edge.edge_id, actor="system",
                        reason="product_truth.remove_edge")

    def clear_edges(self, tenant_id: str | None = None,
                    project_id: str | None = None) -> None:
        tenant, project = self._scope(tenant_id, project_id)
        with self._store.connect() as c:
            c.execute("DELETE FROM truth_lineage WHERE tenant_id=? AND project_id=?",
                      (tenant, project))

    # ------------------------------------------------------------- 邻接查询
    def downstream_of(self, record_id: str, relation: str | None = None,
                      tenant_id: str | None = None,
                      project_id: str | None = None) -> list[str]:
        tenant, project = self._scope(tenant_id, project_id)
        sql = ("SELECT downstream_id FROM truth_lineage "
               "WHERE tenant_id=? AND project_id=? AND upstream_id=?")
        params: list[object] = [tenant, project, record_id]
        if relation is not None:
            sql += " AND relation=?"
            params.append(relation)
        with self._store.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [r["downstream_id"] for r in rows]

    def upstream_of(self, record_id: str, relation: str | None = None,
                    tenant_id: str | None = None,
                    project_id: str | None = None) -> list[str]:
        tenant, project = self._scope(tenant_id, project_id)
        sql = ("SELECT upstream_id FROM truth_lineage "
               "WHERE tenant_id=? AND project_id=? AND downstream_id=?")
        params: list[object] = [tenant, project, record_id]
        if relation is not None:
            sql += " AND relation=?"
            params.append(relation)
        with self._store.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [r["upstream_id"] for r in rows]

    def edges(self, tenant_id: str | None = None,
              project_id: str | None = None) -> list[dict[str, str]]:
        tenant, project = self._scope(tenant_id, project_id)
        with self._store.connect() as c:
            rows = c.execute(
                "SELECT upstream_id,downstream_id,relation FROM truth_lineage "
                "WHERE tenant_id=? AND project_id=?",
                (tenant, project)).fetchall()
        return [{"upstream_id": r["upstream_id"], "downstream_id": r["downstream_id"],
                 "relation": r["relation"]} for r in rows]

    # ------------------------------------------------------------- 受影响计算
    def compute_affected(self, upstream_id: str, tenant_id: str | None = None,
                         project_id: str | None = None) -> list[str]:
        """广度优先计算所有下游受影响项（含环检测，不无限递归）。

        返回按「最上游优先」（层级）排序的下游 id 列表；环仅记录一次。
        """
        affected: list[str] = []
        visited: set[str] = {upstream_id}
        queue = list(self.downstream_of(upstream_id, tenant_id=tenant_id,
                                        project_id=project_id))
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            affected.append(node)
            for nxt in self.downstream_of(node, tenant_id=tenant_id,
                                          project_id=project_id):
                if nxt not in visited:
                    queue.append(nxt)
        return affected

    def has_cycle_from(self, start: str, tenant_id: str | None = None,
                       project_id: str | None = None) -> bool:
        """从 start 出发深度优先检测是否存在环（over路径上）。"""
        visited: set[str] = set()

        def dfs(node: str, path: set[str]) -> bool:
            if node in visited:
                return False
            visited.add(node)
            for nxt in self.downstream_of(node, tenant_id=tenant_id,
                                          project_id=project_id):
                if nxt in path:
                    return True
                if dfs(nxt, path | {nxt}):
                    return True
            return False

        return dfs(start, {start})

    def _has_cycle_all(self, tenant_id: str | None = None,
                       project_id: str | None = None) -> bool:
        """检测全图是否有环（用于 add_edge 的保护性回滚）。"""
        tenant, project = self._scope(tenant_id, project_id)
        with self._store.connect() as c:
            rows = c.execute(
                "SELECT upstream_id,downstream_id FROM truth_lineage "
                "WHERE tenant_id=? AND project_id=?",
                (tenant, project)).fetchall()
        children: dict[str, list[str]] = {}
        for r in rows:
            children.setdefault(r["upstream_id"], []).append(r["downstream_id"])
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for nxt in children.get(node, []):
                nc = color.get(nxt, WHITE)
                if nc == GRAY:
                    return True
                if nc == WHITE and dfs(nxt):
                    return True
            color[node] = BLACK
            return False

        return any(
            color.get(node, WHITE) == WHITE and dfs(node)
            for node in list(children.keys())
        )

    # ------------------------------------------------- canonical 查询（v5.8.2）
    def canonical_edges(self, tenant_id: str | None = None,
                        project_id: str | None = None) -> list[dict[str, Any]]:
        """从 canonical LineageService 读取（跨域统一图）。

        node_type 限定 "product_truth"（域内边）；全图见
        :meth:`canonical_all_edges`。仅 canonical_db 提供时可用。
        """
        if self._canonical_db is None:
            raise RuntimeError(
                "canonical_edges requires canonical_db (AIPDStateDB) at "
                "LineageGraph construction")
        tenant, project = self._scope(tenant_id, project_id)
        lineage = self._canonical_lineage()
        return [
            e.to_dict() for e in lineage.edges(tenant, project)
            if e.source.node_type == "product_truth"
            and e.target.node_type == "product_truth"
        ]

    def canonical_all_edges(self, tenant_id: str | None = None,
                            project_id: str | None = None) -> list[dict[str, Any]]:
        """从 canonical LineageService 读取全图边（跨域，含 claim 等）。"""
        if self._canonical_db is None:
            raise RuntimeError(
                "canonical_all_edges requires canonical_db (AIPDStateDB)")
        tenant, project = self._scope(tenant_id, project_id)
        return [e.to_dict() for e in self._canonical_lineage().edges(tenant,
                                                                     project)]


__all__ = ["LineageGraph", "CycleDetectedError"]
