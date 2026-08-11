"""黄金端到端回归测试：连续附件产品手册执行链。

覆盖：
- scripts/manual_chain.py plan-batches + run-batch（3 批，>=10 页）
- layout.renderer 真实中文 A4 光栅化（每页 2480x3508）
- visual_audit.audit_batch 语义审计（仅视觉维度标记 requiring_vision，绝不假通过）
- compose_pdf / build_zip 合成 PDF 与 ZIP
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from aipd_os.layout.composer import build_zip, compose_pdf
from aipd_os.layout.renderer import A4_PX, render_page
from aipd_os.visual_audit import VisualAuditor

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "scripts" / "manual_chain.py"

FACTS = {
    "params": {
        "peak_torque": 120,
        "weight": 8.5,
        "battery_capacity": 60,
        "max_speed": 20,
        "input_voltage": 48,
        "max_load": 100,
    },
    # CS7：缺省字段改为显式 TBD；测试必须提供完整事实，避免 cmf/curve 页
    # 被完整性审计判定为待重建。
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


def cli(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        [sys.executable, str(MANUAL), *args],
        capture_output=True, text=True, cwd=str(cwd),
    )
    assert r.returncode == 0, f"cli failed: {args}\nstdout={r.stdout}\nstderr={r.stderr}"
    return r.stdout


def sha(path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def load_state(state: Path) -> dict:
    return json.loads(Path(state).read_text(encoding="utf-8"))


def batch_output_pages(state: Path, batch_id: str) -> list:
    for br in load_state(state)["batch_runs"]:
        if br["batch_id"] == batch_id:
            return br["output_pages"]
    raise AssertionError(f"batch {batch_id} not found")


def test_manual_chain_golden_e2e(tmp_path) -> None:
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")

    # 1) init + plan
    cli(tmp_path, "init", "--state", str(state), "--project-id", "golden-exo",
        "--minimum-pages", "10")
    cli(tmp_path, "plan-batches", "--state", str(state), "--minimum-pages", "10")
    plan = load_state(state)["batch_plan"]
    assert len(plan) >= 10
    batches = sorted({e["batch_id"] for e in plan}, key=lambda s: int(s.split("_")[1]))
    assert len(batches) >= 2

    # 2) 逐批执行 + 渲染（用真实排版器光栅化中文页面）
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    rendered: list[tuple[str, Path]] = []
    for i, bid in enumerate(batches):
        bid_pages = [e["page_id"] for e in plan if e["batch_id"] == bid]
        cmd = [
            "run-batch", "--state", str(state), "--batch-id", bid,
            "--prompt", f"golden {bid} 批次提示词", "--theory-version", "T3.1",
            "--truth-version", "PT-2", "--anchors", ",".join(bid_pages),
            "--output-dir", str(tmp_path / f"out_{bid}"), "--facts", str(facts_json),
        ]
        if i > 0:
            cmd += ["--prior-batch", str(pages_dir)]
        cli(tmp_path, *cmd)
        # 渲染本批页面
        for op in batch_output_pages(state, bid):
            out = pages_dir / f"{op['page_id']}.png"
            render_page(op["defn"], str(out))
            rendered.append((op["page_id"], out))

    st = load_state(state)
    brs = st["batch_runs"]
    assert len(brs) == len(batches)

    # 3) 批次上下文完整连续性
    for br in brs:
        for key in ["batch_id", "prompt", "theory_version", "truth_version",
                    "anchors", "prior_batch", "visual_bible", "prohibited",
                    "output_pages"]:
            assert key in br, f"batch context missing {key}"
    assert brs[0]["prior_batch"] is None  # 首批无前批
    assert all(b["prior_batch"] for b in brs[1:])  # 后续批携带前批附件

    # 4) 每页 PNG 为 300dpi A4
    assert len(rendered) >= 10
    for _, png in rendered:
        assert Image.open(png).size == A4_PX

    # 5) PDF + ZIP 产物
    pdf = compose_pdf([str(p) for _, p in rendered], str(tmp_path / "manual.pdf"))
    zipf = build_zip([str(p) for _, p in rendered], str(tmp_path / "manual.zip"))
    assert Path(pdf).exists() and Path(pdf).stat().st_size > 0
    assert Path(zipf).exists() and Path(zipf).stat().st_size > 0
    import zipfile
    with zipfile.ZipFile(zipf) as z:
        names = z.namelist()
        assert any(n.endswith(".pdf") for n in names)
        assert sum(1 for n in names if n.endswith(".png")) >= 10

    # 6) 语义审计：仅视觉维度 requiring_vision，其余必须通过（全新手册无前哈希）
    audit = VisualAuditor().audit_batch(st, str(pages_dir), facts=FACTS, prior_hashes=[])
    assert audit["page_count"] >= 10
    # 无视觉后端时顶层必须 HOLD/not_verified，绝不 passed（诚实门）
    assert audit["passed"] is False, audit
    assert audit["status"] == "hold"
    assert audit["batch_continuity_ok"] is True
    assert audit["narrative_continuity_monotonic"] is True
    assert audit["rebuild_plan"] == []  # 无可重建的责任页
    for page in audit["pages"]:
        assert page["non_vision_passed"] is True, page["dimensions"]
        assert page["pixel_statistics_only"] is False
        # 无视觉后端：人物/CMF 必须标记 requiring_vision，绝不假通过
        assert set(page["vision_pending"]) <= {"character_consistency", "cmf_consistency"}
        for dim in ["character_consistency", "cmf_consistency"]:
            d = page["dimensions"][dim]
            assert d["passed"] is False
            assert d["requiring_vision"] is True

    # 7) 回归护栏：旧图哈希复用必须被禁止（forbidden 维度）
    first_png = rendered[0][1]
    first_defn = next(
        op["defn"] for br in st["batch_runs"] for op in br["output_pages"]
        if op["page_id"] == rendered[0][0]
    )
    redo = VisualAuditor()
    redo.prior_hashes = [sha(str(first_png))]
    reuse_res = redo.audit_page(first_defn, str(first_png), facts=FACTS)
    assert reuse_res["dimensions"]["forbidden"]["passed"] is False
    assert "reused previous page hash" in reuse_res["dimensions"]["forbidden"]["violations"]
