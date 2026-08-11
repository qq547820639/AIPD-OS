"""Idea Truth projection（v5.8 Commit 14 / v5.8.1 Commit 3-4）。

Idea Truth 是 **projection**（查询组合），不是第二个 Store，不创建新 DB/表。

:class:`IdeaTruthProjection.project(idea_id)` 返回 auditable projection
（v5.8.1 Commit 4 review-aware）：
  - supported_claims：有 **reviewed** supports/partially_supports 的命题；
  - known：DEPRECATED 兼容字段（= supported_claims，只含 reviewed supports）；
  - assumption：epistemic_status=A 的命题（待验证假设）；
  - evidence：有 **reviewed** relation 的命题；
  - contradicted：有 **reviewed** contradicts 证据的命题；
  - unknown：epistemic_status=U 的命题；
  - gaps：无 **reviewed** relation 的命题（需检索/评审）；
  - pending_relations / rejected_relations：单独列出（不混入支持/反驳计数）；
  - assessments：per-claim ClaimAssessment（v1，版本化）；
  - maturity：IdeaMaturity.evaluate 判定（I0/I1/I2，保守规则）。

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
        """返回 Idea 的 Truth projection（review-aware，Commit 4/12）。

        supported_claims/known/evidence/contradicted 只统计 reviewed relation；
        pending/rejected 单独列出；gaps = 无 reviewed relation 的命题。

        v5.8.1 Commit 12：计数/分类复用 ``EvidenceGraph.compute_idea_evidence``
        （与 get_idea_evidence_summary 同口径，避免两处语义漂移）。
        """
        idea = self._ideas.get(self._tenant, self._project, idea_id)
        data = self._graph.compute_idea_evidence(self._tenant, self._project,
                                                 idea_id)
        c = data["counts"]
        maturity = IdeaMaturity.evaluate(idea, self._graph).value
        return {
            "idea_id": idea_id,
            "tenant_id": self._tenant,
            "project_id": self._project,
            "title": idea.title,
            "lifecycle_status": idea.lifecycle_status,
            "maturity": maturity,
            # Commit 4 review-aware fields
            "supported_claims": data["supported_claims"],
            # DEPRECATED 兼容字段：只含 reviewed supports（= supported_claims）
            "known": list(data["supported_claims"]),
            "assumption": data["assumption"],
            "evidence": data["evidence"],
            "contradicted": data["contradicted"],
            "unknown": data["unknown"],
            "gaps": data["gaps"],
            "pending_relations": data["pending_relations"],
            "rejected_relations": data["rejected_relations"],
            "assessments": data["assessments"],
            "counts": c,
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
