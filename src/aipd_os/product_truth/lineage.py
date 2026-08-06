"""显式依赖图与血缘图。

每条 truth 记录通过 ``add_edge(upstream_id, downstream_id)`` 建立显式依赖；
``downstream_of`` / ``upstream_of`` 提供邻接查询；``compute_affected`` 沿下游
深度优先遍历并带环检测（不无限递归）。图结构持久化在 ``truth_lineage`` 表。
"""
from __future__ import annotations

from typing import Dict, List, Set

from .store import ProductTruthStore


class CycleDetectedError(Exception):
    """检测到依赖环。"""


class LineageGraph:
    """基于 ProductTruthStore 的显式依赖 / 血缘图。"""

    def __init__(self, store: ProductTruthStore):
        self._store = store

    # ------------------------------------------------------------- 边操作
    def add_edge(self, upstream_id: str, downstream_id: str,
                 relation: str = "affects") -> None:
        # 自环直接拒绝
        if upstream_id == downstream_id:
            raise CycleDetectedError(
                f"self-loop edge {upstream_id} -> {downstream_id} is not allowed")
        with self._store.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO truth_lineage(upstream_id,downstream_id,relation,created_at) "
                "VALUES(?,?,?,datetime('now'))",
                (upstream_id, downstream_id, relation))
        # 新增边后若立即形成环则回滚本次边；图本身仍保持无环。
        if self._has_cycle_all():
            with self._store.connect() as c:
                c.execute("DELETE FROM truth_lineage WHERE upstream_id=? AND downstream_id=?",
                          (upstream_id, downstream_id))
            raise CycleDetectedError(
                f"adding edge {upstream_id} -> {downstream_id} creates a cycle")

    def remove_edge(self, upstream_id: str, downstream_id: str) -> None:
        with self._store.connect() as c:
            c.execute("DELETE FROM truth_lineage WHERE upstream_id=? AND downstream_id=?",
                      (upstream_id, downstream_id))

    def clear_edges(self) -> None:
        with self._store.connect() as c:
            c.execute("DELETE FROM truth_lineage")

    # ------------------------------------------------------------- 邻接查询
    def downstream_of(self, record_id: str, relation: Optional[str] = None) -> List[str]:
        sql = ("SELECT downstream_id FROM truth_lineage WHERE upstream_id=?")
        params: List[object] = [record_id]
        if relation is not None:
            sql += " AND relation=?"
            params.append(relation)
        with self._store.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [r["downstream_id"] for r in rows]

    def upstream_of(self, record_id: str, relation: Optional[str] = None) -> List[str]:
        sql = ("SELECT upstream_id FROM truth_lineage WHERE downstream_id=?")
        params: List[object] = [record_id]
        if relation is not None:
            sql += " AND relation=?"
            params.append(relation)
        with self._store.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [r["upstream_id"] for r in rows]

    def edges(self) -> List[Dict[str, str]]:
        with self._store.connect() as c:
            rows = c.execute(
                "SELECT upstream_id,downstream_id,relation FROM truth_lineage").fetchall()
        return [{"upstream_id": r["upstream_id"], "downstream_id": r["downstream_id"],
                 "relation": r["relation"]} for r in rows]

    # ------------------------------------------------------------- 受影响计算
    def compute_affected(self, upstream_id: str) -> List[str]:
        """广度优先计算所有下游受影响项（含环检测，不无限递归）。

        返回按「最上游优先」（层级）排序的下游 id 列表；环仅记录一次。
        """
        affected: List[str] = []
        visited: Set[str] = {upstream_id}
        queue = list(self.downstream_of(upstream_id))
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            affected.append(node)
            for nxt in self.downstream_of(node):
                if nxt not in visited:
                    queue.append(nxt)
        return affected

    def has_cycle_from(self, start: str) -> bool:
        """从 start 出发深度优先检测是否存在环（over路径上）。"""
        visited: Set[str] = set()

        def dfs(node: str, path: Set[str]) -> bool:
            if node in visited:
                return False
            visited.add(node)
            for nxt in self.downstream_of(node):
                if nxt in path:
                    return True
                if dfs(nxt, path | {nxt}):
                    return True
            return False

        return dfs(start, {start})

    def _has_cycle_all(self) -> bool:
        """检测全图是否有环（用于 add_edge 的保护性回滚）。"""
        with self._store.connect() as c:
            rows = c.execute(
                "SELECT upstream_id,downstream_id FROM truth_lineage").fetchall()
        children: Dict[str, List[str]] = {}
        for r in rows:
            children.setdefault(r["upstream_id"], []).append(r["downstream_id"])
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {}

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

        for node in list(children.keys()):
            if color.get(node, WHITE) == WHITE and dfs(node):
                return True
        return False


__all__ = ["LineageGraph", "CycleDetectedError"]