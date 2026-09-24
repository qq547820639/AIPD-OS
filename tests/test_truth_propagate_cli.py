"""F-TRUTH-PROP-01：失效传播必须有一条**真命令**走得到，而不是只有测试会构造。

接线前的实测事实（本轮 `git grep` + 逐文件读，file:line 见下）：

- 引擎 `src/aipd_os/product_truth/propagation.py:33` 在产品侧 **0 调用点**：9 处构造全在
  `tests/`；产品代码里连 import 都没有（`product_truth/__init__.py:18,25` 只是再导出）。
- 产品侧唯一的 truth 写入者是 `product_intelligence/gate.py:454,475`（`commit_snapshot`），
  而它自己在 `src/aipd_os/cli/` 里也是 0 调用点 ⇒ 把传播挂到它身上只是把「不可达」上移一层。
- 声明门禁 `registry.py:244 probe_entry_callable` 只验「入口字符串解析成 callable + 文件存在」，
  `registry.py:287-290` 明写入口可调用性**不作为降级门槛**，`run_command` 全程不执行
  ⇒ 一条不可达的能力能过今天所有门禁。这就是本文件要补的那道闸。

接线后必须能机器核的四件事：

1. **真的落库**：`aipd truth propagate` 之后，下游记录状态变 `stale`、`rework_tasks` 里
   真有一行待办——不是只打印一句「已传播」。
2. **「已过期」不等于「没影响」**：引擎返回的 `stale` 只含**本次新置**的（
   `propagation.py:54-58`），所以第二次跑会得到空列表。空列表如果被原样转述，读的人会把
   「下游早就 stale、还欠着返工」听成「这次什么都没影响」。因此命令必须分两栏报
   （`supply_chain/impact` 的 `already_stale_deliverables` 是同一条纪律）。
3. **作用域不溢出**：另一个 project 的边与记录一律看不见、改不着。
4. **没接上的那一半要留痕**：`run_rework`（真正执行返工的那半）本轮**刻意不接**——没有真实
   执行器时它唯一的产出是 `blocked`（`propagation.py:177-185`「refusing fake success」），
   一条永远失败的命令比没有更容易被读成「返工跑过了」。这个缺口由
   `test_run_rework_is_still_unreachable` 钉成断言：将来接上执行器时它会红，逼着同一趟把
   断言与文档一起改判，而不是让「已接线」这句话悄悄越界。
"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.cli._helpers import DEFAULT_TENANT
from aipd_os.cli.main import main
from aipd_os.product_truth.lineage import LineageGraph
from aipd_os.product_truth.models import TruthRecord
from aipd_os.product_truth.store import ProductTruthStore
from aipd_os.state.db import AIPDStateDB

T = DEFAULT_TENANT
P = "proj_tp"
REPO = Path(__file__).resolve().parents[1]


_READY: set[tuple[str, str]] = set()


def _db(tmp_path, project: str = P) -> Path:
    """幂等建库：本文件的多个辅助函数会各自再取一次同一条路径。

    不幂等就会在 `init_project` 上撞 `projects` 的唯一约束（第一版就撞了），
    那种红看着像被测代码的缺陷，其实是夹具在自我重复。
    """
    path = Path(tmp_path) / "state.db"
    state = AIPDStateDB(str(path))
    state.ensure_default_tenant()
    key = (str(path), project)
    if key not in _READY:
        state.init_project(T, project, f"{project} 项目", "把支架做成可量产件")
        _READY.add(key)
    return path


def _store(tmp_path, project: str = P) -> ProductTruthStore:
    return ProductTruthStore(str(_db(tmp_path, project)), tenant_id=T,
                             project_id=project)


def _record(store, content: str, rtype: str = "ctq") -> str:
    """store.add 返回的是记录 id 字符串（不是对象）。"""
    return str(store.add(TruthRecord(record_type=rtype, content=content,
                                     trust_level="verified")))


def _chain(store, *ids: str) -> None:
    graph = LineageGraph(store)
    for up, down in zip(ids, ids[1:]):
        graph.add_edge(up, down, relation="derived_from")


def _status(tmp_path, rid: str, project: str = P) -> str:
    return str(_store(tmp_path, project).get(rid).status)


def _tasks(tmp_path, project: str = P):
    store = _store(tmp_path, project)
    with store.connect() as c:
        return c.execute("SELECT task_id,truth_id,status,attempts,max_attempts "
                         "FROM rework_tasks WHERE tenant_id=? AND project_id=? "
                         "ORDER BY created_at", (T, project)).fetchall()


def _run(argv, capsys, expect: int = 0) -> dict:
    capsys.readouterr()
    rc = main(argv)
    out = capsys.readouterr().out.strip()
    assert rc == expect, f"rc={rc}（期望 {expect}）：{out[:600]}"
    payload: dict = json.loads(out)
    return payload


def _propagate(tmp_path, capsys, upstream: str, expect: int = 4, **extra) -> dict:
    argv = ["truth", "propagate", "--db", str(_db(tmp_path)), "--project", P,
            "--upstream", upstream, "--json"]
    for k, v in extra.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return _run(argv, capsys, expect=expect)


class TestPropagationLandsOnDisk:
    def test_downstream_is_marked_stale_and_a_rework_task_is_created(self, tmp_path,
                                                                    capsys):
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        down = _record(store, "图纸 Ø8 孔位公差 ±0.02", rtype="fact")
        _chain(store, up, down)

        payload = _propagate(tmp_path, capsys, up, reason="载荷口径改了")
        assert payload["affected"] == [down]
        assert payload["marked_stale"] == [down]
        assert payload["already_stale"] == []
        assert payload["ok"] is False and payload["pending_rework"] is True
        assert _status(tmp_path, down) == "stale"
        assert _status(tmp_path, up) == "active", "上游本身不该被标 stale"
        rows = _tasks(tmp_path)
        assert [(r["truth_id"], r["status"], r["max_attempts"]) for r in rows] == [
            (down, "pending", 3)]
        assert rows[0]["task_id"].startswith("RW-")
        assert "载荷口径改了" in payload["tasks"][0]["reason"], "--reason 要真的落到任务上"

    def test_max_attempts_is_carried_onto_every_new_task(self, tmp_path, capsys):
        """`--max-attempts` 要真的进任务行，否则「有界」只是命令行为用户画的饼。"""
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        down = _record(store, "图纸 Ø8 孔位公差 ±0.02", rtype="fact")
        _chain(store, up, down)
        payload = _propagate(tmp_path, capsys, up, max_attempts=5)
        assert [t["max_attempts"] for t in payload["tasks"]] == [5]
        assert [r["max_attempts"] for r in _tasks(tmp_path)] == [5]

    def test_a_two_hop_chain_propagates_to_both_downstreams(self, tmp_path, capsys):
        store = _store(tmp_path)
        a = _record(store, "需求：承载 50kg")
        b = _record(store, "CTQ Ø8 ±0.02")
        c = _record(store, "BOM 行 P-3")
        _chain(store, a, b, c)
        payload = _propagate(tmp_path, capsys, a)
        assert set(payload["affected"]) == {b, c}
        assert _status(tmp_path, b) == "stale" and _status(tmp_path, c) == "stale"
        assert len(_tasks(tmp_path)) == 2

    def test_explanation_is_the_owner_facing_four_part_text(self, tmp_path, capsys):
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        down = _record(store, "图纸 Ø8 孔位公差 ±0.02", rtype="fact")
        _chain(store, up, down)
        exp = _propagate(tmp_path, capsys, up)["explanation"]
        assert set(exp) >= {"what_changed", "why_affected", "fix_plan", "approval_needed"}
        assert down in exp["why_affected"]
        assert down in exp["approval_needed"], "批准要落在具体条目上，不是一句概括"


class TestNothingAffectedIsSaidPlainly:
    def test_a_leaf_record_propagates_to_nothing_and_is_a_clean_zero(self, tmp_path,
                                                                    capsys):
        store = _store(tmp_path)
        leaf = _record(store, "没人依赖的假设")
        payload = _propagate(tmp_path, capsys, leaf, expect=0)
        assert payload["affected"] == [] and payload["marked_stale"] == []
        assert payload["upstream_kind"] == "truth"
        assert payload["ok"] is True and payload["pending_rework"] is False
        assert _tasks(tmp_path) == []

    def test_an_upstream_that_is_not_a_truth_record_is_labelled_not_invented(
            self, tmp_path, capsys):
        """上游可能是 Product Intelligence 对象（PI 需求 id，不在 truth 表里）。

        这条钉的是「诚实降级」：认不出就说是 PI/外部上游，绝不因为查不到就把命令判成
        成功——也不顺手编一条 truth 详情出来。
        """
        _store(tmp_path)
        payload = _propagate(tmp_path, capsys, "REQ-does-not-exist", expect=0)
        assert payload["upstream_kind"] == "intelligence_or_external"
        assert payload["affected"] == []
        assert "product intelligence object" in payload["explanation"]["what_changed"]

    def test_second_run_says_already_stale_rather_than_nothing_affected(
            self, tmp_path, capsys):
        """引擎的 stale 只含本次新置的；空列表原样转述就等于把欠着的返工说成没影响。"""
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        down = _record(store, "图纸 Ø8 孔位公差 ±0.02", rtype="fact")
        _chain(store, up, down)
        first = _propagate(tmp_path, capsys, up)
        second = _propagate(tmp_path, capsys, up)
        assert first["marked_stale"] == [down] and first["already_stale"] == []
        assert second["marked_stale"] == []
        assert second["already_stale"] == [down]
        assert second["ok"] is False, "已过期但仍欠返工 ⇒ 不能因为『没新置』就报绿灯"
        assert len(_tasks(tmp_path)) == 2, "每次传播都生成一条新的返工任务（引擎现状）"


class TestScopeDoesNotLeak:
    def test_another_projects_edge_and_record_are_untouched(self, tmp_path, capsys):
        mine = _store(tmp_path, P)
        other = _store(tmp_path, "proj_other")
        up_mine = _record(mine, "本项目 CTQ")
        up_other = _record(other, "另一项目 CTQ")
        down_other = _record(other, "另一项目图纸事实", rtype="fact")
        _chain(other, up_other, down_other)

        payload = _propagate(tmp_path, capsys, up_mine, expect=0)
        assert payload["affected"] == []
        assert _status(tmp_path, down_other, "proj_other") == "active"
        assert _tasks(tmp_path, "proj_other") == []

    def test_tasks_command_reads_only_its_own_scope(self, tmp_path, capsys):
        mine = _store(tmp_path, P)
        other = _store(tmp_path, "proj_other")
        up_mine = _record(mine, "本项目 CTQ")
        down_mine = _record(mine, "本项目图纸事实", rtype="fact")
        up_other = _record(other, "另一项目 CTQ")
        down_other = _record(other, "另一项目图纸事实", rtype="fact")
        _chain(mine, up_mine, down_mine)
        _chain(other, up_other, down_other)
        _propagate(tmp_path, capsys, up_mine)
        _run(["truth", "propagate", "--db", str(_db(tmp_path)), "--project",
              "proj_other", "--upstream", up_other, "--json"], capsys, expect=4)

        payload = _run(["truth", "tasks", "--db", str(_db(tmp_path)), "--project", P,
                        "--json"], capsys)
        assert [t["truth_id"] for t in payload["tasks"]] == [down_mine]


class TestTaskListingIsReadOnly:
    def test_tasks_lists_state_and_changes_nothing(self, tmp_path, capsys):
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        down = _record(store, "图纸 Ø8 孔位公差 ±0.02", rtype="fact")
        _chain(store, up, down)
        _propagate(tmp_path, capsys, up)

        listed = _run(["truth", "tasks", "--db", str(_db(tmp_path)), "--project", P,
                       "--json"], capsys)
        assert listed["ok"] is True and listed["command"] == "truth tasks"
        one = listed["tasks"][0]
        assert one["status"] == "pending" and one["attempts"] == 0
        assert _status(tmp_path, down) == "stale"
        # 只读：**库里**的任务状态在列过之后仍然是 pending（绝对判据）。
        # 只比「列两次结果相同」挡不住「第一次就把状态推进」——那种写法两次都读到
        # 被推进后的值，看起来完全一致（变异 T9 就是这样活下来的，实测）。
        assert [r["status"] for r in _tasks(tmp_path)] == ["pending"], \
            "列待办改到了库里的任务状态：这不是只读命令"
        before = [(r["task_id"], r["status"]) for r in _tasks(tmp_path)]
        _run(["truth", "tasks", "--db", str(_db(tmp_path)), "--project", P,
              "--json"], capsys)
        assert [(r["task_id"], r["status"]) for r in _tasks(tmp_path)] == before

        filtered = _run(["truth", "tasks", "--db", str(_db(tmp_path)), "--project", P,
                         "--status", "succeeded", "--json"], capsys)
        assert filtered["tasks"] == []


class TestBadDeclarationIsTwo:
    def test_missing_db_is_two_not_an_empty_success(self, tmp_path, capsys):
        capsys.readouterr()
        rc = main(["truth", "propagate", "--db", str(tmp_path / "nope.db"),
                   "--project", P, "--upstream", "T-1", "--json"])
        out = capsys.readouterr().out.strip()
        assert rc == 2, f"库不存在却返回 {rc}：{out}"

    def test_non_positive_max_attempts_is_rejected(self, tmp_path, capsys):
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        capsys.readouterr()
        rc = main(["truth", "propagate", "--db", str(_db(tmp_path)), "--project", P,
                   "--upstream", up, "--max-attempts", "0", "--json"])
        capsys.readouterr()
        assert rc == 2, "上限 <=0 会被引擎当合法值，等于一跑就 blocked 或永不 blocked"


class TestReachableFromProductPath:
    """本轮缺陷本体：命令面必须真的存在，并且真的走到引擎与那张表。"""

    def test_the_command_is_registered_as_public_with_required_args(self):
        from aipd_os.cli.command_contract import CommandStatus, get_command_entry

        entry = get_command_entry("truth propagate")
        assert entry is not None, "truth propagate 没进命令契约表"
        assert entry.status is CommandStatus.PUBLIC
        assert {"--db", "--project", "--upstream"} <= set(entry.requires_args)

    def test_the_handler_is_dispatched_from_the_command_table(self):
        from aipd_os.cli.commands import COMMAND_FUNCS

        assert "truth propagate" in COMMAND_FUNCS and "truth tasks" in COMMAND_FUNCS

    def test_the_cli_path_is_the_only_way_this_file_produces_a_task(self, tmp_path,
                                                                   capsys):
        """前提断言：直接构造引擎这条路**不走**——表里那行只能来自 main()。

        少了这条前提，「命令能跑」的用例其实可能是别处的副作用撑绿的。
        """
        store = _store(tmp_path)
        up = _record(store, "支架最大载荷 50kg")
        down = _record(store, "图纸 Ø8 孔位公差 ±0.02", rtype="fact")
        _chain(store, up, down)
        assert _tasks(tmp_path) == []          # 跑命令之前，表是空的
        _propagate(tmp_path, capsys, up)
        assert len(_tasks(tmp_path)) == 1      # 之后才有——只可能来自 CLI


class TestUnwiredHalfStaysVisible:
    def test_run_rework_is_still_unreachable_from_product_code(self):
        """没有真实执行器 ⇒ 本轮不接 `run_rework`，并把这句话钉成断言。

        扫的是 **AST 里的代码引用**（`Name`/`Attribute`），不是子串：本文件的模块 docstring
        与 `--help` 文案都要提到这个名字，子串扫描会把「写清楚了没接」误判成「已经接了」
        ——而这两种情况的正确处置完全相反。

        极性说明：将来接上返工执行器时这条**必须**变红，逼着同一趟把
        `registry_data` 的 `current_limitation`、`docs/architecture/truth_architecture.md`
        与这里的断言一起改判，而不是让「传播已接线」悄悄越界成「返工已接线」。
        """
        import ast

        hits = []
        for path in (REPO / "src" / "aipd_os").rglob("*.py"):
            if path.name == "propagation.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                named = (node.id if isinstance(node, ast.Name) else
                         node.attr if isinstance(node, ast.Attribute) else None)
                if named == "run_rework":
                    hits.append(f"{path.relative_to(REPO)}:{node.lineno}")
        assert hits == [], f"run_rework 已被产品代码引用（{hits}）：请连同本用例极性一起改判"

    def test_the_registry_states_what_is_wired_and_what_is_not(self):
        """登记里两句话必须同时成立：传播已可达；返工执行仍是缺口。

        接线之后还写着「0 调用点」就是低报（本轮之前第 8 片就是这么漂了一轮）；
        反过来，如果哪天整段缺口描述被删掉，那条假绿比低报危险得多——所以这里
        同时断言**新行里必须还留着 run_rework 未接线的说法**。
        """
        from aipd_os.registry_data import CAPABILITIES

        by_id = {str(r.get("id")): r for r in CAPABILITIES}
        old = str(by_id["industrialize.physical_writeback"].get("current_limitation") or "")
        assert "PropagationEngine 仍是 0 调用点" not in old, \
            "传播已经可达了，登记里不该还写着 0 调用点"
        assert "truth propagate" in old, "要指得清是哪条命令接上的"

        new = by_id.get("product_truth.impact_propagation")
        assert new is not None, "新接的能力必须在登记里有自己的行"
        assert new.get("entry_point") == "aipd_os.cli.commands_truth.cmd_truth_propagate"
        assert (REPO / str(new.get("implementation_file"))).is_file()
        limitation = str(new.get("current_limitation") or "")
        assert "run_rework" in limitation and "0 调用点" in limitation, \
            "未接的那一半必须写在这一行里，不能只留在测试断言里"


def test_prose_json_is_not_the_carrier(tmp_path, capsys):
    """`--json` 走 stdout 一份可解析载荷；缺省时走人话，不能把 JSON 直接吐给终端。"""
    store = _store(tmp_path)
    up = _record(store, "支架最大载荷 50kg")
    _propagate(tmp_path, capsys, up, expect=0)
    capsys.readouterr()
    rc = main(["truth", "propagate", "--db", str(_db(tmp_path)), "--project", P,
               "--upstream", up])
    out = capsys.readouterr().out
    assert rc == 0
    assert "下游" in out or "affected" in out.lower()
    assert not out.lstrip().startswith("{"), "人话模式不该输出 JSON"
