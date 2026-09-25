"""第 34 片：`risks.owner` 不再硬写 `'AI'`（没人负责不许读成 AI 负责）。

实测前提（2026-09-25，改之前）：

- 列的形状是 `owner TEXT NOT NULL DEFAULT 'AI'`，同句 DDL 有三份：
  `state/migrations/schema.py:148`（V1 冻结文本，改不得）、`state/db.py:197`（参考 SCHEMA）、
  `scripts/aipd_store.py`（废弃旧库）。
- 比第 32 片那一格更糟：写入口 `AIPDStateDB.add_risk`（`state/db.py:975` 起）
  **连 `owner` 形参都没有**，INSERT 里直接硬写 `"AI"` ⇒ 「这条风险谁负责」在创建时
  无法表达，库里每一条都是 `'AI'` 负责。
  而 `update_risk` 的可改白名单里**有** `owner`（`db.py:996`）：创建时不许说、创建后允许改。
- **没有任何读者**：`list_risks` 的四个调用点
  （`experience/owner_dashboard.py`、`project_summary.py`、`views.py`、`state/checkpoint.py`）
  一个都不碰这一列 ⇒ 这是一根「一直在写、从来没人读、而且写的是假话」的列。
- 生产写入口（去截断重跑 `grep -rn "add_risk("`）：
  `experience/onboarding.py:59,64`、`state/server.py:324`、
  `supply_chain/writeback.py:60,114`，加两处常驻用例与旧 CLI `scripts/aipd_state.py:56`。
  没有一处传 owner（原先也传不了）。

本片做三件事：migration **v21** 重建 `risks`（列可空、无默认值，历史值原样保留）；
写入口加 `owner: str | None = None`（空白串拒绝）；读侧补上第一个真读者——
Owner Dashboard 的「风险责任」块（默认视图只给人话与计数，风险编号留在 `details`）。
"""
from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

from aipd_os import gate_attribution as ga
from aipd_os.actors import classify_actor, summarize_actor_column
from aipd_os.experience.owner_dashboard import build_dashboard, render_dashboard_text
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.migrations import MIGRATIONS, migrate, rollback

# v20 之上那几格现算：这条断言钉的是「升上来到 HEAD」，不是「尾巴停在 v21」。
VERSIONS_ABOVE_20 = [m["version"] for m in MIGRATIONS if m["version"] > 20]

ROOT = Path(__file__).resolve().parents[1]
DB_PY = ROOT / "src" / "aipd_os" / "state" / "db.py"
SCHEMA_PY = ROOT / "src" / "aipd_os" / "state" / "migrations" / "schema.py"
STATE_INVENTORY = ROOT / "docs" / "architecture" / "state_inventory.md"


def _db(tmp_path: Path, project: str = "P-RISK") -> AIPDStateDB:
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant()
    db.init_project("default", project, "风险归属", "slice 34")
    return db


def _owner_col(path: Path | str) -> tuple:
    rows = sqlite3.connect(str(path)).execute("PRAGMA table_info(risks)").fetchall()
    for r in rows:
        if r[1] == "owner":
            return (r[1], r[2], r[3], r[4], r[5])
    raise AssertionError(f"risks 表里没有 owner 列：{rows}")


def _full_row(path: Path | str, risk_id: str) -> dict:
    """整行取回来做逐列比对（重建表丢列时只有这种比对看得见）。"""
    with sqlite3.connect(str(path)) as raw:
        raw.row_factory = sqlite3.Row
        row = raw.execute("SELECT * FROM risks WHERE risk_id=?", (risk_id,)).fetchone()
    return dict(row)


def _seed_mixed(db: AIPDStateDB) -> None:
    """三种形态各一条：真人、机器（历史 'AI'）、没人（NULL）。"""
    db.add_risk("default", "P-RISK", "r-li", owner="li")
    db.add_risk("default", "P-RISK", "r-none")
    with sqlite3.connect(db.path) as raw:
        raw.execute("INSERT INTO risks(risk_id,project_id,tenant_id,title,status,"
                    "owner,updated_at,version_no) VALUES('RISK-900','P-RISK','default',"
                    "'r-legacy','open','AI','2026-01-01T00:00:00+00:00',1)")


