"""ProductIntelligenceService（v5.9 + v5.9.1）。

Insight → Opportunity → ProductPrinciple → Requirement → Feature 的
tenant/project scoped CRUD + canonical lineage 接线 + deterministic 校验。

规则（提示词 §44-46，全部确定性、无 LLM 依赖）：
- Insight 必须有 ≥1 个 source claim（同 scope）；创建时写
  ``insight -derived_from-> claim`` lineage；
- Opportunity 必须有 ≥1 个 source insight；写
  ``opportunity -derived_from-> insight``；
- ProductPrinciple 必须有 ≥1 个 source insight；写
  ``product_principle -derived_from-> insight``；
- Requirement 必须有 ≥1 个 source principle；写
  ``requirement -derived_from-> product_principle``；
- Feature 必须有 ≥1 个 source requirement；写
  ``feature -implements-> requirement``；
- 跨 tenant/project 引用一律拒绝（:class:`ProductScopeError`）。

**v5.9.1 事务语义（P0-05/06/20/22）**：
- create/update/retire/supersede 的对象变更 + lineage reconcile + audit
  在同一 ``db.transaction()`` 内；任何失败 → ROLLBACK（无部分写入）；
- update 顺序：construct candidate → validate refs/lifecycle（**先校验后
  mutate**，失败无副作用）→ optimistic UPDATE → lineage reconcile → audit；
- lineage reconcile：desired refs vs current active edges diff →
  to_retire（soft-retire，历史保留）+ to_add（§22-23）。

**v5.9.1 Opportunity 显式选择（P0-07）**：
:meth:`select_opportunity` —— 恰好 1 个 ``selection_status=selected``；
候选/拒绝/被取代由显式状态表达，不再用「非 archived」暗示选择。

回溯（§37/§58）：
- :meth:`trace_upstream`：任意对象 → Claim → EvidenceRelation → Evidence；
- :meth:`feature_evidence_trace`：Feature → Requirement → Principle →
  Insight → Claim → Evidence（v5.9 核心验收查询）。
"""
from __future__ import annotations

import json as _json_module
from typing import Any, cast

from aipd_os.state.db import AIPDStateDB, now_iso
from aipd_os.state.lineage import LineageNodeRef, LineageService

from .models import (
    LIFECYCLE_ARCHIVED,
    SELECTION_CANDIDATE,
    SELECTION_SELECTED,
    Feature,
    Insight,
    Opportunity,
    ProductPrinciple,
    Requirement,
)

# node_type（canonical lineage）
NODE_INSIGHT = "insight"
NODE_OPPORTUNITY = "opportunity"
NODE_PRINCIPLE = "product_principle"
NODE_REQUIREMENT = "requirement"
NODE_FEATURE = "feature"

# 表名 ↔ 对象映射
_TABLE_FOR = {
    NODE_INSIGHT: "insights",
    NODE_OPPORTUNITY: "opportunities",
    NODE_PRINCIPLE: "product_principles",
    NODE_REQUIREMENT: "requirements",
    NODE_FEATURE: "features",
}
# 模型 list 字段 → DB *_json 列（v5.9：JSON 列统一 *_json 后缀）
_JSON_FIELDS = {
    NODE_INSIGHT: {"source_claim_ids": "source_claim_ids_json",
                   "source_assessment_versions":
                       "source_assessment_versions_json"},
    NODE_OPPORTUNITY: {"source_insight_ids": "source_insight_ids_json",
                       "known_alternatives": "known_alternatives_json",
                       "evidence_gaps": "evidence_gaps_json"},
    NODE_PRINCIPLE: {"source_insight_ids": "source_insight_ids_json",
                     "source_claim_ids": "source_claim_ids_json"},
    NODE_REQUIREMENT: {"source_principle_ids": "source_principle_ids_json",
                       "source_evidence_refs": "source_evidence_refs_json",
                       "derivation_input_refs": "derivation_input_refs_json",
                       "verification_test_refs": "verification_test_refs_json",
                       "affected_item_refs": "affected_item_refs_json"},
    NODE_FEATURE: {"source_requirement_ids": "source_requirement_ids_json",
                   "source_principle_ids": "source_principle_ids_json",
                   "assumptions": "assumptions_json",
                   "constraints": "constraints_json"},
}

