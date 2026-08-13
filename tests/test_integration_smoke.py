"""P0-1 真实集成冒烟测试（CI `integration` job）。

这些测试标记为 ``@pytest.mark.integration``，全部驱动真实端到端流程
（不依赖外部凭据，确定性可回归）：

1. 手工链批次：``scripts/manual_chain.py`` init + plan-batches + run-batch + 真实排版光栅化 +
  视觉审计；
2. 评估报告：``evals_runner`` 运行确定性夹具并生成版本化报告；
3. 研究链：``research`` ingest_attachment + run_research_chain（离线契约获取）；
4. 恢复往返：``state.backup`` 创建备份并恢复到新库，验证数据一致。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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
    }
}


@pytest.mark.integration
def test_integration_manual_chain_batch(tmp_path) -> None:
    """驱动真实手工链：计划 + 执行批次 + 渲染 A4 中文页 + 语义审计。"""
    state = tmp_path / "state.json"
    facts_json = tmp_path / "facts.json"
    facts_json.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")

    def cli(*args: str) -> None:
        r = subprocess.run([sys.executable, str(MANUAL), *args],
                           capture_output=True, text=True, cwd=str(tmp_path))
        assert r.returncode == 0, f"manual_chain failed: {args}\n{r.stdout}\n{r.stderr}"

    cli("init", "--state", str(state), "--project-id", "smoke-exo", "--minimum-pages", "10")
    cli("plan-batches", "--state", str(state), "--minimum-pages", "10")

    plan = json.loads(state.read_text(encoding="utf-8"))["batch_plan"]
    assert len(plan) >= 10
    batches = sorted({e["batch_id"] for e in plan}, key=lambda s: int(s.split("_")[1]))
    assert len(batches) >= 2

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    rendered = []
    for bid in batches:
        cli(
            "run-batch", "--state", str(state), "--batch-id", bid,
            "--prompt", f"smoke {bid}", "--theory-version", "T3.1",
            "--truth-version", "PT-2", "--anchors", "auto",
            "--output-dir", str(tmp_path / f"out_{bid}"), "--facts", str(facts_json),
        )
        d = json.loads(state.read_text(encoding="utf-8"))
        br = next(x for x in d["batch_runs"] if x["batch_id"] == bid)
        for op in br.get("output_pages", []):
            if not op.get("defn"):
                continue
            out = pages_dir / f"{op['page_id']}.png"
            render_page(op["defn"], str(out))
            rendered.append(out)

    assert len(rendered) >= 10
    from PIL import Image
    for png in rendered:
        assert Image.open(png).size == A4_PX

    # 视觉审计：无视觉后端时顶层必须 HOLD/not_verified，绝不 passed
    st = json.loads(state.read_text(encoding="utf-8"))
    audit = VisualAuditor().audit_batch(st, str(pages_dir), facts=FACTS, prior_hashes=[])
    assert audit["page_count"] >= 10
    assert audit["passed"] is False
    assert audit["status"] == "hold"


@pytest.mark.integration
def test_integration_eval_report(tmp_path) -> None:
    """运行确定性夹具评估并生成版本化报告（真实 end-to-end 报告流）。"""
    from aipd_os.evals_runner.registry import load_cases
    from aipd_os.evals_runner.runner import EvalRunner
    from aipd_os.evals_runner.versioning import build_report, load_baseline, save_eval_report

    cases = load_cases(str(ROOT / "evals" / "evals.json"))
    assert cases, "evals.json 必须包含至少一个 case"
    runner = EvalRunner(workdir=str(tmp_path))
    results = runner.run(cases)
    assert len(results) == len(cases)

    report = build_report(results, version="5.5.0")
    assert report["version"] == "5.5.0"
    out = save_eval_report(report, str(tmp_path / "reports"), version="5.5.0")
    loaded = load_baseline(str(tmp_path / "reports"), version="5.5.0")
    assert loaded["version"] == "5.5.0"
    assert len(loaded["results"]) >= 1


@pytest.mark.integration
def test_integration_research_chain(tmp_path) -> None:
    """驱动研究链：附件摄入净化 + 契约获取回写（离线确定性）。"""
    from aipd_os.research import (
        STATUS_VERIFIED,
        Citation,
        ContractFetcher,
        ResearchFinding,
        ingest_attachment,
        run_research_chain,
    )
    from aipd_os.state.db import AIPDStateDB

    # 摄入净化
    txt = tmp_path / "ref.txt"
    txt.write_text("ISO-9001:2015 规定质量体系要求。", encoding="utf-8")
    meta = ingest_attachment(txt)
    assert meta["sanitized_size"] >= 0 and meta["sha256"]

    # 状态库回写
    db = AIPDStateDB(str(tmp_path / "research.db"))
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    finding = ResearchFinding(
        key="quality_system", value="ISO-9001:2015 要求",
        status=STATUS_VERIFIED, confidence=0.9,
        citations=[Citation(source="official_standard", title="ISO-9001:2015",
                            confidence=0.9, kind="standard")],
    )
    out = run_research_chain(db, "default", "p1", finding, fetcher=ContractFetcher())
    assert out["fact_id"] is not None
    fact = db.get_fact("default", "p1", out["fact_id"])
    assert fact["key"] == "quality_system"


@pytest.mark.integration
def test_integration_recovery_roundtrip(tmp_path) -> None:
    """恢复往返：创建项目与事实 -> 备份 -> 继续写入 -> 恢复到新库验证一致。"""
    from aipd_os.state.backup import BackupManager
    from aipd_os.state.db import AIPDStateDB

    db_path = tmp_path / "state.db"
    db = AIPDStateDB(str(db_path))
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    db.add_fact("default", "p1", "latency", 42, "V")

    bm = BackupManager(str(db_path), backup_dir=str(tmp_path / "backups"))
    backup = bm.create_backup(str(db_path))
    assert backup

    # 备份后继续写入
    db.add_fact("default", "p1", "accuracy", 0.9, "V")
    assert len(db.list_facts("default", "p1")) == 2

    # 恢复到新路径 -> 回到备份时状态
    restored = str(tmp_path / "restored.db")
    bm.restore_backup(backup, restored)
    rdb = AIPDStateDB(restored)
    assert len(rdb.list_facts("default", "p1")) == 1
    assert rdb.list_facts("default", "p1")[0]["key"] == "latency"
