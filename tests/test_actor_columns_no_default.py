"""第 35 片：三张表的 actor 列不再自带 `'system'`（migration v22）。

实测前提（2026-09-25，改之前，`grep -rn created_by` 去截断重跑）：

- 带机器默认值的 actor 列有三根，都是 `TEXT NOT NULL DEFAULT 'system'`：
  `claim_evidence_relations.created_by`、`product_definition_snapshots.created_by`、
  `product_definition_commits.actor`。声明它们的 DDL 各有两份
  （`migrations/definitions.py:131` 与重建用的 `migrations/helpers.py:106/150/257/348`），
  参考 SCHEMA 里另有一处（`state/db.py:299`）。
- **与第 32/34 片不同，这一族没有「库里正在跑一条假读数」**：
  产品写入口实测都显式传 actor（`idea/evidence_relations.py:217,247`、
  `product_intelligence/snapshot.py:345`、`product_intelligence/gate.py:491`、
  `execution/research_integration.py:265`），而 `from_dict` 的四个调用点
  喂的都是数据库行（`evidence_relations.py:169`、`evidence_graph.py:41`、
  `snapshot.py:382,391`）⇒ 列一定带着键。
- 所以默认值的真危害是**将来**：任何一个漏传 actor 的写入口都会静默写出 `'system'`，
  而 `to_dict`/`to_public_dict`（`evidence_relations.py:107`、`snapshot.py:246`）
  会把这个戳当归属往外发。数据类自己还带一份 `created_by: str = "system"`
  （`evidence_relations.py:75`、`snapshot.py:188`），`from_dict` 的兜底
  （`evidence_relations.py:131`、`snapshot.py:275`）又把「payload 没这个键」读成 system。

本片把这条路关掉：列**保留 NOT NULL、摘掉 DEFAULT** ⇒ 漏传退化成 `IntegrityError`
（fail-closed，报错点名是哪一列），而不是一个看起来像归属的字符串；
数据类字段与 `from_dict` 兜底同步改成 `None`。值在 up/down 两个方向都不改写。
"""
from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import fields
from pathlib import Path

import pytest

from aipd_os.idea.evidence_relations import EvidenceRelation
from aipd_os.product_intelligence.snapshot import ProductDefinitionSnapshot
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.migrations import MIGRATIONS, migrate, rollback

ROOT = Path(__file__).resolve().parents[1]
DB_PY = ROOT / "src" / "aipd_os" / "state" / "db.py"
SCHEMA_PY = ROOT / "src" / "aipd_os" / "state" / "migrations" / "schema.py"

#: 表名 → actor 列名
ACTOR_COLUMNS = {
    "claim_evidence_relations": "created_by",
    "product_definition_snapshots": "created_by",
    "product_definition_commits": "actor",
}

