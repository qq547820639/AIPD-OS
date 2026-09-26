"""`bom_cost` 的返工执行器（F-REWORK-COST 第 49 片）。

第 48 片接上「BOM 版本 → 成本结论」的边之后，`truth propagate` 真的会生成 `bom_cost`
任务，而执行器只认图纸两类 ⇒ 那些任务停在「点名拒、不烧 attempts」。本片把成本这一支接上：
按记录里那份口径**重算一遍**，并把**这一条**记录演进到新结果。

钉四件事：
1. **返工不新增版本记录**：两个分支（unchanged / recomputed）跑完，`artifact=bom_cost`
   的有效记录仍是同一条（version 由引擎 bump），边仍只有 bom → cost 那一条；
2. **缺输入的旧记录点名拒，不猜口径**：第 48 片写的记录里没有口径五项的值，
   拿 `--tooling 0` 猜一遍会被记成「按当前 BOM 重算过」；
3. **三种「不算收口」各自开火**：重算器抛异常、回得不全、成本不完整（缺供应商/单价）；
   外加两条一致性拒绝：这笔结论挂的 BOM 已不是当前那份、签名没变而金额变了；
4. **参数面门禁**：`cost calc` 的口径旗子与「记录里存的键」「重算器读的键」两处必须同集合
   ——漏一个就是「新加一个影响成本的旗子，返工却按老口径重算」那种静默错账。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from aipd_os.bom.cost_rework import (
    SUPPORTED_ARTIFACT,
    make_cost_rework_fn,
    rework_cost_artifact,
)
from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "COST-REWORK"

# 第 49 片补进 metadata 的口径五项（值，不是哈希）
CALIBER = ("tooling_fee", "target_quantity", "amortize_over", "nre", "margin_pct")


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "cost rework 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _add_line(db, item, *, cost, qty=1.0, supplier="ACME"):
    assert main(["bom", "add", "--db", str(db), "--project", P, "--part", item,
                 "--quantity", str(qty), "--unit", "ea", "--material", "AL",
                 "--supplier", supplier, "--unit-cost", str(cost),
                 "--currency", "CNY"]) == 0


def _calc(db, capsys, *, margin=20.0):
    rc = main(["cost", "calc", "--db", str(db), "--project", P, "--tooling", "50000",
               "--quantity", "1000", "--nre", "1000", "--margin", str(margin),
               "--truth-lineage", "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload


def _rows(db, artifact):
    return [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)
            if (r.metadata or {}).get("artifact") == artifact]


def _edges(db):
    return {(e["upstream_id"], e["downstream_id"], e["relation"])
            for e in LineageGraph(_store(db)).edges(tenant_id=T, project_id=P)}


def _stale_and_task(db, bom_record):
    engine = PropagationEngine(_store(db))
    report = engine.on_upstream_changed(bom_record)
    assert report["tasks"], f"没生成返工任务：{report}"
    return report


def _recalc_ok(db, **over):
    """真重算器（走 CLI 侧那一份实现），可用 over 覆盖单个字段造矛盾读数。"""
    from aipd_os.cli.commands_manufacturing import recalc_cost_from_record

    def recalc(meta):
        out = recalc_cost_from_record(meta, db_path=str(db), project_id=P)
        out.update(over)
        return out

    return recalc


# ---------- 一、生产者今天真的把口径五项写进 metadata ----------

def test_producer_stores_caliber_values(env, capsys):
    """第 49 片第一步的前提：没有这五项，执行器只能猜口径。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    rc, payload = _calc(db, capsys)
    assert rc == 0, payload
    cost_id = payload["lineage"]["cost"]["record_id"]
    meta = _store(db).get(cost_id).metadata or {}
    assert meta["tooling_fee"] == 50000.0
    assert meta["target_quantity"] == 1000
    assert meta["amortize_over"] is None          # 合法值就是 None（缺省=目标数量）
    assert meta["nre"] == 1000.0
    assert meta["margin_pct"] == 20.0


# ---------- 二、两个成功分支，都不新增版本记录 ----------

