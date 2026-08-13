"""``aipd`` 一键命令的实现。

每个命令都真实复用仓库中的既有模块（监督器 / 状态库 / 体验视图 / 评估 /
安全 / 脚本），并返回标准的进程退出码（0 成功，非 0 失败）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aipd_os.cli.product_commands import cmd_product_gate, cmd_product_show
from aipd_os.logging_utils import get_logger, log_event

_logger = get_logger("aipd.cli")
DEFAULT_TENANT = "default"


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def _repo_root() -> Path:
    """定位仓库根目录（含 pyproject.toml 的目录）。"""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("无法定位仓库根目录")


def _import_module(name: str, subdir: str = "scripts"):
    """按路径加载仓库内的顶层脚本模块（非包）。"""
    path = _repo_root() / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _ns(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _resolve_project(db, tenant: str = DEFAULT_TENANT) -> str:
    projects = db.list_projects(tenant)
    if not projects:
        raise ValueError("当前租户下没有项目；请先用 `aipd init-project` 初始化。")
    return projects[0]["project_id"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_legacy(db_path: Path) -> bool:
    """判断一个 sqlite 是否为 v4 单项目旧库（projects 表无 tenant_id 列）。"""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        conn.close()
        return bool(cols) and "tenant_id" not in cols
    except sqlite3.DatabaseError:
        return False


def _run_pytest(repo: Path) -> int:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(repo), capture_output=True, text=True,
    )
    tail = (r.stdout or "")[-2000:]
    if tail:
        print(tail)
    if r.stderr:
        print((r.stderr or "")[-500:], file=sys.stderr)
    print(f"测试退出码：{r.returncode}")
    return r.returncode


def _run_evals_cli(repo: Path, evals: str, provider: str, out: str,
                   threshold: float, baseline: str | None) -> int:
    from aipd_os.evals_runner.cli import build_parser as evals_parser
    argv = ["run", "--evals", evals, "--provider", provider, "--out", out,
            "--threshold", str(threshold)]
    if baseline:
        argv += ["--baseline", baseline]
    ns = evals_parser().parse_args(argv)
    return int(ns.func(ns))


# --------------------------------------------------------------------------
# init-project
# --------------------------------------------------------------------------
def cmd_init_project(args: argparse.Namespace) -> int:
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    db.ensure_default_tenant(DEFAULT_TENANT)
    db.init_project(DEFAULT_TENANT, args.project_id, args.name, args.goal)
    # 同时在数据库上初始化监督器生命周期（共享同一 db 文件；§19：
    # 不再走 scripts 兼容层，直接 aipd_os.supervisor.Supervisor）
    from aipd_os.supervisor import Supervisor as _Sup
    sup = _Sup(args.db, tenant_id=DEFAULT_TENANT,
               project_id=args.project_id, state_db=db)
    sup.init_lifecycle()
    log_event(_logger, "init_project", project_id=args.project_id, db=args.db)
    print(f"项目已初始化：{args.name}（{args.project_id}）")
    print(f"数据库：{args.db}")
    print(f"目标：{args.goal}")
    print("监督器生命周期已就绪，可执行 `aipd run-supervisor`。")
    return 0


# --------------------------------------------------------------------------
# restore-project
# --------------------------------------------------------------------------
def cmd_restore_project(args: argparse.Namespace) -> int:
    from aipd_os.state.backup import BackupManager

    db_path = Path(args.db)
    if args.backup:
        manager = BackupManager(str(db_path))
        restored = manager.restore_backup(args.backup, db_path=str(db_path))
        log_event(_logger, "restore_project", source="backup", restored=restored)
        print(f"已从备份恢复到：{restored}")
        return 0

    if _is_legacy(db_path):
        v4 = _import_module("v4_to_v5", subdir="migrations")
        tmp = db_path.with_suffix(".migrating.db")
        stats = v4.migrate_legacy(str(db_path), str(tmp), tenant_id=DEFAULT_TENANT)
        os.replace(str(tmp), str(db_path))
        log_event(_logger, "restore_project", source="v4_migration", stats=stats.get("counts", {}))
        print(f"已将 v4 旧库迁移到 v5 多租户库：{db_path}")
        print(f"项目：{stats['project_id']}；事实 {stats['counts'].get('facts', 0)} 条，"
              f"决策 {stats['counts'].get('decisions', 0)} 条。")
        return 0

    print(f"数据库 {db_path} 已是 v5 格式，无需迁移/恢复。")
    return 0


# --------------------------------------------------------------------------
# run-supervisor
# --------------------------------------------------------------------------
def cmd_run_supervisor(args: argparse.Namespace) -> int:
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

    print(f"本轮执行 {len(results)} 个步骤：完成 {len(completed)} 项，决策 {len(decisions)} 项，"
          f"内部返工 {len(rework)} 项，外部阻塞 {len(external)} 项。")
    for r in completed:
        print(f"  [完成] {r.get('work_id')}  状态={r.get('status')}")
    for r in rework:
        print(f"  [返工] {r.get('work_id')}  原因={r.get('reason') or r.get('status')}")
    for r in external:
        print(f"  [外部阻塞] {r.get('work_id')}")

    for r in decisions:
        did = r["decision"]["decision_id"]
        card = build_decision_card(db, pid, decision_id=did, tenant_id=DEFAULT_TENANT)
        print(f"  [决策] {card['decision_id']}：{card['topic']}")
        print(f"    AI 建议：{card['ai_recommendation']}")
        print(f"    可选方案：{'、'.join(card['options'])}")
        print(f"    批准后系统将自动执行：{card['after_approval']}")
    return 0


# --------------------------------------------------------------------------
# project-summary
# --------------------------------------------------------------------------
def cmd_project_summary(args: argparse.Namespace) -> int:
    from aipd_os.experience.views import OwnerView
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    view = OwnerView(db, tenant_id=DEFAULT_TENANT)
    if args.markdown:
        print(view.to_markdown(project_id=_resolve_project(db)))
        return 0

    v = view.owner_update(_resolve_project(db))
    ps = v["project_summary"]
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
    return 0


# --------------------------------------------------------------------------
# submit-decision
# --------------------------------------------------------------------------
def cmd_submit_decision(args: argparse.Namespace) -> int:
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db)
    db.resolve_decision(DEFAULT_TENANT, pid, args.decision_id, args.choice, args.comment)
    dec = next((d for d in db.list_decisions(DEFAULT_TENANT, pid)
                if d["decision_id"] == args.decision_id), None)
    log_event(_logger, "submit_decision", decision_id=args.decision_id, choice=args.choice)
    print(f"决策 {args.decision_id} 已裁定：{args.choice}。")
    if dec:
        print(f"系统将按所选方案自动推进「{dec['topic']}」，并同步更新相关产物与检查点。")
    return 0


# --------------------------------------------------------------------------
# run-manual-chain
# --------------------------------------------------------------------------
def cmd_run_manual_chain(args: argparse.Namespace) -> int:
    mc = _import_module("manual_chain")
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
    print("手工批次执行结果：")
    print(f"· 完成页：{run['completed']}")
    print(f"· 外部待办：{run['external_pending']}")
    if run["external_pending"]:
        print(f"· 外部任务包目录：{run['external_task_dir']}")
        print("（图像后端不可用，未生成页面；如需出图请配置后端或消费外部任务包。）")
    return 0


def _db_handle(db_path: str):
    from aipd_os.state.db import AIPDStateDB
    return AIPDStateDB(db_path)


# --------------------------------------------------------------------------
# run-cad-chain
# --------------------------------------------------------------------------
def cmd_run_cad_chain(args: argparse.Namespace) -> int:
    cmg = _import_module("cad_maturity_gate")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    runtime = manifest.get("runtime", "mesh")
    runtime_ceiling = cmg.RUNTIME_MAX.get(runtime, "C0")
    ceiling_idx = cmg.idx(runtime_ceiling)

    reached: str | None = None
    cumulative: list[str] = []
    for level in cmg.LEVELS:
        cumulative += cmg.REQUIREMENTS[level]
        checks = {k: bool(cmg.present(cmg.val(manifest, k))) for k in cumulative}
        runtime_allowed = cmg.idx(level) <= ceiling_idx
        passed = all(checks.values()) and runtime_allowed
        if passed:
            reached = level
        else:
            break

    faceted_capped = runtime == "faceted_brep"
    target_idx = cmg.idx(args.target)
    target_passed = reached is not None and cmg.idx(reached) >= target_idx

    print(f"CAD 成熟度：达到 {reached}（运行时上限 {runtime_ceiling}）")
    if faceted_capped:
        print("faceted_brep 运行时成熟度封顶于 C1。")
    print(f"目标 {args.target} 通过：{'是' if target_passed else '否'}")
    print(json.dumps({
        "reached_level": reached, "runtime_ceiling": runtime_ceiling,
        "faceted_brep_capped": faceted_capped,
        "target_level": args.target, "target_passed": target_passed,
    }, ensure_ascii=False))
    return 0 if target_passed else 4


# --------------------------------------------------------------------------
# run-tests
# --------------------------------------------------------------------------
def cmd_run_tests(args: argparse.Namespace) -> int:
    return _run_pytest(_repo_root())


# --------------------------------------------------------------------------
# run-evals
# --------------------------------------------------------------------------
def cmd_run_evals(args: argparse.Namespace) -> int:
    out = args.out or str(_repo_root() / "evals_out")
    return _run_evals_cli(_repo_root(), args.evals, args.provider, out,
                          args.threshold, args.baseline)


# --------------------------------------------------------------------------
# build-release
# --------------------------------------------------------------------------
def _release_include_roots(repo: Path) -> list[Path]:
    roots: list[Path] = []
    for name in ["src", "scripts", "docs", "references", "evals"]:
        p = repo / name
        if p.exists():
            roots.append(p)
    schemas = repo / "assets" / "schemas"
    if schemas.exists():
        roots.append(schemas)
    return roots


# 发布包必须排除的本地/缓存/垃圾路径片段（任意嵌套层级）。
# 覆盖：虚拟环境、pytest/ruff/mypy 缓存、字节码缓存、pip 元数据目录。
_RELEASE_EXCLUDE_PART = frozenset({
    ".venv", ".venv-ci", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "__pycache__", ".pytest", "src/aipd_os.egg-info",
})
_RELEASE_EXCLUDE_SUFFIX = (".pyc", ".pyo", ".dist-info", ".egg-info")


def _is_release_excluded(rel: str) -> bool:
    """判断相对路径是否应从发布包中排除（垃圾/缓存/虚拟环境等）。"""
    parts = rel.split("/")
    if any(p in _RELEASE_EXCLUDE_PART for p in parts):
        return True
    if any(p.endswith(_RELEASE_EXCLUDE_SUFFIX) for p in parts):
        return True
    return False


def _collect_release_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for root in _release_include_roots(repo):
        for f in sorted(root.rglob("*")):
            if f.is_file() and not _is_release_excluded(f.relative_to(repo).as_posix()):
                files.append(f.relative_to(repo))
    return files


def _build_artifact_zip(repo: Path, artifact: Path, out_dir: Path) -> None:
    manifest_placeholder = out_dir / "RELEASE_MANIFEST.json"
    if not manifest_placeholder.exists():
        manifest_placeholder.write_text(
            json.dumps({"version": "unknown"}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as zf:
        for root in _release_include_roots(repo):
            for f in sorted(root.rglob("*")):
                rel = f.relative_to(repo).as_posix()
                if f.is_file() and not _is_release_excluded(rel):
                    zf.write(f, arcname=rel)
        zf.write(manifest_placeholder, arcname="RELEASE_MANIFEST.json")


def _sign_file(path: Path) -> dict[str, Any]:
    os.environ.setdefault("AIPD_RELEASE_SIGNING_KEY", "aipd-os-dev-signing-key")
    signer = _import_module("sign_release")
    return signer.sign_release(str(path))


def cmd_build_release(args: argparse.Namespace) -> int:
    repo = _repo_root()
    version = args.version
    out_dir = Path(args.out) if args.out else repo / "releases" / version
    out_dir.mkdir(parents=True, exist_ok=True)

    # (a) 运行测试
    if not args.no_tests:
        print("== 步骤 1/6：运行测试 ==")
        rc = _run_pytest(repo)
        if rc != 0:
            print(f"测试失败（exit {rc}），中止发布。", file=sys.stderr)
            return rc

    # (b) 确定性评估
    print("== 步骤 2/6：运行确定性评估 ==")
    evals_out = out_dir / "evals"
    evals_rc = _run_evals_cli(repo, "evals/evals.json", "fake", str(evals_out),
                              0.1, None)
    if evals_rc != 0:
        print("确定性评估失败，中止发布。", file=sys.stderr)
        return evals_rc

    # (c) SBOM
    print("== 步骤 3/6：生成 SBOM ==")
    from aipd_os.security.sbom import generate_sbom
    generate_sbom(str(repo), str(out_dir / "sbom.json"))

    # (d) 构建发布产物 zip
    print("== 步骤 4/6：构建发布产物 ==")
    artifact = out_dir / f"aipd-os-{version}.zip"
    _build_artifact_zip(repo, artifact, out_dir)

    # (e) 逐文件 SHA-256 清单
    print("== 步骤 5/6：计算逐文件 SHA-256 ==")
    per_file = sorted(
        [{"path": p.as_posix(), "sha256": _sha256(repo / p)}
         for p in _collect_release_files(repo)],
        key=lambda e: e["path"],
    )
    sha_manifest = out_dir / "sha256_manifest.json"
    sha_manifest.write_text(
        json.dumps(per_file, ensure_ascii=False, indent=2), encoding="utf-8")

    # (f) 签名清单
    print("== 步骤 6/6：签名清单 ==")
    sig = _sign_file(sha_manifest)

    artifact_sha = _sha256(artifact)
    manifest = {
        "version": version,
        "artifact": artifact.name,
        "artifact_path": str(artifact),
        "sha256": artifact_sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": per_file,
    }
    (out_dir / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    log_event(_logger, "build_release", version=version, artifact=str(artifact),
              sha256=artifact_sha)
    print(f"发布产物：{artifact}")
    print(f"产物 SHA-256：{artifact_sha}")
    print(f"清单签名：{sig['signature']}")
    print(f"发布清单：{out_dir / 'RELEASE_MANIFEST.json'}")
    return 0


# --------------------------------------------------------------------------
# run  —— 运行监督器直到真实决策或步骤耗尽
# --------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    from aipd_os.state.db import AIPDStateDB

    # 校验项目是否存在；不存在则报错并返回非零退出码
    db = AIPDStateDB(args.db)
    known = {p["project_id"] for p in db.list_projects(DEFAULT_TENANT)}
    if args.project not in known:
        print(f"错误：项目 {args.project} 不存在。", file=sys.stderr)
        return 1

    sup = _import_module("aipd_supervisor").Supervisor(
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



# --------------------------------------------------------------------------
# 新增一键命令（Task 7, v5.1）：init/intake/resume/status/decide/manual/cad/
# industrialize/validate/release check/test/eval/package
# --------------------------------------------------------------------------
def _emit(args, result, prose):
    """统一输出：--json 时打印单个 JSON 对象，否则打印 prose 文本。"""
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    else:
        prose()


def _run_script_main(mod, argv):
    """以给定 argv 运行一个脚本模块的 main()，捕获 stdout，返回 (rc, stdout)。"""
    import contextlib
    import io
    old = sys.argv
    sys.argv = ["prog"] + list(argv)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = int(mod.main() or 0)
    finally:
        sys.argv = old
    return rc, buf.getvalue()


# ---- init：映射到 init-project（项目创建）----
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


# ---- intake：由一句自然语言提示初始化项目（确定性）----
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


# ---- resume：恢复/迁移 + 会话续接摘要 ----
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


# ---- status：所有者视图项目摘要（映射 project-summary）----
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


# ---- decide：裁定决策（映射 submit-decision；支持 --natural 自然语言回复）----
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


# ---- manual plan / manual generate（两级子命令）----
def _manual_state(args):
    if args.state:
        return args.state
    if args.db:
        return str(Path(args.db).with_suffix(".manual.json"))
    raise ValueError("缺少 --state 或 --db，无法定位手工批次状态文件。")


def _manual_ensure_state(args, state):
    mc = _import_module("manual_chain")
    if Path(state).exists():
        return mc
    from aipd_os.state.db import AIPDStateDB
    project_id = args.project or _resolve_project(AIPDStateDB(args.db))
    _silent(lambda: mc.cmd_init(_ns(cmd="init", state=state, project_id=project_id,
                                    minimum_pages=args.minimum_pages)))
    return mc


def _silent(fn):
    """运行 fn 并吞掉其 stdout（供 manual_chain 等内部命令使用）。"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()


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


