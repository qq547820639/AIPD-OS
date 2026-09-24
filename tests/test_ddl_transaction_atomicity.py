"""store 建表必须在调用方事务里，不能被 ``executescript`` 隐式 COMMIT 掉。

``sqlite3.Cursor.executescript()`` 执行前先隐式 COMMIT。五个 store 的 ``__init__``
都在 ``ConnectionFactory.transaction()`` 里调它建表，于是：

1. 调用方在这同一个库上尚未提交的写，会被建表动作**静默提交**（回滚失效）；
2. 建表脚本自身不再是原子的——中途失败会留下半个 schema。

两种情形都由本文件的用例钉住。修法统一走 ``migrations.sqlsplit.exec_script``
（拆分后逐条 execute，不隐式提交）。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.state.connection import ConnectionFactory
from aipd_os.state.migrations.sqlsplit import exec_script, split_statements


def _store_ctors():
    from aipd_os.bom.store import BomStore
    from aipd_os.execution.closure_core import ClosureStore
    from aipd_os.execution.runs import RunStore
    from aipd_os.product_truth.store import ProductTruthStore
    from aipd_os.supervisor.supervisor import Supervisor

    return [
        ("BomStore", lambda p: BomStore(p)),
        ("RunStore", lambda p: RunStore(str(p))),
        ("ClosureStore", lambda p: ClosureStore(str(p))),
        ("ProductTruthStore", lambda p: ProductTruthStore(str(p))),
        ("Supervisor", lambda p: Supervisor(str(p))),
    ]


@pytest.mark.parametrize("name,ctor", _store_ctors(), ids=lambda v: v if isinstance(v, str) else "")
def test_store_construction_does_not_commit_the_callers_transaction(tmp_path, name, ctor):
    """在同一库、同一线程的外层事务里构造 store：调用方的写必须还能回滚。"""
    db = tmp_path / f"{name}.db"
    factory = ConnectionFactory(db)
    with factory.transaction() as c:
        c.execute("CREATE TABLE probe(id INTEGER PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="外层中止"), factory.transaction() as c:
        c.execute("INSERT INTO probe(id) VALUES (1)")
        ctor(db)                     # 建表副作用不得提交上面这条写
        raise RuntimeError("外层中止")
    with factory.connection() as c:
        assert c.execute("SELECT count(*) FROM probe").fetchone()[0] == 0, (
            f"{name}.__init__ 把调用方未提交的写隐式提交了")


@pytest.mark.parametrize("name,ctor", _store_ctors(), ids=lambda v: v if isinstance(v, str) else "")
def test_store_construction_still_creates_its_schema(tmp_path, name, ctor):
    """反向保障：改成事务内逐条执行后，schema 照样得建起来（不许改出静默不建表）。"""
    db = tmp_path / f"{name}_bare.db"
    ctor(db)
    with sqlite3.connect(str(db)) as c:
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables - {"probe"}, f"{name} 没有建出自己的表"


def test_exec_script_is_atomic_where_executescript_is_not(tmp_path):
    """配对对照：同样的「第二条语句报错」脚本，executescript 会留下第一条的表。

    这条用例同时证明机制成立（旧写法确实非原子）与修法有效（新写法回滚干净）。
    """
    script = ("CREATE TABLE first_ok(id INTEGER); "
              "CREATE TABLE second_bad(x INTEGER, x TEXT);")
    assert len(split_statements(script)) == 2, "拆分器没把它看成两条"

    old = tmp_path / "old.db"
    with pytest.raises(sqlite3.OperationalError), sqlite3.connect(str(old)) as c:
        try:
            c.executescript(script)
        except Exception:
            c.rollback()
            raise
    with sqlite3.connect(str(old)) as c:
        survived = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "first_ok" in survived, "executescript 的对照失效：旧写法居然是原子的"

    new = tmp_path / "new.db"
    factory = ConnectionFactory(new)
    with pytest.raises(sqlite3.OperationalError), factory.transaction() as c:
        exec_script(c, script)
    with factory.connection() as c:
        assert c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
