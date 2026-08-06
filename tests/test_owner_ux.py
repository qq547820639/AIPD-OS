"""P2 所有者 UX 测试。

覆盖：意图解析（同义词/上下文指代/多条件/单一澄清问题）、影响分析与受影响制品、
成本/时间估算、可撤销预览、批准门禁、自动返工+自动验收+摘要更新、
统一 Owner Dashboard（默认隐藏内部标识/--json 分离/紧凑移动端/进度事件/可取消/
失败恢复/制品差异/成本耗时/why decide）、首次使用引导、以及窄终端/无障碍输出。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.checkpoint import CheckpointManager
from aipd_os.experience.intent_engine import parse_intent
from aipd_os.experience.impact_analysis import analyze_impact, estimate_cost_time
from aipd_os.experience.operations import (
    ProgressTracker, run_operation_loop, revert_operation)
from aipd_os.experience.owner_dashboard import (
    build_dashboard, render_dashboard_text, render_dashboard_json)
from aipd_os.experience.onboarding import (
    onboard, reset_project, provider_config_status, list_examples)


@pytest.fixture
def db(tmp_path):
    return AIPDStateDB(str(tmp_path / "state.db"), encryption_key="test-key")


@pytest.fixture
def project(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "智能护理设备", "打造一款可量产的智能护理设备")
    db.add_fact("default", "p1", "latency", 42, "V", unit="ms", source="bench")
    # 交付物：手册（in_progress）/ CAD（done）/ BOM（planned）
    manual = db.add_deliverable("default", "p1", "manual", path="/out/manual.png",
                                status="in_progress", version="1.0")
    cad = db.add_deliverable("default", "p1", "cad", path="/out/lower.step",
                             status="done", version="1.2")
    bom = db.add_deliverable("default", "p1", "bom", path="/out/bom.xlsx",
                             status="planned", version="0.9")
    CheckpointManager(db).save_checkpoint("p1", {"phase": "design"},
                                          summary={"note": "外壳选型已完成"})
    # 一条待审决策
    did = db.propose_decision("default", "p1", "量产合作方式",
                              "推荐与 A 代工厂合作",
                              ["与 A 代工厂合作", "与 B 代工厂合作", "自建产线"],
                              trigger="irreversible_investment")
    return {"project_id": "p1", "manual": manual, "cad": cad, "bom": bom, "did": did}


# ---------------------------------------------------------- 意图解析：同义词
def test_intent_synonyms(project, db):
    assert parse_intent("没问题", db, "p1").kind == "approve"
    assert parse_intent("同意", db, "p1").kind == "approve"
    assert parse_intent("预算下调10%", db, "p1").kind == "cost_reduction"
    assert parse_intent("价格再降15%", db, "p1").kind == "cost_reduction"
    assert parse_intent("要更硬朗风", db, "p1").kind == "style_constraint"
    assert parse_intent("去医疗化", db, "p1").kind == "style_constraint"
    # 选择方案同义词
    choose = parse_intent("选方案B", db, "p1")
    assert choose.kind == "choose"
    assert choose.params["option_letter"] == "B"


# ---------------------------------------------------------- 意图解析：上下文指代
def test_intent_context_reference(project, db):
    # 无上下文时"批准"仍解析到待审决策
    base = parse_intent("批准", db, "p1")
    assert base.kind == "approve"
    assert base.params.get("decision_id") == project["did"]
    # 上下文指代：代词解析到最近决策
    ctx = {"last_decision_id": project["did"]}
    resolved = parse_intent("批准它", db, "p1", context=ctx)
    assert resolved.target == project["did"]
    # 空上下文时 target 解析为待审决策自身
    assert parse_intent("批准这个方案", db, "p1").target == project["did"]


# ---------------------------------------------------------- 意图解析：多条件
def test_intent_multi_condition(project, db):
    intent = parse_intent("成本降低20%并且外观更工业化", db, "p1")
    assert intent.kind == "cost_reduction"
    kinds = [c["kind"] for c in intent.constraints]
    assert "cost_reduction" in kinds
    assert "style_constraint" in kinds
    # 影响合并
    assert any("20%" in i for i in intent.propagated_impact)
    assert any("工业化" in i for i in intent.propagated_impact)


# ---------------------------------------------------------- 意图解析：单一澄清问题
def test_intent_one_clarifying_question(project, db):
    # 提到成本但没给百分比 → 只问一个最关键问题
    intent = parse_intent("成本降低一些", db, "p1")
    assert intent.ambiguous is True
    assert intent.clarifying_question is not None
    # 只能有一个澄清问题（不是多个）
    assert intent.clarifying_question.count("？") <= 1
    assert "多少" in intent.clarifying_question


# ---------------------------------------------------------- 意图解析：纠错
def test_intent_correction(project, db):
    instr = parse_intent("撤回上次操作", db, "p1")
    assert instr.kind == "revert"
    assert instr.correction is True
    assert parse_intent("撤销", db, "p1").kind == "revert"


# ---------------------------------------------------------- 影响分析与受影响制品
def test_impact_analysis_affected_artifacts(project, db):
    intent = parse_intent("成本降低20%", db, "p1")
    impact = analyze_impact(db, "p1", intent)
    # 成本削减影响所有未发布制品（manual/cad/bom 均未 released/archived）
    ids = {a["deliverable_id"] for a in impact["affected_artifacts"]}
    assert project["manual"] in ids
    assert project["cad"] in ids
    assert project["bom"] in ids
    assert impact["affected_count"] == 3
    assert impact["reversible"] is True


def test_impact_style_constraint_only_manual(project, db):
    intent = parse_intent("外观更工业化", db, "p1")
    impact = analyze_impact(db, "p1", intent)
    ids = {a["deliverable_id"] for a in impact["affected_artifacts"]}
    # 只有手册类受影响
    assert project["manual"] in ids
    assert project["cad"] not in ids
    assert project["bom"] not in ids


# ---------------------------------------------------------- 成本/时间估算
def test_cost_time_estimate(project, db):
    intent = parse_intent("成本降低20%", db, "p1")
    est = estimate_cost_time(intent, [{}] * 3)
    assert est["affected_count"] == 3
    assert est["estimated_minutes"] > 0
    assert est["estimated_cost"] > 0
    assert "预计影响" in est["human_estimate"]
    assert "估算成本" in est["human_estimate"]


# ---------------------------------------------------------- 可撤销预览
def test_reversible_preview(project, db):
    intent = parse_intent("成本降低20%", db, "p1")
    impact = analyze_impact(db, "p1", intent)
    preview = impact["preview"]
    assert "before" in preview and "after" in preview
    assert len(preview["before"]) == len(preview["after"]) == 3
    # 返工后进入推进态
    assert all(b["status"] == "in_progress" for b in preview["after"])


# ---------------------------------------------------------- 批准门禁
def test_approval_gate_stops_before_mutation(project, db):
    intent = parse_intent("批准", db, "p1")  # approve → requires_approval
    result = run_operation_loop(db, "p1", intent, approved=False)
    assert result["status"] == "needs_approval"
    assert result["why_need_decide"]
    # 未批准不改变任何状态：决策仍开放
    open_ids = [d["decision_id"] for d in db.list_open_decisions("default", "p1")]
    assert project["did"] in open_ids


def test_approval_gate_executes_when_approved(project, db):
    intent = parse_intent("批准", db, "p1")
    result = run_operation_loop(db, "p1", intent, approved=True)
    assert result["status"] == "done"
    # 决策已被解析
    open_ids = [d["decision_id"] for d in db.list_open_decisions("default", "p1")]
    assert project["did"] not in open_ids


# ---------------------------------------------------------- 自动返工 + 自动验收 + 摘要更新
def test_auto_rework_acceptance_summary(project, db):
    intent = parse_intent("成本降低20%", db, "p1")
    result = run_operation_loop(db, "p1", intent, approved=True)
    assert result["status"] == "done"
    assert result["rework"]["count"] == 3
    assert result["acceptance"]["count"] == 3
    # 受影响制品最终验收为 done，版本递增
    by_id = {d["deliverable_id"]: d for d in db.list_deliverables("default", "p1")}
    assert by_id[project["manual"]]["status"] == "done"
    assert by_id[project["manual"]]["version"] == "1.1"  # 1.0 → 1.1
    # 成本约束写入事实
    keys = [f["key"] for f in db.list_facts("default", "p1")]
    assert "cost_target" in keys
    # 摘要更新：检查点已保存
    assert CheckpointManager(db).restore_latest("p1") is not None


# ---------------------------------------------------------- 可取消
def test_operation_cancellable(project, db):
    intent = parse_intent("成本降低20%", db, "p1")
    result = run_operation_loop(db, "p1", intent, approved=True,
                                should_cancel=(lambda: True))
    assert result["status"] == "cancelled"


# ---------------------------------------------------------- 进度事件
def test_progress_events(project, db):
    tracker = ProgressTracker()
    run_operation_loop(db, "p1", parse_intent("成本降低20%", db, "p1"),
                       approved=True, progress=tracker)
    steps = [e["step"] for e in tracker.events()]
    assert "intent" in steps
    assert "impact" in steps
    assert "rework" in steps
    assert "acceptance" in steps
    assert "summary" in steps
    assert "done" in steps


# ---------------------------------------------------------- 失败恢复（回滚）
def test_failure_recovery_revert(project, db):
    # 先执行一个可撤销操作
    run_operation_loop(db, "p1", parse_intent("成本降低20%", db, "p1"), approved=True)
    by_id = {d["deliverable_id"]: d for d in db.list_deliverables("default", "p1")}
    assert by_id[project["manual"]]["status"] == "done"
    # 回滚
    r = revert_operation(db, "p1")
    assert r["reverted"]
    by_id = {d["deliverable_id"]: d for d in db.list_deliverables("default", "p1")}
    assert by_id[project["manual"]]["status"] == "in_progress"
    assert by_id[project["manual"]]["version"] == "1.0"  # 回退到 1.1 - 1


# ---------------------------------------------------------- Owner Dashboard
def test_dashboard_default_hides_internals(project, db):
    view = build_dashboard(db, "p1")
    text = render_dashboard_text(view)
    body = text.split("<details>")[0]
    # 关键内部标识不出现在正文
    assert view["details"]["decision_id"] not in body
    assert "S0" not in body
    assert "C4" not in body
    assert project["manual"] not in body  # DEL 前缀制品 id 不泄漏


def test_dashboard_json_separated(project, db):
    view = build_dashboard(db, "p1")
    raw = render_dashboard_json(view)
    parsed = json.loads(raw)
    # JSON 含内部细节（与 human 分离），且含 10 个所有者区块键
    assert "details" in parsed
    assert parsed["details"]["project_id"] == "p1"
    for key in ("current_goal", "executing", "done", "missing", "top_risk",
                "external_waits", "single_decision", "next_milestone",
                "recent_changes", "reversible_operations"):
        assert key in parsed


def test_dashboard_compact_mobile(project, db):
    view = build_dashboard(db, "p1")
    full = render_dashboard_text(view)
    compact = render_dashboard_text(view, compact=True)
    # 紧凑输出明显更短，且每区块单行
    assert len(compact) < len(full)
    assert "目标：" in compact
    assert "执行中：" in compact
    # 紧凑模式无双栏装饰/大标题
    assert "AIPD 项目总览" not in compact


def test_dashboard_why_need_decide(project, db):
    view = build_dashboard(db, "p1")
    dec = view["single_decision"]
    assert dec is not None
    assert dec["why_need_decide"]
    text = render_dashboard_text(view)
    assert "为什么需要您决定" in text


def test_dashboard_artifact_diff_and_cost(project, db):
    # 先执行一次返工，产生制品版本差异
    run_operation_loop(db, "p1", parse_intent("成本降低20%", db, "p1"), approved=True)
    view = build_dashboard(db, "p1")
    text = render_dashboard_text(view)
    assert "制品版本 / 参数差异" in text
    # 成本 / 耗时变化体现在影响分析中
    intent = parse_intent("成本降低20%", db, "p1")
    impact = analyze_impact(db, "p1", intent)
    assert impact["estimated_cost"] > 0
    assert impact["estimated_minutes"] > 0


def test_dashboard_reversible_operations_listed(project, db):
    run_operation_loop(db, "p1", parse_intent("成本降低20%", db, "p1"), approved=True)
    view = build_dashboard(db, "p1")
    assert len(view["reversible_operations"]) >= 1
    text = render_dashboard_text(view)
    assert "可撤销操作" in text


# ---------------------------------------------------------- 窄终端/无障碍
def test_narrow_terminal_output(project, db):
    view = build_dashboard(db, "p1")
    compact = render_dashboard_text(view, compact=True)
    for line in compact.splitlines():
        # 窄终端友好：每行简短，无长 emoji 装饰标题
        assert len(line) < 200
    # 无障碍：关键信息为文本而非纯图形
    assert "健康：🟢" in compact or "健康：" in compact


# ---------------------------------------------------------- 首次使用引导
def test_onboarding_one_sentence_to_first_result(db):
    r = onboard(db, "做一款轻量外骨骼", project_id="exo")
    assert r["project_id"] == "exo"
    db.get_project("default", "exo")  # 项目已创建
    # 立即产出第一份有价值的结果
    assert r["produced"]
    labels = [p["label"] for p in r["produced"]]
    assert any("项目目标" in l for l in labels)
    assert any("需求规格" in l for l in labels)
    assert any("待决定" in l for l in labels)
    # 第一份结果 = owner dashboard
    assert "executing" in r["first_result"]
    # 能力与外部配置
    assert r["capabilities"]
    assert r["external_config_needed"]
    for c in r["external_config_needed"]:
        assert c["status"] == "external_dependency"
    # 示例项目
    assert isinstance(r["examples"], list)
    # 恢复 / 重置提示
    assert "reset" in r and "recover" in r


def test_onboarding_provider_guide(db):
    caps = provider_config_status()
    names = {c["name"] for c in caps}
    assert {"Image 图像生成", "Model 模型", "CAD 内核", "Mail 邮件"} <= names
    # 未配置时如实标 external_dependency
    for c in caps:
        assert c["status"] in ("ok", "external_dependency")
        assert c["guide"]


def test_onboarding_reset(db):
    r = onboard(db, "做一款轻量外骨骼", project_id="exo")
    reset = reset_project(db, "exo")
    assert reset["reset"] is True
    assert reset["backup"]
    with pytest.raises(Exception):
        db.get_project("default", "exo")  # 已被删除


def test_onboarding_examples(db):
    examples = list_examples()
    assert isinstance(examples, list)
    for e in examples:
        assert "name" in e and "goal" in e