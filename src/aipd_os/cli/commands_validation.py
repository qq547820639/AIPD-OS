"""Validation / Issue / Readiness CLI 命令（v5.10 Milestone 5）。

提供：
- `aipd validation plan` — 创建验证计划
- `aipd validation list` — 列出验证计划/测试/结果
- `aipd validation show` — 显示验证详情
- `aipd validation import` — 导入 EVT/DVT/PVT 数据
- `aipd issue list` — 列出 Issue
- `aipd issue show` — 显示 Issue 详情
- `aipd issue resolve` — 解决 Issue
- `aipd readiness check` — 检查制造就绪度
"""

from __future__ import annotations

import json
from typing import Any

from aipd_os.cli._helpers import _emit


# --------------------------------------------------------------------------
# validation plan
# --------------------------------------------------------------------------
def cmd_validation_plan(args: Any) -> int:
    """创建验证计划。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.service import ValidationService

    db = AIPDStateDB(args.db)
    svc = ValidationService(db)

    plan = svc.create_plan(
        tenant_id=args.tenant or "default",
        project_id=args.project,
        stage=args.stage.upper(),
        title=args.title,
        objective=getattr(args, "objective", "") or "",
    )

    result = {"command": "validation plan", "ok": True, "plan": plan.to_dict()}
    _emit(args, result, lambda: print(f"验证计划已创建：{plan.plan_id}（{plan.title}）"))
    return 0


# --------------------------------------------------------------------------
# validation list
# --------------------------------------------------------------------------
def cmd_validation_list(args: Any) -> int:
    """列出验证计划/测试/结果。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.service import ValidationService

    db = AIPDStateDB(args.db)
    svc = ValidationService(db)
    tenant = args.tenant or "default"

    what = getattr(args, "what", "plans")

    data: list[dict[str, Any]] = []
    if what == "plans":
        plans = svc.list_plans(tenant, args.project)
        data = [p.to_dict() for p in plans]
    elif what == "tests":
        tests = svc.list_tests(tenant, args.project)
        data = [t.to_dict() for t in tests]
    elif what == "results":
        results = svc.list_results(tenant, args.project)
        data = [r.to_dict() for r in results]

    result = {"command": "validation list", "ok": True, "what": what, "items": data}
    _emit(args, result, lambda: print(f"共 {len(data)} 个 {what}"))
    return 0


# --------------------------------------------------------------------------
# validation show
# --------------------------------------------------------------------------
def cmd_validation_show(args: Any) -> int:
    """显示验证详情。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.service import ValidationService

    db = AIPDStateDB(args.db)
    svc = ValidationService(db)
    tenant = args.tenant or "default"

    what = getattr(args, "what", "plan")
    item_id = args.id

    item: Any = None
    if what == "plan":
        item = svc.get_plan(tenant, args.project, item_id)
    elif what == "test":
        item = svc.get_test(tenant, args.project, item_id)

    if item is None:
        result = {"command": "validation show", "ok": False,
                  "error": f"{what} {item_id} not found"}
        _emit(args, result, lambda: print(f"未找到 {what}：{item_id}"))
        return 1

    result = {"command": "validation show", "ok": True, "item": item.to_dict()}
    _emit(args, result, lambda: print(json.dumps(item.to_dict(), ensure_ascii=False, indent=2)))
    return 0


# --------------------------------------------------------------------------
# validation import
# --------------------------------------------------------------------------
def cmd_validation_import(args: Any) -> int:
    """导入 EVT/DVT/PVT 数据。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.ingestion import IngestionService
    from aipd_os.validation.issues import IssueService
    from aipd_os.validation.service import ValidationService

    db = AIPDStateDB(args.db)
    vs = ValidationService(db)
    is_ = IssueService(db)
    svc = IngestionService(vs, is_)

    result = svc.ingest_file(
        tenant_id=args.tenant or "default",
        project_id=args.project,
        file_path=args.file,
        stage=args.stage,
        plan_id=getattr(args, "plan_id", "") or "",
    )

    output = {
        "command": "validation import", "ok": len(result.errors) == 0,
        "result": {
            "stage": result.stage,
            "records_imported": result.records_imported,
            "tests_created": result.tests_created,
            "runs_created": result.runs_created,
            "results_created": result.results_created,
            "issues_created": result.issues_created,
            "errors": result.errors,
            "warnings": result.warnings,
        },
    }

    def prose():
        print(f"导入完成：{result.records_imported} 条记录")
        print(f"  测试创建：{result.tests_created}")
        print(f"  执行创建：{result.runs_created}")
        print(f"  结果创建：{result.results_created}")
        print(f"  Issue 创建：{result.issues_created}")
        if result.errors:
            print(f"  错误：{result.errors}")
        if result.warnings:
            print(f"  警告：{result.warnings}")

    _emit(args, output, prose)
    return 0 if len(result.errors) == 0 else 1


