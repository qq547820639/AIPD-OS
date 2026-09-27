"""监督器执行（run_supervisor）测试。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from aipd_supervisor import Supervisor  # noqa: E402


def _make_sup(tmp_path):
    db = str(tmp_path / "sup.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects("
        "project_id TEXT PRIMARY KEY, name TEXT, goal TEXT, gate TEXT DEFAULT 'G0',"
        " status TEXT DEFAULT 'active', version TEXT, owner_policy TEXT,"
        " created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO projects VALUES('P1','t','g','G0','active','0.1.0','{}','t','t')"
    )
    conn.commit()
    conn.close()
    sup = Supervisor(db)
    sup.init_lifecycle()
    return sup


def test_run_supervisor_executes_doc_to_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path)
    wid = sup.add_work(
        "S1_theory", "research", "t", "o",
        capability_floor="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
    )
    results = sup.run_supervisor(steps=1)
    assert results and results[0]["action"] == "complete"
    counts = sup.status()["work_counts"]
    assert counts.get("complete", 0) == 1
    with sup.connect() as c:
        row = c.execute(
            "SELECT outputs_json FROM supervisor_work_items WHERE work_id=?", (wid,)
        ).fetchone()
    assert "markdown" in row[0]


def test_run_supervisor_owner_required_returns_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path)
    sup.add_work(
        "S5_cad", "release_gate", "release", "o",
        capability_floor="doc.generate",
        owner_required=True,
        inputs={"title": "T"},
    )
    results = sup.run_supervisor(steps=1)
    assert results and results[0]["action"] == "decision"
    assert "decision_id" in results[0]["decision"]
    counts = sup.status()["work_counts"]
    assert counts.get("complete", 0) == 0
    assert counts.get("blocked_decision", 0) == 1


def test_run_supervisor_no_work_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path)
    assert sup.run_supervisor(steps=1) == []


def test_mark_stale_exact_dependency_match(tmp_path):
    """回归：_mark_stale 必须按依赖列表精确匹配，不得用 LIKE 子串误伤
    （此前 "%W-001%" 会命中 W-0010 等前缀型 ID）。"""
    sup = _make_sup(tmp_path)
    w1 = sup.add_work("S1_theory", "research", "t1", "o1")
    w2 = sup.add_work("S1_theory", "research", "t2", "o2",
                      depends=[w1])
    w3 = sup.add_work("S2_product_definition", "product", "t3", "o3")
    # w3 不依赖 w1
    sup.complete(w2, {"x": 1})
    # 直接构造一个依赖关系为 [w1] 的行与一个相似前缀行
    with sup.connect() as c:
        c.execute("UPDATE supervisor_work_items SET status='complete' "
                  "WHERE work_id=?", (w3,))
    stale = sup._mark_stale(w1)
    assert w2 in stale["stale"]
    assert w3 not in stale["stale"]


def test_execution_suite_is_constructed_in_exactly_one_place():
    """执行套件（registry → RunStore → router）在 `supervisor.py` 里只许有一处构造。

    第 71 片为了接返工执行器把这三步抄了第二遍，第 72 片读回来时已经漂了两处
    （日志器名、作用域来源）。这类"两处各写一遍"不会让任何现有用例变红，
    所以用 AST 数构造点：多一处就红，且**少一处也红**（防止把共用口子删了还自绿）。
    """
    import ast

    src = (ROOT / "src/aipd_os/supervisor/supervisor.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    routers = [n.lineno for n in ast.walk(tree)
               if isinstance(n, ast.Call)
               and ((isinstance(n.func, ast.Name) and n.func.id == "ExecutionRouter")
                    or (isinstance(n.func, ast.Attribute)
                        and n.func.attr == "ExecutionRouter"))]
    registries = [n.lineno for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "build_registry"]
    runs = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "router"]
    assert len(routers) == 1, f"ExecutionRouter 构造点应恰好一处：{routers}"
    assert len(registries) == 1, f"build_registry 调用点应恰好一处：{registries}"
    assert len(runs) == 1, f"router.run(...) 调用点应恰好一处（两处就有第二套 context）：{runs}"


def test_rerun_uses_the_work_items_own_scope(tmp_path, monkeypatch):
    """重跑一条别的项目的工作项 ⇒ run 记在项目自己的作用域，不是 Supervisor 构造参数那个。

    这是第 72 片顺手改掉的作用域 bug 的反证：旧写法用 `self.project_id()`，
    CLI 传进来的 project 与工作项不一致时，会把证据与 run 记到错的项目下。
    """
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup_owner = _make_sup(tmp_path)                     # 项目 P1
    wid = sup_owner.add_work(
        "S2_product_definition", "doc", "t", "o",
        capability_floor="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]})
    sup_other = _make_sup_other_project(tmp_path)       # 构造参数指向别的项目
    out = sup_other.rerun_for_rework(wid)
    assert out is not None, "重跑应当成功"
    assert out["record"].project_id == "P1", out["record"].project_id
    assert out["record"].run_id, out["record"]


def _make_sup_other_project(tmp_path):
    """同一个库，但 Supervisor 的默认项目指向一个不存在的工作项项目。"""
    return Supervisor(str(tmp_path / "sup.db"), project_id="P-ZZZ")
