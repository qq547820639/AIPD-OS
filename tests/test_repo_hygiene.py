"""Repository Hygiene + Audit Freshness 测试（v5.7 Commit 1 / v5.8.1 Commit 1）。

覆盖：
- git 模式（有 .git）：git ls-files 已跟踪的源文件中不得存在缓存/虚拟环境/
  字节码垃圾（.pyc / __pycache__ / .pytest_cache / .mypy_cache / .ruff_cache /
  .venv）；
- archive 模式（无 .git，如 GitHub source ZIP）：对当前 source tree 做等价
  hygiene 验证（__pycache__ / *.pyc / .pytest_cache / .mypy_cache /
  .ruff_cache / .venv 不得进入源码归档视角）；
- BUNDLE_MANIFEST.json（若存在）的 entries 不得含
  .pytest_cache / __pycache__ / *.pyc / *.dist-info / .venv* 垃圾条目；
- BUNDLE_MANIFEST.json 的 bundle_path 必须是相对路径（relocatable）；
- 发布打包逻辑（cli.commands._is_release_excluded / 清单脚本 _excluded）
  对垃圾路径全部拒绝、对正常源码路径放行，防止回归。
"""
from __future__ import annotations

import json
import os
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
# archive 模式下视为「非源码」而跳过的顶层生成/缓存/虚拟环境目录
# （这些目录本就不会进入 GitHub source ZIP / 发布源码归档）。
ARCHIVE_SKIP_DIRS = {
    ".git",
    ".venv",
    ".venv-ci",
    ".pytest",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "build",
    "dist",
    ".trae",
    ".release_keys",
    "evals_out",
    "node_modules",
}
# archive 模式下视为垃圾的文件后缀（任意嵌套层级命中即失败）
ARCHIVE_GARBAGE_SUFFIXES = (".pyc", ".pyo", ".dist-info", ".egg-info")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def _tracked_files(repo: Path) -> list[str]:
    out = _git(repo, "ls-files")
    return [ln for ln in out.splitlines() if ln.strip()]


def _archive_source_offenders(repo: Path) -> list[str]:
    """archive 模式（无 .git）：遍历 source tree，返回命中垃圾的 rel 路径。

    跳过 ARCHIVE_SKIP_DIRS（这些目录不进入源码归档）；其余路径中任何
    垃圾片段/后缀命中即视为 offender。
    """
    offenders: list[str] = []
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(repo)
        parts = rel.parts
        if any(part in ARCHIVE_SKIP_DIRS for part in parts):
            continue
        # 生成的打包元数据目录（*.egg-info / *.dist-info）不是源码，跳过；
        # 注意只匹配「目录段」（parts[:-1]），避免把 *.pyc 文件本身误跳过。
        if any(part.endswith(ARCHIVE_GARBAGE_SUFFIXES) for part in parts[:-1]):
            continue
        if any(g in parts for g in GARBAGE_PARTS):
            offenders.append(rel.as_posix())
            continue
        if rel.name.endswith(ARCHIVE_GARBAGE_SUFFIXES):
            offenders.append(rel.as_posix())
    return offenders


def _has_git(repo: Path) -> bool:
    """是否 git 工作树（GitHub source ZIP 等归档无 .git）。"""
    return (repo / ".git").exists()


def test_tracked_sources_contain_no_cache_garbage():
    """源码 hygiene：git 模式验证 ls-files；archive 模式（无 .git）等价验证。"""
    if not _has_git(REPO_ROOT):
        # 无 .git（如 GitHub source ZIP）：用 archive 模式验证
        offenders = _archive_source_offenders(REPO_ROOT)
        assert offenders == [], f"archive 模式源码中发现垃圾路径: {offenders}"
        return
    tracked = _tracked_files(REPO_ROOT)
    assert tracked, "git ls-files 不应为空"
    offenders = [p for p in tracked if any(g in p.split("/") for g in GARBAGE_PARTS)]
    assert offenders == [], f"tracked 源文件中存在垃圾路径: {offenders}"


