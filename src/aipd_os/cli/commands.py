"""``aipd`` 一键命令的实现。

每个命令都真实复用仓库中的既有模块（监督器 / 状态库 / 体验视图 / 评估 /
安全 / 脚本），并返回标准的进程退出码（0 成功，非 0 失败）。

按域拆分为多个文件以控制单文件规模（每个 <700 行）：
- 本文件：核心命令（init/intake/resume/status/decide/version）+
  ``COMMAND_FUNCS`` 聚合 + 对拆分文件的 re-export；
- ``commands_legacy.py``：legacy ``cmd_*``（已废弃，映射到新命令）；
- ``commands_manual.py``：``aipd manual plan`` / ``aipd manual generate``；
- ``commands_cad.py``：``aipd cad preflight/build`` / ``industrialize`` / ``validate``；
- ``commands_release.py``：``aipd release check`` / ``test`` / ``eval`` / ``package`` / ``audit``；
- ``commands_doctor.py``：``aipd doctor``；
- ``commands_owner.py``：``operate``/``dashboard``/``onboard``/``reset``/``recover``/``ui``；
- ``_helpers.py``：共享工具函数（避免拆分后循环导入）。

本文件对拆分出去的 ``cmd_*`` 函数做 re-export，保证既有 import 路径
（如 ``from aipd_os.cli.commands import cmd_manual_plan``）不变。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aipd_os.cli.product_commands import cmd_product_gate, cmd_product_show
from aipd_os.logging_utils import log_event

from ._helpers import (
    DEFAULT_TENANT,
    _emit,
    _import_module,
    _is_legacy,
    _logger,
    _repo_root,
    _resolve_project,
    _sha256,
)
from .commands_cad import (
    cmd_cad_build,
    cmd_cad_preflight,
    cmd_industrialize,
    cmd_validate,
)
from .commands_doctor import cmd_doctor
from .commands_legacy import (
    cmd_build_release,
    cmd_init_project,
    cmd_project_summary,
    cmd_restore_project,
    cmd_run,
    cmd_run_cad_chain,
    cmd_run_evals,
    cmd_run_manual_chain,
    cmd_run_supervisor,
    cmd_run_tests,
    cmd_submit_decision,
)
from .commands_manual import cmd_manual_generate, cmd_manual_plan
from .commands_owner import (
    cmd_dashboard,
    cmd_onboard,
    cmd_operate,
    cmd_recover,
    cmd_reset,
    cmd_ui,
)
from .commands_release import (
    cmd_audit,
    cmd_eval,
    cmd_package,
    cmd_release_check,
    cmd_test,
)


# --------------------------------------------------------------------------
# init / intake（一句话建项，确定性）
# --------------------------------------------------------------------------
def cmd_init(args):
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    db.ensure_default_tenant(DEFAULT_TENANT)
    db.init_project(DEFAULT_TENANT, args.project, args.name, args.goal)
    sup = _import_module("aipd_supervisor").Supervisor(
        args.db, tenant_id=DEFAULT_TENANT, project_id=args.project, state_db=db)
    sup.init_lifecycle()
    log_event(_logger, "init", project_id=args.project, db=args.db)
    result = {"command": "init", "ok": True, "project_id": args.project,
              "name": args.name, "goal": args.goal, "db": args.db}

    def prose():
        print(f"项目已初始化：{args.name}（{args.project}）")
        print(f"数据库：{args.db}")
        print(f"目标：{args.goal}")
        print("监督器生命周期已就绪，可执行 `aipd run` / `aipd status`。")
    _emit(args, result, prose)
    return 0


def cmd_intake(args):
    from aipd_os.idea import CAPABILITY_UNAVAILABLE, Idea, IdeaService
    from aipd_os.state.db import AIPDStateDB

    prompt = (args.prompt or "").strip()
    if not prompt:
        raise ValueError("缺少 --prompt：请提供一句自然语言的需求描述。")
    goal = prompt
    name = prompt if len(prompt) <= 24 else prompt[:24]
    project_id = args.project or "p_" + hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]

    db = AIPDStateDB(args.db)
    db.ensure_default_tenant(DEFAULT_TENANT)
    db.init_project(DEFAULT_TENANT, project_id, name, goal)
    sup = _import_module("aipd_supervisor").Supervisor(
        args.db, tenant_id=DEFAULT_TENANT, project_id=project_id, state_db=db)
    sup.init_lifecycle()

    # v5.8 Commit 15：intake 同时创建 Raw Idea（I0）。
    # v5.8.1 Commit 11：创建与执行分离 —— 无 --run 不自动 decompose；
    # 有 --run 且 provider 可用 → 经 Supervisor → ExecutionRouter 执行 idea.structure。
    ideas = IdeaService(db)
    idea = ideas.create(Idea(idea_id="", tenant_id=DEFAULT_TENANT,
                             project_id=project_id, title=name,
                             raw_input=prompt, goal=goal,
                             lifecycle_status="raw"), actor="system")

    decompose_status = CAPABILITY_UNAVAILABLE
    structure_out = None
    if getattr(args, "run", False):
        from aipd_os.execution.execution_router import ExecutionRouter
        from aipd_os.execution.runs import RunStore
        from aipd_os.idea.decomposer import IdeaDecomposer
        from aipd_os.runtime import build_runtime
        from aipd_os.supervisor import schedule_idea_structure
        from aipd_os.tool_adapters.idea_adapter import register_idea_adapters

        # v5.8.2 Commit 3：共享 runtime 装配（providers/adapters/router 同源）。
        # 命令级动态适配器（idea.structure 依赖 decomposer 实例）经
        # runtime.with_adapters 叠加，不污染共享 registry。
        runtime = build_runtime(encryption_key="",
                                db_path=args.db,
                                tenant_id=DEFAULT_TENANT,
                                project_id=project_id,
                                make_default=True)
        # 找已注册的 idea.decompose provider（§18：本 command 全程使用同一
        # runtime —— make_default=True 已安装单例，_find_idea_decompose_provider
        # 经 get_runtime() 拿到的是**同一实例**，不产生 split；同时它是测试
        # 注入点（monkeypatch），保留 fallback 以维持 CLI 可注入性）
        provider = runtime.providers.get_by_capability(
            "idea.decompose") or _find_idea_decompose_provider()
        if provider is not None and provider.available():
            decomposer = IdeaDecomposer(db, provider=provider,
                                        tenant_id=DEFAULT_TENANT,
                                        project_id=project_id)
            registry = runtime.with_adapters({})
            register_idea_adapters(registry, db=db, decomposer=decomposer,
                                   tenant_id=DEFAULT_TENANT,
                                   project_id=project_id)
            store = RunStore(str(Path(args.db).parent / "execution_runs.db"))
            router = ExecutionRouter(store, registry)
            wid = schedule_idea_structure(sup, idea.idea_id,
                                          tenant_id=DEFAULT_TENANT,
                                          project_id=project_id)
            results = sup.run_supervisor(steps=1, adapter_registry=registry,
                                         router=router, project_id=project_id)
            if results and results[0]["action"] == "complete":
                decompose_status = "COMPLETED"
                structure_out = {"work_id": wid,
                                 "status": results[0].get("status")}
            elif results and results[0]["action"] in ("blocked_external",
                                                      "internal_rework"):
                decompose_status = results[0]["action"]
            else:
                decompose_status = CAPABILITY_UNAVAILABLE
        else:
            decompose_status = CAPABILITY_UNAVAILABLE

    result = {"command": "intake", "ok": True, "project_id": project_id,
              "name": name, "goal": goal, "db": args.db,
              "idea_id": idea.idea_id,
              "idea_maturity": "I1" if decompose_status == "COMPLETED" else "I0",
              "decompose_status": decompose_status}
    if structure_out:
        result["structure"] = {"work_id": structure_out["work_id"],
                               "status": structure_out.get("status")}

    def prose():
        print(f"已根据需求初始化项目：{name}（{project_id}）")
        print(f"目标：{goal}")
        print(f"Raw Idea 已创建：{idea.idea_id}（maturity I0）")
        if decompose_status == "COMPLETED":
            print(f"Idea 结构化已完成（idea.structure，maturity I1）："
                  f"work_id={structure_out['work_id']}")
        elif getattr(args, "run", False):
            print(f"Idea 分解能力不可用（{decompose_status}）：结构化未执行，"
                  "Idea 保持 I0。")
        else:
            print("Idea 分解未执行（无 --run；创建与执行分离）。需要结构化请运行 "
                  "`aipd intake --run` 或注册 IdeaDecompositionProvider 后调度 "
                  "idea.structure。")
        print("监督器生命周期已就绪。")
    _emit(args, result, prose)
    return 0


def _find_idea_decompose_provider():
    """从进程级 runtime 的 ProviderRegistry 找已注册的 idea.decompose provider。

    v5.8.2 Commit 3（RuntimeContext）：不再每次 new 一个空 ProviderRegistry
    （旧实现导致「第三方已注册、CLI 永远发现不了」）。
    """
    try:
        from aipd_os.idea import IDEA_DECOMPOSE_CAPABILITY
        from aipd_os.runtime import get_runtime
        return get_runtime().providers.get_by_capability(IDEA_DECOMPOSE_CAPABILITY)
    except Exception:  # noqa: BLE001 - registry 未配置/未注册 → 诚实不可用
        return None


def probe_research_capabilities(registry=None):
    """动态探测研究能力（v5.8.1 Commit 12 / v5.8.2 Commit 3）。

    AdapterRegistry 注册 + provider available；registry 缺省时使用进程级
    runtime 的共享 AdapterRegistry（不再每次 new 一套）。
    返回 ``{"available": [...], "unavailable": [...]}``。
    """
    from aipd_os.idea import RESEARCH_CAPABILITIES
    if registry is None:
        from aipd_os.runtime import get_runtime
        registry = get_runtime().adapters
    available: list = []
    unavailable: list = []
    for cid in sorted(RESEARCH_CAPABILITIES):
        adapter = registry.get(cid)
        if adapter is not None and adapter.discover().get("available", True):
            available.append(cid)
        else:
            unavailable.append(cid)
    return {"available": available, "unavailable": unavailable}


# --------------------------------------------------------------------------
# resume / status / decide
# --------------------------------------------------------------------------
def cmd_resume(args):
    from aipd_os.experience.resume_summary import build_resume_summary
    from aipd_os.state.backup import BackupManager
    from aipd_os.state.db import AIPDStateDB

    db_path = Path(args.db)
    restored_from = None
    if args.backup:
        manager = BackupManager(str(db_path))
        restored_from = manager.restore_backup(args.backup, db_path=str(db_path))
    elif _is_legacy(db_path):
        v4 = _import_module("v4_to_v5", subdir="migrations")
        tmp = db_path.with_suffix(".migrating.db")
        v4.migrate_legacy(str(db_path), str(tmp), tenant_id=DEFAULT_TENANT)
        os.replace(str(tmp), str(db_path))

    db = AIPDStateDB(args.db)
    pid = args.project or _resolve_project(db)
    rs = build_resume_summary(db, pid, DEFAULT_TENANT)
    result = {"command": "resume", "ok": True, "project_id": pid,
              "restored_from": restored_from, "resume": rs}

    def prose():
        if restored_from:
            print(f"已从备份恢复到：{restored_from}")
        elif not args.backup and not _is_legacy(db_path):
            print(f"数据库 {db_path} 已是 v5 格式，无需迁移/恢复。")
        print(f"项目 {pid} 上次进行到：{rs['where_left_off']}")
        print(f"当前阶段：{rs['current_phase']}；状态：{rs['project_status']}")
        print(f"下一步：{rs['next_action']}")
        if rs["decisions_to_ask"]:
            print("待您决策：")
            for d in rs["decisions_to_ask"]:
                print(f"  - {d['decision_id']} {d['topic']}")
        else:
            print("当前没有待您决策的事项。")
    _emit(args, result, prose)
    return 0


def cmd_status(args):
    from aipd_os.experience.views import OwnerView
    from aipd_os.idea import (
        CAPABILITY_UNAVAILABLE,
        EvidenceGraph,
        IdeaService,
        IdeaTruthProjection,
    )
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    view = OwnerView(db, tenant_id=DEFAULT_TENANT)
    pid = args.project or _resolve_project(db)

    # v5.8 Commit 15：Idea/Claims/Evidence 摘要（无 idea 时保持旧输出）
    idea_section = None
    ideas = IdeaService(db).list(DEFAULT_TENANT, pid)
    if ideas:
        graph = EvidenceGraph(db)
        proj = IdeaTruthProjection(db, graph, DEFAULT_TENANT, pid)
        idea_entries = []
        for idea in ideas:
            p = proj.project(idea.idea_id)
            idea_entries.append({
                "idea_id": idea.idea_id,
                "title": idea.title,
                "maturity": p["maturity"],
                "claims": p["counts"]["total_claims"],
                "supporting": p["counts"]["known"],
                "contradicting": p["counts"]["contradicted"],
                "unknown": p["counts"]["unknown"],
                "gaps": p["counts"]["gaps"],
            })
        idea_section = {
            "ideas": idea_entries,
            # v5.8.1 Commit 12：动态探测（不再硬编码 RESEARCH_CAPABILITIES 全 blocked）
            "capabilities": probe_research_capabilities(
                getattr(args, "capability_registry", None)),
            "blocked_capabilities": [],
            "note": CAPABILITY_UNAVAILABLE,
        }
        idea_section["blocked_capabilities"] = \
            idea_section["capabilities"]["unavailable"]
        if not idea_section["blocked_capabilities"]:
            idea_section["note"] = "available"

    if args.markdown:
        text = view.to_markdown(project_id=pid)
        result = {"command": "status", "ok": True, "project_id": pid,
                  "markdown": text}
        if idea_section is not None:
            result["idea"] = idea_section
        _emit(args, result, lambda: print(text))
        return 0

    v = view.owner_update(pid)
    ps = v["project_summary"]
    result = {"command": "status", "ok": True, "project_id": pid, "summary": v}
    if idea_section is not None:
        result["idea"] = idea_section

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
        if idea_section is not None:
            print("Idea 状态（v5.8）")
            for e in idea_section["ideas"]:
                print(f"· {e['title']}（{e['idea_id']}）maturity={e['maturity']} "
                      f"claims={e['claims']} supporting={e['supporting']} "
                      f"contradicting={e['contradicting']} unknown={e['unknown']} "
                      f"gaps={e['gaps']}")
            print("· 阻塞能力（external_dependency）："
                  + ", ".join(idea_section["blocked_capabilities"]))
    _emit(args, result, prose)
    return 0


def cmd_decide(args):
    from aipd_os.experience.instructions import apply_instruction, parse_instruction
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = args.project or _resolve_project(db)

    natural = getattr(args, "natural", None)
    if natural:
        instr = parse_instruction(natural, db, pid, DEFAULT_TENANT)
        applied = apply_instruction(instr, db, pid, DEFAULT_TENANT)
        result = {"command": "decide", "ok": True, "project_id": pid,
                  "kind": applied["kind"],
                  "resolved_decision_id": applied.get("resolved_decision_id"),
                  "recorded_fact_id": applied.get("recorded_fact_id"),
                  "propagated_impact": applied.get("propagated_impact", [])}

        def prose():
            print(f"已理解您的回复（{instr.kind}）：")
            for line in result["propagated_impact"]:
                print(f"· {line}")
        _emit(args, result, prose)
        return 0

    if not args.decision_id or not args.choice:
        raise ValueError("请提供 --decision-id/--choice，或使用 --natural 提供一句自然语言回复。")

    db.resolve_decision(DEFAULT_TENANT, pid, args.decision_id, args.choice, args.comment)
    dec = next((d for d in db.list_decisions(DEFAULT_TENANT, pid)
                if d["decision_id"] == args.decision_id), None)
    result = {"command": "decide", "ok": True, "project_id": pid,
              "decision_id": args.decision_id, "choice": args.choice}

    def prose():
        print(f"决策 {args.decision_id} 已裁定：{args.choice}。")
        if dec:
            print(f"系统将按所选方案自动推进「{dec['topic']}」，并同步更新相关产物与检查点。")
    _emit(args, result, prose)
    return 0


# --------------------------------------------------------------------------
# version —— 打印包版本；--verbose 打印 Git HEAD / 构建时间 / 能力矩阵版本 / 清单哈希
# --------------------------------------------------------------------------
def cmd_version(args):
    from aipd_os import __version__

    result = {"command": "version", "version": __version__}
    if getattr(args, "verbose", False):
        repo = _repo_root()
        try:
            head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        except Exception:  # noqa: BLE001 - 非 git 环境时如实置空
            head = None
        try:
            import aipd_os
            build_time = datetime.fromtimestamp(
                Path(aipd_os.__file__).stat().st_mtime, tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            build_time = None
        cm_path = repo / "docs" / "audit" / "capability_matrix.json"
        cm_version = None
        if cm_path.exists():
            try:
                cm_version = json.loads(cm_path.read_text(encoding="utf-8")).get("version")
            except Exception:  # noqa: BLE001
                cm_version = None
        manifest_path = repo / "RELEASE_MANIFEST.json"
        manifest_hash = _sha256(manifest_path) if manifest_path.exists() else None
        result.update({
            "git_head": head,
            "build_time": build_time,
            "capability_matrix_version": cm_version,
            "release_manifest_sha256": manifest_hash,
        })
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    elif args.verbose:
        print(f"aipd version: {result['version']}")
        print(f"git HEAD: {result['git_head']}")
        print(f"build time: {result['build_time']}")
        print(f"capability matrix version: {result['capability_matrix_version']}")
        print(f"release manifest sha256: {result['release_manifest_sha256']}")
    else:
        print(__version__)
    return 0


# --------------------------------------------------------------------------
# 命令分发表
# --------------------------------------------------------------------------
COMMAND_FUNCS: dict[str, Any] = {
    # 既有 10 个一键命令（向后兼容）
    "init-project": cmd_init_project,
    "restore-project": cmd_restore_project,
    "run-supervisor": cmd_run_supervisor,
    "run": cmd_run,
    "project-summary": cmd_project_summary,
    "submit-decision": cmd_submit_decision,
    "run-manual-chain": cmd_run_manual_chain,
    "run-cad-chain": cmd_run_cad_chain,
    "run-tests": cmd_run_tests,
    "run-evals": cmd_run_evals,
    "build-release": cmd_build_release,
    # v5.1 新增 16 个一键命令
    "init": cmd_init,
    "intake": cmd_intake,
    "resume": cmd_resume,
    "status": cmd_status,
    "decide": cmd_decide,
    "manual plan": cmd_manual_plan,
    "manual generate": cmd_manual_generate,
    "cad preflight": cmd_cad_preflight,
    "cad build": cmd_cad_build,
    "industrialize": cmd_industrialize,
    "validate": cmd_validate,
    "audit": cmd_audit,
    "release check": cmd_release_check,
    "test": cmd_test,
    "eval": cmd_eval,
    "package": cmd_package,
    # v5.5 新增：运维体检与详细版本
    "version": cmd_version,
    "doctor": cmd_doctor,
    # P2 所有者 UX
    "operate": cmd_operate,
    "dashboard": cmd_dashboard,
    "onboard": cmd_onboard,
    "reset": cmd_reset,
    "recover": cmd_recover,
    # v5.6 Owner Web Console
    "ui": cmd_ui,
    # v5.9 Product Intelligence（产品定义查看 / Gate 操作）
    "product show": cmd_product_show,
    "product gate": cmd_product_gate,
}

PLANNED_COMMANDS = list(COMMAND_FUNCS.keys())

__all__ = ["COMMAND_FUNCS", "PLANNED_COMMANDS"]
