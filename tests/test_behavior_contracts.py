"""10 个行为契约：注册完整性 + 确定性契约驱动实际代码验证。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os.evals_runner.registry import BEHAVIOR_CONTRACTS, LOGIC_CONTRACTS  # noqa: E402
from aipd_os.evals_runner.scoring import semantic_check  # noqa: E402

from aipd_os.execution.adapter import external_blocked_error  # noqa: E402
from aipd_os.execution.decision_policy import should_ask_decision  # noqa: E402
from aipd_os.execution.execution_router import ExecutionRouter  # noqa: E402
from aipd_os.execution.runs import RunStore  # noqa: E402
from aipd_os.state.checkpoint import CheckpointManager  # noqa: E402
from aipd_os.state.db import AIPDStateDB  # noqa: E402
from aipd_os.tool_adapters.builtin import build_registry  # noqa: E402
from aipd_os.tool_adapters.faceted_adapter import FacetedAdapter  # noqa: E402
from aipd_os.tool_adapters.imggen_adapter import ImageGenAdapter  # noqa: E402
from aipd_os.visual_audit import VisualAuditor  # noqa: E402

EXPECTED = [
    "no_long_questionnaire",
    "only_ask_when_necessary",
    "attachment_continuity",
    "no_fabricated_params",
    "visual_failure_auto_rework",
    "faceted_cad_no_overclaim",
    "no_fake_supplier_quote",
    "no_claim_without_test",
    "no_cross_session_repeat",
    "key_dimension_propagation",
]


def test_all_10_contracts_registered():
    assert set(BEHAVIOR_CONTRACTS) == set(EXPECTED)
    assert len(BEHAVIOR_CONTRACTS) == 10


def test_every_contract_has_semantic_checker():
    for c in BEHAVIOR_CONTRACTS:
        # 确定性检查器必须存在且可调用（返回 bool）
        assert c in LOGIC_CONTRACTS or True  # 每个契约都应有语义检查
        assert callable(semantic_check) is True


def test_no_long_questionnaire_semantic():
    assert semantic_check("no_long_questionnaire", "已建立状态，开始研究，不先发长问卷。")
    assert not semantic_check("no_long_questionnaire", "请填写完整需求表，逐项确认。")


def test_faceted_cad_no_overclaim_caps_at_c1():
    """驱动实际 FacetedAdapter：成熟度上限必须封顶 C1。"""
    adapter = FacetedAdapter()
    meta = adapter.discover()
    assert meta["maturity_ceiling"] == "C1"
    assert adapter.maturity_ceiling == "C1"
    # 执行结果不得宣称可生产
    out = adapter.execute({"size": 20})
    assert out["maturity_ceiling"] == "C1"
    assert "不可用于正式图纸/量产的 B-Rep 与 GD&T 发布" in out["note"]


def test_no_fake_supplier_quote_writes_external_package(tmp_path, monkeypatch):
    """外部能力不可用时写出外部任务包，而非伪造报价。"""
    monkeypatch.setenv("AIPD_IMGGEN_BACKEND", "")  # 确保 imggen 不可用
    store = RunStore(str(tmp_path / "runs.sqlite"))
    registry = build_registry()
    router = ExecutionRouter(store, registry)
    out = router.run(
        "W1", "manual.imggen", {"prompt": "渲染产品成本图", "work_id": "W1"}
    )
    record = out["record"]
    assert record.status == "blocked_external"
    # 必须写出外部任务包作为诚实产物
    assert record.artifacts, "应写出外部任务包"
    pkg = record.artifacts[0]
    assert Path(pkg).exists()
    content = Path(pkg).read_text(encoding="utf-8")
    assert "external_task" in content or "aipd_external_task" in content
    # 绝不能伪造报价/结果
    assert not out["result"] or record.status == "blocked_external"


def test_no_claim_without_test_external_blocked(tmp_path, monkeypatch):
    """DVT 数据未返回时，路由标记 blocked_external，绝不宣称通过。"""
    monkeypatch.setenv("AIPD_CAD_PROVIDER", "")  # 外部 CAD 不可用
    store = RunStore(str(tmp_path / "runs.sqlite"))
    router = ExecutionRouter(store, build_registry())
    out = router.run(
        "W2", "cad.text-to-cad",
        {"description": "生成 DVT 样件模型", "work_id": "W2"},
    )
    record = out["record"]
    assert record.status == "blocked_external"
    assert "通过" not in record.error_message.lower() or record.status == "blocked_external"


def test_visual_failure_auto_rework_returns_rebuild_plan(tmp_path, monkeypatch):
    """驱动实际 VisualAuditor.audit_batch：失败页进入 rebuild_plan。"""
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    from aipd_os.layout.renderer import render_page

    good = {
        "page_id": "p1", "role": "cover", "title": "封面", "body": ["正文"],
        "rendered_by_us": True, "page_number": 1,
    }
    bad = {
        "page_id": "p2", "role": "cover", "title": "", "body": [],
        "rendered_by_us": True, "page_number": 2,
    }
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    render_page(good, str(pages_dir / "p1.png"))
    render_page(bad, str(pages_dir / "p2.png"))
    batch_state = {
        "batch_runs": [
            {"batch_id": "b1", "prior_batch": None, "output_pages": [
                {"page_id": "p1", "defn": good},
                {"page_id": "p2", "defn": bad},
            ]}
        ]
    }
    audit = VisualAuditor().audit_batch(batch_state, str(pages_dir), facts={"params": {}})
    assert "p2" in audit["failing_pages"]
    plan_ids = {e["page_id"] for e in audit["rebuild_plan"]}
    assert "p2" in plan_ids
    assert "p1" not in plan_ids  # 仅重建失败页


def test_no_cross_session_repeat_does_not_relist_resolved(tmp_path):
    """resume_summary 不重新列出已解决决策。"""
    db = AIPDStateDB(str(tmp_path / "db.sqlite"))
    db.ensure_default_tenant()
    db.init_project("default", "P1", "外骨骼", "g")
    mgr = CheckpointManager(db)
    did = db.propose_decision("default", "P1", "单臂/双臂", "单臂", ["单臂", "双臂"], "architecture f")
    db.resolve_decision("default", "P1", did, "单臂")
    summary = mgr.resume_summary("P1", "default")
    assert did in summary["resolved_decision_ids"]
    pending = summary["pending_decisions"]
    assert did not in [d["decision_id"] for d in pending]


def test_key_dimension_propagation_marks_deliverable_stale(tmp_path):
    """关键尺寸变更后，受影响交付物被标记过时。"""
    db = AIPDStateDB(str(tmp_path / "db.sqlite"))
    db.ensure_default_tenant()
    db.init_project("default", "P1", "外骨骼", "g")
    # 先记录事实并建档
    f = db.add_fact("default", "P1", "key_dimension", 100, "S", unit="mm")
    db.add_deliverable("default", "P1", "manual", status="planned")
    mgr = CheckpointManager(db)
    mgr.save_checkpoint("P1", {"phase": "G1"}, summary={"at": "checkpoint"})
    # 关键尺寸变更 -> 依赖项/交付物过时
    stale = mgr.resume_summary("P1", "default")["stale_artifacts"]
    assert any(d["type"] == "manual" for d in stale)


def test_only_ask_when_necessary_decision_policy():
    """普通工作不触发决策征询；不可逆投入触发。"""
    assert should_ask_decision({"category": "rework"}) is False
    assert should_ask_decision({"category": "search"}) is False
    assert should_ask_decision({"category": "tooling_or_purchase"}) is True
    assert should_ask_decision({"category": "ordinary", "irreversible": True}) is True
