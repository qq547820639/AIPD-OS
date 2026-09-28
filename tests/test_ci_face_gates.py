"""CI 的 lint/type/schema 三面，本地必须真跑（F-CI-SURFACE 第 91 片）。

为什么是常驻用例而不是"记得跑一下"：第 90 片的实测是
`ruff check src tests state_service` 从第 84 片起就在 CI 里当门禁，而本仓收口链
（全量 pytest + 发布门 + 收尾验签）一道都不读它的结果 ⇒ 一条 E501 红了六轮，
全量每次都 2700+ 绿。缺席的判据不会自己报警，它只是让"绿"这件事变小。

三条命令都从 `.github/workflows/ci.yml` 的 `lint`/`schema-validation` job 逐字抄来，
并与 `docs/audit/CI_SURFACE_REGISTER.json` 里"由本文件接住"的那几条**互相点名**：
册子多挂一条 ⇒ `test_register_points_here_and_only_here` 红；本文件多跑一条 ⇒ 同一条红。
缺工具的环境走 SKIP 而不是 FAIL（那是"未覆盖"，不是"红"）。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "audit" / "CI_SURFACE_REGISTER.json"
HERE = "tests/test_ci_face_gates.py"

# 本文件负责接住的 CI 命令（键必须与 ci.yml 里的逐字一致，由 `census` 那边对账）。
COVERED = {
    "ruff check src tests state_service": [sys.executable, "-m", "ruff", "check",
                                           "src", "tests", "state_service"],
    "mypy": [sys.executable, "-m", "mypy"],
    "python -m aipd_os.scripts.schema_check": [sys.executable, "-m",
                                               "aipd_os.scripts.schema_check"],
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900)


def test_ruff_face_is_clean() -> None:
    """CI 的 lint job 第一条：`ruff check src tests state_service`。"""
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("ruff 未安装——这一面在本环境未覆盖（不是绿）")
    proc = _run(COVERED["ruff check src tests state_service"])
    assert proc.returncode == 0, (
        f"CI 的 lint 面在本地复算就红（{proc.returncode}）："
        f"{(proc.stdout + proc.stderr)[-1500:]}")


def test_mypy_face_is_clean() -> None:
    """CI 的 lint job 第二条。`ci.yml` 那句「本地硬基线 ruff 0 / mypy 0」靠这条才成立。"""
    if importlib.util.find_spec("mypy") is None:
        pytest.skip("mypy 未安装——这一面在本环境未覆盖（不是绿）")
    proc = _run(COVERED["mypy"])
    assert proc.returncode == 0, (
        f"mypy 红（{proc.returncode}）：{(proc.stdout + proc.stderr)[-2500:]}")


def test_schema_check_face_is_clean() -> None:
    """CI 的 schema-validation job：模板与 schema 对得上。"""
    proc = _run(COVERED["python -m aipd_os.scripts.schema_check"])
    assert proc.returncode == 0, (
        f"schema_check 红（{proc.returncode}）：{(proc.stdout + proc.stderr)[-1500:]}")


def test_register_points_here_and_only_here() -> None:
    """《消费表》挂着"本文件接住"的那些命令，必须与本文件真跑的那几条**逐字相同**。

    两个方向都要：册子多一条＝有人声称这里守着一个不在这儿的判据（空头委托），
    本文件多一条＝跑了一道没人登记的门（下一轮改 CI 时谁也不知道它存在）。
    这条用例是"登记面 ↔ 执行面"的镜像，`ci_surface_census` 只核到文件级（消费方在不在、
    有没有用例），核不到"这个文件到底跑了哪几条命令"——那一格只能在这里钉。
    """
    if not REGISTER.is_file():
        pytest.skip("消费表还没生成（先跑 docs/audit/s91/build_ci_surface_register.py）")
    entries = json.loads(REGISTER.read_text(encoding="utf-8")).get("entries", [])
    claimed = {e["command"] for e in entries if HERE in (e.get("consumers") or [])}
    assert claimed == set(COVERED), (
        f"册子声称的与本文件实跑的不一致：只在册子 {sorted(claimed - set(COVERED))}；"
        f"只在实跑 {sorted(set(COVERED) - claimed)}")
    src = Path(__file__).read_text(encoding="utf-8")
    for cmd in claimed:
        assert cmd in src, f"{cmd!r} 在册子里挂着，但本文件里没有它的身影"
