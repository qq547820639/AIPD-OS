"""批次 2：legacy 命令 deprecation 与 ``--json`` 兼容测试。

10 个 legacy 命令保留功能不删除，执行时向 stderr 打印 ``DeprecationWarning``，
并补齐与对应 one-click 命令一致的 ``--json`` 输出。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aipd_os.cli import commands as cli_commands
from aipd_os.cli import main as cli_main

ROOT = Path(__file__).resolve().parent.parent

# legacy 命令 -> 对应主线命令（用于 DeprecationWarning match 校验）
LEGACY_TO_MAINLINE = {
    "init-project": "init",
    "restore-project": "resume",
    "run-supervisor": "run",
    "project-summary": "status",
    "submit-decision": "decide",
    "run-manual-chain": "manual generate",
    "run-cad-chain": "cad build",
    "run-tests": "test",
    "run-evals": "eval",
    "build-release": "package",
}


def _mock_heavy(monkeypatch) -> None:
    """把会真正跑 pytest/evals/打包的底层换成 no-op，避免测试套件递归。"""
    monkeypatch.setattr(cli_commands, "_run_pytest", lambda repo: 0)
    monkeypatch.setattr(cli_commands, "_run_evals_cli", lambda *a, **k: 0)
    monkeypatch.setattr(cli_commands, "_build_release_impl", lambda args: 0)

    fake_mc = SimpleNamespace(
        cmd_init=lambda *a, **k: None,
        cmd_plan_batches=lambda *a, **k: None,
        cmd_run_batch=lambda *a, **k: None,
    )
    real_import = cli_commands._import_module

    def _fake_import(name, subdir="scripts"):
        if name == "manual_chain":
            return fake_mc
        return real_import(name, subdir=subdir)

    monkeypatch.setattr(cli_commands, "_import_module", _fake_import)


def _init_db(tmp_path: Path) -> Path:
    db = tmp_path / "state.db"
    rc = cli_main.main([
        "init", "--db", str(db), "--project", "p1",
        "--name", "外骨骼", "--goal", "助力",
    ])
    assert rc == 0
    return db


def _cad_manifest(tmp_path: Path) -> Path:
    m = tmp_path / "cad.json"
    m.write_text(json.dumps({"runtime": "mesh"}), encoding="utf-8")
    return m


def _argv(legacy: str, tmp_path: Path) -> list[str]:
    db = _init_db(tmp_path)
    if legacy == "init-project":
        return ["init-project", "--db", str(db), "--project-id", "p2",
                "--name", "N", "--goal", "G"]
    if legacy == "restore-project":
        return ["restore-project", "--db", str(db)]
    if legacy == "run-supervisor":
        return ["run-supervisor", "--db", str(db), "--steps", "1"]
    if legacy == "project-summary":
        return ["project-summary", "--db", str(db)]
    if legacy == "submit-decision":
        return ["submit-decision", "--db", str(db),
                "--decision-id", "D1", "--choice", "A"]
    if legacy == "run-manual-chain":
        return ["run-manual-chain", "--db", str(db), "--batch-id", "b1",
                "--prompt", "p", "--output-dir", str(tmp_path / "out")]
    if legacy == "run-cad-chain":
        return ["run-cad-chain", "--manifest", str(_cad_manifest(tmp_path)),
                "--target", "C2"]
    if legacy == "run-tests":
        return ["run-tests"]
    if legacy == "run-evals":
        return ["run-evals", "--evals", str(tmp_path / "evals.json")]
    if legacy == "build-release":
        return ["build-release", "--version", "5.6.0", "--no-tests"]
    raise AssertionError(f"unknown legacy command: {legacy}")


@pytest.mark.parametrize("legacy", sorted(LEGACY_TO_MAINLINE))
def test_legacy_command_emits_deprecation_warning(legacy, tmp_path, monkeypatch):
    _mock_heavy(monkeypatch)
    with pytest.warns(DeprecationWarning, match=LEGACY_TO_MAINLINE[legacy]):
        cli_main.main(_argv(legacy, tmp_path))


@pytest.mark.parametrize("legacy", sorted(LEGACY_TO_MAINLINE))
def test_legacy_command_json_output(legacy, tmp_path, monkeypatch, capsys):
    _mock_heavy(monkeypatch)
    cli_main.main(_argv(legacy, tmp_path) + ["--json"])
    out = capsys.readouterr().out
    # 部分 legacy 命令内部会打印进度；JSON 结构恒为最后一行 stdout
    last_line = out.strip().splitlines()[-1]
    data = json.loads(last_line)
    assert "command" in data
    assert data["command"] == legacy


def test_usage_lists_legacy_and_mainline(capsys):
    rc = cli_main.main(["usage"])
    assert rc == 0
    out = capsys.readouterr().out
    # legacy 命令名
    for legacy in LEGACY_TO_MAINLINE:
        assert legacy in out
    # 主线命令名（含双词命令）
    for mainline in ("init", "resume", "run", "status", "decide",
                     "manual generate", "cad build", "test", "eval", "package"):
        assert mainline in out


def test_deprecation_warning_visible_via_real_entry(tmp_path):
    """QA 观察点 1 回归：DeprecationWarning 必须经真实入口进程在 stderr 可见。

    用 subprocess 以 ``.venv`` 的 Python 模拟 console-script 入口（非 ``__main__``
    帧），验证 ``main()`` 里的 ``warnings.simplefilter("default", DeprecationWarning)``
    生效——进程内 ``pytest.warns`` 测不出该 bug（默认 filter 会抑制非 __main__ 帧的
    DeprecationWarning）。
    """
    db = tmp_path / "state.db"
    code = (
        "import sys; "
        "from aipd_os.cli.main import main; "
        "sys.exit(main(sys.argv[1:]))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code,
         "init-project", "--db", str(db), "--project-id", "p1",
         "--name", "N", "--goal", "G"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "已废弃" in proc.stderr
