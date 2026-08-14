"""P2 所有者 UX 与 Owner Web Console 命令。"""

from __future__ import annotations

import json
from pathlib import Path

from ._helpers import DEFAULT_TENANT, _emit, _resolve_project


def cmd_operate(args):
    """自然语言操作闭环：意图→影响→受影响制品→成本/时间→可撤销预览→批准→自动返工→自动验收→摘要。"""
    from aipd_os.experience.intent_engine import parse_intent
    from aipd_os.experience.operations import ProgressTracker, run_operation_loop
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = args.project or _resolve_project(db)
    intent = parse_intent(args.intent, db, pid, DEFAULT_TENANT)
    tracker = ProgressTracker()
    result = run_operation_loop(db, pid, intent, tenant_id=DEFAULT_TENANT,
                                approved=args.approve, progress=tracker,
                                should_cancel=(lambda: False))

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0

    # 进度事件（意图→影响→返工→验收）逐步打印：长任务不再静默
    for ev in tracker.events():
        print(f"[{ev.get('step', '')}] {ev.get('message', '')}")

    status = result["status"]
    if status == "needs_clarification":
        print("需要澄清：")
        print(f"· {result['clarifying_question']}")
    elif status == "needs_approval":
        print("该操作需要您批准后才会执行（当前未执行任何变更）：")
        print(f"· {result['why_need_decide']}")
        print(f"· {result['impact']['human_estimate']}")
        print("· 可撤销预览已生成；确认后请用 --approve 执行。")
    elif status == "cancelled":
        print("操作已取消，未验收。")
    else:
        print("操作闭环已完成：")
        for line in result["impact"]["propagated_impact"]:
            print(f"· {line}")
        print(f"· 自动返工 {result['rework']['count']} 项，自动验收 {result['acceptance']['count']} 项，摘要已更新。")  # noqa: E501
    return 0


def cmd_dashboard(args):
    """统一 Owner Dashboard：默认只展示 10 个所有者区块；--json 输出纯 JSON。"""
    from aipd_os.experience.owner_dashboard import (
        build_dashboard,
        render_dashboard_json,
        render_dashboard_text,
    )
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = args.project or _resolve_project(db)
    view = build_dashboard(db, pid, DEFAULT_TENANT)
    if getattr(args, "json", False):
        print(render_dashboard_json(view))
    else:
        print(render_dashboard_text(view, compact=args.compact))
    return 0


def cmd_onboard(args):
    """首次使用引导：一句话建项 → 立即产出第一份结果 → 能力/外部配置 → 示例 → 恢复/重置。"""
    from aipd_os.experience.onboarding import onboard
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    r = onboard(db, args.idea, args.project, DEFAULT_TENANT)
    if getattr(args, "json", False):
        print(json.dumps(r, ensure_ascii=False, default=str))
        return 0
    print(f"项目已创建：{r['name']}（{r['project_id']}）")
    print(f"目标：{r['goal']}")
    print("已立即产出：")
    for p in r["produced"]:
        print(f"  · {p['label']}：{p['detail']}")
    print("能力与外部配置：")
    for c in r["capabilities"]:
        print(f"  [{c['status']}] {c['name']}（{c['env']}）")
    print(r["reset"])
    print(r["recover"])
    return 0


def cmd_reset(args):
    """重置项目：先备份再删除。"""
    from aipd_os.experience.onboarding import reset_project
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    r = reset_project(db, args.project, DEFAULT_TENANT)
    result = {"command": "reset", "ok": True, **r}

    def prose():
        print(f"已重置项目 {r['project_id']}；备份保存在 {r['backup']}。")
        print("如需恢复请使用 `aipd recover --backup <dir>` 或 `aipd resume --backup`。")
    _emit(args, result, prose)
    return 0


def cmd_recover(args):
    """失败恢复：回滚最近可撤销操作；或从备份恢复数据库。"""
    from aipd_os.experience.onboarding import recover_project
    from aipd_os.experience.operations import revert_operation
    from aipd_os.state.db import AIPDStateDB

    if args.backup:
        r = recover_project(args.db, args.project, args.backup)
        result = {"command": "recover", "ok": True, **r}
        _emit(args, result, lambda: print(f"已从备份恢复：{r['restored']}"))
        return 0

    db = AIPDStateDB(args.db)
    pid = args.project or _resolve_project(db)
    r = revert_operation(db, pid, DEFAULT_TENANT)
    result = {"command": "recover", "ok": True, "project_id": pid, **r}
    _emit(args, result, lambda: print(f"失败恢复：{r['note']}"))
    return 0


def cmd_ui(args):
    """启动本地 Owner Web Console：标准库 HTTP 服务，CLI/Web/JSON 共用同一业务服务。"""
    from aipd_os.config import get_settings
    from aipd_os.web import WebConsole, serve

    settings = get_settings()
    db_path = args.db or str(Path(get_settings().db_dir) / "state.db")
    host = args.host or settings.host
    port = int(args.port or settings.port)

    console = WebConsole(db_path, tenant_id=DEFAULT_TENANT,
                         default_project=args.project)
    serve(console, host=host, port=port)
    return 0


__all__ = [
    "cmd_operate",
    "cmd_dashboard",
    "cmd_onboard",
    "cmd_reset",
    "cmd_recover",
    "cmd_ui",
]
