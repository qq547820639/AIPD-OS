"""P0-3 回归测试：手册发布门禁的视觉语义审计接线。

断言视觉后端缺失时门禁不能通过：
- 无视觉后端 → 顶层 HOLD/not_verified，绝不 passed（release_decision=HOLD，退出码 1）。
- 非视觉维度失败（参数与事实不符）→ 硬失败 FAIL（退出码 2）。
- 配置视觉后端且全部非视觉维度通过 → PASS（退出码 0）。
- 提供黄金清单 → golden_gap 注入门禁报告；缺字段时仍 HOLD。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from aipd_os.layout.renderer import A4_PX, render_page

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "scripts" / "manual_chain.py"
GATE = ROOT / "scripts" / "manual_chain_gate.py"
GOLDEN_MANIFEST = ROOT / "evals" / "wbx1_golden_reference_manifest.json"

FACTS = {
    "params": {
        "peak_torque": 120,
        "weight": 8.5,
        "battery_capacity": 60,
        "max_speed": 20,
        "input_voltage": 48,
        "max_load": 100,
    },
    # CS7：缺省字段改为显式 TBD；提供完整事实以保证 cmf/curve 页完整性审计通过。
    "cmf": {"color": "工程橙", "material": "铝合金6061", "finish": "阳极氧化"},
    "curve": [{"label": "效率曲线", "points": [[0, 10], [1, 20], [2, 18], [3, 30]]},
              {"label": "输出扭矩", "points": [[0, 5], [1, 12], [2, 20], [3, 28]]}],
    "characters": [{"appearance": "工程人员形象"}],
    "principle": ["系统通过电机驱动谐波减速器，将助力传递至关节。"],
    "modules": [{"name": "动力模块", "desc": "高密度无刷电机与谐波减速器"}],
    "scenes": [{"title": "物流搬运", "desc": "仓库装卸环节缓解腰部劳损"}],
    "qa": [{"q": "电池续航多久", "a": "约 4-6 小时"}],
    "closure": [{"text": "本产品致力于降低重体力作业风险。"}],
}


def _run(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


def _build_manual(tmp_path) -> tuple[Path, Path, Path]:
    """init + plan-batches + 运行首批并渲染页面，返回 (state, pages_dir, facts_json)。"""
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")

    r = _run(MANUAL, tmp_path, "init", "--state", str(state),
             "--project-id", "gate-exo", "--minimum-pages", "10")
    assert r.returncode == 0, r.stderr
    r = _run(MANUAL, tmp_path, "plan-batches", "--state", str(state), "--minimum-pages", "10")
    assert r.returncode == 0, r.stderr

    plan = json.loads(state.read_text(encoding="utf-8"))["batch_plan"]
    batches = sorted({e["batch_id"] for e in plan}, key=lambda s: int(s.split("_")[1]))
    assert batches

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    r = _run(
        MANUAL, tmp_path, "run-batch", "--state", str(state),
        "--batch-id", batches[0], "--prompt", f"gate {batches[0]}",
        "--theory-version", "T3.1", "--truth-version", "PT-2",
        "--anchors", "auto", "--output-dir", str(tmp_path / "out"),
        "--facts", str(facts_json),
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

    st = json.loads(state.read_text(encoding="utf-8"))
    br = next(x for x in st["batch_runs"] if x["batch_id"] == batches[0])
    for op in br.get("output_pages", []):
        if not op.get("defn"):
            continue
        render_page(op["defn"], str(pages_dir / f"{op['page_id']}.png"))
    return state, pages_dir, facts_json


def test_gate_holds_without_vision_backend(tmp_path) -> None:
    """无视觉后端时门禁必须 HOLD，绝不 passed。"""
    state, pages_dir, facts_json = _build_manual(tmp_path)
    r = _run(GATE, tmp_path, "--state", str(state), "--pages-dir", str(pages_dir),
             "--facts", str(facts_json))
    assert r.returncode == 1, r.stdout  # HOLD
    report = json.loads(r.stdout)
    assert report["release_decision"] == "HOLD"
    assert report["passed"] is False
    assert report["visual_audit"]["status"] == "hold"
    assert report["visual_audit"]["passed"] is False
    assert any("requiring_vision" in h for h in report["hold_reasons"])


def test_gate_fails_on_nonvision_failure(tmp_path) -> None:
    """参数与事实不符的非视觉失败 → 硬失败 FAIL，绝不放行。"""
    state, pages_dir, facts_json = _build_manual(tmp_path)
    # 破坏 parameter_table 参数与事实不符
    d = json.loads(state.read_text(encoding="utf-8"))
    for br in d["batch_runs"]:
        for op in br["output_pages"]:
            if op.get("page_id") == "parameter_table":
                for row in op["defn"].get("param_table", []):
                    row["value"] = 999  # 与 facts 中 peak_torque=120 不符
    state.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    r = _run(GATE, tmp_path, "--state", str(state), "--pages-dir", str(pages_dir),
             "--facts", str(facts_json))
    assert r.returncode == 2, r.stdout  # FAIL
    report = json.loads(r.stdout)
    assert report["release_decision"] == "FAIL"
    assert "parameter_table" in report["visual_audit"]["failing_pages"]


def test_gate_passes_with_vision_backend(tmp_path) -> None:
    """配置视觉后端且全部非视觉维度通过 → PASS。"""
    state, pages_dir, facts_json = _build_manual(tmp_path)
    r = _run(GATE, tmp_path, "--state", str(state), "--pages-dir", str(pages_dir),
             "--facts", str(facts_json), "--vision-backend", "mock")
    assert r.returncode == 0, r.stdout  # PASS
    report = json.loads(r.stdout)
    assert report["release_decision"] == "PASS"
    assert report["passed"] is True
    assert report["visual_audit"]["passed"] is True


def test_gate_includes_golden_gap(tmp_path) -> None:
    """提供黄金清单时注入 golden_gap；无视觉后端仍 HOLD，且清单缺字段计入原因。"""
    state, pages_dir, facts_json = _build_manual(tmp_path)
    r = _run(GATE, tmp_path, "--state", str(state), "--pages-dir", str(pages_dir),
             "--facts", str(facts_json), "--golden", str(GOLDEN_MANIFEST))
    assert r.returncode == 1, r.stdout  # HOLD（无视觉后端）
    report = json.loads(r.stdout)
    assert report["golden_gap"] is not None
    assert "golden_gap" in report["hold_reasons"] or any(
        "golden" in h for h in report["hold_reasons"])
    assert report["visual_audit"]["status"] == "hold"


def test_gate_structure_only_backward_compat(tmp_path) -> None:
    """未提供 pages_dir 时仅做结构门（向后兼容 selftest_v3），不执行视觉审计。"""
    state = tmp_path / "state.json"
    r = _run(MANUAL, tmp_path, "init", "--state", str(state),
             "--project-id", "compat", "--minimum-pages", "2")
    assert r.returncode == 0, r.stderr
    d = json.loads(state.read_text(encoding="utf-8"))
    d["prompts"] = [{"id": "P1", "purpose": "plan", "instruction": "plan",
                     "inputs": [], "outputs": ["plan"], "status": "completed"}]
    d["pages"] = [{"page_id": "p1", "role": "cover", "path": "/tmp/x.png",
                   "batch_id": "B1"}]
    d["anchors"] = ["p1"]
    d["phase"] = "anchors_locked"
    state.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    r = _run(GATE, tmp_path, "--state", str(state))
    report = json.loads(r.stdout)
    assert report["visual_audit"] is None
    assert report["golden_gap"] is None
    assert report["release_decision"] in {"PASS", "HOLD", "FAIL"}