def test_archive_mode_hygiene_passes_on_repo():
    """当前仓库在 archive 模式视角（等价无 .git）下 hygiene 通过。"""
    offenders = _archive_source_offenders(REPO_ROOT)
    assert offenders == [], f"archive 模式源码中发现垃圾路径: {offenders}"


def test_source_archive_hygiene_without_git(tmp_path):
    """模拟无 .git 环境（迷你 source tree，无任何 git 元数据）：
    archive 模式 hygiene 正确通过干净源码、识别垃圾源码文件。"""
    repo = tmp_path / "src_archive"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    assert not (repo / ".git").exists()
    # 干净源码 → 无 offender
    assert _archive_source_offenders(repo) == []
    # 源码目录内放入 .pyc / __pycache__ → archive 模式识别为垃圾
    (repo / "pkg" / "mod.pyc").write_bytes(b"\x00\x01")
    (repo / "pkg" / "__pycache__").mkdir()
    (repo / "pkg" / "__pycache__" / "mod.cpython-39.pyc").write_bytes(b"\x00")
    offenders = _archive_source_offenders(repo)
    assert any("mod.pyc" in o for o in offenders)
    assert any("__pycache__" in o for o in offenders)
    # 缓存/虚拟环境目录本身不计入源码 → 不误报
    (repo / ".venv").mkdir()
    (repo / ".venv" / "lib").mkdir()
    (repo / ".venv" / "lib" / "x.pyc").write_bytes(b"\x00")
    (repo / ".pytest_cache").mkdir()
    (repo / ".pytest_cache" / "CACHEDIR.TAG").write_text("x", encoding="utf-8")
    offenders2 = _archive_source_offenders(repo)
    assert not any(".venv" in o for o in offenders2)
    assert not any(".pytest_cache" in o for o in offenders2)


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


def test_bundle_manifest_is_relocatable():
    """BUNDLE_MANIFEST.json 的 bundle_path 必须不含绝对路径（可 relocatable）。

    v5.8.1 Commit 1：bundle_path 不再写开发机绝对路径，改为相对路径
    （如 build/release/aipd-os-5.6.0.zip）；bundle 字段保留文件名。
    """
    bundle_manifest = REPO_ROOT / "BUNDLE_MANIFEST.json"
    if not bundle_manifest.is_file():
        return  # 无清单时跳过（不强制）
    data = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    bundle_path = data.get("bundle_path") or ""
    assert bundle_path, "BUNDLE_MANIFEST.json 必须包含 bundle_path"
    assert not os.path.isabs(bundle_path), (
        f"bundle_path 必须是相对路径（relocatable），实际为绝对路径: {bundle_path!r}")
    assert not bundle_path.startswith(("/", "\\")), (
        f"bundle_path 不得以根分隔符开头: {bundle_path!r}")
    # bundle 字段保留文件名（与 bundle_path 的 basename 一致）
    bundle_name = data.get("bundle") or ""
    assert bundle_name, "BUNDLE_MANIFEST.json 必须包含 bundle 文件名"
    assert Path(bundle_path).name == bundle_name, (
        f"bundle_path basename 应等于 bundle 文件名: {bundle_path!r} vs {bundle_name!r}")


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


def test_ci_release_ready_depends_on_python_matrix():
    """v5.8.1 Commit 13（§42）：release-ready.needs 必须含 python-core-matrix。

    Python 3.12 核心矩阵失败也必须阻止发布（不能「宣称 >=3.9 却只验证 3.9」）。
    """
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.is_file(), "ci.yml 必须存在"
    text = ci.read_text(encoding="utf-8")
    # 文本/AST 检查：release-ready job 的 needs 列表含 python-core-matrix
    release_block = text.split("release-ready:", 1)[1]
    needs_block = release_block.split("needs:", 1)[1].split("runs-on:", 1)[0]
    assert "- python-core-matrix" in needs_block, \
        "release-ready.needs 必须包含 python-core-matrix"
    # 结构 sanity：python-core-matrix job 存在且矩阵含 3.12
    assert "python-core-matrix:" in text
    assert '"3.12"' in text
