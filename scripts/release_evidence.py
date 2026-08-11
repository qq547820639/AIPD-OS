"""发布证据体系：生成 Source / Bundle / Provenance 三份独立证据 (P0-1)。

三份证据都以最终 tag SHA（``git rev-parse HEAD``）为锚点，互不依赖、互不自引用：

- ``SOURCE_MANIFEST.json``  —— 只覆盖“确定的源文件集合”（git ls-files 已跟踪文件），
  排除所有“生成后自身改变”的文件（本证据自身、BUNDLE_MANIFEST、PROVENANCE、
  RELEASE_MANIFEST、releases/、build/、dist/、*.zip、*.step 等）。
- ``BUNDLE_MANIFEST.json``  —— 对最终发布压缩包逐条计算 sha256，记录 bundle 自身摘要、
  bundle 文件名与每个条目的 path/size/sha256。
- ``PROVENANCE.json``       —— 记录 source_commit / build_environment / build_time /
  dependency_lock / test_report / bundle_hash。

仅依赖标准库 + ``cryptography``（用于 build_environment 的包版本信息，非强制）。

用法：
    python scripts/release_evidence.py --repo . \
        --bundle releases/aipd-os-5.6.0.zip --version 5.6.0 \
        --test-report .pytest/lastreport.json --out .
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# SOURCE_MANIFEST 需要排除的“生成后自身改变”的文件/目录
SOURCE_EXCLUDE = {
    "SOURCE_MANIFEST.json",
    "BUNDLE_MANIFEST.json",
    "PROVENANCE.json",
    "RELEASE_MANIFEST.json",
}
SOURCE_EXCLUDE_PREFIXES = (
    "releases/",
    "build/",
    "dist/",
    ".venv/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "__pycache__/",
    "src/aipd_os.egg-info/",
    # 审计报告是“生成式证据”（内容依赖清单自身），也属于会随生成而自变的一类，
    # 排除它们以打破“清单↔审计报告”循环哈希，保证 hash_mismatch 可归零。
    "docs/audit/",
)
SOURCE_EXCLUDE_SUFFIXES = (".zip", ".step", ".tar.gz", ".whl", ".egg",
                           ".sig", ".sha256")
# 依赖锁文件名（Provenance 用）
LOCKFILES = ("requirements.txt", "requirements-quality.txt", "requirements-dev.txt",
             "requirements-lock.txt", "Pipfile.lock", "poetry.lock", "uv.lock")


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _run_git(repo: Path, args: list) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=str(repo),
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _tracked_files(repo: Path) -> list[str]:
    out = _run_git(repo, ["ls-files"])
    return [ln for ln in out.splitlines() if ln.strip()]


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_excluded(rel: str) -> bool:
    if rel in SOURCE_EXCLUDE:
        return True
    if rel.startswith(SOURCE_EXCLUDE_PREFIXES):
        return True
    if rel.endswith(SOURCE_EXCLUDE_SUFFIXES):
        return True
    return False


# --------------------------------------------------------------------------
# 1) SOURCE_MANIFEST
# --------------------------------------------------------------------------
def generate_source_manifest(repo: Path, source_commit: str | None = None) -> dict:
    """对 git ls-files 已跟踪文件逐条计算 size + sha256（排除生成后自身改变的文件）。

    source_commit 默认取当前 HEAD；传入显式值（``--source-commit``）时用于在
    最终提交尚未产生前预置最终 tag SHA，从而打破“证据自身随提交而改变”的自引用。
    """
    files: list[dict] = []
    for rel in _tracked_files(repo):
        if _is_excluded(rel):
            continue
        p = repo / rel
        if not p.is_file():
            continue
        files.append({"path": rel, "size": p.stat().st_size,
                      "sha256": _sha256_path(p)})
    files.sort(key=lambda e: e["path"])
    return {
        "name": "AIPD-OS source manifest",
        "version": _parse_version(repo),
        "source_commit": source_commit or _default_source_commit(repo),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverage": "git ls-files tracked sources (generated/self-changing files excluded)",
        "files": files,
    }


def _parse_version(repo: Path) -> str:
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return ""
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _default_source_commit(repo: Path) -> str:
    """返回当前 HEAD 的完整 SHA；失败时返回空串。"""
    return _run_git(repo, ["rev-parse", "HEAD"])


# --------------------------------------------------------------------------
# 2) BUNDLE_MANIFEST
# --------------------------------------------------------------------------
def generate_bundle_manifest(bundle: Path) -> dict:
    """对发布压缩包逐条计算条目 sha256，记录 bundle 自身摘要。"""
    if not bundle.is_file():
        raise FileNotFoundError(f"bundle not found: {bundle}")
    bundle_sha = _sha256_path(bundle)
    entries: list[dict] = []
    if zipfile.is_zipfile(str(bundle)):
        with zipfile.ZipFile(str(bundle)) as zf:
            total = 0
            for info in zf.infolist():
                data = zf.read(info.filename)
                total += len(data)
                entries.append({
                    "path": info.filename,
                    "size": info.file_size,
                    "sha256": _sha256_bytes(data),
                })
    else:
        # 非 zip（如 tar.gz）退化为单条目：整个包自身
        entries.append({"path": bundle.name, "size": bundle.stat().st_size,
                        "sha256": bundle_sha})
    entries.sort(key=lambda e: e["path"])
    return {
        "name": "AIPD-OS bundle manifest",
        "bundle": bundle.name,
        "bundle_path": str(bundle),
        "bundle_sha256": bundle_sha,
        "bundle_size": bundle.stat().st_size,
        "entry_count": len(entries),
        "entries": entries,
    }


# --------------------------------------------------------------------------
# 3) PROVENANCE
# --------------------------------------------------------------------------
def _build_environment() -> dict:
    env = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os": f"{platform.system()} {platform.release()}",
        "platform": platform.platform(),
        "packages": {},
    }
    for pkg in ("cryptography", "aipd_os", "jsonschema"):
        try:
            mod = __import__(pkg)
            env["packages"][pkg] = getattr(mod, "__version__", "unknown")
        except Exception:
            env["packages"][pkg] = "not-installed"
    return env


def _dependency_lock(repo: Path) -> dict:
    lock: dict = {"files": {}, "pip_freeze": None}
    try:
        freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                                capture_output=True, text=True, timeout=60)
        if freeze.returncode == 0:
            lock["pip_freeze"] = freeze.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        # noqa: EMPTY_EXCEPT - pip freeze 尽力而为：失败仅置 pip_freeze=None
        pass
    for name in LOCKFILES:
        p = repo / name
        if p.is_file():
            lock["files"][name] = _sha256_path(p)
    return lock


def _parse_pytest_report(path: Path) -> dict:
    """解析 pytest 机器可读 JSON 报告；失败则返回不可用信息（不硬编码）。"""
    if not path.is_file():
        return {"present": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": True, "path": str(path), "parsed": False}
    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    passed = summary.get("passed")
    failed = summary.get("failed")
    total = summary.get("total")
    if passed is None and failed is None and total is None:
        # 兼容 pytest <8 的 collect 统计
        total = (data.get("total") if isinstance(data, dict) else None) or None
    # pytest-json-report 的 summary 不含 failed 键，需由 total - passed - skipped 推导
    if failed is None and isinstance(total, int):
        skipped = summary.get("skipped")
        if isinstance(passed, int) and isinstance(skipped, int):
            failed = max(total - passed - skipped, 0)
        elif isinstance(passed, int):
            failed = max(total - passed, 0)
    return {
        "present": True,
        "path": str(path),
        "parsed": True,
        "sha256": _sha256_path(path),
        "passed": passed,
        "failed": failed,
        "total": total,
        "errors": summary.get("error") if isinstance(summary, dict) else None,
    }


def generate_provenance(repo: Path, bundle: Path | None = None,
                        test_report: Path | None = None,
                        source_commit: str | None = None) -> dict:
    """生成 Provenance 证据。"""
    bundle_hash = None
    if bundle is not None and bundle.is_file():
        bundle_hash = _sha256_path(bundle)
    return {
        "name": "AIPD-OS provenance",
        "version": _parse_version(repo),
        "source_commit": source_commit or _default_source_commit(repo),
        "build_environment": _build_environment(),
        "build_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dependency_lock": _dependency_lock(repo),
        "test_report": _parse_pytest_report(test_report) if test_report is not None
                       else {"present": False},
        "bundle": bundle.name if bundle is not None else None,
        "bundle_hash": bundle_hash,
    }


# --------------------------------------------------------------------------
# 写出三份文件
# --------------------------------------------------------------------------
def write_evidence(repo: Path, out_dir: Path, version: str,
                   bundle: Path | None, test_report: Path | None,
                   source_commit: str | None = None) -> dict:
    """生成并写出三份证据文件，返回 (path -> manifest dict)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    source = generate_source_manifest(repo, source_commit)
    source["version"] = version
    prov = generate_provenance(repo, bundle, test_report, source_commit)
    prov["version"] = version

    results = {}
    bundle_manifest = None
    if bundle is not None and bundle.is_file():
        bundle_manifest = generate_bundle_manifest(bundle)
        bundle_manifest["version"] = version
        (out_dir / "BUNDLE_MANIFEST.json").write_text(
            json.dumps(bundle_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        results["BUNDLE_MANIFEST.json"] = bundle_manifest

    (out_dir / "SOURCE_MANIFEST.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "PROVENANCE.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    results["SOURCE_MANIFEST.json"] = source
    results["PROVENANCE.json"] = prov
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AIPD-OS 发布证据生成（Source/Bundle/Provenance）")
    ap.add_argument("--repo", default=str(_REPO), help="仓库根目录")
    ap.add_argument("--out", default="", help="证据输出目录（默认仓库根）")
    ap.add_argument("--version", default="5.6.0")
    ap.add_argument("--bundle", default="", help="发布压缩包路径")
    ap.add_argument("--test-report", default="", help="pytest 机器可读 JSON 报告路径")
    ap.add_argument("--source-commit", default="",
                    help="最终 tag SHA（预置到 SOURCE_MANIFEST/PROVENANCE 的 source_commit，"
                         "默认为当前 HEAD）")
    a = ap.parse_args(argv)

    repo = Path(a.repo).resolve()
    out = Path(a.out).resolve() if a.out else repo
    bundle = Path(a.bundle).resolve() if a.bundle else None
    test_report = Path(a.test_report).resolve() if a.test_report else None
    source_commit = a.source_commit or None

    results = write_evidence(repo, out, a.version, bundle, test_report, source_commit)
    for name in results:
        print(f"wrote: {out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())