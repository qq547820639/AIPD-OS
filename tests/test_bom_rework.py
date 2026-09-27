"""`artifact=bom` 的返工执行器（F-REWORK-BOM 第 53 片）。

第 51 片让库自己**发现**「BOM 版本记录该 stale 却还 active」，第 52 片把报价那一格的
漂移键接到库里的事实上；两片的 §六 都留着同一句：**发现之后仍没有执行器收得了口**
（`truth rework` 只认 drawing_spec / drawing_dxf / bom_cost）。本片补第四支。

钉五件事：
1. **返工不新增版本记录**：两个分支跑完，`artifact=bom` 的有效记录还是同一条，
   边集合不变（引擎 bump 的是这一条，另起新版是生产面 `cost calc --truth-lineage` 的规则）；
2. **正文与 metadata 由生产面那份投影给出**（`bom_version_fields`）：
   两边各写一遍映射时「签名相同、正文不同」谁也看不见（第 52 片同格）；
3. **绝对断言**：演进后的键等于**按当前 BOM 行现算**的那把签名，
   而不是"和重算器自己说一致"；
4. **拒绝面各点名一种**且不写任何东西：缺输入 / 记录读不到 / 不是 bom /
   重算器抛 / 重算器回得不全 / 这张 BOM 已不是当前那张 / 当前 BOM 没有行 /
   签名没变而身份字段变了；
5. **收口之后漂移要读成一致**：返工跑完再扫，这条记录不该还被点成「该 stale 却 active」。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.bom.bom_rework import (
    SUPPORTED_ARTIFACT,
    make_bom_rework_fn,
    rework_bom_artifact,
)
from aipd_os.bom.cost_lineage import bom_input_signature, version_content
from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore
from aipd_os.product_truth.drift import IN_SYNC, classify_record
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "BOM-REWORK"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "bom rework 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _add_line(db, item, *, cost=12.5, qty=1.0, supplier="ACME"):
    assert main(["bom", "add", "--db", str(db), "--project", P, "--part", item,
                 "--quantity", str(qty), "--unit", "ea", "--material", "AL",
                 "--supplier", supplier, "--unit-cost", str(cost),
                 "--currency", "CNY"]) == 0


def _calc(db, capsys):
    rc = main(["cost", "calc", "--db", str(db), "--project", P, "--tooling", "50000",
               "--quantity", "1000", "--nre", "1000", "--margin", "20",
               "--truth-lineage", "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    return payload


def _rows(db, artifact):
    return [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)
            if (r.metadata or {}).get("artifact") == artifact]


def _edges(db):
    return {(e["upstream_id"], e["downstream_id"], e["relation"])
            for e in LineageGraph(_store(db)).edges(tenant_id=T, project_id=P)}


def _snapshot(db):
    store = _store(db)
    return {r.record_id: (r.content, r.status, r.version, dict(r.metadata or {}))
            for r in store.query(record_type="artifact_version",
                                 tenant_id=T, project_id=P)}


def _recalc(db, **over):
    """真重算器（CLI 侧那一份实现），可用 over 覆盖单个字段造矛盾读数。"""
    from aipd_os.cli.commands_manufacturing import bom_from_record

    def recalc(meta):
        out = bom_from_record(meta, db_path=str(db), project_id=P)
        out.update(over)
        return out

    return recalc


def _current_bom_signature(db):
    """绝对断言用的那份键：由 BOM 表**当前的行**现算，不经过执行器。"""
    from aipd_os.bom import BomStore
    from aipd_os.cli.commands_manufacturing import _bom_store_path

    store = BomStore(str(_bom_store_path(str(db))))
    header = store.get_bom(T, P)
    lines = store.list_lines(T, P, bom_id=header.bom_id)
    return bom_input_signature(bom_id=header.bom_id, revision=str(header.revision),
                               version_no=header.version_no, lines=lines)


def _stale(db, record_id):
    engine = PropagationEngine(_store(db))
    engine._create_rework(record_id, "第 53 片：造一条待返工", 3)  # noqa: SLF001
    _store(db).set_status(record_id, "stale")
    return engine.list_tasks(status="pending")[0].to_dict()["task_id"]


# ---------- 一、两个分支都不新增版本记录 ----------

def test_unchanged_rework_writes_nothing_and_keeps_one_record(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    task_id = _stale(db, bom_id)
    before = _snapshot(db)

    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--task", task_id, "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    assert payload["results"][0]["executor"]["outcome"] == "unchanged", payload
    assert len(_rows(db, "bom")) == 1
    assert _store(db).get(bom_id).status == "active"
    # unchanged 这一支执行器只留 last_rework 一格；正文与键都不动。
    # status/version **该**变——那是引擎收口的动作（bump 这一条、关 stale），
    # 不是执行器写的，所以这里钉的是「引擎改了状态、执行器没改内容」。
    after = _snapshot(db)
    assert after[bom_id][0] == before[bom_id][0], "unchanged 却重写了正文"
    assert after[bom_id][3]["input_signature"] == before[bom_id][3]["input_signature"]
    assert after[bom_id][1] == "active" and before[bom_id][1] == "stale"
    assert after[bom_id][2] == before[bom_id][2] + 1, "版本要由引擎 bump 这一条"
    assert len(_rows(db, "bom")) == 1


def test_recomputed_rework_evolves_this_record_to_current_rows(env, capsys):
    """效力：BOM 加了行 ⇒ 这条记录演进到新键，且**仍是同一条**（不另起新版）。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    old = _store(db).get(bom_id)
    old_sig = old.metadata["input_signature"]
    task_id = _stale(db, bom_id)

    _add_line(db, "cover", cost=3.2)                  # 真改 BOM
    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--task", task_id, "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    ex = payload["results"][0]["executor"]
    assert ex["outcome"] == "recomputed" and ex["edges"] == 0, ex

    now = _store(db).get(bom_id)
    assert now.metadata["input_signature"] == _current_bom_signature(db), \
        "演进后的键不等于当前 BOM 行现算的那把"
    assert now.metadata["input_signature"] != old_sig
    assert len(_rows(db, "bom")) == 1, "返工不许另起版本记录"
    assert now.status == "active"