class TestColumnShape:
    def test_fresh_database_has_no_default_on_owner(self, tmp_path):
        db = _db(tmp_path)
        name, _type, notnull, dflt, _pk = _owner_col(db.path)
        assert name == "owner"
        assert dflt is None, f"列上又长出默认值了：{dflt!r}"
        assert notnull == 0

    def test_v20_era_database_upgrades_to_the_same_shape(self, tmp_path):
        db = _db(tmp_path)
        rollback(db.path, 20)
        assert _owner_col(db.path)[3] == "'AI'", "降回 v20 应当还原旧形状"
        assert migrate(db.path) == VERSIONS_ABOVE_20
        fresh = _db(tmp_path / "fresh")
        assert _owner_col(db.path) == _owner_col(fresh.path)

    def test_the_reference_schema_no_longer_carries_the_default(self):
        block = DB_PY.read_text(encoding="utf-8").split(
            "CREATE TABLE IF NOT EXISTS risks")[1].split(");")[0]
        assert "owner TEXT," in block
        assert "AI" not in block

    def test_the_frozen_v1_text_still_carries_it(self):
        """诚实记录：V1 冻结文本改不得，修复只能以 v21 重建落地（同第 32 片）。"""
        text = SCHEMA_PY.read_text(encoding="utf-8")
        assert "owner TEXT NOT NULL DEFAULT 'AI'" in text


class TestWritePath:
    def test_no_owner_stores_null(self, tmp_path):
        db = _db(tmp_path)
        db.add_risk("default", "P-RISK", "r1")
        row = db.list_risks("default", "P-RISK")[-1]
        assert row["owner"] is None
        with sqlite3.connect(db.path) as raw:
            assert raw.execute("SELECT owner IS NULL FROM risks").fetchone()[0] == 1

    def test_a_blank_owner_is_rejected(self, tmp_path):
        db = _db(tmp_path)
        with pytest.raises(ValueError, match="空白串"):
            db.add_risk("default", "P-RISK", "r1", owner="   ")
        assert db.list_risks("default", "P-RISK") == []

    def test_a_given_owner_is_stored_trimmed(self, tmp_path):
        db = _db(tmp_path)
        db.add_risk("default", "P-RISK", "r1", owner="  zhang  ")
        assert db.list_risks("default", "P-RISK")[-1]["owner"] == "zhang"

    def test_the_supply_chain_writeback_no_longer_bakes_in_ai(self, tmp_path):
        """自动开风险的那条生产路径：以前每条都是 'AI'，现在是「没人认领」。"""
        from aipd_os.supply_chain.writeback import PhysicalWriteback
        db = _db(tmp_path, "P-WB")
        analysis = {"failed": 2, "passed": 0}
        out = PhysicalWriteback(db, "default").write_stage("P-WB", "pvt", analysis)
        assert out["risk_id"]
        row = [r for r in db.list_risks("default", "P-WB")
               if r["risk_id"] == out["risk_id"]][0]
        assert row["owner"] is None


class TestReadSide:
    def test_historical_ai_row_is_never_read_as_a_person(self, tmp_path):
        db = _db(tmp_path)
        _seed_mixed(db)
        got = summarize_actor_column(db.list_risks("default", "P-RISK"),
                                     column="owner", id_field="risk_id")
        assert got["counts"] == {ga.HUMAN: 1, ga.NON_HUMAN: 1, ga.UNATTRIBUTED: 1}
        assert sorted(got["unassigned"]) == ["RISK-002", "RISK-900"]

    def test_missing_column_is_unattributed(self):
        got = summarize_actor_column([{"risk_id": "R1"}], column="owner",
                                     id_field="risk_id")
        assert got["counts"][ga.UNATTRIBUTED] == 1
        assert got["unassigned"] == ["R1"]

    def test_counts_always_carry_three_states(self, tmp_path):
        db = _db(tmp_path)
        got = summarize_actor_column(db.list_risks("default", "P-RISK"),
                                     column="owner", id_field="risk_id")
        assert set(got["counts"]) == {ga.HUMAN, ga.NON_HUMAN, ga.UNATTRIBUTED}
        assert got["total"] == 0


