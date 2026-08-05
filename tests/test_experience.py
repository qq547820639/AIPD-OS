"""体验层（对话层）测试。

覆盖：项目摘要、单一决策卡片、会话恢复摘要、制品预览、自然语言指令解析与应用。
"""
from __future__ import annotations

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.checkpoint import CheckpointManager
from aipd_os.experience.project_summary import build_project_summary
from aipd_os.experience.decision_card import build_decision_card
from aipd_os.experience.resume_summary import build_resume_summary
from aipd_os.experience.artifact_preview import artifact_preview
from aipd_os.experience.instructions import apply_instruction, parse_instruction
from aipd_os.experience.views import OwnerView


@pytest.fixture
def db(tmp_path):
    return AIPDStateDB(str(tmp_path / "state.db"), encryption_key="test-key")


@pytest.fixture
def seeded(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "智能护理设备", "打造一款可量产的智能护理设备")

    # 事实
    db.add_fact("default", "p1", "latency", 42, "V", unit="ms", source="bench")
    db.add_fact("default", "p1", "material", "ABS", "C", source="design")

    # 一条已解决的决策
    d1 = db.propose_decision("default", "p1", "外壳材质选择",
                             "推荐使用工业级 ABS", ["工业级 ABS", "医用级 PC", "铝合金"],
                             trigger="product_architecture_fork")
    db.resolve_decision("default", "p1", d1, "工业级 ABS", "已批准")

    # 风险
    db.add_risk("default", "p1", "供应商交期不稳", probability="medium",
                impact="high", mitigation="引入备选供应商")

    # 交付物：手册 / CAD / BOM
    manual = db.add_deliverable("default", "p1", "manual", path="/out/manual_pg1.png",
                                status="in_progress", version="1.0",
                                metadata={"thumbnail": "/out/thumb_pg1.png"})
    cad = db.add_deliverable("default", "p1", "cad", path="/out/lower_case.step",
                             status="done", version="1.2")
    bom = db.add_deliverable("default", "p1", "bom", path="/out/bom_v1.xlsx",
                             status="planned", version="0.9")

    # 保存检查点（在新增事实之前）
    CheckpointManager(db).save_checkpoint(
        "p1", {"phase": "design"}, summary={"note": "外壳选型已完成"})

    # 检查点之后新增的事实（应被恢复摘要列出）
    db.add_fact("default", "p1", "weight", 12.5, "S", unit="kg")

    # 一条新的待审决策
    d2 = db.propose_decision("default", "p1", "量产合作方式",
                             "推荐与 A 代工厂合作",
                             ["与 A 代工厂合作", "与 B 代工厂合作", "自建产线"],
                             trigger="irreversible_investment")

    return {
        "did": d2,
        "manual": manual,
        "cad": cad,
        "bom": bom,
    }


# ---------------------------------------------------------------- 项目摘要
def test_project_summary_is_natural_language(seeded, db):
    summary = build_project_summary(db, "p1")
    for field in ("current_work", "completed", "gaps", "top_risk", "next_milestone"):
        value = summary[field]
        assert isinstance(value, str) and value.strip(), field
        # 顶层字段不得出现内部代号 S0 / C4
        assert "S0" not in value, field
        assert "C4" not in value, field
    # 内部代号只放在 details 里
    assert summary["details"]["project_id"] == "p1"
    assert summary["details"]["counts"]["open_decisions"] == 1


# ---------------------------------------------------------------- 决策卡片
def test_decision_card_single_highest_priority(seeded, db):
    card = build_decision_card(db, "p1")
    assert card is not None
    assert card["decision_id"] == seeded["did"]
    assert 2 <= len(card["options"]) <= 4
    assert card["after_approval"]
    # 每个选项都有成本/性能/时间/安全影响
    for opt in card["options"]:
        imp = card["impacts"][opt]
        for dim in ("cost", "performance", "time", "safety"):
            assert dim in imp


def test_decision_card_none_when_no_open_decision(db):
    db.ensure_default_tenant()
    db.init_project("default", "empty", "空项目", "无决策")
    assert build_decision_card(db, "empty") is None


# ---------------------------------------------------------------- 恢复摘要
def test_resume_summary_lists_new_facts_not_resolved(seeded, db):
    resume = build_resume_summary(db, "p1")
    # 检查点之后新增的事实被列出
    assert "weight" in resume["new_fact_keys"]
    # 已解决的决策不被重新追问
    ask_ids = [d["decision_id"] for d in resume["decisions_to_ask"]]
    assert seeded["did"] in ask_ids
    # 更强的断言：质料决策（已解决）不出现在待追问列表
    assert all(d["topic"] != "外壳材质选择" for d in resume["decisions_to_ask"])


# ---------------------------------------------------------------- 制品预览
def test_artifact_preview_seeded_structure(seeded, db):
    preview = artifact_preview(db, "p1")
    assert isinstance(preview["manual_pages"], list)
    assert isinstance(preview["cad_versions"], list)
    assert isinstance(preview["bom_diffs"], list)
    assert isinstance(preview["parameter_diffs"], list)
    # 手册页带路径与缩略图
    manual = preview["manual_pages"][0]
    assert manual["deliverable_id"] == seeded["manual"]
    assert manual["path"] == "/out/manual_pg1.png"
    assert manual["thumbnail"] == "/out/thumb_pg1.png"


# ---------------------------------------------------------------- 指令解析
def test_parse_instruction_kinds(seeded, db):
    assert parse_instruction("批准", db, "p1").kind == "approve"
    cost = parse_instruction("成本再降低20%", db, "p1")
    assert cost.kind == "cost_reduction"
    assert cost.params["percentage"] == 20.0
    ind = parse_instruction("外观更工业化", db, "p1")
    assert ind.kind == "style_constraint"
    assert ind.params["style"] == "industrial"
    med = parse_instruction("不要医疗风", db, "p1")
    assert med.kind == "style_constraint"
    assert med.params["avoid"] == "medical"


def test_apply_cost_reduction_marks_deliverables_stale(seeded, db):
    instr = parse_instruction("成本再降低20%", db, "p1")
    result = apply_instruction(instr, db, "p1")
    assert result["applied"] is True
    assert result["recorded_fact_id"] is not None
    # 成本目标被记录为约束事实
    keys = [f["key"] for f in db.list_facts("default", "p1")]
    assert "cost_target" in keys
    # 受影响交付物被标记为过期
    by_id = {d["deliverable_id"]: d for d in db.list_deliverables("default", "p1")}
    assert by_id[seeded["manual"]]["status"] == "stale"
    assert seeded["manual"] in result["stale_deliverables"]


# ---------------------------------------------------------------- 顶层视图
def test_owner_view_composition(seeded, db):
    view = OwnerView(db).owner_update("p1")
    assert set(view) == {"project_summary", "decision_card",
                         "resume_summary", "artifact_preview"}
    assert view["decision_card"] is not None
    md = OwnerView(db).to_markdown(view)
    assert "产品所有者视图" in md
    assert "<details>" in md
    # 决策卡片在正文出现、内部代号在 details 中
    assert view["decision_card"]["topic"] in md
