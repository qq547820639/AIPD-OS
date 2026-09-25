"""第 32 片：`gates.approved_by` 不再自带 `'AI-internal'`。

实测前提（2026-09-25，改之前）：

- 列的形状是 `approved_by TEXT NOT NULL DEFAULT 'AI-internal'`，写在**三处**：
  `state/migrations/schema.py:173`（V1 冻结文本，`V1_FROZEN_SHA256` 钉住，改不掉）、
  `state/db.py:222`（参考 SCHEMA 常量）、`scripts/aipd_store.py:135`（废弃旧库）。
- 写入口 `AIPDStateDB.add_gate`（`state/db.py:1025`）的形参默认值
  `approved_by: str = "AI-internal"` ⇒ 任何不写审批人的调用都把「没人批」记成
  「AI-internal 批了」。**常驻用例自己就是受害者**：
  `tests/test_golden_projects_e2e.py:262,440` 两处都没传审批人。
- 全仓仅有的两个生产写入口（`supply_chain/writeback.py:129,154`）显式盖
  `supply-chain`，而这个词**不在** ECO 的机器身份表里 ⇒ 只复用那张表读数，
  这两行会被读成「真人批的」。

第 26 片的 ECO 三张表就是照这条教训建的（`approver` 无默认值），
但 `gates` 这张表本身一直没改 —— 这一片补的就是这一格。
"""
from __future__ import annotations

import ast
import inspect
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os import gate_attribution as ga
from aipd_os.actors import NON_HUMAN_ACTORS, classify_actor
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.migrations import MIGRATIONS, migrate, rollback

# v19 之上那几格现算：链上每进一格这里就多跑一格。硬写 `[20]` 会让第 34 片的
# v21 变成一次假红——它想钉的从来不是"尾巴停在哪一格"。
VERSIONS_ABOVE_19 = [m["version"] for m in MIGRATIONS if m["version"] > 19]

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "quality_gate.py"
SCHEMA_PY = ROOT / "src" / "aipd_os" / "state" / "migrations" / "schema.py"
ECO_PY = ROOT / "src" / "aipd_os" / "change_orders" / "eco.py"
DB_PY = ROOT / "src" / "aipd_os" / "state" / "db.py"
_UNSET = object()


def _db(tmp_path: Path, project: str = "P-GATE") -> AIPDStateDB:
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant()
    db.init_project("default", project, "门禁台账", "slice 32")
    return db


def _gate_col(path: Path | str) -> tuple:
    """`PRAGMA table_info(gates)` 里 approved_by 那一行的 (name, type, notnull, dflt, pk)。"""
    rows = sqlite3.connect(str(path)).execute("PRAGMA table_info(gates)").fetchall()
    for r in rows:
        if r[1] == "approved_by":
            return (r[1], r[2], r[3], r[4], r[5])
    raise AssertionError(f"gates 表里没有 approved_by 列：{rows}")


