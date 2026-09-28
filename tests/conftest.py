"""让测试在未安装包的情况下也能导入 src 目录下的源码。"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# 清单指纹的算法只许有一处定义（`scripts/release_fingerprint.py`）：生产侧（这里）、
# 验签侧（`closeout_verifier.py`）与写入侧（`release_evidence.py` 绑定前的那道闸）三方
# 必须同一把尺，否则「报告记的」与「验的」与「即将写出的」会各算各的。
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import release_fingerprint  # noqa: E402


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
    - ``generated_at``：ISO 时间；
    - ``source_manifest_fingerprint``：磁盘上 ``SOURCE_MANIFEST.json`` 那份**内容**的
      规范摘要（第 83 片）。前面三个字段说明「测的是哪个提交」，这一个说明「测的是哪一份
      清单」：提交号在重绑时不变，而清单会随刷新一同重写，只有把清单内容摘要抄进报告，
      验签才能区分「报告测的就是当前这份清单」与「清单在跑完之后又被重写」。
      读不出清单（文件缺失/坏 JSON）时**不写这个键**：缺字段是「生产者没记」，不是
      「值恰好为空」。缺席由两处一起处置，但都不是「判红」——验签侧
      ``closeout_verifier.report_fingerprint_recorded`` 读成**前提塌（退 2）**（判红会自锁：
      第 83 片实测），写入侧 ``release_evidence.preflight_report_vs_source``（第 84 片）
      则在**第一个字节落盘之前**直接拒绑这种报告并退 2。

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
    fp, _err = release_fingerprint.fingerprint_from_file(_ROOT / "SOURCE_MANIFEST.json")
    if fp:
        json_report["source_manifest_fingerprint"] = fp
