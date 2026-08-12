"""Upstream impact propagation（v5.9.2，§32-34）。

**问题**：Claim/EvidenceRelation 变化时，下游 PI 对象（Insight →
Opportunity → Principle → Requirement → Feature）与已冻结 Snapshot 需要
失效。§35 的 ``upstream_basis_hash`` 是 **Snapshot 层的第二道防线**；
本模块提供 **对象层确定性影响分析**（Digital Thread）：

- :meth:`find_affected_objects`：沿 Generic Lineage 反向（claim →
  insight → opportunity → principle → requirement → feature）找受影响
  对象（含 relation 标注）；
- :meth:`affected_snapshot_ids`：受影响对象关联的 frozen snapshot；
- :meth:`mark_affected_snapshots_stale`：把受影响 frozen snapshot 标记
  STALE（旧审批立即失效）。

**不创建第三套 propagation**（§32）：复用 canonical LineageService +
snapshot 生命周期。对象层不自动改 lifecycle（PI 对象生命周期保持
candidate/active；stale 语义由 snapshot basis + 本服务的报告承载）。

触发策略（§34）：上游变更入口（Claim update / EvidenceRelation
review/update）由调用方在变更后调用 :meth:`propagate` —— 不在
claim_service 内硬编码 import（避免 idea↔product_intelligence 循环依赖）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.lineage import LineageNodeRef, LineageService

from .service import (
    _ID_FIELD_FOR,
    NODE_FEATURE,
    NODE_INSIGHT,
    NODE_OPPORTUNITY,
    NODE_PRINCIPLE,
    NODE_REQUIREMENT,
    ProductIntelligenceService,
)
from .snapshot import (
    SNAPSHOT_FROZEN,
    ProductDefinitionSnapshotService,
)

# claim → 下游 PI 节点类型链（Generic Lineage 反向）
_DOWNSTREAM_CHAIN = (NODE_INSIGHT, NODE_OPPORTUNITY, NODE_PRINCIPLE,
                     NODE_REQUIREMENT, NODE_FEATURE)

# 上游变化类型 → 影响判定（§34 deterministic impact policy）
IMPACT_CLAIM = "claim"
IMPACT_RELATION = "evidence_relation"
IMPACT_ASSESSMENT = "claim_assessment"
IMPACT_PRINCIPLE_SOURCE = "principle_source"
IMPACT_REQUIREMENT_SOURCE = "requirement_source"


class ImpactPropagationService:
    """基于 Generic Lineage 的确定性影响传播（对象级 + snapshot 级）。"""

    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db
        self._pi = ProductIntelligenceService(db)
        self._lineage = LineageService(db)
        self._snapshots = ProductDefinitionSnapshotService(db)

    # ------------------------------------------------------------- 查询
    def find_affected_objects(self, tenant_id: str, project_id: str,
                              changed_node_type: str,
                              changed_node_ids: list[str],
                              max_depth: int = 8) -> list[dict[str, Any]]:
        """沿 Generic Lineage 反向找受影响 PI 对象（含 relation 标注）。

        从 changed 节点出发，对每个下游 PI 节点类型收集「该节点有出边指向
        changed 或其下游」的对象。返回 ``[{node_type, node_id,
        relation, via}]``。
        """
        affected: list[dict[str, Any]] = []
        seed = {changed_node_type: set(changed_node_ids)}
        for _depth in range(max_depth):
            progressed = False
            for node_type in _DOWNSTREAM_CHAIN:
                seed_ids = set()
                for _prev_type, prev_ids in seed.items():
                    seed_ids |= prev_ids
                if not seed_ids:
                    continue
                candidates = self._objects(node_type, tenant_id, project_id)
                for obj in candidates:
                    obj_id = self._obj_id(obj, node_type)
                    if obj_id in seed.get(node_type, set()):
                        continue
                    for edge in self._lineage.outgoing(
                            LineageNodeRef(node_type, obj_id, tenant_id,
                                           project_id)):
                        if edge.target.node_id in seed_ids:
                            affected.append({
                                "node_type": node_type, "node_id": obj_id,
                                "relation": edge.relation_type,
                                "via": edge.target.node_id,
                            })
                            seed.setdefault(node_type, set()).add(obj_id)
                            progressed = True
            if not progressed:
                break
        return affected

    def affected_snapshot_ids(self, tenant_id: str, project_id: str,
                              changed_node_type: str,
                              changed_node_ids: list[str]) -> list[str]:
        """受影响（含其对象的）frozen snapshot ids。"""
        affected = self.find_affected_objects(
            tenant_id, project_id, changed_node_type, changed_node_ids)
        affected_ids = {a["node_id"] for a in affected}
        frozen = [s for s in self._snapshots.list_snapshots(tenant_id,
                                                            project_id)
                  if s.lifecycle_status == SNAPSHOT_FROZEN]
        out = []
        for s in frozen:
            snap_ids = {r.get("id") for r in
                        (s.principle_refs + s.requirement_refs
                         + s.feature_refs)}
            if snap_ids & affected_ids:
                out.append(s.snapshot_id)
        return out

    def mark_affected_snapshots_stale(self, tenant_id: str, project_id: str,
                                      changed_node_type: str,
                                      changed_node_ids: list[str],
                                      actor: str = "system") -> list[str]:
        """把受影响 frozen snapshot 标记 STALE（旧审批立即失效，§30/33）。"""
        snap_ids = self.affected_snapshot_ids(
            tenant_id, project_id, changed_node_type, changed_node_ids)
        for sid in snap_ids:
            snap = self._snapshots.get_snapshot(tenant_id, project_id, sid)
            self._snapshots.mark_stale(
                snap, actor=actor,
                reason=f"upstream {changed_node_type} changed: "
                       f"{sorted(changed_node_ids)}")
        return snap_ids

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _obj_id(obj: Any, node_type: str) -> str:
        # node_type 是 NODE_* 值（如 "product_principle"），id 字段名复用
        # service._ID_FIELD_FOR（如 product_principle → principle_id）
        value = getattr(obj, _ID_FIELD_FOR[node_type])
        return str(value)

    def _objects(self, node_type: str, tenant_id: str,
                 project_id: str) -> list[Any]:
        from typing import cast
        fn = {
            NODE_INSIGHT: self._pi.list_insights,
            NODE_OPPORTUNITY: self._pi.list_opportunities,
            NODE_PRINCIPLE: self._pi.list_principles,
            NODE_REQUIREMENT: self._pi.list_requirements,
            NODE_FEATURE: self._pi.list_features,
        }[node_type]
        return cast(list[Any], fn(tenant_id, project_id))


__all__ = [
    "ImpactPropagationService",
    "IMPACT_CLAIM", "IMPACT_RELATION", "IMPACT_ASSESSMENT",
    "IMPACT_PRINCIPLE_SOURCE", "IMPACT_REQUIREMENT_SOURCE",
]
