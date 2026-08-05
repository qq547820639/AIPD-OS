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
# 命令分发表
# --------------------------------------------------------------------------
COMMAND_FUNCS: Dict[str, Any] = {
    "init-project": cmd_init_project,
    "restore-project": cmd_restore_project,
    "run-supervisor": cmd_run_supervisor,
    "project-summary": cmd_project_summary,
    "submit-decision": cmd_submit_decision,
    "run-manual-chain": cmd_run_manual_chain,
    "run-cad-chain": cmd_run_cad_chain,
    "run-tests": cmd_run_tests,
    "run-evals": cmd_run_evals,
    "build-release": cmd_build_release,
}

PLANNED_COMMANDS = list(COMMAND_FUNCS.keys())

__all__ = ["COMMAND_FUNCS", "PLANNED_COMMANDS"]