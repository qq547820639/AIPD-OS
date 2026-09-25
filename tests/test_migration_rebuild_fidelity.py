"""第 36 片：迁移的「重建保真」常驻尺子。

为什么要有这把尺子：拷贝重建是这族修复唯一的手段（V1 冻结文本改不得，SQLite 也没有
`ALTER COLUMN`），而重建最容易出的事故不是「没改成」，是**顺手改了别的东西**——
列清单少一根、某一列的 `NOT NULL` 或默认值在搬运中掉掉。
第 35 片为了写 v22 的 DDL 模板，第一次把 HEAD 实形与「当初声明它的那句迁移文本」逐列对账，
当场报出一条「strength 掉了默认值」的假缺陷（真相是 v9 有意改的），
过程记在 `docs/audit/ACTOR_COLUMNS_NO_DEFAULT_F-C6_2026-09-25.md` §三.4。
那趟排查里真正有用的轴是这条：**把每一格迁移单独重放，比较它前后全表的列形状**。

本片把那条轴变成常驻断言：除下面这 6 处已声明、已复核的改动之外，
任何一格迁移都不许改变或删掉已有列的形状。
新增列（建表与 `ADD COLUMN`）不在本尺子的射程内——那是常态，不是漂移。
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from aipd_os.state.migrations import MIGRATIONS, migrate
from aipd_os.state.migrations.sqlsplit import exec_script

#: 已声明的「列形状被改动/被删掉」清单：`{版本: {table.column: 一句话理由}}`。
#: 由本文件的重放实测生成（2026-09-25），不是抄来的。
DECLARED_SHAPE_CHANGES: dict[int, dict[str, str]] = {
    9: {
        "claim_evidence_relations.strength":
            "v9 有意把评分改成可空（None=未评分），见 evidence_relations.py 的模型说明",
        "claims.confidence":
            "v9 同一处置：置信度不再自带 0.5 哨兵",
    },
    20: {"gates.approved_by": "第 32 片：没人批不许读成 AI-internal 批了"},
    21: {"risks.owner": "第 34 片：没人负责不许读成 AI 负责"},
    22: {
        "claim_evidence_relations.created_by": "第 35 片：摘掉自带的 'system'",
        "product_definition_snapshots.created_by": "第 35 片：同上",
        "product_definition_commits.actor": "第 35 片：同上",
    },
}


def _shapes(conn: sqlite3.Connection) -> dict[str, dict[str, tuple]]:
    out: dict[str, dict[str, tuple]] = {}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in tables:
        out[t] = {r[1]: (r[2].upper(), r[3], r[4])
                  for r in conn.execute(f"PRAGMA table_info({t})")}
    return out


def _changed_columns(conn: sqlite3.Connection, migration: dict,
                     before: dict[str, dict[str, tuple]]) -> dict[str, str]:
    """只跑这一格的 up，返回「已有列被改了形状 / 被删掉」的清单（不含新增列）。"""
    before_tables = set(before)
    for step in migration["up"]:
        exec_script(conn, step) if isinstance(step, str) else step(conn)
    after = _shapes(conn)
    changed: dict[str, str] = {}
    for table, cols in after.items():
        old = before.get(table, {})
        for column, val in cols.items():
            if column in old and old[column] != val:
                changed[f"{table}.{column}"] = "shape"
    for table in before_tables & set(after):
        for column in before[table]:
            if column not in after[table]:
                changed[f"{table}.{column}"] = "dropped"
    return changed


def replay_changes(version: int) -> dict[str, str]:
    """**前进式**建到 version-1，再只重放 version 这一格，看它动了哪些已有列。

    轴选错了会整把尺子失效：先用「建到 HEAD 再 rollback 到 N-1」拿基线，
    rollback 会跑 N 的 down，而 down 用的正是同一份重建模板 ⇒
    基线已经被这一格自己刷过一遍，比出「零变化」是自证，不是实测
    （本文件第一版就是这么假绿的）。所以基线只能正向建。
    """
    from aipd_os.state.migrations import runner

    migration = next(m for m in MIGRATIONS if m["version"] == version)
    original_chain = runner.MIGRATIONS
    with tempfile.TemporaryDirectory() as td:
        path = str(Path(td) / "replay.db")
        runner.MIGRATIONS = [m for m in original_chain if int(m["version"]) < version]
        try:
            migrate(path)
        finally:
            runner.MIGRATIONS = original_chain
        with sqlite3.connect(path) as conn:
            before = _shapes(conn)
            changed = _changed_columns(conn, migration, before)
    return changed


@pytest.mark.parametrize("version", sorted(DECLARED_SHAPE_CHANGES))
def test_the_declared_versions_still_change_exactly_those_columns(version):
    assert replay_changes(version) == {k: "shape"
                                       for k in DECLARED_SHAPE_CHANGES[version]}, (
        f"v{version} 改变了已有列的形状，与声明清单不一致")


def test_no_other_migration_changes_or_drops_an_existing_column():
    """除声明过的那几格，链上任何一格都不许改或删已有列。"""
    offenders = {}
    for m in MIGRATIONS:
        version = int(m["version"])
        if version in DECLARED_SHAPE_CHANGES or version == 1:
            continue
        got = replay_changes(version)
        if got:
            offenders[version] = got
    assert not offenders, f"这些迁移改了已有列的形状：{offenders}"


def test_every_declared_entry_names_a_real_migration():
    names = {int(m["version"]): str(m["name"]) for m in MIGRATIONS}
    for version, entries in DECLARED_SHAPE_CHANGES.items():
        assert version in names, f"声明清单里的 v{version} 不在链上"
        assert entries, f"v{version} 声明了却空着——该整条删掉"


# --- 这把尺子自己会红吗 ---------------------------------------------------
def test_the_ruler_fires_when_a_rebuild_looses_a_columns_not_null(tmp_path, monkeypatch):
    """反向对照：让 v22 的重建顺手把 `review_status` 的 NOT NULL 搬掉，尺子必须看见。

    注入选「丢 NOT NULL」而不是「丢默认值」：实测 v21 那一格上 `review_status`
    已经是 `('TEXT', 1, None)`——这张表的默认值早被之前的重建搬空了，
    拿「丢默认值」当注入等于空放（本条第一次就是这么假绿的）。
    """
    from aipd_os.state.migrations import helpers

    table = "claim_evidence_relations"
    actor, cols, body = helpers._V22_ACTOR_TABLES[table]
    original_clause = "review_status TEXT NOT NULL DEFAULT 'pending'"
    assert original_clause in body, "模板形状变了，这一枪打不到东西"
    patched_body = body.replace(original_clause, "review_status TEXT")
    assert patched_body != body and "NOT NULL DEFAULT 'pending'" not in patched_body
    monkeypatch.setattr(helpers, "_V22_ACTOR_TABLES", {
        **helpers._V22_ACTOR_TABLES, table: (actor, cols, patched_body)})
    got = replay_changes(22)
    assert got.get(f"{table}.review_status") == "shape", (
        f"重建丢了 NOT NULL，尺子却没看见：{got}")


def test_the_ruler_is_silent_on_the_real_v22():
    """合规侧：不注入时同一把尺子对 v22 只报声明过的那三列。"""
    assert set(replay_changes(22)) == set(DECLARED_SHAPE_CHANGES[22])