class TestColumnShape:
    def test_fresh_database_has_no_default_on_approved_by(self, tmp_path):
        db = _db(tmp_path)
        name, _type, notnull, dflt, _pk = _gate_col(db.path)
        assert name == "approved_by"
        assert dflt is None, f"列上又长出默认值了：{dflt!r}"
        assert notnull == 0, "NOT NULL 会逼写入点填一个假名字"

    def test_v19_era_database_upgrades_to_the_same_shape(self, tmp_path):
        """老库升上来与新建库同形（migration runner 是唯一的建库权威）。"""
        db = _db(tmp_path)
        rollback(db.path, 19)
        assert _gate_col(db.path)[3] == "'AI-internal'", "降回 v19 应当还原旧形状"
        assert migrate(db.path) == VERSIONS_ABOVE_19
        fresh = _db(tmp_path / "fresh")
        assert _gate_col(db.path) == _gate_col(fresh.path)

    def test_the_frozen_v1_text_still_carries_the_old_default(self):
        """诚实记录：V1 冻结文本改不得，所以修复只能以 v20 重建的形式落地。

        若哪天有人为了「把 DEFAULT 从源头删掉」去改 V1 文本，
        `test_migration_freeze.py::test_frozen_v1_schema_does_not_drift` 会红；
        这里把这层因果钉住，免得后来人以为漏改了一处。
        """
        text = SCHEMA_PY.read_text(encoding="utf-8")
        assert "approved_by TEXT NOT NULL DEFAULT 'AI-internal'" in text
        assert "V1_FROZEN_SHA256" in text

    def test_v20_keeps_historical_values_verbatim(self, tmp_path):
        """up 只改列的形状，不许顺手改写历史值（改写等于给旧台账造新读数）。"""
        db = _db(tmp_path)
        rollback(db.path, 19)
        with sqlite3.connect(db.path) as raw:
            for gate, actor in (("G3", "AI-internal"), ("G4", "wang")):
                raw.execute(
                    "INSERT INTO gates(project_id,tenant_id,gate,result,checks_json,"
                    "approved_by,created_at) VALUES('P-GATE','default',?,'PASS','{}',?,"
                    "'2026-01-01T00:00:00+00:00')", (gate, actor))
        assert migrate(db.path) == VERSIONS_ABOVE_19
        assert [r["approved_by"] for r in db.list_gates("default", "P-GATE")] \
            == ["AI-internal", "wang"]
        out = ga.project_gates(db, "default", "P-GATE")
        assert out["counts"] == {ga.HUMAN: 1, ga.NON_HUMAN: 1, ga.UNATTRIBUTED: 0}

    def test_the_reference_schema_in_db_py_has_no_default(self):
        """`state/db.py` 的参考 SCHEMA 不许再留第二份带默认值的形状。"""
        block = DB_PY.read_text(encoding="utf-8").split(
            "CREATE TABLE IF NOT EXISTS gates")[1].split(");")[0]
        assert "approved_by TEXT," in block
        assert "AI-internal" not in block


class TestWritePath:
    def test_no_approver_stores_null_not_ai_internal(self, tmp_path):
        db = _db(tmp_path)
        db.add_gate("default", "P-GATE", "G3", "PASS")
        row = db.list_gates("default", "P-GATE")[-1]
        assert row["approved_by"] is None
        raw = sqlite3.connect(db.path).execute(
            "SELECT approved_by IS NULL FROM gates").fetchall()
        assert raw == [(1,)]

    def test_the_signature_no_longer_supplies_a_default(self):
        sig = inspect.signature(AIPDStateDB.add_gate)
        assert sig.parameters["approved_by"].default is None

    def test_a_blank_approver_is_rejected(self, tmp_path):
        db = _db(tmp_path)
        with pytest.raises(ValueError, match="空白串"):
            db.add_gate("default", "P-GATE", "G3", "PASS", approved_by="   ")
        assert db.list_gates("default", "P-GATE") == []

    def test_a_given_name_is_stored_trimmed(self, tmp_path):
        db = _db(tmp_path)
        db.add_gate("default", "P-GATE", "G3", "PASS", approved_by="  zhang  ")
        assert db.list_gates("default", "P-GATE")[-1]["approved_by"] == "zhang"


