"""手工批次相关命令（``aipd manual plan`` / ``aipd manual generate``）。"""

from __future__ import annotations

import json
from pathlib import Path

from aipd_os.cli._helpers import (
    _emit,
    _import_module,
    _ns,
    _resolve_project,
)


def _manual_state(args):
    if args.state:
        return args.state
    if args.db:
        return str(Path(args.db).with_suffix(".manual.json"))
    raise ValueError("缺少 --state 或 --db，无法定位手工批次状态文件。")


def _silent(fn):
    """运行 fn 并吞掉其 stdout（供 manual_chain 等内部命令使用）。"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()


def _manual_ensure_state(args, state):
    mc = _import_module("manual_chain")
    if Path(state).exists():
        return mc
    from aipd_os.state.db import AIPDStateDB
    project_id = args.project or _resolve_project(AIPDStateDB(args.db))
    _silent(lambda: mc.cmd_init(_ns(cmd="init", state=state, project_id=project_id,
                                    minimum_pages=args.minimum_pages)))
    return mc


def cmd_manual_plan(args):
    mc = _import_module("manual_chain")
    state = _manual_state(args)
    _manual_ensure_state(args, state)
    _silent(lambda: mc.cmd_plan_batches(_ns(cmd="plan-batches", state=state,
                                            minimum_pages=args.minimum_pages)))
    data = json.loads(Path(state).read_text(encoding="utf-8"))
    plan = data.get("batch_plan", [])
    batches = sorted({e["batch_id"] for e in plan})
    result = {"command": "manual plan", "ok": True, "state": state,
              "page_count": len(plan), "batches": batches}

    def prose():
        print(f"手工批次计划已生成：{len(plan)} 页，{len(batches)} 个批次。")
        print(f"批次：{'、'.join(batches)}")
    _emit(args, result, prose)
    return 0


def cmd_manual_generate(args):
    mc = _import_module("manual_chain")
    state = _manual_state(args)
    _manual_ensure_state(args, state)
    data = json.loads(Path(state).read_text(encoding="utf-8"))
    if not data.get("batch_plan"):
        _silent(lambda: mc.cmd_plan_batches(_ns(cmd="plan-batches", state=state,
                                                minimum_pages=args.minimum_pages)))
    _silent(lambda: mc.cmd_run_batch(_ns(
        cmd="run-batch", state=state, batch_id=args.batch_id, prompt=args.prompt,
        theory_version="auto", truth_version="auto", anchors="",
        prior_batch=None, output_dir=args.output_dir, visual_bible=None,
        prohibited=None, facts=None)))
    data = json.loads(Path(state).read_text(encoding="utf-8"))
    run = data["batch_runs"][-1]
    result = {"command": "manual generate", "ok": True, "batch_id": args.batch_id,
              "completed": run["completed"], "external_pending": run["external_pending"],
              "external_task_dir": run.get("external_task_dir")}

    def prose():
        print(f"手工批次 {args.batch_id} 执行结果：")
        print(f"· 完成页：{run['completed']}")
        print(f"· 外部待办：{run['external_pending']}")
        if run.get("external_task_dir"):
            print(f"· 外部任务包目录：{run['external_task_dir']}")
            print("（图像后端不可用，未生成页面；如需出图请配置后端或消费外部任务包。）")
    _emit(args, result, prose)
    return 0