# ---- CAD 门禁通用逻辑（复用 cad_maturity_gate）----
def _cad_gate_summary(cmg, manifest, target):
    runtime = manifest.get("runtime", "mesh")
    runtime_ceiling = cmg.RUNTIME_MAX.get(runtime, "C0")
    ceiling_idx = cmg.idx(runtime_ceiling)
    reached = None
    cumulative = []
    for level in cmg.LEVELS:
        cumulative += cmg.REQUIREMENTS[level]
        checks = {k: bool(cmg.present(cmg.val(manifest, k))) for k in cumulative}
        runtime_allowed = cmg.idx(level) <= ceiling_idx
        if all(checks.values()) and runtime_allowed:
            reached = level
        else:
            break
    faceted_capped = runtime == "faceted_brep"
    target_passed = reached is not None and cmg.idx(reached) >= cmg.idx(target)
    return {
        "runtime": runtime, "runtime_ceiling": runtime_ceiling,
        "faceted_brep_capped": faceted_capped, "reached_level": reached,
        "target_level": target, "target_passed": target_passed,
    }


# ---- cad preflight：运行时上限与成熟度约束检查 ----
def cmd_cad_preflight(args):
    cmg = _import_module("cad_maturity_gate")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    s = _cad_gate_summary(cmg, manifest, args.target)
    result = {"command": "cad preflight", "ok": True, **s}
    result["passed"] = s["runtime_ceiling"] and cmg.idx(s["runtime_ceiling"]) >= cmg.idx(args.target)

    def prose():
        print(f"运行时：{s['runtime']}；上限 {s['runtime_ceiling']}；目标 {args.target}。")
        print(f"运行时上限允许目标：{'是' if result['passed'] else '否'}")
        if s["faceted_brep_capped"]:
            print("faceted_brep 运行时成熟度封顶于 C1。")
    _emit(args, result, prose)
    return 0 if result["passed"] else 4