def test_unchanged_when_inputs_identical(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    lin = _calc(db, capsys)[1]["lineage"]
    cost_id = lin["cost"]["record_id"]
    before = [r.record_id for r in _rows(db, "bom_cost")]

    _stale_and_task(db, lin["bom"]["record_id"])
    out = rework_cost_artifact(_store(db), cost_id, recalc=_recalc_ok(db))
    assert out["ok"] is True and out["outcome"] == "unchanged", out
    assert out["edges"] == 0
    assert [r.record_id for r in _rows(db, "bom_cost")] == before   # 同一条，不另起
    meta = _store(db).get(cost_id).metadata or {}
    assert meta["last_rework"]["outcome"] == "unchanged"


def test_recomputed_when_bom_lines_change(env, capsys):
    """BOM 真动过 ⇒ 这条结论演进到新输入集合与新金额，并把边改挂当前 BOM 记录。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    lin = _calc(db, capsys)[1]["lineage"]
    bom_id, cost_id = lin["bom"]["record_id"], lin["cost"]["record_id"]
    old_total = (_store(db).get(cost_id).metadata or {})["total_cost"]
    old_content = _store(db).get(cost_id).content
    _stale_and_task(db, bom_id)

    _add_line(db, "cover", cost=3.2, qty=2.0)      # BOM 变了，但没重跑 cost calc
    out = rework_cost_artifact(_store(db), cost_id, recalc=_recalc_ok(db))
    assert out["ok"] is True and out["outcome"] == "recomputed", out
    assert out["total_cost"] != old_total, "金额没跟着 BOM 动，重算等于没算"
    assert out["upstream_record_id"] == bom_id and out["edges"] == 1

    rec = _store(db).get(cost_id)
    assert rec.content != old_content
    assert f"total={out['total_cost']}" in rec.content
    assert (bom_id, cost_id, "affects") in _edges(db)
    assert len(_rows(db, "bom_cost")) == 1, "返工不许新增版本记录"


def test_rework_closes_the_stale_task_end_to_end(env, capsys):
    """引擎侧收口：跑一次 truth rework，任务 succeeded、记录回 active。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    lin = _calc(db, capsys)[1]["lineage"]
    _stale_and_task(db, lin["bom"]["record_id"])

    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--all-pending", "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    assert payload["ok"] is True and payload["refused"] == []
    assert payload["supported_artifacts"] == ["drawing_spec", "drawing_dxf",
                                              "bom", "bom_cost"]
    assert [r["executor"]["outcome"] for r in payload["results"]] == ["unchanged"]
    assert _store(db).get(lin["cost"]["record_id"]).status == "active"


def test_make_rework_fn_is_boolean_for_the_engine(env, capsys):
    """`run_rework` 只认 True/False：这里钉住适配层不吞掉失败。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    assert make_cost_rework_fn(_store(db), _recalc_ok(db))(cost_id) is True
    assert make_cost_rework_fn(_store(db), _recalc_ok(db))("T-9999") is False


# ---------- 三、拒绝面：每一种都要点名，且不写任何东西 ----------

def _snapshot(db):
    store = _store(db)
    return {r.record_id: (r.content, r.status, dict(r.metadata or {}))
            for r in store.query(record_type="artifact_version",
                                 tenant_id=T, project_id=P)}


def _assert_untouched(db, before, out, outcome, **extra):
    assert out["ok"] is False and out["outcome"] == outcome, out
    assert out["truth_id"] in before
    after = _snapshot(db)
    assert after == before, f"{outcome} 这一支不该写任何东西，却改了记录"


def test_refuses_other_artifacts(env, capsys):
    assert SUPPORTED_ARTIFACT == "bom_cost"      # 分派表与执行器说的是同一个制品
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    bom_id = _calc(db, capsys)[1]["lineage"]["bom"]["record_id"]
    before = _snapshot(db)
    out = rework_cost_artifact(_store(db), bom_id, recalc=_recalc_ok(db))
    _assert_untouched(db, before, out, "unsupported_artifact")
    assert out["artifact"] == "bom"


def test_refuses_when_record_missing(env):
    tmp_path, db = env
    out = rework_cost_artifact(_store(db), "T-4242", recalc=_recalc_ok(db))
    assert out["ok"] is False and out["outcome"] == "missing_record"


def test_refuses_pre_slice49_record_without_guessing(env, capsys):
    """第 48 片写的记录没有口径值 ⇒ 点名拒，而不是拿 --tooling 0 猜一遍。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    store = _store(db)
    legacy = {k: v for k, v in (store.get(cost_id).metadata or {}).items()
              if k not in CALIBER}
    store.update(cost_id, metadata=legacy)
    assert "tooling_fee" not in (_store(db).get(cost_id).metadata or {})
    before = _snapshot(db)

    called: list = []
    out = rework_cost_artifact(_store(db), cost_id,
                               recalc=lambda m: called.append(1) or {})
    _assert_untouched(db, before, out, "missing_inputs")
    assert set(out["missing_inputs"]) >= set(CALIBER)
    assert called == [], "缺输入就不该去调重算器"


def test_refuses_when_recalc_raises(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    before = _snapshot(db)

    def boom(meta):
        raise RuntimeError("BOM 读不到行")

    out = rework_cost_artifact(_store(db), cost_id, recalc=boom)
    _assert_untouched(db, before, out, "recalc_failed")
    assert "BOM 读不到行" in out["reason"]


def test_refuses_when_recalc_result_is_incomplete(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    before = _snapshot(db)
    out = rework_cost_artifact(_store(db), cost_id,
                               recalc=lambda m: {"bom_id": m["bom_id"]})
    _assert_untouched(db, before, out, "recalc_incomplete_result")
    assert "total_cost" in out["missing_fields"]


def test_refuses_other_boms_conclusion(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    before = _snapshot(db)
    out = rework_cost_artifact(_store(db), cost_id,
                               recalc=_recalc_ok(db, bom_id="BOM-777"))
    _assert_untouched(db, before, out, "bom_moved")
    assert out["recorded"] != out["current"]


def test_refuses_incomplete_cost(env, capsys):
    """缺单价时 compute_bom_cost 明写 cost_complete=False ⇒ 不能关掉 stale。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    before = _snapshot(db)
    out = rework_cost_artifact(_store(db), cost_id,
                               recalc=_recalc_ok(db, cost_complete=False))
    _assert_untouched(db, before, out, "cost_incomplete")


def test_refuses_signature_same_but_total_differs(env, capsys):
    """确定性计算器不该给出「输入没变、钱变了」——拿它 bump 版本等于把错账转正。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)[1]["lineage"]["cost"]["record_id"]
    before = _snapshot(db)
    out = rework_cost_artifact(_store(db), cost_id,
                               recalc=_recalc_ok(db, total_cost=-1.0))
    _assert_untouched(db, before, out, "recalc_disagrees")


# ---------- 四、参数面门禁（AST 反查，不靠手写名单） ----------

# cost calc 里影响成本的旗子 dest（与 CALIBER 一一对应）
CALIBER_DESTS = {"tooling", "quantity", "amortize_over", "nre", "margin"}
# 声明了但不进入成本口径的旗子：必须逐个点名，新旗子不归类就会红
NON_COST_DESTS = {"db", "project", "json", "truth_lineage"}


def _cost_calc_dests() -> set[str]:
    """从 cli/main.py 的 AST 里读出 `cost calc` 真正声明的旗子 dest。

    两处都必须钉住，缺一就会得到「看着合理但错」的读数：
    - **不能只按变量名收**：`cp` 在本文件里被赋值过三次（cad preflight / cad build /
      cost calc），只认名字会把 `--manifest`、`--target` 一起收进来；
    - **不能用 ast.walk 的顺序推「进没进到这一段」**：walk 是广度优先，不是源码序。
    所以按「该次赋值的行号 → 该变量的下一次赋值行号」把范围切出来。
    """
    src = (ROOT / "src/aipd_os/cli/main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assignments: dict[str, list[int]] = {}
    target: tuple[str, int] | None = None
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "add_parser" and node.value.args
                and isinstance(node.value.args[0], ast.Constant)):
            continue
        name = node.targets[0].id
        assignments.setdefault(name, []).append(node.lineno)
        if node.value.args[0].value == "calc":
            target = (name, node.lineno)
    assert target, "找不到 cost calc 的子解析器：判据的前提塌了，不要当成「没有旗子」"
    var, line = target
    later = [ln for ln in assignments[var] if ln > line]
    upper = min(later) if later else 10 ** 9

    dests: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == var and node.args
                and line < node.lineno < upper):
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)
                and first.value.startswith("--")):
            continue
        dest = next((k.value.value for k in node.keywords
                     if k.arg == "dest" and isinstance(k.value, ast.Constant)), None)
        dests.add(dest or first.value.lstrip("-").replace("-", "_"))

    # 反向对照：这三样属于别的子命令，混进来就说明范围切错了（over-collection 看得见）
    foreign = {"manifest", "target", "views"} & dests
    assert not foreign, f"范围切错，混进了别的子命令：{sorted(foreign)}"
    assert {"tooling", "quantity", "amortize_over", "nre", "margin"} <= dests, dests
    return dests


