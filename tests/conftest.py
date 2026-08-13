"""让测试在未安装包的情况下也能导入 src 目录下的源码。"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.hookimpl(optionalhook=True)
def pytest_json_modifyreport(json_report: dict) -> None:
    """为 pytest-json-report 注入发布证据所需的 freshness 字段。

    发布门禁（``production_release_gate._check_test_report``）要求机器测试
    报告绑定 ``source_commit``（防 STALE 报告冒充 release PASS 证据）。
    pytest-json-report 默认不生成这些字段，故在此 hook 注入：
    - ``source_commit``：优先读 ``AIPD_SOURCE_COMMIT`` 环境变量（发布流程
      在代码提交 + 证据提交分离时用其锚定被测试的代码提交），否则取当前
      git HEAD 完整 SHA；
    - ``package_version``：``aipd_os.__version__``；
    - ``generated_at``：ISO 时间。

    ``optionalhook=True``：pytest-json-report 仅在传 ``--json-report`` 时
    注册 ``pytest_json_modifyreport`` hookspec；不带该参数运行时本 hook
    无对应 hookspec，optionalhook 使其不致报 unknown hook 错误。
    """
    import os

    head = os.environ.get("AIPD_SOURCE_COMMIT", "")
    if not head:
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=15,
            ).stdout.strip()
        except Exception:  # noqa: BLE001 - git 不可用时留空，由门禁判 STALE
            head = ""
    if head:
        json_report["source_commit"] = head
    try:
        from aipd_os import __version__
    except Exception:  # noqa: BLE001
        __version__ = "unknown"
    json_report["package_version"] = __version__
    json_report["generated_at"] = datetime.now(timezone.utc).isoformat()