# ---- cad build：运行 CAD 成熟度门禁（映射 run-cad-chain）----
def cmd_cad_build(args):
    cmg = _import_module("cad_maturity_gate")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    s = _cad_gate_summary(cmg, manifest, args.target)
    result = {"command": "cad build", "ok": s["target_passed"], **s}

    def prose():
        print(f"CAD 成熟度：达到 {s['reached_level']}（运行时上限 {s['runtime_ceiling']}）")
        if s["faceted_brep_capped"]:
            print("faceted_brep 运行时成熟度封顶于 C1。")
        print(f"目标 {args.target} 通过：{'是' if s['target_passed'] else '否'}")
    _emit(args, result, prose)
    return 0 if s["target_passed"] else 4


# ---- industrialize：供应链 + 验证执行（端到端，绝不虚构）----
def cmd_industrialize(args):
    from aipd_os.supply_chain.analysis import analyze_stage, create_correction_tasks
    from aipd_os.supply_chain.lab import import_lab_csv
    from aipd_os.supply_chain.quotes import QuoteRegistry, parse_quote_file

    official_quotes = []
    quotes_note = None
    if args.quote:
        parsed = parse_quote_file(args.quote)
        registry = QuoteRegistry()
        for rec in parsed["records"]:
            q = registry.add_quote(supplier=rec["supplier"], part=rec["part"], data=rec,
                                   source_file=str(parsed.get("source", "")))
            official_quotes.append({
                "supplier": q.supplier, "part": q.part, "quote_id": q.quote_id,
                "unit_price": q.data["unit_price"], "status": q.status,
            })
    else:
        quotes_note = "未收到报价数据，未登记任何官方报价（不发散、不虚构）。"

    analysis = None
    correction_tasks = []
    lab_note = None
    if args.lab_data:
        stage = args.stage or "validation"
        lab = import_lab_csv(args.lab_data, stage)
        analysis = analyze_stage(lab["records"], stage)
        correction_tasks = create_correction_tasks(analysis, stage)
        pass_flag = analysis["total"] > 0 and analysis["failed"] == 0
        analysis = {"stage": stage, "total": analysis["total"],
                    "passed": analysis["passed"], "failed": analysis["failed"],
                    "items": analysis["items"], "pass_flag": pass_flag}
    else:
        lab_note = "未收到实验室数据，未执行阶段分析（不虚构）。"

    result = {"command": "industrialize", "ok": True,
              "official_quotes": official_quotes, "quotes_note": quotes_note,
              "analysis": analysis, "lab_note": lab_note,
              "correction_tasks": correction_tasks}

    def prose():
        print(f"官方报价：{len(official_quotes)} 条")
        for q in official_quotes:
            print(f"  · {q['supplier']}/{q['part']} {q['quote_id']} 单价 {q['unit_price']}")
        if quotes_note:
            print(quotes_note)
        if lab_note:
            print(lab_note)
        if analysis:
            print(f"阶段分析：共 {analysis['total']} 项，通过 {analysis['passed']}，失败 {analysis['failed']}"
                  f"；阶段通过：{'是' if analysis['pass_flag'] else '否'}")
            print(f"纠偏任务：{len(correction_tasks)} 个")
            for t in correction_tasks:
                print(f"  · {t['work_id']} {t['test_item']} -> {t['action']}")
    _emit(args, result, prose)
    return 0