# 对象 id 字段名（模型层；product_principle 特殊，其余 = {node_type}_id）
_ID_FIELD_FOR = {
    NODE_INSIGHT: "insight_id",
    NODE_OPPORTUNITY: "opportunity_id",
    NODE_PRINCIPLE: "principle_id",
    NODE_REQUIREMENT: "requirement_id",
    NODE_FEATURE: "feature_id",
}

# ID 序列名（id_sequences）
_SEQ_FOR = {
    NODE_INSIGHT: ("insight", "INS"),
    NODE_OPPORTUNITY: ("opportunity", "OPP"),
    NODE_PRINCIPLE: ("product_principle", "PRN"),
    NODE_REQUIREMENT: ("requirement", "REQ"),
    NODE_FEATURE: ("feature", "FTR"),
}
# 上游引用字段（用于 lineage 与 scope 校验）
_REF_FOR = {
    NODE_INSIGHT: ("source_claim_ids", "claim"),
    NODE_OPPORTUNITY: ("source_insight_ids", NODE_INSIGHT),
    NODE_PRINCIPLE: ("source_insight_ids", NODE_INSIGHT),
    NODE_REQUIREMENT: ("source_principle_ids", NODE_PRINCIPLE),
    NODE_FEATURE: ("source_requirement_ids", NODE_REQUIREMENT),
}
# lineage relation：对象 -relation-> 上游
_RELATION_FOR = {
    NODE_INSIGHT: "derived_from",
    NODE_OPPORTUNITY: "derived_from",
    NODE_PRINCIPLE: "derived_from",
    NODE_REQUIREMENT: "derived_from",
    NODE_FEATURE: "implements",
}


class ProductScopeError(ValueError):
    """跨 tenant/project 引用拒绝。"""


class ProductObjectNotFoundError(KeyError):
    """在指定 scope 下找不到对象。"""


class ProductLineageMissingError(ValueError):
    """deterministic lineage 校验失败（缺必需上游引用）。"""


class ProductOptimisticLockError(Exception):
    """version_no 乐观锁冲突。"""


