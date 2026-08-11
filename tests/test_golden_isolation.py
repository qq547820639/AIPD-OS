"""Change Set 13 golden E2E 证据隔离测试。

验证默认（无 ``AIPD_GOLDEN_RELEASE`` / ``AIPD_PIN_COMMIT``）运行 golden/manual
E2E 时**不污染** tracked 的 ``releases/golden-projects/``：
- 输出目录改为 pytest 临时目录；
- 仅 pin 模式（AIPD_GOLDEN_RELEASE=1 或 AIPD_PIN_COMMIT 已设置）才写 tracked 目录。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "releases" / "golden-projects"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _git_status_short(path: Path) -> str:
    r = subprocess.run(["git", "status", "--short", "--", str(path)],
                       cwd=str(ROOT), capture_output=True, text=True)
    return r.stdout


def _clear_pin_env() -> dict:
    env = dict(os.environ)
    env.pop("AIPD_GOLDEN_RELEASE", None)
    env.pop("AIPD_PIN_COMMIT", None)
    return env


def test_default_run_does_not_pollute_tracked_golden_dir():
    """默认（无 env）跑 golden e2e + manual e2e → releases/golden-projects/ 无改动。"""
    env = _clear_pin_env()
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         str(ROOT / "tests/test_golden_projects_e2e.py"),
         str(ROOT / "tests/test_manual_chain_e2e.py"),
         "-q"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, f"golden/manual e2e 失败：\n{r.stdout}\n{r.stderr}"
    status = _git_status_short(GOLDEN_DIR)
    assert status.strip() == "", f"releases/golden-projects/ 被污染：\n{status}"


def test_pin_mode_helper():
    """pin 模式开关：默认 False；AIPD_GOLDEN_RELEASE=1 或 AIPD_PIN_COMMIT 为 True。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "test_golden_projects_e2e",
        str(ROOT / "tests" / "test_golden_projects_e2e.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    enabled = mod._golden_release_enabled

    saved = dict(os.environ)
    for k in ("AIPD_GOLDEN_RELEASE", "AIPD_PIN_COMMIT"):
        os.environ.pop(k, None)
    try:
        assert enabled() is False
        os.environ["AIPD_GOLDEN_RELEASE"] = "1"
        assert enabled() is True
        os.environ.pop("AIPD_GOLDEN_RELEASE", None)
        os.environ["AIPD_PIN_COMMIT"] = "deadbeef"
        assert enabled() is True
    finally:
        os.environ.clear()
        os.environ.update(saved)
