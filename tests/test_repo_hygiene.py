"""Repository Hygiene + Audit Freshness 测试（v5.7 Commit 1）。

覆盖：
- git ls-files 已跟踪的源文件中不得存在缓存/虚拟环境/字节码垃圾
  （.pyc / __pycache__ / .pytest_cache / .mypy_cache / .ruff_cache / .venv）；
- BUNDLE_MANIFEST.json（若存在）的 entries 不得含
  .pytest_cache / __pycache__ / *.pyc / *.dist-info / .venv* 垃圾条目；
- 发布打包逻辑（cli.commands._is_release_excluded / 清单脚本 _excluded）
  对垃圾路径全部拒绝、对正常源码路径放行，防止回归。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# 缓存/虚拟环境/字节码垃圾路径片段（任意嵌套层级命中即失败）
GARBAGE_PARTS = (
    ".pyc",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
)
# BUNDLE_MANIFEST entries 中不允许出现的模式（子串匹配）
BUNDLE_GARBAGE_SUBSTRINGS = (
    ".pytest_cache",
    "__pycache__",
    ".pyc",
    ".dist-info",
    ".venv",
)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def _tracked_files(repo: Path) -> list[str]:
    out = _git(repo, "ls-files")
    return [ln for ln in out.splitlines() if ln.strip()]


def test_tracked_sources_contain_no_cache_garbage():
    """git ls-files 已跟踪文件不得包含任何缓存/虚拟环境/字节码路径。"""
    tracked = _tracked_files(REPO_ROOT)
    assert tracked, "git ls-files 不应为空"
    offenders = [p for p in tracked if any(g in p.split("/") for g in GARBAGE_PARTS)]
    assert offenders == [], f"tracked 源文件中存在垃圾路径: {offenders}"


def test_bundle_manifest_entries_are_clean():
    """BUNDLE_MANIFEST.json（若存在）的 entries 不得含发布垃圾条目。"""
    bundle_manifest = REPO_ROOT / "BUNDLE_MANIFEST.json"
    if not bundle_manifest.is_file():
        return  # 无清单时跳过（不强制）
    data = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    assert entries, "BUNDLE_MANIFEST.json 不应为空清单"
    offenders = [
        e["path"] for e in entries
        if any(sub in e["path"] for sub in BUNDLE_GARBAGE_SUBSTRINGS)
    ]
    assert offenders == [], (
        f"BUNDLE_MANIFEST.json 含 {len(offenders)} 个垃圾条目: {offenders[:5]} ..."
    )


def test_bundle_manifest_points_to_existing_bundle():
    """BUNDLE_MANIFEST.json 的 bundle_path 必须真实存在（禁止伪造清单）。"""
    bundle_manifest = REPO_ROOT / "BUNDLE_MANIFEST.json"
    if not bundle_manifest.is_file():
        return
    data = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    bundle = Path(data.get("bundle_path") or "")
    if not bundle.is_absolute():
        bundle = REPO_ROOT / bundle
    assert bundle.is_file(), f"BUNDLE_MANIFEST.json 指向的 bundle 不存在: {bundle}"


def test_release_exclusion_logic_rejects_garbage():
    """发布打包排除逻辑：垃圾路径全部拒绝，正常路径放行。"""
    from aipd_os.cli.commands import _is_release_excluded

    garbage = [
        ".venv/bin/python",
        ".venv-ci/lib/site-packages/x.py",
        "src/foo/__pycache__/bar.cpython-39.pyc",
        "src/foo/bar.pyc",
        "docs/.pytest_cache/CACHEDIR.TAG",
        "evals/.ruff_cache/x",
        "scripts/.mypy_cache/y",
        "references/pkg-1.0.dist-info/METADATA",
        "src/aipd_os.egg-info/PKG-INFO",
    ]
    clean = [
        "src/aipd_os/state/server.py",
        "scripts/release_evidence.py",
        "docs/audit/BASELINE_REPORT.md",
        "tests/test_auth.py",
        "references/AIPD-OS-v4.0.docx",
        "assets/schemas/project.schema.json",
    ]
    for rel in garbage:
        assert _is_release_excluded(rel), f"应排除垃圾路径: {rel}"
    for rel in clean:
        assert not _is_release_excluded(rel), f"不应排除正常路径: {rel}"


def test_manifest_scripts_exclusion_logic_rejects_garbage():
    """清单生成脚本的排除逻辑：垃圾路径全部拒绝，正常路径放行。"""
    import regenerate_release_manifest as rrm
    import release_evidence as rev

    garbage = [
        ".venv/bin/python",
        ".venv-ci/lib/python3.9/site-packages/x.py",
        "src/aipd_os/state/__pycache__/server.cpython-39.pyc",
        "src/aipd_os/state/server.pyc",
        ".pytest_cache/v/cache/nodeids",
        "docs/.pytest_cache/README.md",
        "evals/.ruff_cache/0.4.0/index",
        "scripts/.mypy_cache/3.9/aipd_os",
        "references/pkg-2.0.dist-info/RECORD",
    ]
    clean = [
        "src/aipd_os/state/server.py",
        "scripts/release_evidence.py",
        "tests/test_auth.py",
        "README.md",
        "pyproject.toml",
    ]
    for rel in garbage:
        assert rrm._excluded(rel), f"regenerate_release_manifest 应排除: {rel}"
        assert rev._is_excluded(rel), f"release_evidence 应排除: {rel}"
    for rel in clean:
        assert not rrm._excluded(rel), f"regenerate_release_manifest 不应排除: {rel}"
        assert not rev._is_excluded(rel), f"release_evidence 不应排除: {rel}"
