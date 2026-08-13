"""Product Definition Gate（v5.9.1 重构，§46-48/57）。

**分层**（§47 推荐）：
1. **Technical Gate**（deterministic，无 LLM）：READY / CONDITIONAL / BLOCKED；
2. **Authorization**（Owner Decision）：APPROVED / REJECTED / PENDING /
   APPROVED_WITH_WAIVER —— 绑定确切 snapshot（id + content_hash）；
3. **Commit Eligibility**：technical READY+APPROVED，或 technical
   CONDITIONAL+APPROVED_WITH_WAIVER；BLOCKED 永不 commit。

**结构化输出**（P0-01）：:class:`GateEvaluation` 含
``hard_blockers / conditional_blockers / warnings / information`` +
``criteria_results``（每条 criterion_id/status/severity/message/affected_refs）。
**0 contradiction 是 information，不是 blocker**；contradiction > 0 按
criticality/review/waiver 分类为 conditional 或 warning。

**Snapshot 输入**（P0-02/48）：Gate 评估对象是 immutable
:class:`ProductDefinitionSnapshot`（含 content_hash）。历史 approve 不自动
授权任何 snapshot；授权必须绑定同一 snapshot_id + content_hash
（:meth:`get_effective_decision`，最新 resolved 为准，P0-03）。

**Commit**（P0-04/08/29）：:meth:`commit_snapshot` 提交 **snapshot refs 的
exact versions**（不重查 live tables）；snapshot stale → 拒绝并要求新
snapshot；CONDITIONAL 无 waiver → 拒绝；ProductTruth trust_level 按真实
来源推导（Owner approval ≠ verified）。

**兼容**：:meth:`evaluate` / :meth:`commit_approved` 保留（评估 live
view 的确定性结果；commit_approved 走新语义）。

criteria 静态定义 / 结果类型 / 逐条评估在
:mod:`aipd_os.product_intelligence.gate_criteria`；本模块保留授权 / commit
事务语义并 re-export criteria 常量（导出集与拆分前一致）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB, now_iso

from .gate_criteria import (
    CRIT_CONDITIONAL,
    CRIT_FAIL,
    CRITERION_CONDITIONAL_WAIVER,
    CRITERION_CRITICAL_CONFLICT,
    CRITERION_CRITICAL_CONTRADICTIONS,
    CRITERION_CRITICAL_REQUIREMENT_SOURCE,
    CRITERION_CRITICAL_REQUIREMENT_VERIFICATION,
    CRITERION_CRITICAL_UNKNOWN,
    CRITERION_FEATURE_TRACEABILITY,
    CRITERION_IDEA_MATURITY,
    CRITERION_KEY_CLAIM_ASSESSMENT,
    CRITERION_OWNER_DECISION,
    CRITERION_PRINCIPLES_PRESENT,
    CRITERION_REQUIREMENT_TRACEABILITY,
    CRITERION_SELECTED_OPPORTUNITY,
    CRITERION_SNAPSHOT_FRESHNESS,
    GATE_EVALUATOR_VERSION,
    GATE_POLICY_VERSION,
    SEV_CONDITIONAL,
    SEV_HARD,
    SEV_INFO,
    SEV_WARNING,
    CriterionResult,
    GateCriteriaEvaluator,
    GateEvaluation,
    _derive_trust,
    _head_sha,
    _json,
)
from .snapshot import (
    SNAPSHOT_COMMITTED,
    SNAPSHOT_FROZEN,
    ProductDefinitionSnapshot,
)

# Gate 结果
GATE_READY = "READY"
GATE_CONDITIONAL = "CONDITIONAL"
GATE_BLOCKED = "BLOCKED"

# Owner Decision topic（复用 canonical decisions 表）
GATE_DECISION_TOPIC = "product_definition_gate"
GATE_CHOICE_APPROVE = "approve"
GATE_CHOICE_REJECT = "reject"
GATE_CHOICE_REQUEST_REVISION = "request_revision"
GATE_CHOICE_APPROVE_WITH_WAIVER = "approve_with_waiver"
OWNER_CHOICES = frozenset({GATE_CHOICE_APPROVE, GATE_CHOICE_REJECT,
                           GATE_CHOICE_REQUEST_REVISION,
                           GATE_CHOICE_APPROVE_WITH_WAIVER})

# authorization states
AUTH_APPROVED = "APPROVED"
AUTH_REJECTED = "REJECTED"
AUTH_PENDING = "PENDING"
AUTH_APPROVED_WITH_WAIVER = "APPROVED_WITH_WAIVER"


class SnapshotAlreadyCommittedError(RuntimeError):
    """同一 snapshot 已提交过（exactly-once，§26/30）。"""


class ProductDefinitionGate(GateCriteriaEvaluator):
    """确定性 Product Definition Gate（技术评估 + 授权 + 提交资格）。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = "default",
                 project_id: str = "default") -> None:
        super().__init__(db, tenant_id=tenant_id, project_id=project_id)

    # ------------------------------------------------------------- evaluate
    def evaluate_snapshot(self, snap: ProductDefinitionSnapshot) -> GateEvaluation:
        """对**具体 snapshot** 做技术评估（§48：Gate 输入明确，不推断）。

        §10：Product 相关 criteria 全部只读 :class:`SnapshotView`
        （frozen snapshot 解析结果）；live tables 仅用于 freshness/basis
        校验。"""
        results = self.criteria_results(snap)

        hard = [c for c in results if c.severity == SEV_HARD
                and c.status == CRIT_FAIL]
        conditional = [c for c in results
                       if c.severity == SEV_CONDITIONAL
                       and c.status in (CRIT_CONDITIONAL, CRIT_FAIL)]
        warnings = [c for c in results if c.severity == SEV_WARNING]
        information = [c for c in results if c.severity == SEV_INFO]

        if hard:
            result = GATE_BLOCKED
        elif conditional:
            result = GATE_CONDITIONAL
        else:
            result = GATE_READY

        return GateEvaluation(
            evaluation_id=self._db.next_sequence("gate_evaluation", "GEV"),
            tenant_id=self._tenant, project_id=self._project,
            snapshot_id=snap.snapshot_id, snapshot_hash=snap.content_hash,
            result=result,
            hard_blockers=[c.message for c in hard],
            conditional_blockers=[c.message for c in conditional],
            warnings=[c.message for c in warnings],
            information=[c.message for c in information],
            criteria_results=results,
            evaluated_at=now_iso())

    def evaluate(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """兼容入口：评估指定（或最新）snapshot。返回 GateEvaluation dict。"""
        if snapshot_id is None:
            snap = self._snapshots.latest_snapshot(self._tenant, self._project)
            if snap is None:
                raise ValueError(
                    "no ProductDefinitionSnapshot exists; create one via "
                    "create_snapshot() before gate evaluation (P0-48)")
            snapshot_id = snap.snapshot_id
        snap = self._snapshots.get_snapshot(self._tenant, self._project,
                                            snapshot_id)
        return self.evaluate_snapshot(snap).to_dict()

    def record_gate(self, actor: str = "system",
                    snapshot_id: str | None = None) -> dict[str, Any]:
        """把 Gate 结果写入 gates 表（auditable）+ gate_evaluations 表。"""
        if snapshot_id is None:
            latest = self._snapshots.latest_snapshot(self._tenant,
                                                     self._project)
            if latest is None:
                raise ValueError(
                    "no ProductDefinitionSnapshot; create_snapshot() first")
            snapshot_id = latest.snapshot_id
        evaluation = self.evaluate_snapshot(
            self._snapshots.get_snapshot(self._tenant, self._project,
                                         snapshot_id))
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO gate_evaluations(evaluation_id,project_id,"
                "tenant_id,snapshot_id,snapshot_hash,result,"
                "hard_blockers_json,conditional_blockers_json,warnings_json,"
                "information_json,criteria_results_json,evaluated_at,"
                "evaluator_version,policy_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (evaluation.evaluation_id, evaluation.project_id,
                 evaluation.tenant_id, evaluation.snapshot_id,
                 evaluation.snapshot_hash, evaluation.result,
                 _json(evaluation.hard_blockers),
                 _json(evaluation.conditional_blockers),
                 _json(evaluation.warnings), _json(evaluation.information),
                 _json([c.to_dict() for c in evaluation.criteria_results]),
                 evaluation.evaluated_at, evaluation.evaluator_version,
                 evaluation.policy_version))
            self._db.add_audit(
                actor, "product_definition_gate.evaluate",
                evaluation.project_id, evaluation.tenant_id,
                after=evaluation.to_dict())
        return evaluation.to_dict()

    # ------------------------------------------------------------- owner
    def propose_owner_decision(self, recommendation: str = "",
                               actor: str = "system",
                               snapshot_id: str | None = None,
                               gate_evaluation_id: str = "") -> str:
        """创建 Owner Decision（绑定 snapshot + hash + evaluation）。"""
        if snapshot_id is None:
            latest = self._snapshots.latest_snapshot(self._tenant,
                                                     self._project)
            if latest is None:
                raise ValueError(
                    "no ProductDefinitionSnapshot; create_snapshot() first "
                    "(Owner Decision must bind an exact snapshot, P0-02)")
            snapshot_id = latest.snapshot_id
        snap = self._snapshots.get_snapshot(self._tenant, self._project,
                                            snapshot_id)
        return self._db.propose_decision(
            self._tenant, self._project, topic=GATE_DECISION_TOPIC,
            recommendation=recommendation or (
                "Approve to commit approved Product Definition Snapshot "
                f"{snap.snapshot_id} to Product Truth; reject/request_revision "
                "to keep EXPLORE state"),
            options=[GATE_CHOICE_APPROVE, GATE_CHOICE_REJECT,
                     GATE_CHOICE_REQUEST_REVISION,
                     GATE_CHOICE_APPROVE_WITH_WAIVER],
            trigger=f"{GATE_DECISION_TOPIC}:{self._project}",
            metadata={
                "snapshot_id": snap.snapshot_id,
                "snapshot_hash": snap.content_hash,
                "gate_evaluation_id": gate_evaluation_id,
                "decision_version": 1,
            })

    def resolve_owner_decision(self, decision_id: str, choice: str,
                               comment: str = "",
                               actor: str = "system",
                               waiver: dict[str, Any] | None = None) -> dict[str, Any]:
        """Owner 显式裁定。approve_with_waiver 需 waiver 记录
        （accepted_conditions/accepted_risks/owner/decision_id/snapshot_id/
        expires_if_changed/created_at，P0-04）。"""
        if choice not in OWNER_CHOICES:
            raise ValueError(f"invalid gate choice {choice!r}; expected one of "
                             f"{sorted(OWNER_CHOICES)}")
        decisions = self._db.list_decisions(self._tenant, self._project)
        decision = next((d for d in decisions if d["decision_id"] == decision_id),
                        None)
        if decision is None:
            raise KeyError(decision_id)
        metadata = dict(decision.get("metadata") or {})
        snap_id = metadata.get("snapshot_id")
        if choice == GATE_CHOICE_APPROVE_WITH_WAIVER:
            if not waiver:
                raise ValueError(
                    "approve_with_waiver requires explicit waiver "
                    "(accepted_conditions/accepted_risks/owner)")
            metadata["waiver"] = {
                **waiver,
                "decision_id": decision_id,
                "snapshot_id": snap_id,
                "created_at": now_iso(),
                "expires_if_changed": waiver.get("expires_if_changed", True),
            }
        with self._db.transaction() as c:
            c.execute(
                "UPDATE decisions SET status='resolved',choice=?,comment=?,"
                "resolved_at=?,version_no=version_no+1,metadata_json=? "
                "WHERE tenant_id=? AND project_id=? AND decision_id=?",
                (choice, comment or None, now_iso(), _json(metadata),
                 self._tenant, self._project, decision_id))
            open_count = c.execute(
                "SELECT COUNT(*) FROM decisions WHERE tenant_id=? AND "
                "project_id=? AND status='proposed'",
                (self._tenant, self._project)).fetchone()[0]
            new_status = "awaiting_owner_decision" if open_count else "active"
            c.execute("UPDATE projects SET status=?,updated_at=? "
                      "WHERE tenant_id=? AND project_id=?",
                      (new_status, now_iso(), self._tenant, self._project))
            self._db.add_audit(actor, "product_definition_gate.resolve",
                               self._project, self._tenant,
                               after={"decision_id": decision_id,
                                      "choice": choice,
                                      "snapshot_id": snap_id})
        return {"decision_id": decision_id, "choice": choice,
                "comment": comment, "snapshot_id": snap_id,
                "waiver": metadata.get("waiver"),
                "resolved_at": now_iso()}

    def get_effective_decision(self, snapshot_id: str) -> dict[str, Any] | None:
        """P0-03：该 snapshot 的最新 resolved decision（deterministic
        projection：resolved_at desc / version desc / created_at desc）。
        历史 decision 保留（不删除）；无 mutable boolean。"""
        decisions = self._db.list_decisions(self._tenant, self._project)
        bound = [d for d in decisions
                 if d["topic"] == GATE_DECISION_TOPIC
                 and d["status"] == "resolved"
                 and (d.get("metadata") or {}).get("snapshot_id") == snapshot_id]
        if not bound:
            return None
        bound.sort(key=lambda d: (
            d.get("resolved_at") or "", int(d.get("version_no", 1)),
            d.get("created_at") or ""))
        return bound[-1]

    def authorization_status(self, snapshot_id: str) -> dict[str, Any]:
        """Authorization 层（§47）：APPROVED / REJECTED / PENDING /
        APPROVED_WITH_WAIVER。"""
        effective = self.get_effective_decision(snapshot_id)
        if effective is None:
            return {"state": AUTH_PENDING, "decision_id": None,
                    "choice": None, "waiver": None}
        choice = effective["choice"]
        if choice == GATE_CHOICE_APPROVE_WITH_WAIVER:
            state = AUTH_APPROVED_WITH_WAIVER
        elif choice == GATE_CHOICE_APPROVE:
            state = AUTH_APPROVED
        elif choice == GATE_CHOICE_REJECT:
            state = AUTH_REJECTED
        else:
            state = AUTH_PENDING
        return {"state": state, "decision_id": effective["decision_id"],
                "choice": choice,
                "waiver": (effective.get("metadata") or {}).get("waiver")}

    def commit_eligibility(self, evaluation: GateEvaluation,
                           authorization: dict[str, Any]) -> dict[str, Any]:
        """Final Commit Eligibility（§47/62）：
        READY+APPROVED → YES；CONDITIONAL+APPROVED_WITH_WAIVER → YES；
        其余 → NO（含 reason）。BLOCKED 永不 commit。"""
        tech = evaluation.result
        auth = authorization["state"]
        if tech == GATE_BLOCKED:
            return {"eligible": False, "reason": "technical gate BLOCKED"}
        if auth in (AUTH_REJECTED,):
            return {"eligible": False, "reason": "owner REJECTED"}
        if auth == AUTH_PENDING:
            return {"eligible": False, "reason": "owner decision PENDING"}
        if tech == GATE_READY and auth == AUTH_APPROVED:
            return {"eligible": True, "reason": "READY + APPROVED"}
        if tech == GATE_CONDITIONAL and auth == AUTH_APPROVED_WITH_WAIVER:
            return {"eligible": True,
                    "reason": "CONDITIONAL + APPROVE_WITH_WAIVER (waiver "
                              "recorded)"}
        return {"eligible": False,
                "reason": f"{tech} requires explicit "
                          f"{'APPROVE' if tech == GATE_READY else 'APPROVE_WITH_WAIVER'}"}

    def owner_decision_status(self) -> dict[str, Any]:
        """当前 Owner 决策概览（owner UX）。"""
        decisions = self._db.list_decisions(self._tenant, self._project)
        gate_decisions = [d for d in decisions
                          if d["topic"] == GATE_DECISION_TOPIC]
        return {
            "pending": [d for d in gate_decisions if d["status"] == "proposed"],
            "resolved": [d for d in gate_decisions
                         if d["status"] == "resolved"],
            "latest_approved": any(
                d["status"] == "resolved" and d["choice"] in (
                    GATE_CHOICE_APPROVE, GATE_CHOICE_APPROVE_WITH_WAIVER)
                for d in gate_decisions),
        }

    # ------------------------------------------------------------- commit
    def commit_snapshot(self, snap: ProductDefinitionSnapshot,
                        actor: str = "system",
                        idempotent: bool = True) -> dict[str, Any]:
        """P0-02/04/05/06/07/08/29/30：**原子 exactly-once** commit。

        单 transaction boundary（§27）：ProductTruth records + canonical
        lineage + truth_lineage 兼容边 + commit ledger + snapshot lifecycle
        （frozen→committed）+ audit —— 任何失败 ROLLBACK（0 部分写入）。

        1. 前置校验（事务外，无副作用）：stale / hash / authorization /
           eligibility；
        2. exactly-once：ledger 已有该 snapshot → 返回已有 receipt（幂等，
           idempotent=False 时抛 SnapshotAlreadyCommittedError）；UNIQUE
           约束兜底并发；
        3. 原子占用：snapshot 必须 frozen（UPDATE rowcount=1 才算成功）→
           frozen→committed（**绝不 frozen→stale**，P0-05）；
        4. trust_level 按真实来源推导（approval ≠ verified，P0-08）。
        """
        from aipd_os.product_truth.lineage import LineageGraph
        from aipd_os.product_truth.models import SourceRef, TruthRecord
        from aipd_os.product_truth.store import ProductTruthStore

        # §30/33：非 frozen（含 STALE）快照不可 commit —— 显式前置校验，
        # 语义清晰（不依赖事务内 rowcount 兜底）
        if snap.lifecycle_status != SNAPSHOT_FROZEN:
            raise RuntimeError(
                f"snapshot {snap.snapshot_id} is {snap.lifecycle_status}; "
                f"only frozen snapshots can be committed")

        stale, reasons = self._snapshots.is_stale(snap, self._tenant,
                                                  self._project)
        if stale:
            raise RuntimeError(
                f"snapshot {snap.snapshot_id} is STALE; create a new snapshot, "
                f"re-evaluate and re-approve: {'; '.join(reasons)}")
        if not snap.verify_hash():
            raise RuntimeError(
                f"snapshot {snap.snapshot_id} content_hash mismatch "
                "(integrity breach); refuse commit")

        evaluation = self.evaluate_snapshot(snap)
        authorization = self.authorization_status(snap.snapshot_id)
        eligibility = self.commit_eligibility(evaluation, authorization)
        if not eligibility["eligible"]:
            raise RuntimeError(
                f"cannot commit snapshot {snap.snapshot_id}: "
                f"{eligibility['reason']}")

        store = ProductTruthStore(str(self._db.path),
                                  tenant_id=self._tenant,
                                  project_id=self._project)
        graph = LineageGraph(store, tenant_id=self._tenant,
                             project_id=self._project,
                             canonical_db=self._db)
        metadata_base = {
            "approval_state": "approved",
            "gate_approved": True,
            "definition_status": "approved",
            "source_snapshot_id": snap.snapshot_id,
            "source_snapshot_hash": snap.content_hash,
            "owner_decision_id": authorization["decision_id"],
            "owner_choice": authorization["choice"],
            "source_commit": _head_sha(),
        }
        if authorization["waiver"]:
            metadata_base["waiver"] = authorization["waiver"]

        with self._db.transaction() as c:
            # 2) exactly-once：已有 commit → receipt（幂等）或抛错
            existing = c.execute(
                "SELECT * FROM product_definition_commits WHERE "
                "tenant_id=? AND project_id=? AND snapshot_id=?",
                (self._tenant, self._project, snap.snapshot_id)).fetchone()
            if existing is not None:
                if not idempotent:
                    raise SnapshotAlreadyCommittedError(
                        f"snapshot {snap.snapshot_id} already committed "
                        f"(commit {existing['commit_id']})")
                return self._receipt(existing, snap)
            # 3) 原子占用：frozen → committed（race protection，§30）
            cur = c.execute(
                "UPDATE product_definition_snapshots SET lifecycle_status=? "
                "WHERE snapshot_id=? AND project_id=? AND tenant_id=? "
                "AND lifecycle_status='frozen'",
                (SNAPSHOT_COMMITTED, snap.snapshot_id,
                 self._project, self._tenant))
            if cur.rowcount != 1:
                raise SnapshotAlreadyCommittedError(
                    f"snapshot {snap.snapshot_id} not in frozen state; "
                    "cannot commit (race or already committed)")
            # 4) commit ledger（UNIQUE(tenant,project,snapshot) 兜底并发）
            commit_id = self._db.next_sequence("product_commit", "C")
            committed: list[str] = []
            for r in snap.requirement_refs:
                req = self._pi.get_requirement(self._tenant, self._project,
                                               r["id"])
                rid = store.add(TruthRecord(
                    record_type="requirement",
                    content=f"{req.title}: {req.statement}",
                    source=SourceRef(
                        note=f"product_intelligence:{req.requirement_id}"),
                    trust_level=_derive_trust(req.epistemic_status,
                                              req.verification_method,
                                              req.verification_test_refs),
                    metadata={
                        **metadata_base,
                        "requirement_id": req.requirement_id,
                        "source_requirement_version": req.version_no,
                        "criticality": req.criticality,
                        "epistemic_status": req.epistemic_status,
                    }), conn=c)
                graph.add_edge(req.requirement_id, rid,
                               relation="derived_from", conn=c)
                committed.append(rid)
            for r in snap.feature_refs:
                feat = self._pi.get_feature(self._tenant, self._project,
                                            r["id"])
                fid = store.add(TruthRecord(
                    record_type="feature",
                    content=f"{feat.title}: {feat.description}",
                    source=SourceRef(
                        note=f"product_intelligence:{feat.feature_id}"),
                    trust_level=_derive_trust(feat.epistemic_status, "", []),
                    metadata={
                        **metadata_base,
                        "feature_id": feat.feature_id,
                        "source_feature_version": feat.version_no,
                        "epistemic_status": feat.epistemic_status,
                    }), conn=c)
                graph.add_edge(feat.feature_id, fid,
                               relation="derived_from", conn=c)
                committed.append(fid)
            c.execute(
                "INSERT INTO product_definition_commits(commit_id,project_id,"
                "tenant_id,snapshot_id,snapshot_hash,gate_evaluation_id,"
                "owner_decision_id,committed_truth_refs_json,committed_at,"
                "actor) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (commit_id, self._project, self._tenant, snap.snapshot_id,
                 snap.content_hash, evaluation.evaluation_id,
                 authorization["decision_id"] or "",
                 _json(committed), now_iso(), actor))
            self._db.add_audit(actor, "product_definition_gate.commit",
                               self._project, self._tenant,
                               after={"committed": committed,
                                      "commit_id": commit_id,
                                      "snapshot_id": snap.snapshot_id,
                                      "snapshot_hash": snap.content_hash,
                                      "decision_id":
                                          authorization["decision_id"],
                                      "requirements": len(snap.requirement_refs),
                                      "features": len(snap.feature_refs)})
            receipt = self._receipt(
                {"commit_id": commit_id, "snapshot_id": snap.snapshot_id,
                 "snapshot_hash": snap.content_hash,
                 "committed_truth_refs_json": _json(committed),
                 "owner_decision_id": authorization["decision_id"] or ""},
                snap, committed=committed)
        return receipt

    @staticmethod
    def _receipt(row: Any, snap: ProductDefinitionSnapshot,
                 committed: list[str] | None = None) -> dict[str, Any]:
        """commit receipt（幂等返回值，§25/26）。"""
        refs = committed
        if refs is None:
            import json as _j
            try:
                refs = _j.loads(row["committed_truth_refs_json"] or "[]")
            except (ValueError, TypeError):
                refs = []
        return {
            "commit_id": row["commit_id"],
            "committed": refs,
            "requirements": len(snap.requirement_refs),
            "features": len(snap.feature_refs),
            "snapshot_id": snap.snapshot_id,
            "snapshot_hash": snap.content_hash,
            "decision_id": str(row["owner_decision_id"] or ""),
            "gate": "committed",
            "authorization": "APPROVED",
            "idempotent_replay": committed is None,
        }

    def get_commit(self, snapshot_id: str) -> dict[str, Any] | None:
        """ledger 查询（§25）。"""
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM product_definition_commits WHERE "
                "tenant_id=? AND project_id=? AND snapshot_id=?",
                (self._tenant, self._project, snapshot_id)).fetchone()
        if row is None:
            return None
        return dict(row)

    def commit_approved(self, actor: str = "system") -> dict[str, Any]:
        """兼容入口：最新 snapshot + 绑定决策 → commit_snapshot。

        旧语义（任意历史 approve 直接提交 live tables）已废弃 —— 新语义
        要求 snapshot 绑定（P0-02/29）。"""
        snap = self._snapshots.latest_snapshot(self._tenant, self._project)
        if snap is None:
            raise RuntimeError(
                "no snapshot; create_snapshot() then propose/resolve Owner "
                "Decision before commit (P0-02)")
        return self.commit_snapshot(snap, actor=actor)