def test_every_cost_flag_is_classified():
    """新加一个 `cost calc` 旗子必须在这里显式归类，否则「按老口径重算」会静默成立。"""
    dests = _cost_calc_dests()
    unknown = dests - CALIBER_DESTS - NON_COST_DESTS
    assert not unknown, (
        f"这些 cost calc 旗子既不进成本口径、也不在「不影响成本」名单里：{sorted(unknown)}；"
        "影响成本的旗子必须同时进 metadata 与重算器，否则返工会按老口径重算")


def test_recalc_reads_exactly_the_stored_caliber_keys():
    """重算器读的键 == 生产者存的键 == 口径五项：三处任一处漏一个都会红。"""
    src = (ROOT / "src/aipd_os/cli/commands_manufacturing.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef)
              and n.name == "recalc_cost_from_record")
    read = {n.args[0].value for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get" and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "meta"
            and n.args and isinstance(n.args[0], ast.Constant)
            and isinstance(n.args[0].value, str)}
    assert read == set(CALIBER), read

    lin = ast.parse((ROOT / "src/aipd_os/bom/cost_lineage.py").read_text(encoding="utf-8"))
    stored: set[str] = set()
    for node in ast.walk(lin):
        if (isinstance(node, ast.keyword) and node.arg == "metadata"
                and isinstance(node.value, ast.Dict)):
            # ast.Dict.keys 就是键表达式本身（不是 key/value 成对节点）；
            # 另有一处 metadata=metadata 传的是变量，不是字面量，得先按类型筛掉。
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
            if "input_signature" in keys and "total_cost" in keys:
                stored |= (keys & set(CALIBER))
    assert stored == set(CALIBER), stored
