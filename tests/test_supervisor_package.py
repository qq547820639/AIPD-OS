"""Change Set 12 Supervisor package 化测试（P1-1）。

覆盖：
- ``from aipd_os.supervisor import Supervisor`` 可用（最小集 re-export）；
- CLI 冒烟：init → add-work → run → status（subprocess 真实跑，输出合法 JSON）；
- AST 断言 src/aipd_os/supervisor 无 scripts import（runtime 包不依赖 scripts）；
- wrapper 模块可被 ``import aipd_supervisor``（scripts 加 sys.path）且与包内类一致。
"""
from __future__ import annotations

import ast
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SUPERVISOR_PKG = ROOT / "src" / "aipd_os" / "supervisor"
WRAPPER = SCRIPTS / "aipd_supervisor.py"


def _base_project(db: str) -> None:
    """创建监督器所需的单基项目（与现有测试同构：projects 表 + 一行）。"""
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects("
        "project_id TEXT PRIMARY KEY, name TEXT, goal TEXT, gate TEXT DEFAULT 'G0',"
        " status TEXT DEFAULT 'active', version TEXT, owner_policy TEXT,"
        " created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO projects VALUES('P1','t','g','G0','active',"
        "'0.1.0','{}','t','t')")
    conn.commit()
    conn.close()


def test_package_import_available():
    from aipd_os.supervisor import PHASES, WORK_STATUSES, Supervisor, main, parser
    assert callable(Supervisor)
    assert len(PHASES) == 9
    assert len(WORK_STATUSES) == 8
    assert callable(parser) and callable(main)


def test_cli_smoke(tmp_path):
    db = str(tmp_path / "s.db")
    _base_project(db)

    def cli(*args):
        r = subprocess.run(
            [sys.executable, str(WRAPPER), "--db", db, *args],
            capture_output=True, text=True)
        assert r.returncode == 0, f"cli failed: {args}\n{r.stdout}\n{r.stderr}"
        # run 会先输出 log_event 的单行 JSON；main() 的结果 JSON 是最后一个文档。
        docs = []
        decoder = json.JSONDecoder()
        i = 0
        while i < len(r.stdout):
            i = r.stdout.find("{", i)
            if i == -1:
                break
            try:
                obj, end = decoder.raw_decode(r.stdout[i:])
            except json.JSONDecodeError:
                i += 1
                continue
            docs.append(obj)
            i += end
        if not docs:
            raise AssertionError(f"stdout 无合法 JSON 结果：{r.stdout}")
        return docs[-1]

    out = cli("init")
    assert out == {"ok": True}
    out = cli("add-work", "--phase", "S1_theory", "--module", "research",
              "--title", "t", "--objective", "o", "--priority", "90")
    assert out["work_id"] == "W-001"
    out = cli("run", "--steps", "1")
    assert "results" in out and isinstance(out["results"], list)
    out = cli("status")
    assert out["work_counts"].get("internal_rework") == 1  # 无 capability_floor → 返工
    assert out["phases"] and len(out["phases"]) == 9


def test_no_scripts_import_in_package():
    """AST 断言：src/aipd_os/supervisor/** 不得 import scripts。"""
    files = list(SUPERVISOR_PKG.rglob("*.py"))
    assert files
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "scripts", (
                        f"{f}: 静态 import scripts ({alias.name})")
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "scripts", (
                    f"{f}: 静态 import scripts ({node.module})")


def test_wrapper_re_exports_package_identity():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import aipd_supervisor  # noqa: PLC2701
    finally:
        sys.path.remove(str(SCRIPTS))
    from aipd_os.supervisor import PHASES as PkgPhases
    from aipd_os.supervisor import Supervisor as PkgSupervisor
    from aipd_os.supervisor import main as pkg_main
    assert aipd_supervisor.Supervisor is PkgSupervisor
    assert aipd_supervisor.main is pkg_main
    assert PkgPhases == aipd_supervisor.PHASES