class TestReadSide:
    @pytest.mark.parametrize("value,want", [
        ("AI-internal", ga.NON_HUMAN), ("ai-internal", ga.NON_HUMAN),
        ("SYSTEM", ga.NON_HUMAN), ("", ga.NON_HUMAN), ("   ", ga.NON_HUMAN),
        ("supply-chain", ga.NON_HUMAN),
        (None, ga.UNATTRIBUTED), ("zhang", ga.HUMAN),
        ("owner@example.com", ga.HUMAN),
    ])
    def test_classification_table(self, value, want):
        assert classify_actor(value) == want
        assert ga.attribute_row({"approved_by": value}) == want

    def test_a_historical_ai_internal_row_is_never_read_as_human(self, tmp_path):
        """v20 之前写进去的 `'AI-internal'` 留在盘上，但读侧不许把人算上去。"""
        db = _db(tmp_path)
        # 绕过写入口，直接照 v20 之前的形状落一行历史（Python 的 sqlite3 对 DML
        # 开隐式事务，所以必须显式 commit，否则读侧看到的还是空表）。
        with sqlite3.connect(db.path) as raw:
            raw.execute(
                "INSERT INTO gates(project_id,tenant_id,gate,result,checks_json,"
                "approved_by,created_at) VALUES('P-GATE','default','G3','PASS','{}',"
                "'AI-internal','2026-01-01T00:00:00+00:00')")
        out = ga.project_gates(db, "default", "P-GATE")
        assert out["status"] == "ok"
        assert out["counts"][ga.HUMAN] == 0
        assert out["counts"][ga.NON_HUMAN] == 1

    def test_the_supply_chain_stamp_reads_as_non_human(self, tmp_path):
        """唯一在产的两个写入口盖的是子系统名，不是人。"""
        from aipd_os.supply_chain.writeback import PhysicalWriteback
        db = _db(tmp_path, "P-WB")
        PhysicalWriteback(db, "default").write_release_gate("P-WB", "G7", True)
        out = ga.project_gates(db, "default", "P-WB")
        assert out["counts"] == {ga.HUMAN: 0, ga.NON_HUMAN: 1, ga.UNATTRIBUTED: 0}
        assert out["rows"][0]["attribution"] == ga.NON_HUMAN

    def test_counts_always_carry_all_three_states(self, tmp_path):
        db = _db(tmp_path)
        out = ga.project_gates(db, "default", "P-GATE")
        assert set(out["counts"]) == {ga.HUMAN, ga.NON_HUMAN, ga.UNATTRIBUTED}
        assert out["counts"] == {ga.HUMAN: 0, ga.NON_HUMAN: 0, ga.UNATTRIBUTED: 0}

    def test_missing_column_is_unattributed_not_human(self):
        """读不到这一列 ≠ 有人批了（老副本、别的投影都可能不带这列）。"""
        assert ga.attribute_row({"gate": "G3"}) == ga.UNATTRIBUTED

    def test_unreadable_table_is_not_read_as_zero_rows(self, tmp_path):
        db = _db(tmp_path)
        sqlite3.connect(db.path).execute("DROP TABLE gates")
        out = ga.project_gates(db, "default", "P-GATE")
        assert out["status"] == "unreadable" and out["why"]
        assert out["counts"] == {ga.HUMAN: 0, ga.NON_HUMAN: 0, ga.UNATTRIBUTED: 0}


class TestSingleSourceVocabulary:
    """两处读者（ECO 的审批人、gates 的归类）必须共用一份机器身份表。"""

    def test_eco_imports_rather_than_recopies_the_list(self):
        tree = ast.parse(ECO_PY.read_text(encoding="utf-8"))
        assigned = {t.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
                    for t in node.targets if isinstance(t, ast.Name)}
        assert "NON_HUMAN_ACTORS" not in assigned, "eco.py 又抄了一份机器身份表"
        imported = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                    and node.module == "aipd_os.actors"]
        assert imported, "eco.py 不再从 aipd_os.actors 取词表"

    def test_the_vocabulary_covers_both_machine_stamps_in_this_repo(self):
        assert {"ai-internal", "supply-chain", "system", ""} <= NON_HUMAN_ACTORS

    def test_no_actor_check_bypasses_the_shared_helper(self):
        """域里不许再出现「本地判一下是不是机器身份」的第二套写法。"""
        text = ECO_PY.read_text(encoding="utf-8")
        assert "casefold() not in" not in text
        assert "is_human_actor(" in text


