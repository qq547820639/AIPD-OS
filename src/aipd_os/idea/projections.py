"""Idea Truth projection（v5.8 Commit 14）。

Idea Truth 是 **projection**（查询组合），不是第二个 Store，不创建新 DB/表。

:class:`IdeaTruthProjection.project(idea_id)` 返回 auditable projection：
  - known：有 supports/partially_supports 证据的命题；
  - assumption：epistemic_status=A 的命题（待验证假设）；
  - evidence：有任何 relation 的命题；
  - contradicted：有 contradicts 证据的命题；
  - unknown：epistemic_status=U 的命题；
  - gaps：无任何 evidence relation 的命题（需验证）；
  - maturity：IdeaMaturity.evaluate 判定（I0/I1/I2）。

:class:`IdeaTruthSnapshot`：可选不可变快照（JSON 可序列化，仅快照语义；
生成后修改源数据不影响 snapshot）。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from .evidence_graph import EvidenceGraph
from .maturity import IdeaMaturity
from .service import IdeaService


@dataclass(frozen=True)
class IdeaTruthSnapshot:
    """Idea Truth 的不可变快照（仅快照语义，非 canonical source）。"""

    idea_id: str
    tenant_id: str
    project_id: str
    generated_at: str
    projection: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({
            "idea_id": self.idea_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "projection": self.projection,
        }, ensure_ascii=False, indent=2, sort_keys=True)


class IdeaTruthProjection:
    """Idea Truth projection（查询组合；不建第二 Store）。"""

    def __init__(self, db: Any, graph: EvidenceGraph,
                 tenant_id: str = "default", project_id: str = "default") -> None:
        self._db = db
        self._graph = graph
        self._tenant = tenant_id
        self._project = project_id
        self._ideas = IdeaService(db)

    def project(self, idea_id: str) -> dict[str, Any]:
        """返回 Idea 的 Truth projection（known/assumption/evidence/contradicted/
        unknown/gaps/maturity）。"""
        idea = self._ideas.get(self._tenant, self._project, idea_id)
        claims = self._graph.list_claims(self._tenant, self._project, idea_id=idea_id)
        known: list[dict[str, Any]] = []
        assumption: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        contradicted: list[dict[str, Any]] = []
        unknown: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []

        for cl in claims:
            entry = {"claim_id": cl.claim_id, "claim_type": cl.claim_type,
                     "statement": cl.statement,
                     "epistemic_status": cl.epistemic_status}
            rels = self._graph.get_claim_evidence(self._tenant, self._project,
                                                  cl.claim_id)
            if rels:
                evidence.append(entry)
                if any(r.relation_type in ("supports", "partially_supports")
                       for r in rels):
                    known.append(entry)
                if any(r.relation_type == "contradicts" for r in rels):
                    contradicted.append(entry)
            else:
                gaps.append(entry)
            if cl.epistemic_status == "A":
                assumption.append(entry)
            if cl.epistemic_status == "U":
                unknown.append(entry)

        maturity = IdeaMaturity.evaluate(idea, self._graph).value
        return {
            "idea_id": idea_id,
            "tenant_id": self._tenant,
            "project_id": self._project,
            "title": idea.title,
            "lifecycle_status": idea.lifecycle_status,
            "maturity": maturity,
            "known": known,
            "assumption": assumption,
            "evidence": evidence,
            "contradicted": contradicted,
            "unknown": unknown,
            "gaps": gaps,
            "counts": {
                "total_claims": len(claims),
                "known": len(known),
                "assumption": len(assumption),
                "evidence": len(evidence),
                "contradicted": len(contradicted),
                "unknown": len(unknown),
                "gaps": len(gaps),
            },
        }

    def snapshot(self, idea_id: str) -> IdeaTruthSnapshot:
        """生成不可变快照（深拷贝 projection；源数据后续修改不影响 snapshot）。"""
        projection = self.project(idea_id)
        from aipd_os.state.db import now_iso
        return IdeaTruthSnapshot(
            idea_id=idea_id, tenant_id=self._tenant, project_id=self._project,
            generated_at=now_iso(), projection=copy.deepcopy(projection),
        )


__all__ = ["IdeaTruthProjection", "IdeaTruthSnapshot"]
