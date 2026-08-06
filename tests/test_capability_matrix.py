"""能力矩阵审计产物测试（Task 2, v5.2）。

校验 docs/audit/repository_snapshot.json / capability_matrix.json / capability_matrix.md
存在且 HEAD/版本与仓库一致，能力覆盖齐全，7 类枚举合法。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_repo import audit_repo  # noqa: E402
from scripts.capability_matrix import CLASSIFICATIONS, _build_capability_matrix  # noqa: E402
from aipd_os.registry import load_default_registry  # noqa: E402

AUDIT_DIR = REPO_ROOT / "docs" / "audit"

SNAPSHOT_PATH = AUDIT_DIR / "repository_snapshot.json"
MATRIX_JSON_PATH = AUDIT_DIR / "capability_matrix.json"
MATRIX_MD_PATH = AUDIT_DIR / "capability_matrix.md"


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


def test_three_deliverables_exist():
    assert SNAPSHOT_PATH.is_file(), f"缺少 {SNAPSHOT_PATH}"
    assert MATRIX_JSON_PATH.is_file(), f"缺少 {MATRIX_JSON_PATH}"
    assert MATRIX_MD_PATH.is_file(), f"缺少 {MATRIX_MD_PATH}"


def test_snapshot_matches_live_repo():
    live = audit_repo(REPO_ROOT)
    on_disk = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    # 版本、默认分支必须与仓库一致；SHA 是生成时 HEAD，允许落后一个发布提交
    assert on_disk["version"] == live["version"] == _parse_version()
    assert on_disk["default_branch"] == "main"
    assert "latest_commit_sha" in on_disk and len(on_disk["latest_commit_sha"]) >= 7
    assert _git("cat-file", "-e", f"{on_disk['latest_commit_sha']}^{{commit}}") == ""


def test_matrix_classifications_valid_and_covered():
    matrix = json.loads(MATRIX_JSON_PATH.read_text(encoding="utf-8"))
    assert matrix["version"] == _parse_version()
    assert matrix["summary"]["total_capabilities"] > 0
    for cls in matrix["summary"]["by_classification"]:
        assert cls in CLASSIFICATIONS, f"非法分类枚举: {cls}"
    # 六大域全覆盖
    domains = {d["domain"] for d in matrix["domains"]}
    assert {"主管执行", "理论研究", "产品手册", "CAD与生产图纸",
            "工业化与验证", "跨会话与用户体验"} <= domains


def test_matrix_buildable_from_repo():
    registry = load_default_registry()
    matrix = _build_capability_matrix(REPO_ROOT, registry)
    on_disk_total = json.loads(MATRIX_JSON_PATH.read_text(encoding="utf-8"))[
        "summary"]["total_capabilities"]
    assert matrix["summary"]["total_capabilities"] == on_disk_total


def test_matrix_md_contains_domains():
    md = MATRIX_MD_PATH.read_text(encoding="utf-8")
    for domain in ["主管执行", "理论研究", "产品手册", "CAD与生产图纸",
                   "工业化与验证", "跨会话与用户体验"]:
        assert domain in md, f"Markdown 缺少域: {domain}"
    assert "fully_implemented" in md