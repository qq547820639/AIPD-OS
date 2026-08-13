"""物理验证结果回写：产品真相（facts）、证据登记（evidence）、风险登记、发布门禁。

诚实护栏：只有当物理验证数据真实存在（有记录）时才回写为已通过/已失败；
物理证据缺失时保持 ``HOLD``（写入 pending 事实 + 未完成风险 + HOLD 门禁），
绝不把未验证项标记为通过。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aipd_os.state.db import AIPDStateDB

DEFAULT_TENANT = "default"


class PhysicalWriteback:
    """把阶段/门禁物理验证结果写回状态库。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = DEFAULT_TENANT) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def write_stage(
        self,
        project_id: str,
        stage: str,
        analysis: dict[str, Any] | None,
        evidence_files: list[str | Path] | None = None,
        gate: str | None = None,
    ) -> dict[str, Any]:
        """把某物理验证阶段的结果写回。

        :param analysis: ``analyze_stage`` 的输出；为 None 或 total==0 表示
            无物理数据，结果保持 HOLD。
        :returns: ``{"written": [...], "hold": [...], "risk_id": ..., "gate_result": ...}``
        """
        written: list[Any] = []
        hold: list[Any] = []
        risk_id: str | None = None
        analysis = analysis or {}
        total = int(analysis.get("total", 0) or 0)

        if total == 0:
            # 无物理证据 -> 保持 HOLD（不虚构）
            fact_id = self.db.add_fact(
                self.tenant_id,
                project_id,
                key=f"verification.{stage}",
                value={
                    "status": "HOLD",
                    "passed_flag": False,
                    "reason": f"缺少 {stage} 阶段物理验证数据，物理结果保持 HOLD（未验证）",
                },
                status="P",
                source="physical_writeback",
            )
            hold.append(fact_id)
            risk_id = self.db.add_risk(
                self.tenant_id,
                project_id,
                title=f"物理验证 {stage} 尚未完成（HOLD）",
                probability="unknown",
                impact="medium",
                mitigation="补齐物理验证数据并回写后再判定",
                status="open",
                trigger=f"{stage} 阶段缺少物理验证数据",
            )
            return {
                "written": written,
                "hold": hold,
                "risk_id": risk_id,
                "gate_result": None,
            }

        passed = int(analysis.get("failed", 0) or 0) == 0
        fact_id = self.db.add_fact(
            self.tenant_id,
            project_id,
            key=f"verification.{stage}",
            value={
                "status": "verified" if passed else "failed",
                "passed_flag": passed,
                "total": total,
                "passed": analysis.get("passed", 0),
                "failed": analysis.get("failed", 0),
            },
            status="V" if passed else "S",
            source="physical_writeback",
        )
        written.append(fact_id)

        # 证据登记：把阶段报告文件写为 evidence 并关联到事实
        for f in (evidence_files or []):
            p = Path(f)
            eid = self.db.add_evidence(
                self.tenant_id,
                project_id,
                kind="stage_report",
                title=p.name,
                url=str(p),
                summary=f"{stage} 阶段物理验证数据",
                metadata={"stage": stage},
            )
            self.db.link_evidence(self.tenant_id, project_id, fact_id, eid)
            written.append(eid)

        if not passed:
            # 失败项 -> 风险登记
            risk_id = self.db.add_risk(
                self.tenant_id,
                project_id,
                title=f"{stage} 阶段存在 {analysis.get('failed', 0)} 项失败",
                probability="high" if passed is False else "medium",
                impact="medium",
                mitigation="按纠偏行动（corrective action）处理并复测",
                status="open",
                trigger=f"{stage} 阶段失败项未清零",
            )
            written.append(risk_id)

        gate_result: str | None = None
        if gate:
            gate_result = "PASS" if passed else "FAIL"
            self.db.add_gate(
                self.tenant_id,
                project_id,
                gate=gate,
                result=gate_result,
                checks={"stage": stage, "failed": analysis.get("failed", 0)},
                approved_by="supply-chain",
            )
            written.append(f"gate:{gate}:{gate_result}")

        return {"written": written, "hold": hold, "risk_id": risk_id, "gate_result": gate_result}

    def write_release_gate(
        self,
        project_id: str,
        gate: str,
        physical_ok: bool,
        note: str = "",
    ) -> dict[str, Any]:
        """写回发布门禁的物理验证判定。

        :param physical_ok: 是否有充分的已通过物理证据；False/缺失 -> HOLD。
        """
        result: str
        result = "PASS" if physical_ok else "HOLD"
        self.db.add_gate(
            self.tenant_id,
            project_id,
            gate=gate,
            result=result,
            checks={"physical_ok": physical_ok, "note": note},
            approved_by="supply-chain",
        )
        return {"gate": gate, "result": result, "physical_ok": physical_ok}


__all__ = ["PhysicalWriteback", "DEFAULT_TENANT"]