class ProductIntelligenceService:
    """Product Intelligence 五域 canonical service（事务安全）。"""

    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    # ------------------------------------------------------------- helpers
    def _next_id(self, node_type: str) -> str:
        seq, prefix = _SEQ_FOR[node_type]
        return self._db.next_sequence(seq, prefix)

    @staticmethod
    def _refs(obj: Any, node_type: str) -> list[str]:
        field, _ = _REF_FOR[node_type]
        return list(getattr(obj, field) or [])

    @staticmethod
    def _scope_of(obj: Any) -> tuple[str, str]:
        return obj.tenant_id, obj.project_id

    def _ensure_refs_in_scope(self, obj: Any, node_type: str) -> None:
        """上游引用必须存在且同 tenant+project（跨 scope 拒绝；**先校验**，
        P0-05 —— 调用发生在任何 UPDATE 之前）。"""
        ref_field, ref_type = _REF_FOR[node_type]
        refs = list(getattr(obj, ref_field) or [])
        if not refs:
            raise ProductLineageMissingError(
                f"{node_type} {getattr(obj, node_type + '_id', '')!r} requires "
                f"at least one {ref_field} (deterministic lineage contract)")
        table = "claims" if ref_type == "claim" else _TABLE_FOR[ref_type]
        id_col = "claim_id" if ref_type == "claim" else _ID_FIELD_FOR[ref_type]
        for rid in refs:
            with self._db.connect() as c:
                row = c.execute(
                    f"SELECT 1 FROM {table} WHERE {id_col}=? "
                    "AND project_id=? AND tenant_id=?",
                    (rid, obj.project_id, obj.tenant_id)).fetchone()
            if row is None:
                raise ProductScopeError(
                    f"{ref_type} {rid!r} does not exist in "
                    f"tenant {obj.tenant_id!r}/project {obj.project_id!r} "
                    f"(cross-scope {ref_field} rejected)")

    def _reconcile_lineage(self, obj: Any, node_type: str, actor: str) -> None:
        """P0-06/22-23：desired refs vs current active edges diff。

        to_retire = current - desired（soft-retire，历史保留在 audit/行）；
        to_add = desired - current（add_edge 幂等）。事务内调用时
        LineageService 复用活动连接（同一事务）。
        """
        lineage = LineageService(self._db)
        ref_field, ref_type = _REF_FOR[node_type]
        obj_id = getattr(obj, _ID_FIELD_FOR[node_type])
        desired = set(getattr(obj, ref_field) or [])
        node = LineageNodeRef(node_type=node_type, node_id=obj_id,
                              tenant_id=obj.tenant_id,
                              project_id=obj.project_id)
        current = {e.target.node_id for e in lineage.outgoing(node)
                   if e.target.node_type == ref_type}
        to_retire = sorted(current - desired)
        to_add = sorted(desired - current)
        for rid in to_retire:
            for edge in lineage.outgoing(node):
                if edge.target.node_type == ref_type \
                        and edge.target.node_id == rid:
                    lineage.retire_edge(
                        edge.edge_id, actor=actor,
                        reason=f"{node_type} {obj_id} source changed: "
                               f"{ref_field} removed {rid}")
        for rid in to_add:
            lineage.add_edge(
                node,
                LineageNodeRef(node_type=ref_type, node_id=rid,
                               tenant_id=obj.tenant_id,
                               project_id=obj.project_id),
                _RELATION_FOR[node_type],
                provenance={"source": "product_intelligence",
                            "object_type": node_type},
                actor=actor)

    def _audit(self, actor: str, action: str, obj: Any, before: Any = None) -> None:
        self._db.add_audit(actor, action, obj.project_id, obj.tenant_id,
                           before=before, after=obj.to_dict())

    # ------------------------------------------------------ generic CRUD
    def _create(self, obj: Any, node_type: str, actor: str) -> Any:
        """创建：scope 校验（先）→ 事务内 insert + audit + lineage reconcile。"""
        id_field = _ID_FIELD_FOR[node_type]
        if not getattr(obj, id_field):
            obj = type(obj)(
                **{**obj.to_dict(), id_field: self._next_id(node_type)})
        self._ensure_refs_in_scope(obj, node_type)
        ts = now_iso()
        d = obj.to_dict()
        id_col = id_field  # DB 列名与模型字段名一致（principle_id 等）
        json_map = _JSON_FIELDS[node_type]
        db_entries = {}
        for k, v in d.items():
            if k in (id_col, "created_at", "updated_at"):
                continue
            if k in json_map:
                db_entries[json_map[k]] = _json_module.dumps(
                    list(v) if isinstance(v, (list, tuple)) else v,
                    ensure_ascii=False, sort_keys=True)
            else:
                db_entries[k] = v
        cols = sorted(db_entries)
        table = _TABLE_FOR[node_type]
        with self._db.transaction() as c:
            c.execute(
                f"INSERT INTO {table}({id_col},{','.join(cols)},created_at,"
                f"updated_at) VALUES(?{',?' * len(cols)},?,?)",
                [d[id_field]] + [db_entries[k] for k in cols] + [ts, ts])
            row = c.execute(
                f"SELECT * FROM {table} WHERE {id_col}=? AND project_id=? "
                "AND tenant_id=?",
                (d[id_field], obj.project_id, obj.tenant_id)).fetchone()
            created = self._row_to_object(node_type, dict(row))
            self._audit(actor, f"{node_type}.create", created)
            self._reconcile_lineage(created, node_type, actor)
        return created

    def _get(self, node_type: str, tenant_id: str, project_id: str,
             obj_id: str) -> Any:
        table = _TABLE_FOR[node_type]
        id_col = _ID_FIELD_FOR[node_type]
        with self._db.connect() as c:
            row = c.execute(
                f"SELECT * FROM {table} WHERE {id_col}=? AND project_id=? "
                "AND tenant_id=?", (obj_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise ProductObjectNotFoundError(obj_id)
        return self._row_to_object(node_type, dict(row))

    def _list(self, node_type: str, tenant_id: str,
              project_id: str) -> list[Any]:
        table = _TABLE_FOR[node_type]
        with self._db.connect() as c:
            rows = c.execute(
                f"SELECT * FROM {table} WHERE project_id=? AND tenant_id=? "
                "ORDER BY created_at", (project_id, tenant_id)).fetchall()
        return [self._row_to_object(node_type, dict(r)) for r in rows]

    @staticmethod
    def _row_to_object(node_type: str, row: dict[str, Any]) -> Any:
        if node_type == NODE_INSIGHT:
            return Insight.from_dict(row)
        if node_type == NODE_OPPORTUNITY:
            return Opportunity.from_dict(row)
        if node_type == NODE_PRINCIPLE:
            return ProductPrinciple.from_dict(row)
        if node_type == NODE_REQUIREMENT:
            return Requirement.from_dict(row)
        return Feature.from_dict(row)

    def _update(self, node_type: str, tenant_id: str, project_id: str,
                obj_id: str, expected_version: int, actor: str,
                **fields: Any) -> Any:
        """事务化更新（P0-05/06/18/20）。

        顺序：construct candidate → validate refs/lifecycle（先校验，
        失败无副作用）→ optimistic UPDATE → lineage reconcile → audit →
        COMMIT。任何失败 → ROLLBACK。
        """
        before = self._get(node_type, tenant_id, project_id, obj_id)
        if not fields:
            raise ValueError("no editable fields provided")
        ref_field, _ = _REF_FOR[node_type]
        # 1) candidate state（模型 __post_init__ 校验枚举/lifecycle）
        merged_dict = before.to_dict()
        merged_dict.update(fields)
        merged = self._row_to_object(node_type, merged_dict)
        # 2) 先校验（UPDATE 前）：跨 scope ref → 抛错，无任何写入
        if ref_field in fields:
            self._ensure_refs_in_scope(merged, node_type)
        table = _TABLE_FOR[node_type]
        id_col = _ID_FIELD_FOR[node_type]
        json_map = _JSON_FIELDS[node_type]
        db_fields: dict[str, Any] = {}
        for k, v in fields.items():
            if k in json_map:
                db_fields[json_map[k]] = _json_module.dumps(
                    list(v) if isinstance(v, (list, tuple)) else v,
                    ensure_ascii=False, sort_keys=True)
            else:
                db_fields[k] = v
        set_cols = sorted(db_fields)
        set_sql = ", ".join([f"{col}=?" for col in set_cols]
                            + ["updated_at=?", "version_no=version_no+1"])
        params: list[Any] = [db_fields[k] for k in set_cols] + [now_iso()]
        with self._db.transaction() as c:
            # 3) optimistic lock UPDATE（rowcount!=1 → 抛错 → ROLLBACK）
            cur = c.execute(
                f"UPDATE {table} SET {set_sql} WHERE {id_col}=? AND "
                "project_id=? AND tenant_id=? AND version_no=?",
                params + [obj_id, project_id, tenant_id, expected_version])
            if cur.rowcount != 1:
                raise ProductOptimisticLockError(
                    f"{node_type} {obj_id} optimistic-lock conflict")
            # 4) after（同事务读取）
            row = c.execute(
                f"SELECT * FROM {table} WHERE {id_col}=? AND project_id=? "
                "AND tenant_id=?",
                (obj_id, project_id, tenant_id)).fetchone()
            after = self._row_to_object(node_type, dict(row))
            # 5) audit + lineage reconcile（同事务）
            self._audit(actor, f"{node_type}.update", after,
                        before=before.to_dict())
            if ref_field in fields:
                self._reconcile_lineage(after, node_type, actor)
        return after

    # ------------------------------------------------------ 五域便捷 API
    # Insight
    def create_insight(self, obj: Insight, actor: str = "system") -> Insight:
        return cast(Insight, self._create(obj, NODE_INSIGHT, actor))

    def update_insight(self, tenant_id: str, project_id: str, insight_id: str,
                       expected_version: int, actor: str = "system",
                       **fields: Any) -> Insight:
        return cast(Insight, self._update(NODE_INSIGHT, tenant_id, project_id,
                                          insight_id, expected_version,
                                          actor, **fields))

    def get_insight(self, tenant_id: str, project_id: str,
                    insight_id: str) -> Insight:
        return cast(Insight, self._get(NODE_INSIGHT, tenant_id, project_id,
                                       insight_id))

    def list_insights(self, tenant_id: str, project_id: str) -> list[Insight]:
        return cast(list[Insight], self._list(NODE_INSIGHT, tenant_id,
                                              project_id))

    # Opportunity
    def create_opportunity(self, obj: Opportunity,
                           actor: str = "system") -> Opportunity:
        return cast(Opportunity, self._create(obj, NODE_OPPORTUNITY, actor))

    def update_opportunity(self, tenant_id: str, project_id: str,
                           opportunity_id: str, expected_version: int,
                           actor: str = "system",
                           **fields: Any) -> Opportunity:
        return cast(Opportunity, self._update(
            NODE_OPPORTUNITY, tenant_id, project_id, opportunity_id,
            expected_version, actor, **fields))

    def get_opportunity(self, tenant_id: str, project_id: str,
                        opportunity_id: str) -> Opportunity:
        return cast(Opportunity, self._get(NODE_OPPORTUNITY, tenant_id,
                                           project_id, opportunity_id))

    def list_opportunities(self, tenant_id: str,
                           project_id: str) -> list[Opportunity]:
        return cast(list[Opportunity], self._list(NODE_OPPORTUNITY, tenant_id,
                                                  project_id))

    def select_opportunity(self, tenant_id: str, project_id: str,
                           opportunity_id: str,
                           actor: str = "system") -> Opportunity:
        """P0-07：显式选择 —— 恰好 1 个 selected（事务：先取消其他 selected，
        再选中目标；audit 同事务）。archived 不可选。"""
        before = self._get(NODE_OPPORTUNITY, tenant_id, project_id,
                           opportunity_id)
        if before.lifecycle_status == LIFECYCLE_ARCHIVED:
            raise ValueError(
                f"cannot select archived opportunity {opportunity_id}")
        with self._db.transaction() as c:
            c.execute(
                "UPDATE opportunities SET selection_status=?, updated_at=?, "
                "version_no=version_no+1 WHERE project_id=? AND tenant_id=? "
                "AND selection_status=? AND opportunity_id<>?",
                (SELECTION_CANDIDATE, now_iso(), project_id, tenant_id,
                 SELECTION_SELECTED, opportunity_id))
            cur = c.execute(
                "UPDATE opportunities SET selection_status=?, updated_at=?, "
                "version_no=version_no+1 WHERE project_id=? AND tenant_id=? "
                "AND opportunity_id=? AND lifecycle_status<>?",
                (SELECTION_SELECTED, now_iso(), project_id, tenant_id,
                 opportunity_id, LIFECYCLE_ARCHIVED))
            if cur.rowcount != 1:
                raise ProductObjectNotFoundError(opportunity_id)
            self._db.add_audit(actor, "opportunity.select", project_id,
                               tenant_id,
                               after={"opportunity_id": opportunity_id,
                                      "selection_status": SELECTION_SELECTED})
        return cast(Opportunity, self._get(NODE_OPPORTUNITY, tenant_id,
                                           project_id, opportunity_id))

    # ProductPrinciple
    def create_principle(self, obj: ProductPrinciple,
                         actor: str = "system") -> ProductPrinciple:
        return cast(ProductPrinciple, self._create(obj, NODE_PRINCIPLE,
                                                   actor))

    def update_principle(self, tenant_id: str, project_id: str,
                         principle_id: str, expected_version: int,
                         actor: str = "system",
                         **fields: Any) -> ProductPrinciple:
        return cast(ProductPrinciple, self._update(
            NODE_PRINCIPLE, tenant_id, project_id, principle_id,
            expected_version, actor, **fields))

    def get_principle(self, tenant_id: str, project_id: str,
                      principle_id: str) -> ProductPrinciple:
        return cast(ProductPrinciple, self._get(NODE_PRINCIPLE, tenant_id,
                                                project_id, principle_id))

    def list_principles(self, tenant_id: str,
                        project_id: str) -> list[ProductPrinciple]:
        return cast(list[ProductPrinciple], self._list(NODE_PRINCIPLE,
                                                       tenant_id, project_id))

    # Requirement
    def create_requirement(self, obj: Requirement,
                           actor: str = "system") -> Requirement:
        return cast(Requirement, self._create(obj, NODE_REQUIREMENT, actor))

    def update_requirement(self, tenant_id: str, project_id: str,
                           requirement_id: str, expected_version: int,
                           actor: str = "system",
                           **fields: Any) -> Requirement:
        return cast(Requirement, self._update(
            NODE_REQUIREMENT, tenant_id, project_id, requirement_id,
            expected_version, actor, **fields))

    def get_requirement(self, tenant_id: str, project_id: str,
                        requirement_id: str) -> Requirement:
        return cast(Requirement, self._get(NODE_REQUIREMENT, tenant_id,
                                           project_id, requirement_id))

    def list_requirements(self, tenant_id: str,
                          project_id: str) -> list[Requirement]:
        return cast(list[Requirement], self._list(NODE_REQUIREMENT, tenant_id,
                                                  project_id))

    # Feature
    def create_feature(self, obj: Feature, actor: str = "system") -> Feature:
        return cast(Feature, self._create(obj, NODE_FEATURE, actor))

    def update_feature(self, tenant_id: str, project_id: str,
                       feature_id: str, expected_version: int,
                       actor: str = "system",
                       **fields: Any) -> Feature:
        return cast(Feature, self._update(NODE_FEATURE, tenant_id, project_id,
                                          feature_id, expected_version,
                                          actor, **fields))

    def get_feature(self, tenant_id: str, project_id: str,
                    feature_id: str) -> Feature:
        return cast(Feature, self._get(NODE_FEATURE, tenant_id, project_id,
                                       feature_id))

    def list_features(self, tenant_id: str, project_id: str) -> list[Feature]:
        return cast(list[Feature], self._list(NODE_FEATURE, tenant_id,
                                              project_id))

    # ------------------------------------------------------ traceability
    def trace_upstream(self, node_type: str, node_id: str,
                       tenant_id: str, project_id: str,
                       max_depth: int = 10) -> list[dict[str, Any]]:
        """沿 lineage 上游回溯（BFS）：返回边序列。"""
        lineage = LineageService(self._db)
        node = LineageNodeRef(node_type=node_type, node_id=node_id,
                              tenant_id=tenant_id, project_id=project_id)
        chain: list[dict[str, Any]] = []
        visited: set[tuple] = set()
        queue: list[tuple[Any, int]] = [(node, 0)]
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for edge in lineage.outgoing(current):
                chain.append(edge.to_dict())
                key = (edge.target.node_type, edge.target.node_id,
                       edge.target.project_id)
                if key in visited:
                    continue
                visited.add(key)
                queue.append((edge.target, depth + 1))
        return chain

    def feature_evidence_trace(self, feature_id: str,
                               tenant_id: str = "default",
                               project_id: str = "default",
                               max_depth: int = 12) -> dict[str, Any]:
        """v5.9 核心验收：Feature → Requirement → Principle → Insight →
        Claim → EvidenceRelation → Evidence 全链回溯。"""
        lineage = LineageService(self._db)
        start = LineageNodeRef(node_type=NODE_FEATURE, node_id=feature_id,
                               tenant_id=tenant_id, project_id=project_id)
        path: list[dict[str, Any]] = []
        visited: set[tuple] = {(NODE_FEATURE, feature_id, project_id)}
        queue: list[tuple[Any, int]] = [(start, 0)]
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for edge in lineage.outgoing(current):
                path.append({
                    "source": edge.source.to_dict(),
                    "target": edge.target.to_dict(),
                    "relation": edge.relation_type,
                })
                key = (edge.target.node_type, edge.target.node_id,
                       edge.target.project_id)
                if key in visited:
                    continue
                visited.add(key)
                queue.append((edge.target, depth + 1))
        claims = sorted({e["target"]["node_id"] for e in path
                         if e["target"]["node_type"] == "claim"})
        evidence = sorted({e["target"]["node_id"] for e in path
                           if e["target"]["node_type"] == "evidence"})
        return {
            "feature_id": feature_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "path": path,
            "claims": claims,
            "evidence": evidence,
            "evidence_reached": bool(evidence),
        }

    def principle_why(self, principle_id: str, tenant_id: str = "default",
                      project_id: str = "default") -> dict[str, Any]:
        """ProductPrinciple 的 WHY 链（§37）。"""
        chain = self.trace_upstream(NODE_PRINCIPLE, principle_id,
                                    tenant_id, project_id)
        return {
            "principle_id": principle_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "chain": chain,
            "explainable": any(e["target"]["node_type"] == "evidence"
                               for e in chain),
        }


__all__ = [
    "ProductIntelligenceService",
    "ProductScopeError",
    "ProductObjectNotFoundError",
    "ProductLineageMissingError",
    "ProductOptimisticLockError",
    "NODE_INSIGHT", "NODE_OPPORTUNITY", "NODE_PRINCIPLE",
    "NODE_REQUIREMENT", "NODE_FEATURE",
]
