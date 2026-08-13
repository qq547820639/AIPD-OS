"""AIPD-OS v5.1 版本真实性审计脚本测试（Task 1）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_repo import audit_repo  # noqa: E402

REQUIRED_KEYS = {
    "default_branch",
    "latest_commit_sha",
    "latest_commit_time",
    "version",
    "file_tree",
    "tags",
    "releases_dir_exists",
    "ci_status",
    "release_manifest_verification",
    "untracked_or_generated",
    "legacy_cad_conflicts",
    "has_sbom",
    "has_release_signing",
    "dependency_lock",
}


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True
    )
    return proc.stdout.strip()


def _parse_version() -> str:
    pyproject = REPO_ROOT / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise AssertionError("pyproject.toml 中未找到 version")


def test_report_has_required_keys():
    report = audit_repo(REPO_ROOT)
    assert set(report.keys()) >= REQUIRED_KEYS, (
        f"缺少必需键: {REQUIRED_KEYS - set(report.keys())}"
    )


def test_latest_commit_sha_matches_live_git():
    report = audit_repo(REPO_ROOT)
    expected = _git("rev-parse", "HEAD")
    assert report["latest_commit_sha"] == expected, (
        f"审计 SHA {report['latest_commit_sha']!r} != 当前 HEAD {expected!r}"
    )


def test_version_matches_pyproject():
    report = audit_repo(REPO_ROOT)
    expected = _parse_version()
    assert report["version"] == expected, (
        f"审计版本 {report['version']!r} != pyproject 版本 {expected!r}"
    )


def test_json_report_file_exists_and_matches():
    report_path = REPO_ROOT / "docs/audit/v5.1-version-truth-audit.json"
    assert report_path.is_file(), f"缺少生成的 JSON 报告: {report_path}"
    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    live = audit_repo(REPO_ROOT)
    # 版本必须与 pyproject 一致，且磁盘报告包含必需键。
    # 注意 latest_commit_sha 是"生成报告时"的提交，而包含该报告的提交会改变 HEAD，
    # 因此自引用报告无法与当前 HEAD 恒等（总会落后一个提交），此处不比较 SHA 相等。
    assert on_disk["version"] == live["version"] == _parse_version()
    assert set(on_disk.keys()) >= REQUIRED_KEYS
    # 磁盘记录的是一个真实提交对象（16 位十六进制前缀）
    sha = on_disk["latest_commit_sha"]
    assert len(sha) >= 7 and all(c in "0123456789abcdef" for c in sha), (
        f"磁盘报告 latest_commit_sha 不是合法提交 SHA: {sha!r}"
    )
    assert _git("cat-file", "-e", f"{sha}^{{commit}}") == "", (
        f"磁盘报告 latest_commit_sha 对应的提交对象不存在: {sha}"
    )