def test_reworked_record_takes_the_producer_content_shape(env, capsys):
    """正文必须等于**生产面那份投影**算出来的形状，不是执行器自己拼的串。

    这条是「两边各写一遍映射」的闸：投影函数一改，这里立刻对不上。
    """
    from aipd_os.bom.cost_lineage import bom_version_fields
    from aipd_os.cli.commands_manufacturing import bom_from_record

    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    store = _store(db)
    meta = dict(store.get(bom_id).metadata or {})
    _add_line(db, "cover", cost=3.2)
    out = bom_from_record(meta, db_path=str(db), project_id=P)
    rework_bom_artifact(store, bom_id, recalc=lambda m: out)

    fields = bom_version_fields(out["header"], out["lines"],
                                signature=out["bom_signature"])
    rec = store.get(bom_id)
    assert rec.content == version_content(artifact="bom", bom_id=str(meta["bom_id"]),
                                         signature=out["bom_signature"],
                                         detail=fields["detail"])
    assert {k: v for k, v in rec.metadata.items() if k != "last_rework"} == \
        fields["metadata"], "metadata 与生产面投影不再是同一份形状"


def test_rework_then_drift_reads_the_record_in_sync(env, capsys):
    """第 52 片发现 + 第 53 片收口要对得上：返工跑完，扫描不该再点这条。"""
    from aipd_os.cli.commands_drift import build_resolvers

    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    _stale(db, bom_id)
    _add_line(db, "cover", cost=3.2)

    out = rework_bom_artifact(_store(db), bom_id, recalc=_recalc(db))
    assert out["ok"] is True and out["outcome"] == "recomputed", out
    verdict = classify_record(_store(db).get(bom_id),
                              build_resolvers(str(db), P)["bom"])
    assert verdict["state"] == IN_SYNC, verdict


# ---------- 二、拒绝面：每种各点名一次，且一个字都不写 ----------

def _assert_untouched(db, before, out, outcome, **extra):
    assert out["ok"] is False and out["outcome"] == outcome, out
    after = _snapshot(db)
    assert after == before, f"{outcome} 这一支不该写任何东西，却改了记录"


def test_refuses_quote_batch(env, capsys):
    """接上 bom 之后，「没有执行器」那一格换成了 quote_batch：仍要点名拒、不烧 attempts。"""
    assert SUPPORTED_ARTIFACT == "bom"
    tmp_path, db = env
    _add_line(db, "bracket")
    _calc(db, capsys)
    assert main(["quote", "apply", "--db", str(db), "--project", P,
                 "--file", _quote_file(tmp_path), "--currency", "CNY",
                 "--truth-lineage", "--json"]) == 0
    capsys.readouterr()
    qid = _rows(db, "quote_batch")[0].record_id
    before = _snapshot(db)
    out = rework_bom_artifact(_store(db), qid, recalc=_recalc(db))
    _assert_untouched(db, before, out, "unsupported_artifact")
    assert out["artifact"] == "quote_batch"


def _quote_file(tmp_path) -> str:
    p = tmp_path / "q.csv"
    p.write_text("supplier,part,moq,tooling_fee,unit_price,lead_time_days\n"
                 "ACME,bracket,100,5000,12.5,15\n", encoding="utf-8")
    return str(p)


