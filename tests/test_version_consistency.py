"""Change Set 10 版本单源一致性测试（P0-16）。

权威版本 5.6.0：pyproject.toml / aipd_os.__version__ / aipd_os.state.__version__
三处必须一致；README 首行标题含 v5.6.0；QUICKSTART 无 5.5.0 / v5.3 残留；
SECURITY / THREAT_MODEL / docs/architecture.md 无 v5.0 残留；CLI 版本字符串含 5.6。
历史版本引用（CHANGELOG、releases/ 历史目录）豁免。
"""
from __future__ import annotations

import re
from pathlib import Path

import aipd_os
import aipd_os.state

ROOT = Path(__file__).resolve().parent.parent
AUTHORITATIVE_VERSION = "5.6.0"


def test_pyproject_and_package_versions_align():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m, "pyproject.toml 缺少 version 字段"
    assert m.group(1) == AUTHORITATIVE_VERSION
    assert aipd_os.__version__ == AUTHORITATIVE_VERSION
    assert aipd_os.state.__version__ == AUTHORITATIVE_VERSION


def test_readme_first_line_contains_version():
    first = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
    assert f"v{AUTHORITATIVE_VERSION}" in first


def test_quickstart_no_stale_current_version():
    text = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
    assert "5.5.0" not in text, "QUICKSTART.md 不应残留 5.5.0"
    assert "v5.3" not in text, "QUICKSTART.md 不应残留 v5.3"


def test_security_threat_model_architecture_no_v5_0_residual():
    for name in ("SECURITY.md", "THREAT_MODEL.md", "docs/architecture.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "v5.0" not in text, f"{name} 不应残留 v5.0"


def test_cli_main_contains_current_version():
    text = (ROOT / "src/aipd_os/cli/main.py").read_text(encoding="utf-8")
    assert "5.6" in text