# ---- validate：生产发布证据门禁（映射 production_release_gate）----
def cmd_validate(args):
    prg = _import_module("production_release_gate")
    rc, out = _run_script_main(prg, ["--manifest", args.manifest, "--target", args.target])
    try:
        gate = json.loads(out)
    except Exception:
        gate = {"passed": rc == 0}
    result = {"command": "validate", "ok": rc == 0, "target": args.target,
              "manifest": args.manifest, "passed": gate.get("passed", rc == 0),
              "gate": gate}
    _emit(args, result, lambda: print(out.rstrip()))
    return rc


# ---- audit：生成能力矩阵审计产物（repository_snapshot / capability_matrix）----
def cmd_audit(args):
    repo = Path(args.repo) if args.repo else _repo_root()
    out = Path(args.out)
    mod = _import_module("capability_matrix")
    summary = mod.generate(str(repo), str(out))
    result = {"command": "audit", "ok": True, **summary}
    _emit(args, result, lambda: print(json.dumps(summary, ensure_ascii=False, indent=2)))
    return 0


# ---- release check：版本真实性审计 + 生产发布门禁 + 通过性报告 ----
def cmd_release_check(args):
    repo = Path(args.repo) if args.repo else _repo_root()
    manifest_path = repo / "RELEASE_MANIFEST.json"
    if not manifest_path.exists():
        err = f"未找到 {manifest_path}，无法进行发布就绪检查；请先构建发布包。"
        if getattr(args, "json", False):
            print(json.dumps({"command": "release check", "ok": False, "error": err},
                             ensure_ascii=False))
        else:
            print(f"错误：{err}", file=sys.stderr)
        return 1

    audit = _import_module("audit_repo").audit_repo(repo)
    prg = _import_module("production_release_gate")
    rc, out = _run_script_main(prg, ["--manifest", str(manifest_path), "--target", args.target])
    try:
        gate = json.loads(out)
    except Exception:
        gate = {"passed": rc == 0}
    result = {"command": "release check", "ok": True, "repo": str(repo),
              "target": args.target, "audit": audit,
              "gate_passed": gate.get("passed", rc == 0), "gate": gate}
    _emit(args, result, lambda: print(json.dumps(result, ensure_ascii=False, indent=2)))
    return 0


