"""迁移脚本的语句拆分与执行（无内部依赖的叶子模块）。

P2-M8 把 migrations 拆成 schema / helpers / definitions / runner 后，
``helpers`` 需要 ``_exec_script`` 而 ``runner`` 需要 ``MIGRATIONS``，
形成 ``definitions → helpers → runner → definitions`` 的导入环。
把这段工具下沉到本叶子模块即可断环，且不引入新的调用方向。
"""
from __future__ import annotations

import sqlite3


def split_statements(script: str) -> list[str]:
    """把多语句脚本拆成单语句列表（引号/注释感知，支持同一行多条语句）。

    用于替代 executescript 执行迁移脚本：executescript 会先隐式 COMMIT，
    使迁移无法纳入事务（非原子）；拆分后逐条 conn.execute，保持外层事务。
    """
    statements: list[str] = []
    buf = ""
    in_single = False
    in_double = False
    in_comment = False
    i = 0
    n = len(script)
    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        if in_comment:
            buf += ch
            if ch == "\n":
                in_comment = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            buf += "--"
            in_comment = True
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        buf += ch
        if ch == ";" and not in_single and not in_double:
            stmt = buf.strip()
            if stmt:
                statements.append(stmt)
            buf = ""
        i += 1
    if buf.strip():
        statements.append(buf.strip())
    return statements


def exec_script(conn: sqlite3.Connection, script: str) -> None:
    """事务内执行多语句脚本（不触发隐式 COMMIT）。"""
    for stmt in split_statements(script):
        if stmt:
            conn.execute(stmt)
