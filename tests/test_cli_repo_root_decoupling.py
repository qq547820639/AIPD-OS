"""CLI 运行时与源码仓库布局解耦回归测试。

非 editable 安装 / 脱离仓库目录运行时，``_repo_root()`` 无法定位
pyproject.toml。``_import_module`` 必须回退到已安装包解析
（如 aipd_supervisor → aipd_os.supervisor），保证 ``aipd init --db X``
等纯 DB 命令在任意目录可用；确实无法解析的模块仍报原
"无法定位仓库根目录" 错误。仓库内开发行为（路径优先）保持不变。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aipd_os.cli import _helpers as cli_helpers
from aipd_os.cli import main as cli_main
from aipd_os.supervisor import Supervisor

ROOT = Path(__file__).resolve().parent.parent


def _no_repo_root():
    raise RuntimeError("无法定位仓库根目录")


# ---------------------------------------------------------------------------
# 1) 仓库布局可用时行为不变：优先按路径加载 scripts/ 顶层脚本
# ---------------------------------------------------------------------------
def test_import_module_prefers_repo_layout(monkeypatch):
    # 工作树中 pyproject.toml 可能被移除（如非 editable 安装），故显式钉住
    # _repo_root 指向真实仓库根，只验证"仓库布局可用时路径优先"这一行为契约。
    monkeypatch.setattr(cli_helpers, "_repo_root", lambda: ROOT)
    mod = cli_helpers._import_module("aipd_supervisor")
    assert mod.__file__.replace("\\", "/").endswith("scripts/aipd_supervisor.py")
    assert mod.Supervisor is Supervisor


# ---------------------------------------------------------------------------
# 2) 无仓库根时回退到已安装包解析同名能力
# ---------------------------------------------------------------------------
def test_import_module_fallback_to_installed_package(monkeypatch):
    monkeypatch.setattr(cli_helpers, "_repo_root", _no_repo_root)
    mod = cli_helpers._import_module("aipd_supervisor")
    assert mod.Supervisor is Supervisor


# ---------------------------------------------------------------------------
# 3) 无仓库根且包内/环境中都解析不到时，仍报原定位错误
# ---------------------------------------------------------------------------
def test_import_module_unknown_module_still_raises(monkeypatch):
    monkeypatch.setattr(cli_helpers, "_repo_root", _no_repo_root)
    with pytest.raises(RuntimeError, match="无法定位仓库根目录"):
        cli_helpers._import_module("no_such_script_xyz")


# ---------------------------------------------------------------------------
# 4) 验收标准：`aipd init --db X` 在无法定位仓库根时可用
# ---------------------------------------------------------------------------
def test_cmd_init_works_without_repo_root(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_helpers, "_repo_root", _no_repo_root)
    db = tmp_path / "state.db"
    rc = cli_main.main([
        "init", "--db", str(db), "--project", "p1",
        "--name", "外骨骼", "--goal", "助力",
    ])
    assert rc == 0
    assert db.exists()
