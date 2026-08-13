"""legacy 一键命令（已废弃，保留向后兼容，均映射到新命令）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any, cast

from aipd_os.logging_utils import log_event

# 注意：_run_pytest / _run_evals_cli / _build_release_impl / _import_module 通过
# _helpers 模块属性在调用时解析（而非直接绑名），使 tests/test_cli_deprecation.py
# 对 _helpers 的 monkeypatch 能真实作用于本文件的命令。
from . import _helpers
from ._helpers import (
    DEFAULT_TENANT,
    _emit,
    _is_legacy,
    _logger,
    _ns,
    _repo_root,
    _resolve_project,
)


# --------------------------------------------------------------------------
# init-project
# --------------------------------------------------------------------------
def cmd_init_project(args: argparse.Namespace) -> int:
    warnings.warn("'aipd init-project' 已废弃，请使用 'aipd init'", DeprecationWarning, stacklevel=2)  # noqa: E501
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    db.ensure_default_tenant(DEFAULT_TENANT)
    db.init_project(DEFAULT_TENANT, args.project_id, args.name, args.goal)
    from aipd_os.supervisor import Supervisor as _Sup
    sup = _Sup(args.db, tenant_id=DEFAULT_TENANT,
               project_id=args.project_id, state_db=db)
    sup.init_lifecycle()
    log_event(_logger, "init_project", project_id=args.project_id, db=args.db)
    result = {"command": "init-project", "ok": True, "project_id": args.project_id,
              "name": args.name, "goal": args.goal, "db": args.db}

    def prose():
        print(f"项目已初始化：{args.name}（{args.project_id}）")
        print(f"数据库：{args.db}")
        print(f"目标：{args.goal}")
        print("监督器生命周期已就绪，可执行 `aipd run` / `aipd status`。")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# restore-project
# --------------------------------------------------------------------------
def cmd_restore_project(args: argparse.Namespace) -> int:
    warnings.warn("'aipd restore-project' 已废弃，请使用 'aipd resume'", DeprecationWarning, stacklevel=2)  # noqa: E501
    from aipd_os.state.backup import BackupManager

    db_path = Path(args.db)
    result: dict[str, Any] = {"command": "restore-project", "ok": True, "db": args.db,
                              "restored_from": None, "migrated": False}
    restored = None
    migrated_project = None
    migrated_counts = None
    if args.backup:
        manager = BackupManager(str(db_path))
        restored = manager.restore_backup(args.backup, db_path=str(db_path))
        log_event(_logger, "restore_project", source="backup", restored=restored)
        result["restored_from"] = restored
    elif _is_legacy(db_path):
        v4 = _helpers._import_module("v4_to_v5", subdir="migrations")
        tmp = db_path.with_suffix(".migrating.db")
        stats = v4.migrate_legacy(str(db_path), str(tmp), tenant_id=DEFAULT_TENANT)
        os.replace(str(tmp), str(db_path))
        log_event(_logger, "restore_project", source="v4_migration", stats=stats.get("counts", {}))
        result["migrated"] = True
        result["project_id"] = stats["project_id"]
        result["counts"] = stats.get("counts", {})
        migrated_project = stats["project_id"]
        migrated_counts = stats.get("counts", {})

    def prose():
        if args.backup:
            print(f"已从备份恢复到：{restored}")
        elif result["migrated"]:
            print(f"已将 v4 旧库迁移到 v5 多租户库：{db_path}")
            print(f"项目：{migrated_project}；事实 {migrated_counts.get('facts', 0)} 条，"
                  f"决策 {migrated_counts.get('decisions', 0)} 条。")
        else:
            print(f"数据库 {db_path} 已是 v5 格式，无需迁移/恢复。")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# run-supervisor
# --------------------------------------------------------------------------
def cmd_run_supervisor(args: argparse.Namespace) -> int:
    warnings.warn("'aipd run-supervisor' 已废弃，请使用 'aipd run'", DeprecationWarning, stacklevel=2)  # noqa: E501
    from aipd_os.experience.decision_card import build_decision_card
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = getattr(args, "project", None) or _resolve_project(db)
    from aipd_os.supervisor import Supervisor as _Sup
    sup = _Sup(args.db, tenant_id=DEFAULT_TENANT, project_id=pid,
               state_db=db)
    results = sup.run_supervisor(steps=args.steps or 1, project_id=pid)
    completed = [r for r in results if r.get("action") == "complete"]
    decisions = [r for r in results if r.get("action") == "decision"]
    rework = [r for r in results if r.get("action") == "internal_rework"]
    external = [r for r in results if r.get("action") == "blocked_external"]

    result = {"command": "run-supervisor", "ok": True, "project_id": pid,
              "steps_run": len(results), "decisions": len(decisions),
              "completed": len(completed), "external_blocked": len(external),
              "rework": len(rework), "stopped_reason": "steps_exhausted"}

    def prose():
        print(f"本轮执行 {len(results)} 个步骤：完成 {len(completed)} 项，决策 {len(decisions)} 项，"  # noqa: E501
              f"内部返工 {len(rework)} 项，外部阻塞 {len(external)} 项。")
        for r in completed:
            print(f"  [完成] {r.get('work_id')}  状态={r.get('status')}")
        for r in rework:
            print(f"  [返工] {r.get('work_id')}  原因={r.get('reason') or r.get('status')}")
        for r in external:
            print(f"  [外部阻塞] {r.get('work_id')}")
        for r in decisions:
            did = r["decision"]["decision_id"]
            card = cast(dict[str, Any], build_decision_card(db, pid, decision_id=did, tenant_id=DEFAULT_TENANT))  # noqa: E501
            print(f"  [决策] {card['decision_id']}：{card['topic']}")
            print(f"    AI 建议：{card['ai_recommendation']}")
            print(f"    可选方案：{'、'.join(card['options'])}")
            print(f"    批准后系统将自动执行：{card['after_approval']}")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# project-summary
# --------------------------------------------------------------------------
def cmd_project_summary(args: argparse.Namespace) -> int:
    warnings.warn("'aipd project-summary' 已废弃，请使用 'aipd status'", DeprecationWarning, stacklevel=2)  # noqa: E501
    from aipd_os.experience.views import OwnerView
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    view = OwnerView(db, tenant_id=DEFAULT_TENANT)
    pid = _resolve_project(db)
    if args.markdown:
        text = view.to_markdown(project_id=pid)
        result = {"command": "project-summary", "ok": True, "project_id": pid,
                  "markdown": text}
        _emit(args, result, lambda: print(text))
        return 0

    v = view.owner_update(pid)
    ps = v["project_summary"]
    result = {"command": "project-summary", "ok": True, "project_id": pid,
              "summary": v}

    def prose():
        print("项目摘要")
        print(f"· 当前工作：{ps['current_work']}")
        print(f"· 已完成：{ps['completed']}")
        print(f"· 还缺什么：{ps['gaps']}")
        print(f"· 最大风险：{ps['top_risk']}")
        print(f"· 下一个里程碑：{ps['next_milestone']}")
        card = v.get("decision_card")
        if card:
            print(f"· 待您决策：{card['topic']}（{card['decision_id']}）")
            print(f"  AI 建议：{card['ai_recommendation']}")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# submit-decision
# --------------------------------------------------------------------------
def cmd_submit_decision(args: argparse.Namespace) -> int:
    warnings.warn("'aipd submit-decision' 已废弃，请使用 'aipd decide'", DeprecationWarning, stacklevel=2)  # noqa: E501
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db)
    db.resolve_decision(DEFAULT_TENANT, pid, args.decision_id, args.choice, args.comment)
    dec = next((d for d in db.list_decisions(DEFAULT_TENANT, pid)
                if d["decision_id"] == args.decision_id), None)
    log_event(_logger, "submit_decision", decision_id=args.decision_id, choice=args.choice)
    result = {"command": "submit-decision", "ok": True, "project_id": pid,
              "decision_id": args.decision_id, "choice": args.choice}

    def prose():
        print(f"决策 {args.decision_id} 已裁定：{args.choice}。")
        if dec:
            print(f"系统将按所选方案自动推进「{dec['topic']}」，并同步更新相关产物与检查点。")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# run-manual-chain
# --------------------------------------------------------------------------
def _db_handle(db_path: str):
    from aipd_os.state.db import AIPDStateDB
    return AIPDStateDB(db_path)


def cmd_run_manual_chain(args: argparse.Namespace) -> int:
    warnings.warn("'aipd run-manual-chain' 已废弃，请使用 'aipd manual generate'", DeprecationWarning, stacklevel=2)  # noqa: E501
    mc = _helpers._import_module("manual_chain")
    state = str(Path(args.db).with_suffix(".manual.json"))

    if not Path(state).exists():
        mc.cmd_init(_ns(cmd="init", state=state,
                        project_id=_resolve_project(_db_handle(args.db)),
                        minimum_pages=10))
    data = json.loads(Path(state).read_text(encoding="utf-8"))
    if not data.get("batch_plan"):
        mc.cmd_plan_batches(_ns(cmd="plan-batches", state=state, minimum_pages=10))

    mc.cmd_run_batch(_ns(
        cmd="run-batch", state=state, batch_id=args.batch_id, prompt=args.prompt,
        theory_version="auto", truth_version="auto", anchors="",
        prior_batch=None, output_dir=args.output_dir, visual_bible=None,
        prohibited=None, facts=None,
    ))
    data = json.loads(Path(state).read_text(encoding="utf-8"))
    run = data["batch_runs"][-1]
    result = {"command": "run-manual-chain", "ok": True, "batch_id": args.batch_id,
              "completed": run["completed"], "external_pending": run["external_pending"],
              "external_task_dir": run.get("external_task_dir")}

    def prose():
        print("手工批次执行结果：")
        print(f"· 完成页：{run['completed']}")
        print(f"· 外部待办：{run['external_pending']}")
        if run["external_pending"]:
            print(f"· 外部任务包目录：{run['external_task_dir']}")
            print("（图像后端不可用，未生成页面；如需出图请配置后端或消费外部任务包。）")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# run-cad-chain
# --------------------------------------------------------------------------
def cmd_run_cad_chain(args: argparse.Namespace) -> int:
    warnings.warn("'aipd run-cad-chain' 已废弃，请使用 'aipd cad build'", DeprecationWarning, stacklevel=2)  # noqa: E501
    cmg = _helpers._import_module("cad_maturity_gate")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    # 复用 _cad_gate_summary（与 cad preflight/build 同源），不再内联复制
    # 累计成熟度计算（此前两处实现漂移）。
    s = _helpers._cad_gate_summary(cmg, manifest, args.target)
    reached = s["reached_level"]
    runtime_ceiling = s["runtime_ceiling"]
    faceted_capped = s["faceted_brep_capped"]
    target_passed = s["target_passed"]

    result = {"command": "run-cad-chain", "ok": target_passed,
              "reached_level": reached, "runtime_ceiling": runtime_ceiling,
              "faceted_brep_capped": faceted_capped,
              "target_level": args.target, "target_passed": target_passed}

    def prose():
        print(f"CAD 成熟度：达到 {reached}（运行时上限 {runtime_ceiling}）")
        if faceted_capped:
            print("faceted_brep 运行时成熟度封顶于 C1。")
        print(f"目标 {args.target} 通过：{'是' if target_passed else '否'}")
    _emit(args, result, prose)
    return 0 if target_passed else 4


# --------------------------------------------------------------------------
# run-tests
# --------------------------------------------------------------------------
def cmd_run_tests(args: argparse.Namespace) -> int:
    warnings.warn("'aipd run-tests' 已废弃，请使用 'aipd test'", DeprecationWarning, stacklevel=2)  # noqa: E501
    rc = _helpers._run_pytest(_repo_root())
    result = {"command": "run-tests", "ok": rc == 0, "exit_code": rc}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# --------------------------------------------------------------------------
# run-evals
# --------------------------------------------------------------------------
def cmd_run_evals(args: argparse.Namespace) -> int:
    warnings.warn("'aipd run-evals' 已废弃，请使用 'aipd eval'", DeprecationWarning, stacklevel=2)  # noqa: E501
    out = args.out or str(_repo_root() / "evals_out")
    rc = _helpers._run_evals_cli(_repo_root(), args.evals, args.provider, out,
                        args.threshold, args.baseline)
    result = {"command": "run-evals", "ok": rc == 0, "out": out}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# --------------------------------------------------------------------------
# build-release
# --------------------------------------------------------------------------
def cmd_build_release(args: argparse.Namespace) -> int:
    warnings.warn("'aipd build-release' 已废弃，请使用 'aipd package'", DeprecationWarning, stacklevel=2)  # noqa: E501
    rc = _helpers._build_release_impl(args)
    result = {"command": "build-release", "ok": rc == 0, "version": args.version}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# --------------------------------------------------------------------------
# run  —— 运行监督器直到真实决策或步骤耗尽
# --------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    known = {p["project_id"] for p in db.list_projects(DEFAULT_TENANT)}
    if args.project not in known:
        print(f"错误：项目 {args.project} 不存在。", file=sys.stderr)
        return 1

    sup = _helpers._import_module("aipd_supervisor").Supervisor(
        args.db, tenant_id=DEFAULT_TENANT, project_id=args.project, state_db=db)
    max_steps = args.steps or (100 if args.until_decision else 1)
    results: list[dict[str, Any]] = []
    steps_run = 0
    stopped_reason: str | None = None
    for _ in range(max_steps):
        step_results = sup.run_supervisor(steps=1, project_id=args.project)
        results.extend(step_results)
        steps_run += len(step_results)
        if not step_results:
            stopped_reason = "no_work"
            break
        if any(r.get("action") == "decision" for r in step_results):
            stopped_reason = "decision"
            break
    if stopped_reason is None:
        stopped_reason = "steps_exhausted"

    decisions = [r for r in results if r.get("action") == "decision"]
    completed = [r for r in results if r.get("action") == "complete"]
    external_blocked = [r for r in results if r.get("action") == "blocked_external"]
    rework = [r for r in results if r.get("action") == "internal_rework"]

    summary = {
        "project_id": args.project,
        "steps_run": steps_run,
        "decisions": len(decisions),
        "completed": len(completed),
        "external_blocked": len(external_blocked),
        "rework": len(rework),
        "stopped_reason": stopped_reason,
    }
    if getattr(args, "json", False):
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    print(f"项目 {args.project}：本轮运行 {steps_run} 个步骤"
          f"（完成 {len(completed)}，决策 {len(decisions)}，外部阻塞 {len(external_blocked)}，"
          f"内部返工 {len(rework)}）。")
    print(f"停止原因：{stopped_reason}")
    for r in completed:
        print(f"  [完成] {r.get('work_id')}  状态={r.get('status')}")
    for r in decisions:
        print(f"  [决策] {r.get('work_id')}  {r['decision']['decision_id']}")
    for r in rework:
        print(f"  [返工] {r.get('work_id')}  原因={r.get('reason') or r.get('status')}")
    for r in external_blocked:
        print(f"  [外部阻塞] {r.get('work_id')}")
    return 0


__all__ = [
    "cmd_init_project",
    "cmd_restore_project",
    "cmd_run_supervisor",
    "cmd_project_summary",
    "cmd_submit_decision",
    "cmd_run_manual_chain",
    "cmd_run_cad_chain",
    "cmd_run_tests",
    "cmd_run_evals",
    "cmd_build_release",
    "cmd_run",
]
