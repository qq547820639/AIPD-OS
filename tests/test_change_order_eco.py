"""ECR/ECO 工程变更单（capability `industrialize.change_control`，F-C6-ECO 第 26 片）。

这里钉的全是**能机器核的三条规矩**，每条都配了「必须开火」与「必须不开火」两侧：

1. 不许自批：`APPROVED`/`REJECTED` 的 actor 必须是与创建人不同的**人**；
   `approver` 列在没有真人批之前恒为空（对比 `gates.approved_by` 的
   `DEFAULT 'AI-internal'` —— 那种默认值让「没人批」读成「AI 批了」）。
2. 影响清单必须带 sha256，且送审即冻结。
3. 「已实施 / 已复验」必须交凭据；转移流水只追加，仓储层没有任何
   UPDATE/DELETE 入口（用例直接按方法名扫一遍，防止以后有人顺手加）。

状态机与「谁不能批谁」的形状借自公开可查的实现（详见
`docs/audit/ECO_CHANGE_ORDER_F-C6-ECO_2026-09-25.md` §二）：
Dynamics 365 ECM 的 Approve→Process→Complete、OdooPLM 的 released 冻结写、
frappe `has_approval_access()` 的 `user != doc.owner`。
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from aipd_os.change_orders.eco import (
    APPROVED,
    DRAFT,
    ECO_TRANSITIONS,
    IMPLEMENTED,
    INVALID_ACTOR_HINT,
    PENDING_REVIEW,
    REJECTED,
    SUPERSEDED,
    VERIFIED,
    EcoError,
    EcoStore,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.errors import (
    ConcurrentModificationError,
    InvalidTransitionError,
    NotFoundError,
)

TENANT = "default"
PROJECT = "P1"
BEFORE = "a" * 64
AFTER = "b" * 64


@pytest.fixture()
def store(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant()
    db.init_project(TENANT, PROJECT, "测试项目", "目标")
    return EcoStore(db)


def _created(store, creator="zhang", title="把 Ø8 孔从 25 移到 30"):
    return store.create(tenant_id=TENANT, project_id=PROJECT, title=title, creator=creator)


def _affected(store, record, **kw):
    fields = dict(object_type="drawing", object_id="BRK-1.dxf", change_type="UPDATE",
                  before_sha256=BEFORE, after_sha256=AFTER)
    fields.update(kw)
    return store.add_affected(eco_id=record["eco_id"], tenant_id=TENANT,
                              project_id=PROJECT, **fields)


def _to_review(store, record, actor="zhang"):
    return store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                            project_id=PROJECT, to_status=PENDING_REVIEW, actor=actor)


class TestOpeningAnOrder:
    def test_a_new_order_is_draft_and_has_no_approver_yet(self, store):
        record = _created(store)
        assert record["status"] == DRAFT and record["version"] == 1
        assert record["creator"] == "zhang"
        assert record["approver"] == "" and record["approved_at"] is None

    def test_ids_come_from_one_sequence_and_do_not_reuse(self, store):
        first, second = _created(store, title="甲"), _created(store, title="乙")
        assert (first["eco_id"], second["eco_id"]) == ("ECO-001", "ECO-002")
        assert store.get(eco_id="ECO-001", tenant_id=TENANT, project_id=PROJECT) is not None

    def test_the_creator_must_be_a_person_not_a_tool(self, store):
        """作者身份决定「谁不能批」，所以机器作者当场拒，不是记个空值。"""
        for machine in ("AI-internal", "system", "", "  ", "bot", "agent"):
            with pytest.raises(EcoError, match="creator 必须是人"):
                store.create(tenant_id=TENANT, project_id=PROJECT, title="t",
                             creator=machine)

    def test_an_empty_title_or_unknown_kind_is_refused(self, store):
        with pytest.raises(EcoError, match="标题"):
            store.create(tenant_id=TENANT, project_id=PROJECT, title="   ", creator="zhang")
        with pytest.raises(EcoError, match="kind"):
            store.create(tenant_id=TENANT, project_id=PROJECT, title="t", creator="zhang",
                         kind="BUGZAP")

    def test_an_ecr_is_the_same_shape_as_an_eco(self, store):
        record = store.create(tenant_id=TENANT, project_id=PROJECT, title="要不要改孔位",
                              creator="zhang", kind="ECR")
        assert record["kind"] == "ECR"


class TestTheAffectedListCarriesHashes:
    def test_an_update_needs_both_hashes(self, store):
        record = _created(store)
        with pytest.raises(EcoError, match="before_sha256"):
            _affected(store, record, before_sha256="")
        with pytest.raises(EcoError, match="after_sha256"):
            _affected(store, record, after_sha256="")

    def test_add_and_remove_only_need_the_side_that_exists(self, store):
        record = _created(store)
        added = _affected(store, record, change_type="ADD", object_id="BRK-2.dxf",
                          before_sha256="", after_sha256=AFTER)
        removed = _affected(store, record, change_type="REMOVE", object_id="BRK-0.dxf",
                            before_sha256=BEFORE, after_sha256="")
        assert (added["before_sha256"], removed["after_sha256"]) == ("", "")
        assert [row["seq"] for row in store.affected(eco_id=record["eco_id"],
                                                     tenant_id=TENANT,
                                                     project_id=PROJECT)] == [1, 2]

    def test_a_hash_that_is_not_64_hex_is_not_a_hash(self, store):
        """形状不对就拒：短、非十六进制、给了值却读不出的，都不算 sha256。"""
        record = _created(store)
        for bad in ("abc", "z" * 64, "a" * 63, "", None, "0x" + "a" * 62):
            with pytest.raises(EcoError, match="sha256"):
                _affected(store, record, after_sha256=bad)

    def test_a_uppercase_hash_is_the_same_hash_stored_lower(self, store):
        """十六进制大小写不敏感：归一化存小写，但**不能**借归一化把非哈希蒙过去。"""
        record = _created(store)
        row = _affected(store, record, after_sha256="B" * 64)
        assert row["after_sha256"] == AFTER
        assert store.affected(eco_id=record["eco_id"], tenant_id=TENANT,
                              project_id=PROJECT)[0]["after_sha256"] == AFTER

    def test_an_object_needs_both_type_and_id(self, store):
        record = _created(store)
        with pytest.raises(EcoError, match="object_type"):
            _affected(store, record, object_id="")
        with pytest.raises(EcoError, match="object_type"):
            _affected(store, record, object_type="  ")

    def test_the_optional_side_still_has_to_look_like_a_hash(self, store):
        """ADD 不要求改前值，但**给了一个不像哈希的东西**当改前值也要拒：
        「这一格没查」会被读成「这一格是空的」，而它其实写着 `not-a-hash`。"""
        record = _created(store)
        with pytest.raises(EcoError, match="不是 64 位十六进制"):
            _affected(store, record, change_type="ADD", before_sha256="not-a-hash",
                      after_sha256=AFTER)

    def test_the_list_freezes_once_the_order_leaves_draft(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        with pytest.raises(InvalidTransitionError, match="冻结"):
            _affected(store, record, object_id="BRK-9.dxf")


class TestTheStateMachineRefusesIllegalMoves:
    def test_every_declared_edge_is_the_only_way_out_of_a_state(self, store):
        """转移表是真值：未列出的边一律拒，列出的边一律走得住（终态除外）。"""
        record = _created(store)
        with pytest.raises(InvalidTransitionError, match="不是合法转移"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=IMPLEMENTED, actor="li")
        # 词表外的状态名是**输入错**，不是「转移不合法」——两种错误各说各话。
        with pytest.raises(EcoError, match="未知状态"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status="SHIPPED", actor="li")

    def test_terminal_states_hold(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=APPROVED, actor="li")
        store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=IMPLEMENTED, actor="li", evidence_ref="v5.7.0 发布",
                         effective_at="2026-09-25T00:00:00+00:00")
        done = store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                                project_id=PROJECT, to_status=VERIFIED, actor="wang",
                                evidence_ref="复验报告 R-12")
        assert done["status"] == VERIFIED and done["closed_at"]
        assert not ECO_TRANSITIONS[VERIFIED]
        with pytest.raises(InvalidTransitionError, match="终态"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=DRAFT, actor="wang")

    def test_a_concurrent_writer_is_a_conflict_not_a_silent_overwrite(self, store,
                                                                      monkeypatch):
        """CAS 唯一的开火方式：在「读单据」与「带版本写」之间塞进另一个写者。

        注入成功与否由 `bumped` 自己作证——否则这条会静默变成「什么都没测」。
        """
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        original = EcoStore._find_by_id
        bumped = {"done": False}

        def read_then_let_someone_else_write(self, **kw):
            row = original(self, **kw)
            if row and row["status"] == PENDING_REVIEW and not bumped["done"]:
                bumped["done"] = True
                with self._db.transaction() as c:
                    c.execute("UPDATE eco_records SET version=version+1 WHERE eco_id=?",
                              (row["eco_id"],))
            return row

        monkeypatch.setattr(EcoStore, "_find_by_id", read_then_let_someone_else_write)
        with pytest.raises(ConcurrentModificationError):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=APPROVED, actor="li")
        assert bumped["done"], "注入没开火：这条用例是空转"
        assert store.get(eco_id=record["eco_id"], tenant_id=TENANT,
                         project_id=PROJECT)["approver"] == ""

    def test_the_happy_path_walks_and_bumps_version_once_per_step(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        approved = store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                                    project_id=PROJECT, to_status=APPROVED, actor="li")
        assert (approved["status"], approved["version"]) == (APPROVED, 3)
        assert approved["approver"] == "li" and approved["approved_at"]
        implemented = store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                                       project_id=PROJECT, to_status=IMPLEMENTED,
                                       actor="li", evidence_ref="commit 0b9ed1a",
                                       effective_at="2026-09-25")
        assert implemented["effective_at"] == "2026-09-25"


class TestNobodyApprovesTheirOwnOrder:
    def test_the_creator_can_not_approve_even_after_review(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        with pytest.raises(InvalidTransitionError, match="不能自己批准"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=APPROVED, actor="zhang")

    def test_the_creator_can_not_reject_it_either(self, store):
        """否掉自己的单同样是「决定」；作者要撤单走 SUPERSEDED 并指出替代者。"""
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        with pytest.raises(InvalidTransitionError, match="不能自己"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=REJECTED, actor="zhang")

    def test_a_machine_actor_can_never_take_a_decision(self, store):
        record = _created(store, creator="zhang")
        _affected(store, record)
        _to_review(store, record)
        for machine in ("AI-internal", "system", "", "Bot", "cli"):
            with pytest.raises(InvalidTransitionError, match=INVALID_ACTOR_HINT):
                store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                                 project_id=PROJECT, to_status=APPROVED, actor=machine)
        still = store.get(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT)
        assert (still["status"], still["approver"]) == (PENDING_REVIEW, ""), \
            "被拒的转移不许留下任何痕迹"

    def test_nobody_is_left_as_approver_when_approval_never_happened(self, store):
        """这条对着 gates 那个 DEFAULT 'AI-internal' 的形状：没有真人 ⇒ 列必须空。"""
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        with pytest.raises(InvalidTransitionError):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=APPROVED, actor="AI-internal")
        row = store.get(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT)
        assert row["approver"] == "" and row["approved_at"] is None


class TestImplementationAndVerificationNeedEvidence:
    def _approved(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        return store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                                project_id=PROJECT, to_status=APPROVED, actor="li")

    def test_implemented_needs_both_an_evidence_ref_and_a_time(self, store):
        record = self._approved(store)
        with pytest.raises(InvalidTransitionError, match="落地凭据"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=IMPLEMENTED, actor="li")
        with pytest.raises(InvalidTransitionError, match="生效时间"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=IMPLEMENTED, actor="li",
                             evidence_ref="v5.7.0", effective_at="下周二")

    def test_verified_needs_its_own_evidence_not_the_implementation_one(self, store):
        record = self._approved(store)
        store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=IMPLEMENTED, actor="li", evidence_ref="v5.7.0",
                         effective_at="2026-09-25")
        with pytest.raises(InvalidTransitionError, match="复验凭据"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=VERIFIED, actor="wang")

    def test_superseding_points_at_the_order_that_replaces_it(self, store):
        old = _created(store, title="旧方案")
        _affected(store, old)
        with pytest.raises(InvalidTransitionError, match="替代"):
            store.transition(eco_id=old["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                             to_status=SUPERSEDED, actor="zhang", reason="改法变了")
        with pytest.raises(InvalidTransitionError, match="替代"):
            store.transition(eco_id=old["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                             to_status=SUPERSEDED, actor="zhang", reason="改法变了",
                             evidence_ref="ECO-999")
        replacement = _created(store, title="新方案")
        done = store.transition(eco_id=old["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                                to_status=SUPERSEDED, actor="zhang", reason="改法变了",
                                evidence_ref=replacement["eco_id"])
        assert done["status"] == SUPERSEDED and done["closed_at"]

    def test_an_order_can_not_be_its_own_replacement(self, store):
        record = _created(store)
        with pytest.raises(InvalidTransitionError, match="另一张"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                             to_status=SUPERSEDED, actor="zhang", reason="自指",
                             evidence_ref=record["eco_id"])

    def test_an_empty_affected_list_can_not_be_approved(self, store):
        """批准一张什么都不改的单 = 给空白背书的形状错误。"""
        record = _created(store)
        _to_review(store, record)
        with pytest.raises(InvalidTransitionError, match="影响清单为空"):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=APPROVED, actor="li")


class TestTheTransitionLogIsAppendOnly:
    def test_every_surviving_step_leaves_exactly_one_row(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=APPROVED, actor="li")
        rows = store.transitions(eco_id=record["eco_id"], tenant_id=TENANT,
                                 project_id=PROJECT)
        assert [(r["from_status"], r["to_status"], r["actor"]) for r in rows] == [
            ("", DRAFT, "zhang"), (DRAFT, PENDING_REVIEW, "zhang"),
            (PENDING_REVIEW, APPROVED, "li")]

    def test_a_refused_transition_leaves_no_row(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        before = len(store.transitions(eco_id=record["eco_id"], tenant_id=TENANT,
                                       project_id=PROJECT))
        with pytest.raises(InvalidTransitionError):
            store.transition(eco_id=record["eco_id"], tenant_id=TENANT,
                             project_id=PROJECT, to_status=APPROVED, actor="zhang")
        assert len(store.transitions(eco_id=record["eco_id"], tenant_id=TENANT,
                                     project_id=PROJECT)) == before

    def test_the_store_exposes_no_way_to_rewrite_history(self, store):
        """只追加是这张表的规矩：入口层面就不该有 update/delete。"""
        forbidden = [name for name in dir(store)
                     if any(verb in name.casefold() for verb in ("delete", "remove",
                                                                 "update_", "set_"))]
        assert forbidden == [], forbidden

    def test_decisions_also_land_in_the_project_audit_trail(self, store):
        record = _created(store)
        _affected(store, record)
        _to_review(store, record)
        store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=APPROVED, actor="li")
        actions = [row["action"] for row in store._db.list_audit(limit=50)
                   if row["project_id"] == PROJECT]
        assert "eco_created" in actions and "eco_affected_added" in actions
        assert "eco_approved" in actions


class TestReadingBack:
    def test_listing_filters_by_status_and_by_open(self, store):
        closed = _created(store, title="已闭合")
        open_one = _created(store, title="还在审")
        _affected(store, closed)
        _to_review(store, closed)
        store.transition(eco_id=closed["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=APPROVED, actor="li")
        store.transition(eco_id=closed["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=IMPLEMENTED, actor="li", evidence_ref="x",
                         effective_at="2026-09-25")
        store.transition(eco_id=closed["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=VERIFIED, actor="wang", evidence_ref="y")
        assert [r["eco_id"] for r in store.list_orders(tenant_id=TENANT, project_id=PROJECT,
                                                status=VERIFIED)] == [closed["eco_id"]]
        assert [r["eco_id"] for r in store.list_orders(tenant_id=TENANT, project_id=PROJECT,
                                                open_only=True)] == [open_one["eco_id"]]
        with pytest.raises(EcoError, match="未知状态"):
            store.list_orders(tenant_id=TENANT, project_id=PROJECT, status="NOPE")

    def test_scope_is_enforced_on_both_axes(self, store):
        record = _created(store)
        with pytest.raises(NotFoundError):
            store.get(eco_id=record["eco_id"], tenant_id="other", project_id=PROJECT)
        with pytest.raises(NotFoundError):
            store.get(eco_id=record["eco_id"], tenant_id=TENANT, project_id="other")
        assert store.list_orders(tenant_id=TENANT, project_id="other") == []

    def test_open_orders_touching_answers_what_a_release_gate_would_ask(self, store):
        record = _created(store)
        _affected(store, record)
        hits = store.open_orders_touching(tenant_id=TENANT, project_id=PROJECT,
                                          object_type="drawing", object_id="BRK-1.dxf")
        assert [r["eco_id"] for r in hits] == [record["eco_id"]]
        assert store.open_orders_touching(tenant_id=TENANT, project_id=PROJECT,
                                          object_type="drawing",
                                          object_id="NOT-THERE.dxf") == []
        _to_review(store, record)
        store.transition(eco_id=record["eco_id"], tenant_id=TENANT, project_id=PROJECT,
                         to_status=REJECTED, actor="li", reason="风险大")
        assert store.open_orders_touching(tenant_id=TENANT, project_id=PROJECT,
                                          object_type="drawing",
                                          object_id="BRK-1.dxf") == []


class TestMigrationV19:
    def test_a_fresh_db_and_an_upgraded_db_converge_on_the_same_tables(self, tmp_path):
        from aipd_os.state.migrations import MIGRATIONS, current_version, migrate, rollback

        HEAD = MIGRATIONS[-1]["version"]
        # v19 是那三张表的版本；它**不再是链尾**（第 32 片加了 v20），
        # 所以这里按版本号取条目，而不是拿链尾当它。
        assert [m["name"] for m in MIGRATIONS if m["version"] == 19] == ["eco_change_orders"]
        fresh = str(tmp_path / "fresh.db")
        AIPDStateDB(fresh)
        assert current_version(fresh) == HEAD

        old = str(tmp_path / "old.db")
        AIPDStateDB(old)                       # 先建到 HEAD
        rollback(old, 18)                      # 真退到 v18，模拟升级上来的老库
        assert current_version(old) == 18
        migrate(old)
        tables = lambda path: {  # noqa: E731
            row[0] for row in sqlite3.connect(path).execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'eco%'")}
        assert tables(fresh) == tables(old) == {"eco_records", "eco_affected",
                                                "eco_transitions"}

    def test_rollback_removes_the_tables_and_applying_again_recreates_them(self, tmp_path):
        from aipd_os.state.migrations import MIGRATIONS, current_version, migrate, rollback

        path = str(tmp_path / "eco.db")
        AIPDStateDB(path)
        assert current_version(path) == MIGRATIONS[-1]["version"]
        # 链尾现在是 v20：退到 v18 要连着退两格
        assert rollback(path, 18) == [20, 19]
        assert current_version(path) == 18
        with sqlite3.connect(path) as conn:
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'eco%'")}
        assert names == set()
        migrate(path)
        assert current_version(path) == MIGRATIONS[-1]["version"]


class TestCliSurface:
    """`aipd eco …` 的四面：退出码就是判据的一部分（被拒 ≠ 成功）。"""

    def _db(self, tmp_path):
        from aipd_os.cli.main import main

        path = tmp_path / "state.db"
        db = AIPDStateDB(str(path))
        db.ensure_default_tenant()
        db.init_project(TENANT, PROJECT, "测试项目", "目标")
        return path, main

    def _run(self, main, path, *argv):
        return main(["eco", *argv, "--db", str(path), "--project", PROJECT])

    def test_create_makes_a_draft_and_reads_back(self, tmp_path, capsys):
        path, main = self._db(tmp_path)
        rc = self._run(main, path, "create", "--title", "改孔位", "--creator", "zhang",
                       "--json")
        assert rc == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] and doc["eco"]["status"] == DRAFT
        assert doc["eco"]["creator"] == "zhang" and doc["eco"]["approver"] == ""

    def test_a_machine_creator_is_refused_and_leaves_no_record(self, tmp_path, capsys):
        path, main = self._db(tmp_path)
        assert self._run(main, path, "create", "--title", "t",
                         "--creator", "AI-internal") == 2
        capsys.readouterr()
        assert self._run(main, path, "show", "--open", "--json") == 0
        assert json.loads(capsys.readouterr().out)["ecos"] == []

    def test_the_walk_end_to_end_and_the_self_approval_refused(self, tmp_path, capsys):
        path, main = self._db(tmp_path)
        assert self._run(main, path, "create", "--title", "改孔位", "--creator", "zhang",
                         "--json") == 0
        eco_id = json.loads(capsys.readouterr().out)["eco"]["eco_id"]
        assert self._run(main, path, "affected", "--id", eco_id, "--object-type", "drawing",
                         "--object-id", "BRK-1.dxf", "--change", "UPDATE",
                         "--before-sha256", BEFORE, "--after-sha256", AFTER) == 0
        assert self._run(main, path, "transition", "--id", eco_id,
                         "--to", PENDING_REVIEW, "--actor", "zhang") == 0
        capsys.readouterr()
        assert self._run(main, path, "transition", "--id", eco_id, "--to", APPROVED,
                         "--actor", "zhang") == 4, "自批必须退 4，不能退 0"
        assert "不能自己批准" in capsys.readouterr().out
        assert self._run(main, path, "transition", "--id", eco_id, "--to", APPROVED,
                         "--actor", "li", "--json") == 0
        approved = json.loads(capsys.readouterr().out)["eco"]
        assert approved["approver"] == "li" and approved["approved_at"]

    def test_missing_hashes_and_missing_evidence_are_distinct_refusals(self, tmp_path,
                                                                       capsys):
        path, main = self._db(tmp_path)
        self._run(main, path, "create", "--title", "t", "--creator", "zhang", "--json")
        eco_id = json.loads(capsys.readouterr().out)["eco"]["eco_id"]
        assert self._run(main, path, "affected", "--id", eco_id, "--object-type", "bom",
                         "--object-id", "BOM-1", "--change", "UPDATE",
                         "--after-sha256", AFTER) == 2          # 缺改前哈希
        assert self._run(main, path, "affected", "--id", eco_id, "--object-type", "bom",
                         "--object-id", "BOM-1", "--change", "UPDATE",
                         "--before-sha256", BEFORE, "--after-sha256", AFTER) == 0
        self._run(main, path, "transition", "--id", eco_id, "--to", PENDING_REVIEW,
                  "--actor", "zhang")
        self._run(main, path, "transition", "--id", eco_id, "--to", APPROVED, "--actor", "li")
        capsys.readouterr()
        assert self._run(main, path, "transition", "--id", eco_id, "--to", IMPLEMENTED,
                         "--actor", "li") == 4                 # 无落地凭据
        assert "落地凭据" in capsys.readouterr().out

    def test_show_prints_the_affected_line_and_the_flow(self, tmp_path, capsys):
        path, main = self._db(tmp_path)
        self._run(main, path, "create", "--title", "t", "--creator", "zhang", "--json")
        eco_id = json.loads(capsys.readouterr().out)["eco"]["eco_id"]
        self._run(main, path, "affected", "--id", eco_id, "--object-type", "step",
                  "--object-id", "bracket.step", "--change", "ADD",
                  "--after-sha256", AFTER, "--actor", "zhang")
        capsys.readouterr()
        assert self._run(main, path, "show", "--id", eco_id) == 0
        text = capsys.readouterr().out
        assert eco_id in text and "[ADD] step/bracket.step" in text
        assert "—→" + AFTER[:8] in text, "ADD 没有改前值：那一格必须显式画成破折号，不是空"
        assert "(建单)→DRAFT by zhang" in text

    def test_a_missing_order_is_not_found_not_a_crash(self, tmp_path, capsys):
        path, main = self._db(tmp_path)
        assert self._run(main, path, "show", "--id", "ECO-900") == 1
        assert "没有单据 ECO-900" in capsys.readouterr().out
        assert self._run(main, path, "transition", "--id", "ECO-900",
                         "--to", APPROVED, "--actor", "li") == 1


class TestTheTablesAreShapedForTheQueriesWeRun:
    """三张表 + 三条索引是这一片的全部落点；索引必须**真的被热查询用上**。

    为什么钉到查询计划：`open_orders_touching` 是发布前会问的那一句
    （「这版改动有没有对应的未闭合变更单」）。少一条索引或索引列序不对，
    这条查询在规模上就是全表 SCAN——而所有功能用例照样绿。
    """

    def test_the_three_expected_indexes_exist_on_the_right_columns(self, tmp_path):
        path = str(tmp_path / "shape.db")
        AIPDStateDB(path)
        with sqlite3.connect(path) as conn:
            got = {}
            for name in ("idx_eco_scope_status", "idx_eco_affected_object",
                         "idx_eco_transition_order"):
                row = conn.execute("SELECT tbl_name FROM sqlite_master"
                                   " WHERE type='index' AND name=?", (name,)).fetchone()
                assert row, f"v19 该建 {name}"
                cols = [r[2] for r in conn.execute(f"PRAGMA index_info({name})")]
                got[name] = (row[0], cols)
        assert got["idx_eco_scope_status"] == (
            "eco_records", ["tenant_id", "project_id", "status"])
        assert got["idx_eco_affected_object"] == (
            "eco_affected", ["tenant_id", "project_id", "object_type", "object_id"])
        assert got["idx_eco_transition_order"] == (
            "eco_transitions", ["tenant_id", "project_id", "eco_id", "transition_id"])

    def test_the_hot_query_uses_the_affected_index(self, tmp_path):
        store = EcoStore(AIPDStateDB(str(tmp_path / "plan.db")))
        record = _created(store)
        _affected(store, record)
        with store._db.connect() as conn:
            plan = "\n".join(str(row[-1]) for row in conn.execute(
                "EXPLAIN QUERY PLAN SELECT DISTINCT r.* FROM eco_records r"
                " JOIN eco_affected a ON a.eco_id=r.eco_id AND a.tenant_id=r.tenant_id"
                " AND a.project_id=r.project_id WHERE r.tenant_id=? AND r.project_id=?"
                " AND a.object_type=? AND a.object_id=?"
                " AND r.status NOT IN ('VERIFIED','REJECTED','SUPERSEDED')",
                (TENANT, PROJECT, "drawing", "BRK-1.dxf")))
        assert "USING COVERING INDEX idx_eco_affected_object" in plan \
            or "USING INDEX idx_eco_affected_object" in plan, plan
        assert store.open_orders_touching(tenant_id=TENANT, project_id=PROJECT,
                                          object_type="drawing",
                                          object_id="BRK-1.dxf")