class TestReportOnlyInQualityGate:
    """`pass` 判决不许被批准归属牵着走：这条判据只报不判（待裁项）。"""

    def _world(self, tmp_path: Path, *, approved_by) -> dict:
        """一个**合规侧为绿**的 G3 世界：两档只差 `approved_by` 这一个字段。

        两侧同红等于什么都没测（`pass` 早就被别的缺项打掉了，归属进不进判决
        都看不出差别），所以这里把 G3 的 5 项交付物与 `cad_contract` 的落点补齐。
        """
        root = tmp_path / "proj"
        (root / "cad").mkdir(parents=True)
        body = json.loads((ROOT / "assets" / "templates"
                           / "cad_contract.json").read_text(encoding="utf-8"))
        (root / "cad" / "cad_contract.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8")
        db = _db(root, "P-QG")  # state.db 落在 root 下
        for t in ("v1_engineering_definition", "preliminary_bom", "interface_register",
                  "dfmea_draft"):
            db.add_deliverable("default", "P-QG", t, path=f"out/{t}.md",
                               status="complete", gate="G3")
        db.add_deliverable("default", "P-QG", "cad_contract",
                           path="cad/cad_contract.json", status="complete", gate="G3")
        if approved_by is not _UNSET:
            db.add_gate("default", "P-QG", "G3", "PASS", approved_by=approved_by)
        proc = subprocess.run([sys.executable, str(GATE), "--db", str(root / "state.db"),
                               "--project", "P-QG", "--gate", "G3", "--root", str(root)],
                              capture_output=True, text=True, cwd=str(ROOT))
        assert proc.returncode in (0, 1), proc.stderr[-400:]
        out: dict = json.loads(proc.stdout)
        return out

    def test_only_the_attribution_differs_between_the_two_arms(self, tmp_path):
        quiet = self._world(tmp_path / "a", approved_by=_UNSET)
        human = self._world(tmp_path / "b", approved_by="zhang")
        assert quiet["pass"] is True, quiet          # 合规侧必须先绿，配对才有意义
        assert quiet["pass"] == human["pass"], "归属改了判决 ⇒ 这条判据已经偷偷进闸"
        assert quiet["gate_approval_attribution"]["counts"][ga.UNATTRIBUTED] == 0
        assert quiet["gate_approval_attribution"]["total"] == 0
        assert human["gate_approval_attribution"]["counts"][ga.HUMAN] == 1

    def test_a_machine_stamp_shows_up_as_non_human_in_the_report(self, tmp_path):
        out = self._world(tmp_path / "c", approved_by="AI-internal")
        assert out["gate_approval_attribution"]["counts"][ga.NON_HUMAN] == 1
        assert out["gate_approval_attribution"]["counts"][ga.HUMAN] == 0


class TestDownMigration:
    def test_down_restores_shape_without_fabricating_an_approver(self, tmp_path):
        """NULL 在 v19 的 NOT NULL 列里放不下，只能落成空串——不许落成 'AI-internal'。"""
        db = _db(tmp_path)
        db.add_gate("default", "P-GATE", "G3", "PASS")
        db.add_gate("default", "P-GATE", "G3", "PASS", approved_by="zhang")
        rollback(db.path, 19)
        rows = sqlite3.connect(db.path).execute(
            "SELECT gate_record_id, approved_by FROM gates ORDER BY gate_record_id"
        ).fetchall()
        assert rows == [(1, ""), (2, "zhang")], rows
        assert _gate_col(db.path)[3] == "'AI-internal'"

    def test_round_trip_preserves_ids_and_never_creates_a_human_row(self, tmp_path):
        db = _db(tmp_path)
        db.add_gate("default", "P-GATE", "G3", "PASS")
        db.add_gate("default", "P-GATE", "G4", "HOLD", approved_by="li")
        before = [(r["gate_record_id"], r["approved_by"])
                  for r in db.list_gates("default", "P-GATE")]
        rollback(db.path, 19)
        assert migrate(db.path) == VERSIONS_ABOVE_19
        after = [(r["gate_record_id"], r["approved_by"])
                 for r in db.list_gates("default", "P-GATE")]
        assert [x[0] for x in after] == [x[0] for x in before], "重建表把主键挪了"
        assert [x for x in after if x[1] == "li"] == [(2, "li")]
        # 唯一的已知不对称：NULL 过一趟 down 会变成 ''（v19 表达不了「没人批」）。
        # 两者在词表里同态，所以归类不变。
        kinds = [classify_actor(v) for _, v in after]
        assert kinds == [ga.NON_HUMAN, ga.HUMAN]


class TestEcoBehaviourUnchanged:
    """词表搬家不许改变 ECO 的判决：机器身份仍然不能开单、不能批单。"""

    def test_machine_actors_are_still_rejected_as_creators(self, tmp_path):
        from aipd_os.change_orders.eco import EcoError, EcoStore
        repo = EcoStore(_db(tmp_path, "P-ECO"))
        for machine in ("AI-internal", "system", "   ", "supply-chain"):
            with pytest.raises(EcoError, match="必须是人"):
                repo.create(tenant_id="default", project_id="P-ECO",
                            title="机器身份不许开单", creator=machine)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
