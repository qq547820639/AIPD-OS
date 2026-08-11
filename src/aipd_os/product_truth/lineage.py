"""显式依赖图与血缘图。

每条 truth 记录通过 ``add_edge(upstream_id, downstream_id)`` 建立显式依赖；
``downstream_of`` / ``upstream_of`` 提供邻接查询；``compute_affected`` 沿下游
深度优先遍历并带环检测（不无限递归）。图结构持久化在 ``truth_lineage`` 表。

作用域：边与 truth 记录一样带 ``tenant_id`` / ``project_id``（默认
``'default'``）。构造器缺省继承 store 的 scope；方法级参数可覆盖。
"""
from __future__ import annotations

from .store import ProductTruthStore


class CycleDetectedError(Exception):
    """检测到依赖环。"""


class LineageGraph:
    """基于 ProductTruthStore 的显式依赖 / 血缘图（带 tenant/project 作用域）。"""

    def __init__(self, store: ProductTruthStore,
                 tenant_id: str | None = None,
                 project_id: str | None = None):
        self._store = store
        self.tenant_id = tenant_id or store.tenant_id
        self.project_id = project_id or store.project_id

    def _scope(self, tenant_id: str | None,
               project_id: str | None) -> tuple[str, str]:
        return (tenant_id or self.tenant_id, project_id or self.project_id)

    # ------------------------------------------------------------- 边操作
    def add_edge(self, upstream_id: str, downstream_id: str,
                 relation: str = "affects", tenant_id: str | None = None,
                 project_id: str | None = None) -> None:
        tenant, project = self._scope(tenant_id, project_id)
        # 自环直接拒绝
        if upstream_id == downstream_id:
            raise CycleDetectedError(
                f"self-loop edge {upstream_id} -> {downstream_id} is not allowed")
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
            raise CycleDetectedError(
                f"adding edge {upstream_id} -> {downstream_id} creates a cycle")

    def remove_edge(self, upstream_id: str, downstream_id: str,
                    tenant_id: str | None = None,
                    project_id: str | None = None) -> None:
        tenant, project = self._scope(tenant_id, project_id)
        with self._store.connect() as c:
            c.execute(
                "DELETE FROM truth_lineage WHERE tenant_id=? AND project_id=? "
                "AND upstream_id=? AND downstream_id=?",
                (tenant, project, upstream_id, downstream_id))

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


__all__ = ["LineageGraph", "CycleDetectedError"]
