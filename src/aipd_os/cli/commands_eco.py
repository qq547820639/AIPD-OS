"""`aipd eco …` —— ECR/ECO 工程变更单的命令面（F-C6-ECO 第 26 片）。

四个动词各自只做一件事，退出码沿用本仓口径：
0 成功｜1 单据不存在｜2 输入不合法（缺哈希、机器身份当作者…）｜
4 **状态机拒绝**（不许自批、空清单不可批准、无凭据不算已实施、终态不动）。

把「状态机拒绝」判成 4 而不是 0：这一格存在的意义就是让脚本与发布流程
**不能**把「被拒的批准」读成成功。
"""
from __future__ import annotations

from typing import Any

from ._helpers import _emit

NOT_FOUND = 1
BAD_INPUT = 2
REFUSED = 4


def _store(args: Any):
    from aipd_os.change_orders.eco import EcoStore
    from aipd_os.state.db import AIPDStateDB

    return EcoStore(AIPDStateDB(args.db))


def _fail(command: str, args: Any, error: str, prose: str, rc: int) -> int:
    _emit(args, {"command": command, "ok": False, "error": error},
          lambda: print(f"{command}：{prose}"))
    return rc


# ------------------------------------------------------------------ eco create
def cmd_eco_create(args: Any) -> int:
    """开一张 DRAFT 的变更单（ECR 或 ECO）。"""
    from aipd_os.change_orders.eco import EcoError

    try:
        record = _store(args).create(
            tenant_id=args.tenant, project_id=args.project, title=args.title,
            creator=args.creator, kind=args.kind, reason=args.reason,
            source_commit=args.source_commit)
    except EcoError as exc:
        return _fail("eco create", args, str(exc), str(exc), BAD_INPUT)
    _emit(args, {"command": "eco create", "ok": True, "eco": record},
          lambda: print(f"{record['eco_id']}｜{record['kind']}｜{record['status']}｜"
                        f"{record['title']}（创建人 {record['creator']}）"))
    return 0


# ----------------------------------------------------------------- eco affected
def cmd_eco_affected(args: Any) -> int:
    """往影响清单里加一行（带改前/改后 sha256）。"""
    from aipd_os.change_orders.eco import EcoError
    from aipd_os.state.errors import InvalidTransitionError, NotFoundError

    try:
        row = _store(args).add_affected(
            eco_id=args.id, tenant_id=args.tenant, project_id=args.project,
            object_type=args.object_type, object_id=args.object_id,
            change_type=args.change, before_sha256=args.before_sha256,
            after_sha256=args.after_sha256, note=args.note, actor=args.actor)
    except EcoError as exc:
        return _fail("eco affected", args, str(exc), str(exc), BAD_INPUT)
    except NotFoundError as exc:
        return _fail("eco affected", args, str(exc), f"没有单据 {args.id}", NOT_FOUND)
    except InvalidTransitionError as exc:
        return _fail("eco affected", args, str(exc), str(exc), REFUSED)
    _emit(args, {"command": "eco affected", "ok": True, "affected": row},
          lambda: print(f"{row['eco_id']} 影响清单第 {row['seq']} 行："
                        f"{row['change_type']} {row['object_type']}/{row['object_id']}"))
    return 0


# ---------------------------------------------------------------- eco transition
def cmd_eco_transition(args: Any) -> int:
    """走一步状态；被状态机拒就退 4，并把拒绝理由原样交出去。"""
    from aipd_os.change_orders.eco import EcoError
    from aipd_os.state.errors import (
        ConcurrentModificationError,
        InvalidTransitionError,
        NotFoundError,
    )

    store = _store(args)
    try:
        record = store.transition(
            eco_id=args.id, tenant_id=args.tenant, project_id=args.project,
            to_status=args.to, actor=args.actor, reason=args.reason,
            evidence_ref=args.evidence_ref, effective_at=args.effective_at)
    except EcoError as exc:
        return _fail("eco transition", args, str(exc), str(exc), BAD_INPUT)
    except NotFoundError as exc:
        return _fail("eco transition", args, str(exc), f"没有单据 {args.id}", NOT_FOUND)
    except (InvalidTransitionError, ConcurrentModificationError) as exc:
        return _fail("eco transition", args, str(exc), str(exc), REFUSED)
    _emit(args, {"command": "eco transition", "ok": True, "eco": record},
          lambda: print(f"{record['eco_id']} → {record['status']}"
                        + (f"（批准人 {record['approver']}）"
                           if record["status"] == "APPROVED" else "")))
    return 0


# --------------------------------------------------------------------- eco show
def cmd_eco_show(args: Any) -> int:
    """看一张单（含影响清单与转移流水）；不给 --id 时按 --open 列未闭合的单。"""
    from aipd_os.change_orders.eco import EcoError
    from aipd_os.state.errors import NotFoundError

    store = _store(args)
    try:
        if args.id:
            record = store.get(eco_id=args.id, tenant_id=args.tenant,
                               project_id=args.project)
            payload = {"command": "eco show", "ok": True, "eco": record,
                       "affected": store.affected(eco_id=args.id, tenant_id=args.tenant,
                                                  project_id=args.project),
                       "transitions": store.transitions(eco_id=args.id,
                                                        tenant_id=args.tenant,
                                                        project_id=args.project)}
        else:
            payload = {"command": "eco show", "ok": True,
                       "ecos": store.list_orders(tenant_id=args.tenant,
                                          project_id=args.project,
                                          status=args.status,
                                          open_only=args.open)}
    except EcoError as exc:
        return _fail("eco show", args, str(exc), str(exc), BAD_INPUT)
    except NotFoundError as exc:
        return _fail("eco show", args, str(exc), f"没有单据 {args.id}", NOT_FOUND)

    def prose() -> None:
        if args.id:
            eco = payload["eco"]
            print(f"{eco['eco_id']}｜{eco['kind']}｜{eco['status']}｜{eco['title']}")
            print(f"  创建 {eco['creator']} @ {eco['created_at']}"
                  f"｜批准 {eco['approver'] or '—'} @ {eco['approved_at'] or '—'}"
                  f"｜凭据 {eco['applied_evidence_ref'] or '—'}"
                  f"｜复验 {eco['verified_evidence_ref'] or '—'}")
            for row in payload["affected"]:
                print(f"  影响 [{row['change_type']}] {row['object_type']}/{row['object_id']}"
                      f"  {row['before_sha256'][:8] or '—'}→{row['after_sha256'][:8] or '—'}")
            for row in payload["transitions"]:
                print(f"  {row['from_status'] or '(建单)'}→{row['to_status']}"
                      f" by {row['actor']} @ {row['occurred_at']}"
                      + (f"：{row['reason']}" if row["reason"] else ""))
        else:
            rows = payload["ecos"]
            if not rows:
                print("没有符合条件的变更单")
            for eco in rows:
                print(f"{eco['eco_id']}｜{eco['kind']}｜{eco['status']}｜{eco['title']}")

    _emit(args, payload, prose)
    return 0


__all__ = ["cmd_eco_create", "cmd_eco_affected", "cmd_eco_transition", "cmd_eco_show"]