class TestDashboardBlock:
    def test_default_view_says_it_in_words_and_hides_the_ids(self, tmp_path):
        db = _db(tmp_path)
        _seed_mixed(db)
        view = build_dashboard(db, "P-RISK")
        block = view["risk_ownership"]
        assert block["waiting_for_owner"] == 2
        assert "2 条还没有真人负责" in block["summary"]
        assert "RISK-" not in str(block), "默认视图不许漏内部编号"
        assert view["details"]["unassigned_risk_ids"] == ["RISK-002", "RISK-900"]
        # 归属口径与 `test_owner_ux.py::test_dashboard_default_hides_internals` 一致：
        # 「默认视图」= `<details>` 折叠之前的正文，编号该出现在折叠区里而不是没有。
        text = render_dashboard_text(view)
        body, fold = text.split("<details>", 1)
        assert "RISK-" not in body
        assert "还没有真人负责" in body
        for rid in ("RISK-002", "RISK-900"):
            assert rid in fold, f"编号在折叠区也读不到了：{rid}"
        # 两种渲染档位都要看得到这一格：紧凑档是给窄屏的人看的，不是给机器读的。
        assert "还没有真人负责" in render_dashboard_text(view, compact=True)

    def test_the_all_held_arm_says_everything_is_claimed(self, tmp_path):
        """配对的另一侧：全都有真人认领时，措辞必须换掉，而不是继续报「还差 N 条」。"""
        db = _db(tmp_path)
        db.add_risk("default", "P-RISK", "r-li", owner="li")
        db.add_risk("default", "P-RISK", "r-zhao", owner="zhao")
        block = build_dashboard(db, "P-RISK")["risk_ownership"]
        assert block["waiting_for_owner"] == 0
        assert block["summary"] == "2 条风险都有真人认领"

    def test_an_empty_ledger_is_not_reported_as_all_claimed(self, tmp_path):
        """第三档：0 条风险是一句关于空集的断言，不该写成「都有真人认领」。"""
        db = _db(tmp_path)
        block = build_dashboard(db, "P-RISK")["risk_ownership"]
        assert block["waiting_for_owner"] == 0
        assert block["summary"] == "暂无风险条目"


class TestMigrationRoundTrip:
    def test_up_keeps_history_verbatim(self, tmp_path):
        db = _db(tmp_path)
        rollback(db.path, 20)
        with sqlite3.connect(db.path) as raw:
            raw.execute("INSERT INTO risks(risk_id,project_id,tenant_id,title,status,"
                        "owner,updated_at,version_no) VALUES"
                        "('RISK-900','P-RISK','default','legacy','open','AI',"
                        "'2026-01-01T00:00:00+00:00',1)")
        assert migrate(db.path) == VERSIONS_ABOVE_20
        rows = [(r["risk_id"], r["owner"]) for r in db.list_risks("default", "P-RISK")]
        assert rows == [("RISK-900", "AI")]

    def test_down_restores_shape_without_inventing_an_owner(self, tmp_path):
        db = _db(tmp_path)
        db.add_risk("default", "P-RISK", "r-none")
        db.add_risk("default", "P-RISK", "r-li", owner="li")
        rollback(db.path, 20)
        with sqlite3.connect(db.path) as raw:
            assert raw.execute("SELECT owner FROM risks ORDER BY risk_id").fetchall() \
                == [("",), ("li",)], "NULL 只能落成空串，不许落成 'AI'"
        assert _owner_col(db.path)[3] == "'AI'"

    def test_round_trip_keeps_ids_and_classification(self, tmp_path):
        db = _db(tmp_path)
        _seed_mixed(db)
        before = [(r["risk_id"], r["owner"]) for r in db.list_risks("default", "P-RISK")]
        rollback(db.path, 20)
        assert migrate(db.path) == VERSIONS_ABOVE_20
        after = [(r["risk_id"], r["owner"]) for r in db.list_risks("default", "P-RISK")]
        assert [x[0] for x in after] == [x[0] for x in before]
        # 唯一的已知不对称（与 gates 那张表同一条）：NULL 过一趟 down 会变成 ''。
        # 所以「没人」退上去再降回来会读成「机器代签」——两档都不是真人，
        # waiting_for_owner 不因这趟往返而改变，这才是不变量。
        kinds_before = {rid: classify_actor(owner) for rid, owner in before}
        kinds_after = {rid: classify_actor(owner) for rid, owner in after}
        assert kinds_before == {"RISK-001": ga.HUMAN, "RISK-002": ga.UNATTRIBUTED,
                                "RISK-900": ga.NON_HUMAN}, before
        assert kinds_after == {"RISK-001": ga.HUMAN, "RISK-002": ga.NON_HUMAN,
                               "RISK-900": ga.NON_HUMAN}, after


    def test_a_round_trip_moves_every_column_value(self, tmp_path):
        """重建表最容易丢的不是形状而是列：列清单少一列，INSERT 照样成功、值静默变 NULL。

        电池 J15（从 `_V21_RISK_COLUMNS` 里删掉 `mitigation`）第一轮就是全绿活下来的，
        这一条补的就是那一格。
        """
        db = _db(tmp_path)
        rid = db.add_risk("default", "P-RISK", "全列", probability="高", impact="严重",
                          mitigation="加筋", status="open", trigger="温漂", owner="li")
        before = _full_row(db.path, rid)
        assert before["mitigation"] == "加筋"
        rollback(db.path, 20)
        assert migrate(db.path) == VERSIONS_ABOVE_20
        assert _full_row(db.path, rid) == before


