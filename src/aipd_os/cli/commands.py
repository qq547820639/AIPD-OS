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
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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
    # 同时在数据库上初始化监督器生命周期（共享同一 db 文件）
    sup = _import_module("aipd_supervisor").Supervisor(args.db)
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

    sup = _import_module("aipd_supervisor").Supervisor(args.db)
    results = sup.run_supervisor(steps=args.steps or 1)
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
        db = AIPDStateDB(args.db)
        pid = _resolve_project(db)
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
    cumulative: List[str] = []
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
def _release_include_roots(repo: Path) -> List[Path]:
    roots: List[Path] = []
    for name in ["src", "scripts", "docs", "references", "evals"]:
        p = repo / name
        if p.exists():
            roots.append(p)
    schemas = repo / "assets" / "schemas"
    if schemas.exists():
        roots.append(schemas)
    return roots


def _collect_release_files(repo: Path) -> List[Path]:
    files: List[Path] = []
    for root in _release_include_roots(repo):
        for f in sorted(root.rglob("*")):
            if f.is_file():
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
                if f.is_file():
                    zf.write(f, arcname=f.relative_to(repo).as_posix())
        zf.write(manifest_placeholder, arcname="RELEASE_MANIFEST.json")


def _sign_file(path: Path) -> Dict[str, Any]:
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

    sup = _import_module("aipd_supervisor").Supervisor(args.db)
    max_steps = args.steps or (100 if args.until_decision else 1)
    results: List[Dict[str, Any]] = []
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
    sup = _import_module("aipd_supervisor").Supervisor(args.db)
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
    sup = _import_module("aipd_supervisor").Supervisor(args.db)
    sup.init_lifecycle()
    result = {"command": "intake", "ok": True, "project_id": project_id,
              "name": name, "goal": goal, "db": args.db}

    def prose():
        print(f"已根据需求初始化项目：{name}（{project_id}）")
        print(f"目标：{goal}")
        print("监督器生命周期已就绪。")
    _emit(args, result, prose)
    return 0


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
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    view = OwnerView(db, tenant_id=DEFAULT_TENANT)
    pid = args.project or _resolve_project(db)

    if args.markdown:
        text = view.to_markdown(project_id=pid)
        result = {"command": "status", "ok": True, "project_id": pid, "markdown": text}
        _emit(args, result, lambda: print(text))
        return 0

    v = view.owner_update(pid)
    ps = v["project_summary"]
    result = {"command": "status", "ok": True, "project_id": pid, "summary": v}

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


# ---- decide：裁定决策（映射 submit-decision）----
def cmd_decide(args):
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = args.project or _resolve_project(db)
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
# 命令分发表
# --------------------------------------------------------------------------
COMMAND_FUNCS: Dict[str, Any] = {
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
    "release check": cmd_release_check,
    "test": cmd_test,
    "eval": cmd_eval,
    "package": cmd_package,
}

PLANNED_COMMANDS = list(COMMAND_FUNCS.keys())

__all__ = ["COMMAND_FUNCS", "PLANNED_COMMANDS"]