def test_refuses_when_record_missing(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    _calc(db, capsys)
    out = rework_bom_artifact(_store(db), "T-4242", recalc=_recalc(db))
    assert out["ok"] is False and out["outcome"] == "missing_record", out


def test_refuses_record_without_identity_inputs(env, capsys):
    """第 48 片那种只存哈希没存身份字段的记录：点名拒，不猜「最近那张 BOM」。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    store = _store(db)
    meta = dict(store.get(bom_id).metadata or {})
    meta.pop("bom_id")
    store.update(bom_id, metadata=meta)
    before = _snapshot(db)
    out = rework_bom_artifact(store, bom_id, recalc=_recalc(db))
    assert out["outcome"] == "missing_inputs" and "bom_id" in out["missing_inputs"], out
    assert _snapshot(db) == before


def test_refuses_when_recalc_raises(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]

    def boom(meta):
        raise RuntimeError("bom.db 读不到")

    out = rework_bom_artifact(_store(db), bom_id, recalc=boom)
    assert out["ok"] is False and out["outcome"] == "recalc_failed", out
    assert "bom.db 读不到" in out["reason"]


def test_refuses_incomplete_recalc_result(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    before = _snapshot(db)
    out = rework_bom_artifact(_store(db), bom_id, recalc=lambda m: {"bom_id": "B-1"})
    assert out["outcome"] == "recalc_incomplete_result", out
    assert "bom_signature" in out["missing_fields"], out
    assert _snapshot(db) == before


def test_refuses_when_the_bom_moved(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    before = _snapshot(db)
    out = rework_bom_artifact(_store(db), bom_id, recalc=_recalc(db, bom_id="别的BOM"))
    assert out["outcome"] == "bom_moved" and out["current"] == "别的BOM", out
    assert _snapshot(db) == before


def test_refuses_current_empty_bom(env, capsys):
    """行被删光 ≠ 一次正常返工：空表不能把 stale 关掉。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    before = _snapshot(db)
    out = rework_bom_artifact(_store(db), bom_id, recalc=_recalc(db, line_count=0))
    assert out["outcome"] == "empty_bom", out
    assert _snapshot(db) == before


def test_refuses_same_signature_but_identity_moved(env, capsys):
    """签名没变而 revision/version_no 变了 ⇒ 签名漏吃了这一项，不许拿它 bump。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    rec = _store(db).get(bom_id)
    sig = rec.metadata["input_signature"]
    before = _snapshot(db)
    out = rework_bom_artifact(
        _store(db), bom_id,
        recalc=lambda m: {"bom_id": m["bom_id"], "bom_signature": sig,
                          "revision": "999", "version_no": m["version_no"],
                          "line_count": len(m["lines"]),
                          "header": None, "lines": None})
    assert out["outcome"] == "recalc_disagrees", out
    assert _snapshot(db) == before


def test_refuses_when_projection_inputs_absent(env, capsys):
    """判定字段齐了但没交出 BOM 表本体 ⇒ 仍不许自己拼一份正文（那是第二份映射）。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    before = _snapshot(db)
    out = rework_bom_artifact(
        _store(db), bom_id,
        recalc=lambda m: {"bom_id": m["bom_id"], "bom_signature": "f" * 64,
                          "revision": m["revision"], "version_no": m["version_no"],
                          "line_count": len(m["lines"]), "header": None,
                          "lines": None})
    assert out["outcome"] == "recalc_incomplete_result", out
    assert "header" in out["missing_fields"] and "lines" in out["missing_fields"], out
    assert _snapshot(db) == before


# ---------- 三、引擎适配与注册 ----------

def test_make_rework_fn_is_boolean_for_the_engine(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    bom_id = _calc(db, capsys)["lineage"]["bom"]["record_id"]
    assert make_bom_rework_fn(_store(db), _recalc(db))(bom_id) is True
    assert make_bom_rework_fn(_store(db), _recalc(db))("T-9999") is False


def test_executor_is_wired_into_the_cli_and_readme_states_four_kinds():
    """接线证明 + README 镜像：执行器只在模块里定义等于死代码（第 51 片同一条纪律）。

    `bom_rework` **不**调 `add_edge`（返工不新增边，也不重指边——BOM 是中间那一格），
    所以它不进 AST 生产者棘轮；棘轮那条由 `test_drawing_spec_lineage.py` 自己守住。
    """
    import ast

    tree = ast.parse((ROOT / "src/aipd_os/cli/commands_truth.py").read_text(
        encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "rework_bom_artifact" in names, "执行器没接进 CLI 就是死代码"
    assert "bom_from_record" in names, "重算器没接进 CLI 就跑不到当前 BOM"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # 第 71 片把这一类清单从四改五（登记表与 README 同步改口）；
    # 钉的是「README 说的是同一份清单」，不是「停在四」。
    assert "执行器今天认五类制品" in readme
    assert "执行器今天认三类制品" not in readme