class TestTheDocMirrorMatchesTheChain:
    """`state_inventory.md` 抄了迁移链的两处：页眉/正文的 `HEAD = vNN` 和版本清单表。

    第 32 片留下的实况是正文写 v20、页眉仍写 v19 —— 抄本之间一致不等于对得上链，
    所以真值只有 `MIGRATIONS` 一份，这里做双向对账（表里缺什么、多什么）。
    """

    #: 那张表是 P2 窗口的清单，从 v14 起列；窗口之外（v1..v13）不归它抄。
    WINDOW_FLOOR = 14

    @staticmethod
    def _text() -> str:
        return STATE_INVENTORY.read_text(encoding="utf-8")

    @classmethod
    def _chain_window(cls) -> list[int]:
        return [m["version"] for m in MIGRATIONS if m["version"] >= cls.WINDOW_FLOOR]

    @staticmethod
    def _table_rows(text: str) -> list[int]:
        section = text.split("## Migration 版本清单")[1].split("\n## ")[0]
        return [int(v) for v in re.findall(r"^\|\s*v(\d+)\s*\|", section, re.M)]

    @staticmethod
    def _head_claims(text: str) -> list[str]:
        return re.findall(r"HEAD\s*=\s*(?:\*\*)?v(\d+)", text)

    @staticmethod
    def _tail() -> tuple[int, str]:
        """链尾那一格的 (版本号, 名字)：注入对照一律由它现算，
        免得写死 v21 —— 第 35 片加进 v22 时这两条对照就差点变成假绿。"""
        last = MIGRATIONS[-1]
        return int(last["version"]), str(last["name"])

    def test_the_table_matches_the_chain_row_for_row(self):
        assert self._table_rows(self._text()) == self._chain_window()

    def test_dropping_a_row_makes_the_reconciliation_fire(self):
        """反向对照：这条对账真会红，不是永远绿。"""
        version, name = self._tail()
        row = f"| v{version} | {name} |\n"
        text = self._text()
        assert text.count(row) == 1, f"链尾那一行在表里要恰好一处：{row!r}"
        mutated = text.replace(row, "", 1)
        assert self._table_rows(mutated) == [v for v in self._chain_window()
                                             if v != version]
        assert self._table_rows(mutated) != self._chain_window()

    def test_both_head_claims_read_the_chain_tail(self):
        claims = self._head_claims(self._text())
        assert len(claims) == 2, f"页眉与正文各一处：{claims}"
        assert set(claims) == {str(MIGRATIONS[-1]["version"])}, claims

    def test_a_stale_head_claim_makes_that_reconciliation_fire(self):
        version, _ = self._tail()
        text = self._text()
        fresh, stale = f"HEAD = **v{version}**", f"HEAD = **v{version - 1}**"
        assert fresh in text, "正文那一处 HEAD 声明的形状变了，对照要跟着改"
        claims = self._head_claims(text.replace(fresh, stale, 1))
        assert len(claims) == 2 and set(claims) != {str(MIGRATIONS[-1]["version"])}


def test_tempdir_is_not_shared() -> None:
    """防呆：本文件的夹具都走 tmp_path，不落在仓库里。"""
    with tempfile.TemporaryDirectory() as td:
        assert not str(td).startswith(str(ROOT))
