"""CLI 命令共享工具函数与常量。

从 ``commands.py`` 抽出，供 ``commands.py`` 及其拆分文件
（commands_manual / commands_cad / commands_release）共用，避免拆分后
出现循环导入。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

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


# 仓库布局不可用时（非 editable 安装 / 脱离仓库目录运行）的包内等价模块。
# 这些 scripts/ 顶层脚本已迁入 src/aipd_os/，scripts/ 下只剩薄兼容 wrapper，
# 因此可直接从已安装包解析同名能力（如 aipd init 只需 Supervisor 类）。
_PACKAGE_FALLBACK_MODULES = {
    "aipd_supervisor": "aipd_os.supervisor",
}


def _import_module(name: str, subdir: str = "scripts"):
    """按路径加载仓库内的顶层脚本模块（非包）。

    仓库内开发行为不变：优先按 ``<repo>/<subdir>/<name>.py`` 路径加载。
    仓库布局定位失败（如非 editable 安装、在任意目录运行 CLI）时回退：
    1. 包内等价模块（见 :data:`_PACKAGE_FALLBACK_MODULES`）；
    2. 环境中的同名顶层模块（``importlib.import_module(name)``）。
    都找不到才抛出与原 ``_repo_root()`` 相同的定位失败错误。
    """
    try:
        path = _repo_root() / subdir / f"{name}.py"
    except RuntimeError:
        path = None
    if path is not None and path.exists():
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(cast(Any, spec))
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    candidates = [_PACKAGE_FALLBACK_MODULES.get(name), name]
    for candidate in dict.fromkeys(c for c in candidates if c):
        try:
            return importlib.import_module(candidate)
        except ImportError:
            continue
    raise RuntimeError("无法定位仓库根目录")


def _ns(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _resolve_project(db, tenant: str = DEFAULT_TENANT) -> str:
    projects = db.list_projects(tenant)
    if not projects:
        raise ValueError("当前租户下没有项目；请先用 `aipd init-project` 初始化。")
    return cast(str, projects[0]["project_id"])


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
        # 进度/报告只走 stderr：--json 模式下 stdout 必须是纯净 JSON
        print(tail, file=sys.stderr)
    if r.stderr:
        print((r.stderr or "")[-500:], file=sys.stderr)
    print(f"测试退出码：{r.returncode}", file=sys.stderr)
    return r.returncode


def _run_evals_cli(repo: Path, evals: str, provider: str, out: str,
                   threshold: float, baseline: str | None,
                   json_mode: bool = False) -> int:
    from aipd_os.evals_runner.cli import build_parser as evals_parser
    argv = ["run", "--evals", evals, "--provider", provider, "--out", out,
            "--threshold", str(threshold)]
    if baseline:
        argv += ["--baseline", baseline]
    ns = evals_parser().parse_args(argv)
    if json_mode:
        # --json 模式下 stdout 必须是纯净 JSON：评估报告重定向到 stderr
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            return int(ns.func(ns))
    return int(ns.func(ns))


def _emit(args, result, prose):
    """统一输出：--json 时打印单个 JSON 对象，否则打印 prose 文本。"""
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        prose()


def _run_script_main(mod, argv):
    """以给定 argv 运行一个脚本模块的 main()，捕获 stdout，返回 (rc, stdout)。"""
    import contextlib
    import io
    old = sys.argv
    sys.argv = ["prog"] + list(argv)
    buf = io.StringIO()
    err_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err_buf):
            rc = int(mod.main() or 0)
    finally:
        sys.argv = old
    # 被调脚本的 stderr 转发到真实 stderr（不丢失错误信息，也不污染 stdout）
    if err_buf.getvalue():
        print(err_buf.getvalue().rstrip(), file=sys.stderr)
    return rc, buf.getvalue()


# --------------------------------------------------------------------------
# 发布包构建（cmd_build_release / cmd_package 共用）
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
    return bool(any(p.endswith(_RELEASE_EXCLUDE_SUFFIX) for p in parts))


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
    return cast(dict[str, Any], signer.sign_release(str(path)))


def _build_release_impl(args: argparse.Namespace) -> int:
    repo = _repo_root()
    version = args.version
    out_dir = Path(args.out) if args.out else repo / "releases" / version
    out_dir.mkdir(parents=True, exist_ok=True)

    # (a) 运行测试
    if not args.no_tests:
        print("== 步骤 1/6：运行测试 ==", file=sys.stderr)
        rc = _run_pytest(repo)
        if rc != 0:
            print(f"测试失败（exit {rc}），中止发布。", file=sys.stderr)
            return rc

    # (b) 确定性评估
    print("== 步骤 2/6：运行确定性评估 ==", file=sys.stderr)
    evals_out = out_dir / "evals"
    evals_rc = _run_evals_cli(repo, "evals/evals.json", "fake", str(evals_out),
                              0.1, None)
    if evals_rc != 0:
        print("确定性评估失败，中止发布。", file=sys.stderr)
        return evals_rc

    # (c) SBOM
    print("== 步骤 3/6：生成 SBOM ==", file=sys.stderr)
    from aipd_os.security.sbom import generate_sbom
    generate_sbom(str(repo), str(out_dir / "sbom.json"))

    # (d) 构建发布产物 zip
    print("== 步骤 4/6：构建发布产物 ==", file=sys.stderr)
    artifact = out_dir / f"aipd-os-{version}.zip"
    _build_artifact_zip(repo, artifact, out_dir)

    # (e) 逐文件 SHA-256 清单
    print("== 步骤 5/6：计算逐文件 SHA-256 ==", file=sys.stderr)
    per_file = sorted(
        [{"path": p.as_posix(), "sha256": _sha256(repo / p)}
         for p in _collect_release_files(repo)],
        key=lambda e: e["path"],
    )
    sha_manifest = out_dir / "sha256_manifest.json"
    sha_manifest.write_text(
        json.dumps(per_file, ensure_ascii=False, indent=2), encoding="utf-8")

    # (f) 签名清单
    print("== 步骤 6/6：签名清单 ==", file=sys.stderr)
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
    print(f"发布产物：{artifact}", file=sys.stderr)
    print(f"产物 SHA-256：{artifact_sha}", file=sys.stderr)
    print(f"清单签名：{sig['signature']}", file=sys.stderr)
    print(f"发布清单：{out_dir / 'RELEASE_MANIFEST.json'}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# CAD 门禁通用逻辑（复用 cad_maturity_gate）
# --------------------------------------------------------------------------
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