#: 三张表除 actor 列以外的最小可插入集（值只为满足 NOT NULL，不承载语义）
_MIN_ROWS = {
    "claim_evidence_relations": {
        "relation_id": "REL-1", "project_id": "P", "claim_id": "C",
        "evidence_id": "E", "relation_type": "supports",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00"},
    "product_definition_snapshots": {
        "snapshot_id": "SNAP-1", "project_id": "P",
        "content_hash": "h", "created_at": "2026-01-01T00:00:00+00:00"},
    "product_definition_commits": {
        "commit_id": "COMMIT-1", "project_id": "P", "snapshot_id": "SNAP-1",
        "snapshot_hash": "h", "committed_at": "2026-01-01T00:00:00+00:00"},
}

VERSIONS_ABOVE_21 = [m["version"] for m in MIGRATIONS if m["version"] > 21]


#: 每张表里参与 PK / UNIQUE 的列：造多行时这些必须逐行不同
#: （`claim_evidence_relations` 的 UNIQUE 不含 `relation_id`，只换主键会当场撞约束——
#: 这条 fixture 第一次就是这么红的）
_UNIQUE_BEARERS = {
    "claim_evidence_relations": ("relation_id", "claim_id", "evidence_id"),
    "product_definition_snapshots": ("snapshot_id",),
    "product_definition_commits": ("commit_id", "snapshot_id"),
}


def _full_row(path: Path | str, table: str, i: int) -> dict:
    """每一列都填上值的行。

    只填最小列集的 fixture 看不见「重建时列清单少一根」——那一列会被写成 NULL，
    而它本来也就是 NULL（第 34 片电池 J15 教的就是这一格）。
    """
    cols = sqlite3.connect(str(path)).execute(f"PRAGMA table_info({table})").fetchall()
    values: dict = {}
    for name, type_ in ((r[1], (r[2] or "").upper()) for r in cols):
        if name in _MIN_ROWS[table]:
            base = _MIN_ROWS[table][name]
            values[name] = f"{base}-{i}" if name in _UNIQUE_BEARERS[table] else base
        elif "REAL" in type_:
            values[name] = 0.25 + i
        elif "INT" in type_:
            values[name] = 10 + i
        else:
            values[name] = f"{name}-{i}"
    values[ACTOR_COLUMNS[table]] = "li" if i % 2 == 0 else "system"
    return values


def _db(tmp_path: Path) -> AIPDStateDB:
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant()
    db.init_project("default", "P", "actor 归属", "slice 35")
    return db


def _column(path: Path | str, table: str, column: str) -> tuple:
    rows = sqlite3.connect(str(path)).execute(f"PRAGMA table_info({table})").fetchall()
    for r in rows:
        if r[1] == column:
            return (r[1], r[2], r[3], r[4], r[5])
    raise AssertionError(f"{table} 里没有 {column} 列：{rows}")


def _insert(path: Path | str, table: str, values: dict) -> None:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    with sqlite3.connect(str(path)) as raw:
        raw.execute(f"INSERT INTO {table}({cols}) VALUES({marks})",
                    tuple(values.values()))


class TestColumnShape:
    @pytest.mark.parametrize("table,column", sorted(ACTOR_COLUMNS.items()))
    def test_fresh_database_keeps_not_null_but_drops_the_default(
            self, tmp_path, table, column):
        """两半都要钉：摘了默认值但放开 NOT NULL，等于把 fail-closed 也丢了。"""
        db = _db(tmp_path)
        _name, _type, notnull, dflt, _pk = _column(db.path, table, column)
        assert dflt is None, f"{table}.{column} 又长出默认值：{dflt!r}"
        assert notnull == 1, f"{table}.{column} 的 NOT NULL 被一起放掉了"

    @pytest.mark.parametrize("table,column", sorted(ACTOR_COLUMNS.items()))
    def test_v21_era_database_upgrades_to_the_same_shape(
            self, tmp_path, table, column):
        db = _db(tmp_path)
        rollback(db.path, 21)
        assert _column(db.path, table, column)[3] == "'system'", "降回 v21 应还原旧形状"
        assert migrate(db.path) == VERSIONS_ABOVE_21
        fresh = _db(tmp_path / "fresh")
        assert _column(db.path, table, column) == _column(fresh.path, table, column)

    def test_the_declaring_ddl_and_v1_text_still_carry_the_default(self):
        """诚实记录：V1 冻结文本与当初声明它的迁移文本都改不得，修复只能以重建落地。"""
        text = SCHEMA_PY.read_text(encoding="utf-8") + \
            (ROOT / "src/aipd_os/state/migrations/definitions.py").read_text(encoding="utf-8")
        assert "created_by TEXT NOT NULL DEFAULT 'system'" in text

    def test_the_reference_schema_in_db_py_has_no_default(self):
        block = DB_PY.read_text(encoding="utf-8").split(
            "CREATE TABLE IF NOT EXISTS claim_evidence_relations")[1].split(");")[0]
        assert "created_by TEXT NOT NULL," in block
        assert "'system'" not in block


class TestFailClosed:
    """这一片真正的牙齿：漏传 actor 必须**写不进去**，而不是被兜底戳救活。"""

    @pytest.mark.parametrize("table", sorted(_MIN_ROWS))
    def test_insert_without_an_actor_raises_instead_of_baking_in_system(
            self, tmp_path, table):
        db = _db(tmp_path)
        with pytest.raises(sqlite3.IntegrityError) as err:
            _insert(db.path, table, dict(_MIN_ROWS[table]))
        assert "NOT NULL" in str(err.value)

    @pytest.mark.parametrize("table,column", sorted(ACTOR_COLUMNS.items()))
    def test_insert_with_an_actor_round_trips(self, tmp_path, table, column):
        db = _db(tmp_path)
        values = dict(_MIN_ROWS[table])
        values[column] = "li"
        _insert(db.path, table, values)
        with sqlite3.connect(db.path) as raw:
            got = raw.execute(f"SELECT {column} FROM {table}").fetchall()
        assert got == [("li",)], "带 actor 的正常路径不许被这一片改坏"


class TestMigrationRoundTrip:
    def test_up_keeps_history_verbatim(self, tmp_path):
        """v22 只改列的形状；历史里那些 `'system'` 是当时真写进去的值，不许改写。"""
        db = _db(tmp_path)
        for table, column in sorted(ACTOR_COLUMNS.items()):
            values = dict(_MIN_ROWS[table])
            values[column] = "system"
            _insert(db.path, table, values)
        rollback(db.path, 21)
        assert migrate(db.path) == VERSIONS_ABOVE_21
        with sqlite3.connect(db.path) as raw:
            for table, column in sorted(ACTOR_COLUMNS.items()):
                got = raw.execute(f"SELECT {column} FROM {table}").fetchall()
                assert got == [("system",)], f"{table} 的历史值被 up 改写了：{got}"

    def test_down_restores_the_default_without_touching_values(self, tmp_path):
        db = _db(tmp_path)
        for table, column in sorted(ACTOR_COLUMNS.items()):
            values = dict(_MIN_ROWS[table])
            values[column] = "zhang"
            _insert(db.path, table, values)
        rollback(db.path, 21)
        for table, column in sorted(ACTOR_COLUMNS.items()):
            name, _type, notnull, dflt, _pk = _column(db.path, table, column)
            assert notnull == 1 and dflt == "'system'", (table, name, dflt)
            with sqlite3.connect(db.path) as raw:
                assert raw.execute(f"SELECT {column} FROM {table}").fetchall() \
                    == [("zhang",)], table

    def test_round_trip_keeps_every_column_of_every_row(self, tmp_path):
        db = _db(tmp_path)
        for table in sorted(ACTOR_COLUMNS):
            for i in range(3):
                _insert(db.path, table, _full_row(db.path, table, i))
        before = {t: sqlite3.connect(db.path).execute(f"SELECT * FROM {t}").fetchall()
                  for t in ACTOR_COLUMNS}
        assert all(len(rows) == 3 for rows in before.values()), before
        rollback(db.path, 21)
        assert migrate(db.path) == VERSIONS_ABOVE_21
        after = {t: sqlite3.connect(db.path).execute(f"SELECT * FROM {t}").fetchall()
                 for t in ACTOR_COLUMNS}
        assert after == before, "往返把某一列的值弄丢了（列清单少一根只有这种比对看得见）"


class TestModelsStopInventingAnActor:
    def test_dataclass_default_is_none_not_system(self):
        for cls in (EvidenceRelation, ProductDefinitionSnapshot):
            by_name = {f.name: f for f in fields(cls)}
            assert by_name["created_by"].default is None, (
                f"{cls.__name__} 的字段默认值又变回一个戳")

    def test_from_dict_on_a_payload_without_the_key_is_unattributed(self):
        """DB 行永远带这一列，所以这条只对**手工 payload** 成立：没写就是没写。"""
        rel = EvidenceRelation.from_dict({"relation_id": "R"})
        assert rel.created_by is None
        snap = ProductDefinitionSnapshot.from_dict({"snapshot_id": "S"})
        assert snap.created_by is None

    def test_from_dict_keeps_a_given_actor(self):
        assert EvidenceRelation.from_dict(
            {"relation_id": "R", "created_by": "alice"}).created_by == "alice"

    def test_serialising_an_unattributed_object_publishes_null_not_system(self):
        """`to_public_dict` 是这一列的对外读者：兜底戳以前就是从这里发出去的。"""
        assert EvidenceRelation(relation_id="R").to_dict()["created_by"] is None


def test_tempdir_is_not_shared() -> None:
    with tempfile.TemporaryDirectory() as td:
        assert not str(td).startswith(str(ROOT))