# --------------------------------------------------------------------------
# issue list
# --------------------------------------------------------------------------
def cmd_issue_list(args: Any) -> int:
    """列出 Issue。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.issues import IssueService

    db = AIPDStateDB(args.db)
    svc = IssueService(db)
    tenant = args.tenant or "default"

    status = getattr(args, "status", None)
    blocking_only = getattr(args, "blocking", False)

    issues = svc.list_issues(tenant, args.project, status=status,
                             blocking_only=blocking_only)
    data = [i.to_dict() for i in issues]

    result = {"command": "issue list", "ok": True, "items": data}
    _emit(args, result, lambda: print(f"共 {len(data)} 个 Issue"))
    return 0


# --------------------------------------------------------------------------
# issue show
# --------------------------------------------------------------------------
def cmd_issue_show(args: Any) -> int:
    """显示 Issue 详情。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.issues import IssueService

    db = AIPDStateDB(args.db)
    svc = IssueService(db)
    tenant = args.tenant or "default"

    issue = svc.get_issue(tenant, args.project, args.id)
    if issue is None:
        result = {"command": "issue show", "ok": False,
                  "error": f"Issue {args.id} not found"}
        _emit(args, result, lambda: print(f"未找到 Issue：{args.id}"))
        return 1

    result = {"command": "issue show", "ok": True, "issue": issue.to_dict()}
    _emit(args, result,
          lambda: print(json.dumps(issue.to_dict(), ensure_ascii=False, indent=2)))
    return 0


# --------------------------------------------------------------------------
# issue resolve
# --------------------------------------------------------------------------
def cmd_issue_resolve(args: Any) -> int:
    """解决 Issue（设置 disposition 并更新状态）。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.issues import IssueService

    db = AIPDStateDB(args.db)
    svc = IssueService(db)
    tenant = args.tenant or "default"

    issue = svc.get_issue(tenant, args.project, args.id)
    if issue is None:
        result = {"command": "issue resolve", "ok": False,
                  "error": f"Issue {args.id} not found"}
        _emit(args, result, lambda: print(f"未找到 Issue：{args.id}"))
        return 1

    # 设置 disposition
    svc.set_disposition(
        tenant, args.project, args.id,
        disposition=args.disposition,
        root_cause=getattr(args, "root_cause", "") or "",
        revalidation_required=getattr(args, "revalidation", False),
    )

    # 更新状态为 RESOLVED
    svc.update_issue_status(tenant, args.project, args.id, "RESOLVED")

    updated = svc.get_issue(tenant, args.project, args.id)
    issue_data = updated.to_dict() if updated else {}
    result = {"command": "issue resolve", "ok": True, "issue": issue_data}
    _emit(args, result, lambda: print(f"Issue {args.id} 已解决"))
    return 0


# --------------------------------------------------------------------------
# readiness check
# --------------------------------------------------------------------------
def cmd_readiness_check(args: Any) -> int:
    """检查制造就绪度。"""
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.validation.issues import IssueService
    from aipd_os.validation.readiness import ReadinessService
    from aipd_os.validation.service import ValidationService

    db = AIPDStateDB(args.db)
    vs = ValidationService(db)
    is_ = IssueService(db)
    svc = ReadinessService(vs, is_)

    report = svc.evaluate(
        tenant_id=args.tenant or "default",
        project_id=args.project,
    )

    result = {"command": "readiness check", "ok": True, "report": report.to_dict()}

    def prose():
        print(report.to_human_readable())

    _emit(args, result, prose)
    return 0 if report.overall_status == "PASS" else 1


__all__ = [
    "cmd_validation_plan", "cmd_validation_list", "cmd_validation_show",
    "cmd_validation_import", "cmd_issue_list", "cmd_issue_show",
    "cmd_issue_resolve", "cmd_readiness_check",
]