__all__ = [
    "ProductDefinitionGate",
    "GateEvaluation",
    "CriterionResult",
    "GATE_READY", "GATE_CONDITIONAL", "GATE_BLOCKED",
    "GATE_DECISION_TOPIC",
    "GATE_CHOICE_APPROVE", "GATE_CHOICE_REJECT",
    "GATE_CHOICE_REQUEST_REVISION", "GATE_CHOICE_APPROVE_WITH_WAIVER",
    "OWNER_CHOICES",
    "AUTH_APPROVED", "AUTH_REJECTED", "AUTH_PENDING",
    "AUTH_APPROVED_WITH_WAIVER",
    "GATE_POLICY_VERSION", "GATE_EVALUATOR_VERSION",
    "CRITERION_IDEA_MATURITY", "CRITERION_KEY_CLAIM_ASSESSMENT",
    "CRITERION_CRITICAL_CONTRADICTIONS", "CRITERION_SELECTED_OPPORTUNITY",
    "CRITERION_PRINCIPLES_PRESENT", "CRITERION_REQUIREMENT_TRACEABILITY",
    "CRITERION_FEATURE_TRACEABILITY", "CRITERION_CRITICAL_REQUIREMENT_SOURCE",
    "CRITERION_CRITICAL_REQUIREMENT_VERIFICATION", "CRITERION_CRITICAL_UNKNOWN",
    "CRITERION_CRITICAL_CONFLICT", "CRITERION_SNAPSHOT_FRESHNESS",
    "CRITERION_OWNER_DECISION", "CRITERION_CONDITIONAL_WAIVER",
]