# ---- test：运行测试套件（映射 run-tests）----
def cmd_test(args):
    rc = _run_pytest(_repo_root())
    result = {"command": "test", "ok": rc == 0, "exit_code": rc}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# ---- eval：运行评估套件（映射 run-evals）----
def cmd_eval(args):
    out = args.out or str(_repo_root() / "evals_out")
    rc = _run_evals_cli(_repo_root(), args.evals, args.provider, out,
                        args.threshold, None)
    result = {"command": "eval", "ok": rc == 0, "out": out}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


# ---- package：构建发布包（映射 build-release）----
def cmd_package(args):
    rc = cmd_build_release(args)
    result = {"command": "package", "ok": rc == 0, "version": args.version}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    return rc


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
# doctor —— 一键体检：依赖 / 配置 / 外部能力 / 数据库 / 对象存储 / 权限
# --------------------------------------------------------------------------
def _doctor_check(checks, name, status, detail):
    checks.append({"name": name, "status": status, "detail": detail})


def _check_repo_permissions(repo: Path) -> tuple:
    targets = [repo]
    from aipd_os.config import get_settings
    db_dir = get_settings().db_dir
    if db_dir and db_dir != "data":
        p = Path(db_dir)
        targets.append(p if p.is_dir() else p.parent)
    for t in targets:
        try:
            with tempfile.NamedTemporaryFile(dir=str(t), delete=True):
                pass
        except Exception as exc:  # noqa: BLE001
            return False, f"{t}: {exc}"
    return True, "writable"


