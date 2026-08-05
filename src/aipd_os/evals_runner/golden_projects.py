"""黄金端到端项目夹具运行器。

对每个黄金项目：
1. 在临时 DB 上建 tenant/project；
2. 生成 >= minimum_pages 页的产品手册页面定义，用真实排版器光栅化为 A4 PNG；
3. 按批次执行（首批无前批，后续批携带前批），用 VisualAuditor 做语义审计；
4. 用假图像适配器（诚实写出外部任务包，绝不伪造成图）经 ExecutionRouter 驱动；
5. 合成 PDF/ZIP，产出一份黄金报告，断言端到端流程完成。

覆盖契约：attachment_continuity（批次连续性）、visual_failure_auto_rework（审计）、
no_fake_supplier_quote / no_claim_without_test（外部任务包诚实性）。
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.runs import RunStore
from aipd_os.layout.composer import build_zip, compose_pdf
from aipd_os.layout.renderer import render_page
from aipd_os.state.db import AIPDStateDB
from aipd_os.tool_adapters.builtin import build_registry
from aipd_os.visual_audit import VisualAuditor


DEFAULT_ROLES = [
    "cover", "principle", "parameter_table", "module", "user_scene",
    "cmf", "curve", "qa", "closure",
]


class FakeImageAdapter(ToolAdapter):
    """黄金项目用的假图像适配器：诚实写出外部任务包，绝不伪造成图。"""

    provider = "eval-fake-imggen"

    def capability_id(self) -> str:
        return "manual.imggen.eval-fake"

    def discover(self) -> Dict[str, Any]:
        return {
            "id": self.capability_id(),
            "name": "Eval Fake ImageGen",
            "provider": self.provider,
            "version": "1.0",
            "maturity_ceiling": None,
            "available": False,  # 诚实：外部成图能力不可用，走 blocked_external
        }

    def validate_input(self, input: Dict[str, Any]) -> List[str]:
        if not input.get("prompt"):
            return ["'prompt' 必填"]
        return []

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        raise external_blocked_error(
            self.capability_id(),
            "黄金夹具：图像需外部文生图后端生成。请人工/外部按提示词成图并回填。\n"
            f"提示词: {input.get('prompt', '')}",
            work_id=input.get("work_id"),
        )


@dataclass
class GoldenProject:
    """黄金项目夹具。"""

    id: str
    name: str
    goal: str
    brief: str
    facts: Dict[str, Any] = field(default_factory=dict)
    minimum_pages: int = 10
    roles: List[str] = field(default_factory=lambda: list(DEFAULT_ROLES))
    expected: List[str] = field(
        default_factory=lambda: [
            "manual_pages_produced",
            "batch_continuity_holds",
            "no_fabricated_external_evidence",
            "pdf_zip_produced",
        ]
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "brief": self.brief,
            "facts": self.facts,
            "minimum_pages": self.minimum_pages,
            "roles": self.roles,
            "expected": self.expected,
        }


def load_golden_project(project_dir: str) -> GoldenProject:
    """从夹具目录加载 project.json。"""
    path = Path(project_dir) / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return GoldenProject(
        id=data["id"],
        name=data.get("name", data["id"]),
        goal=data.get("goal", ""),
        brief=data.get("brief", ""),
        facts=data.get("facts", {}),
        minimum_pages=int(data.get("minimum_pages", 10)),
        roles=data.get("roles") or list(DEFAULT_ROLES),
        expected=data.get("expected", []),
    )


def _param_table(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for key, val in (facts.get("params", {}) or {}).items():
        rows.append({"param": key, "label": key, "value": val, "unit": ""})
    return rows


def build_manual_pages(project: GoldenProject, minimum_pages: int) -> List[Dict[str, Any]]:
    """生成 >= minimum_pages 页的手册页面定义。"""
    pages: List[Dict[str, Any]] = []
    idx = 0
    while len(pages) < minimum_pages:
        role = project.roles[idx % len(project.roles)]
        num = len(pages) + 1
        pid = f"gp_{role}_{num:03d}"
        defn: Dict[str, Any] = {
            "page_id": pid,
            "role": role,
            "title": f"{project.name} - {role}",
            "body": [f"{project.brief}（第{num}页 {role} 内容，由黄金夹具生成）"],
            "caption": f"{role} 配图说明",
            "rendered_by_us": True,
            "footer": project.name,
        }
        if role == "parameter_table":
            defn["param_table"] = _param_table(project.facts)
        if role == "curve":
            defn["curve"] = [
                {"label": "扭矩", "points": [[0, 0], [1, 20], [2, 40], [3, 44]]}
            ]
        if role == "qa":
            defn["body"] = [
                "常见问题：安全使用与维护。所有测试结论均标注待外部验证，不虚构通过。"
            ]
        pages.append(defn)
        idx += 1
    # 保证页码唯一且单调
    for i, defn in enumerate(pages, 1):
        defn["page_number"] = i
    return pages


def _split_batches(pages: List[Dict[str, Any]], per_batch: int = 5) -> List[Dict[str, Any]]:
    batches: List[Dict[str, Any]] = []
    for i in range(0, len(pages), per_batch):
        chunk = pages[i : i + per_batch]
        batches.append(
            {
                "batch_id": f"batch_{(i // per_batch) + 1}",
                "prior_batch": None if i == 0 else f"batch_{(i // per_batch)}",
                "output_pages": [{"page_id": d["page_id"], "defn": d} for d in chunk],
            }
        )
    return batches


def run_golden_project(
    project: GoldenProject,
    workdir: str,
    minimum_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """运行一个黄金项目，返回黄金报告。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    min_pages = minimum_pages or project.minimum_pages

    # 1) 临时 DB + 项目
    db = AIPDStateDB(str(workdir / "state.sqlite"))
    db.ensure_default_tenant()
    db.init_project("default", project.id, project.name, project.goal)

    # 2) 生成并渲染手册页面
    pages = build_manual_pages(project, min_pages)
    pages_dir = workdir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    rendered: List[str] = []
    for defn in pages:
        png = render_page(defn, str(pages_dir / f"{defn['page_id']}.png"))
        rendered.append(png)

    # 3) 批次 + 审计
    batches = _split_batches(pages)
    batch_state = {"batch_runs": batches}
    audit = VisualAuditor().audit_batch(batch_state, str(pages_dir), facts=project.facts)

    # 4) 假图像适配器经真实路由驱动（诚实外部任务包）
    store = RunStore(str(workdir / "runs.sqlite"))
    registry = build_registry()
    registry.register(FakeImageAdapter())
    router = ExecutionRouter(store, registry)
    ext = router.run(
        project.id,
        "manual.imggen.eval-fake",
        {"prompt": f"{project.name} 封面渲染", "work_id": project.id},
    )
    ext_record = ext.get("record")
    ext_status = getattr(ext_record, "status", None)
    external_pkgs = list(getattr(ext_record, "artifacts", []) or [])
    if not external_pkgs:
        result = ext.get("result") or {}
        pkg = result.get("external_task_package")
        if pkg:
            external_pkgs = [pkg]

    # 5) PDF/ZIP
    pdf = compose_pdf(rendered, str(workdir / "manual.pdf"))
    zipf = build_zip(rendered, str(workdir / "manual.zip"))

    # 6) 断言与报告
    checks: List[Dict[str, Any]] = [
        {"name": "manual_pages_produced", "ok": len(rendered) >= min_pages},
        {"name": "batch_continuity_holds", "ok": bool(audit.get("batch_continuity_ok"))},
        {
            "name": "no_fabricated_external_evidence",
            "ok": ext_status == "blocked_external" and bool(external_pkgs),
        },
        {"name": "pdf_zip_produced", "ok": Path(pdf).exists() and Path(zipf).exists()},
    ]
    passed = all(c["ok"] for c in checks)
    return {
        "project_id": project.id,
        "project_name": project.name,
        "model_version": "golden-deterministic",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manual_pages": len(rendered),
        "batches": len(batches),
        "batch_continuity_ok": audit.get("batch_continuity_ok"),
        "failing_pages": audit.get("failing_pages"),
        "external_status": ext_status,
        "external_task_packages": external_pkgs,
        "pdf": pdf,
        "zip": zipf,
        "checks": checks,
        "passed": passed,
    }


def run_golden_dir(
    project_dir: str,
    workdir: str,
    minimum_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """便捷：从夹具目录运行黄金项目。"""
    project = load_golden_project(project_dir)
    return run_golden_project(project, workdir, minimum_pages=minimum_pages)


__all__ = [
    "GoldenProject",
    "FakeImageAdapter",
    "load_golden_project",
    "build_manual_pages",
    "run_golden_project",
    "run_golden_dir",
]