def cmd_doctor(args):
    from aipd_os import __version__
    from aipd_os.config import get_settings

    repo = _repo_root()
    checks: list[dict[str, Any]] = []

    # 1) 包版本
    _doctor_check(checks, "version", "ok", __version__)

    # 2) 依赖可用性
    deps = {
        "jsonschema": "jsonschema",
        "PIL": "PIL",
        "reportlab": "reportlab",
        "requests": "requests",
        "yaml": "yaml",
        "cryptography": "cryptography",
    }
    for label, mod in deps.items():
        try:
            __import__(mod)
            status, detail = "ok", "import ok"
        except ImportError:
            status, detail = "missing", f"import failed: {mod}"
        _doctor_check(checks, f"dependency.{label}", status, detail)

    # 3) 配置
    s = get_settings()
    _doctor_check(checks, "config.mode", "ok", s.mode)
    _doctor_check(checks, "config.db_dir", "ok", s.db_dir)
    _doctor_check(checks, "config.log_level", "ok", s.log_level)
    _doctor_check(checks, "config.files",
                  "ok" if s.config_files else "info",
                  ", ".join(str(p) for p in s.config_files) or "none")

    # 4) 外部能力（配置 vs external_dependency）
    external_envs = {
        "vision_backend": "AIPD_VISION_BACKEND",
        "model_endpoint": "AIPD_EVAL_MODEL_ENDPOINT",
        "image_backend": "AIPD_IMGGEN_BACKEND",
        "mail": "AIPD_MAIL_PROVIDER",
    }
    for name, env in external_envs.items():
        val = os.environ.get(env, "").strip()
        status = "ok" if val else "external_dependency"
        detail = val or "not configured (external_dependency)"
        _doctor_check(checks, f"capability.{name}", status, detail)
    cq_ok = importlib.util.find_spec("cadquery") is not None
    _doctor_check(checks, "capability.cad_kernel",
                  "ok" if cq_ok else "external_dependency",
                  "cadquery available" if cq_ok else "cadquery not installed (external_dependency)")

    # 5) 数据库
    try:
        from aipd_os.state.db import AIPDStateDB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name
        try:
            db = AIPDStateDB(str(db_path))
            db.ensure_default_tenant()
            _doctor_check(checks, "database", "ok", "AIPDStateDB init + default tenant ok")
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                # noqa: EMPTY_EXCEPT - 清理探测用临时 db 文件：不存在/被占用时忽略
                pass
    except Exception as exc:  # noqa: BLE001
        _doctor_check(checks, "database", "fail", str(exc))

    # 6) 对象存储
    try:
        from aipd_os.state.objects import ObjectStore
        with tempfile.TemporaryDirectory() as td:
            store = ObjectStore(td)
            store.put("probe", "probe-key", b"probe")
            _doctor_check(checks, "object_store", "ok", "ObjectStore put ok")
    except Exception as exc:  # noqa: BLE001
        _doctor_check(checks, "object_store", "fail", str(exc))

    # 7) 权限
    perm_ok, perm_detail = _check_repo_permissions(repo)
    _doctor_check(checks, "permissions", "ok" if perm_ok else "fail", perm_detail)

    # 8) 凭据保护与脱敏：检查常见敏感环境变量是否已登记、是否已脱敏
    from aipd_os.security.secrets import SecretStore, is_sensitive_var
    store = SecretStore()
    for env in ("AIPD_EVAL_MODEL_ENDPOINT_API_KEY", "AIPD_MAIL_PASSWORD",
                "AIPD_IMGGEN_API_KEY", "AIPD_VISION_API_KEY",
                # v5.8.2 Commit 9：canonical 是 AIPD_ENCRYPTION_KEY；
                # deprecated alias 一并登记（迁移期兼容）。
                "AIPD_ENCRYPTION_KEY", "AIPD_DATA_ENCRYPTION_KEY"):
        store.register(env, "...")
    sensitive_envs = [e for e in os.environ if is_sensitive_var(e)]
    registered = [e for e in sensitive_envs if store.is_registered(e)]
    unregistered = [e for e in sensitive_envs if not store.is_registered(e)]
    exposed = [e for e in sorted(sensitive_envs) if store.exposed(e)]
    leaked = [e for e in exposed if not store.is_registered(e)]
    masking_on = all(store.masked(e) is not None and store.masked(e) != e
                     for e in exposed) if exposed else True
    if leaked:
        _doctor_check(checks, "security.credentials",
                      "fail",
                      f"unregistered sensitive env set: {', '.join(leaked)}")
    else:
        _doctor_check(checks, "security.credentials",
                      "ok" if (not sensitive_envs or masking_on) else "warn",
                      f"registered={len(registered)} unregistered={len(unregistered)} "
                      f"exposed={len(exposed)} masking={masking_on}")
    _doctor_check(checks, "security.masking",
                  "ok" if masking_on else "fail",
                  "credential masking active" if masking_on else "credential masking disabled")

    failed = [c for c in checks if c["status"] == "fail"]
    result = {"command": "doctor", "ok": not failed, "version": __version__, "checks": checks}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"AIPD-OS doctor v{__version__}")
        for c in checks:
            print(f"[{c['status']:>18}] {c['name']}: {c['detail']}")
        print("体检结论：" + ("通过（无硬失败）" if result["ok"] else f"存在 {len(failed)} 项硬失败"))
    return 0 if result["ok"] else 1


# --------------------------------------------------------------------------
# P2 所有者 UX：operate / dashboard / onboard / reset / recover
# --------------------------------------------------------------------------
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
        print(f"· 自动返工 {result['rework']['count']} 项，自动验收 {result['acceptance']['count']} 项，摘要已更新。")
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
    print("示例项目：")
    for e in r["examples"][:5]:
        print(f"  · {e['name']}：{e['goal']}")
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


# --------------------------------------------------------------------------
# ui —— 启动本地 Owner Web Console（aipd ui）
# --------------------------------------------------------------------------
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
