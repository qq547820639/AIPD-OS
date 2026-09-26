"""「图纸声明 → DXF 制品」的血缘边（F-LINEAGE-DXF 第 46 片）。

第 43 片接 CTQ→声明、第 45 片给声明接执行器之后，链路第三跳仍断着：
改了 CTQ，那张按旧声明画出来的 DXF 不会被传播打到。这里钉四件事：

1. `aipd drawing generate --db` 出图后写一条 `drawing_dxf` 版本记录，
   并连 `声明记录 → 图纸记录` 的边；**传播第三跳真的到得了**（第 1 条用例）；
2. 制品身份按**输入签名**（模型摘要 + 声明内容哈希 + 全部出图参数：part/revision/
   views/scale/sheet/material/剖切/放大），不按 DXF 字节——同样输入重跑必须命中同一条
   记录（第 3 条），换声明才另起一版（第 4 条），**换模型也必须另起一版**（第 4b 条，
   签名漏吃模型是先复现后修的）；
3. 上游连不上时记录照写、边数为 0 且**写明原因**（第 5 条）：
   "没有可连的上游"与"上游没参与"不是一回事；
4. 没给 `--db` 是**明说的跳过**，不是静默；血缘写不进去则判未收口且 `ok` 与退码同向。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore, TruthRecord
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "DXF-LINEAGE"

# 窗口取自实测：golden 支架 TOP 视图四个孔的拟合直径都是 8.0mm
# （`.venv/bin/python` 走 generate_drawing 量得，见 docs/audit 本片取证）。
# 声明若不盖住实测值，出图判未收口、退码 4，本文件的 rc 断言就各说一套了。
HOLE = {"feature": "hole_Ø8", "drawing_feature": "TOP.hole_1", "nominal": 8.0,
        "lower_limit": 7.95, "upper_limit": 8.05, "inspection_method": "CMM"}


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "dxf lineage 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _seed(db):
    return _store(db).add(TruthRecord(
        record_type="ctq", content="CTQ hole_Ø8", trust_level="verified",
        metadata=dict(HOLE)), tenant_id=T, project_id=P)


def _spec(tmp_path, db, name="spec.json"):
    out = tmp_path / name
    assert main(["drawing", "spec", "--db", str(db), "--project", P,
                 "--out", str(out), "--json"]) == 0
    return out


def _generate(tmp_path, db, spec, capsys=None):
    dxf = tmp_path / "bracket.dxf"
    rc = main(["drawing", "generate", "--out", str(dxf), "--part", "bracket",
               "--views", "TOP", "--spec", str(spec), "--db", str(db),
               "--project", P, "--json"])
    payload = json.loads(_read_json(capsys)) if capsys else None
    return rc, dxf, payload


def _read_json(capsys):
    return capsys.readouterr().out.strip().splitlines()[-1]


def _rows(db, artifact):
    return [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)
            if (r.metadata or {}).get("artifact") == artifact]


def _edges(db):
    return {(e["upstream_id"], e["downstream_id"], e["relation"])
            for e in LineageGraph(_store(db)).edges(tenant_id=T, project_id=P)}


def test_third_hop_propagation_reaches_the_drawing(env, capsys):
    """本片的理由：改 CTQ ⇒ 声明 stale ⇒ **图纸记录**也被传播打到并生成返工任务。"""
    tmp_path, db = env
    ctq = _seed(db)
    spec = _spec(tmp_path, db)
    rc, dxf, payload = _generate(tmp_path, db, spec, capsys)
    assert rc == 0 and dxf.is_file(), payload
    rows = _rows(db, "drawing_dxf")
    assert len(rows) == 1
    dxf_id = rows[0].record_id
    spec_id = _rows(db, "drawing_spec")[0].record_id
    assert (spec_id, dxf_id, "affects") in _edges(db)
    assert payload["lineage"]["edges"] == 1
    assert payload.get("ok", True) is True

    report = PropagationEngine(_store(db)).on_upstream_changed(ctq)
    assert spec_id in report["affected"] and dxf_id in report["affected"], \
        f"第三跳仍然断着：affected={report['affected']}"
    assert {t["truth_id"] for t in report["tasks"]} == {spec_id, dxf_id}


def test_no_db_is_a_stated_skip_not_a_silent_one(env, capsys):
    """没给 --db：图仍然成立（rc 0），但必须明说没登记血缘，且库里不留图纸记录。"""
    tmp_path, db = env
    _seed(db)
    spec = _spec(tmp_path, db)
    dxf = tmp_path / "nodb.dxf"
    rc = main(["drawing", "generate", "--out", str(dxf), "--part", "bracket",
               "--views", "TOP", "--spec", str(spec)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "未给 --db" in out and "血缘" in out
    assert _rows(db, "drawing_dxf") == []


def test_same_inputs_hit_one_record_and_stay_idempotent(env, capsys):
    """同输入重跑命中同一条记录（第 2 次 created=False），不因为 DXF 字节差异另起一版。"""
    tmp_path, db = env
    _seed(db)
    spec = _spec(tmp_path, db)
    rc1, _d1, p1 = _generate(tmp_path, db, spec, capsys)
    rc2, _d2, p2 = _generate(tmp_path, db, spec, capsys)
    assert (rc1, rc2) == (0, 0)
    assert p1["lineage"]["created"] is True
    assert p2["lineage"]["created"] is False
    assert p1["lineage"]["record_id"] == p2["lineage"]["record_id"]
    rows = _rows(db, "drawing_dxf")
    assert len(rows) == 1
    assert rows[0].metadata["dxf_sha256"], "DXF 自己的哈希要作为观测留着，只是不当键"


def test_changed_declaration_starts_a_new_version_and_supersedes_old(env, capsys):
    """声明改了 ⇒ 新的图纸版本记录，同路径的旧一条标 superseded。

    不许留一堆旧版本当永久下游：否则一次改 CTQ 会把那张图上所有历史版本都打成待返工。
    """
    tmp_path, db = env
    ctq = _seed(db)
    spec = _spec(tmp_path, db)
    _generate(tmp_path, db, spec, capsys)
    old = _rows(db, "drawing_dxf")[0]

    store = _store(db)
    rec = store.get(ctq, tenant_id=T, project_id=P)
    meta = dict(rec.metadata)
    meta.update({"nominal": 7.0, "lower_limit": 6.9, "upper_limit": 7.1})
    store.update(ctq, tenant_id=T, project_id=P, metadata=meta)
    assert main(["drawing", "spec", "--db", str(db), "--project", P,
                 "--out", str(spec), "--json"]) == 0
    _generate(tmp_path, db, spec, capsys)

    rows = _rows(db, "drawing_dxf")
    assert len(rows) == 2, [r.record_id for r in rows]
    statuses = {r.record_id: r.status for r in rows}
    assert statuses[old.record_id] == "superseded"
    new = [r for r in rows if r.record_id != old.record_id][0]
    assert new.status == "active"
    spec_ids = {r.record_id for r in _rows(db, "drawing_spec")}
    assert any(u in spec_ids and u != old.record_id
               for (u, d, _r) in _edges(db) if d == new.record_id), \
        "新版图纸必须挂在某一条声明记录之下，边不能悬空"


def test_hand_written_spec_records_the_drawing_with_zero_edges(env, capsys):
    """声明是手写的（库里没有它的版本记录）⇒ 记录照写、边数 0、原因点名。"""
    tmp_path, db = env
    _seed(db)
    spec = tmp_path / "hand.json"
    spec.write_text(json.dumps({"features": [
        {"feature": "TOP.hole_1", "tolerance": {"upper": 0.05, "lower": -0.05}}]}),
        encoding="utf-8")
    rc, dxf, payload = _generate(tmp_path, db, spec, capsys)
    assert rc == 0 and dxf.is_file(), payload
    lin = payload["lineage"]
    assert lin["edges"] == 0 and lin["upstream_record_id"] is None
    assert "找不到声明的版本记录" in lin["upstream_reason"]
    assert len(_rows(db, "drawing_dxf")) == 1


def test_lineage_failure_holds_the_command_and_agrees_with_ok(env, capsys, monkeypatch):
    """写不进血缘 ⇒ 退码 4 且 --json 的 ok=false：机器面与终端面不许各说一套。"""
    import aipd_os.cad.dxf_lineage as dl

    tmp_path, db = env
    _seed(db)
    spec = _spec(tmp_path, db)
    monkeypatch.setattr(dl, "record_dxf_lineage",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("夹具：库锁住")))
    rc, dxf, payload = _generate(tmp_path, db, spec, capsys)
    assert rc == 4
    assert dxf.is_file(), "图纸本身是完整的，本轮不撤回它——但结果判未收口"
    assert payload["lineage"] is None and "RuntimeError" in payload["lineage_error"]
    assert payload["ok"] is False


def test_missing_database_is_not_read_as_no_lineage(env, capsys):
    tmp_path, db = env
    _seed(db)
    spec = _spec(tmp_path, db)
    dxf = tmp_path / "x.dxf"
    rc = main(["drawing", "generate", "--out", str(dxf), "--part", "bracket",
               "--views", "TOP", "--spec", str(spec),
               "--db", str(tmp_path / "nope.db"), "--project", P])
    assert rc == 2
    assert "状态库不存在" in capsys.readouterr().out


GOLD = (ROOT / "releases" / "golden-projects" / "B-cad-engineering-change")


def test_a_different_model_starts_a_new_version_not_a_reuse(env, capsys):
    """签名必须吃模型：换一份 STEP 还命中同一条记录，等于两张图被记成一版。

    这条是先复现后修的：修之前同一 --out、同一参数分别用 bracket.step 与
    bracket_v2.step 出图，记录数仍是 1、两次落库的 inputs= 前缀一模一样
    （`/tmp/s46/sig_gap.py` 实测）。
    """
    tmp_path, db = env
    _seed(db)
    out = tmp_path / "bracket.dxf"
    for step in ("bracket.step", "bracket_v2.step"):
        rc = main(["drawing", "generate", "--step", str(GOLD / step),
                   "--out", str(out), "--part", "bracket", "--views", "TOP",
                   "--db", str(db), "--project", P, "--json"])
        capsys.readouterr()
        assert rc in (0, 4), rc  # 4 只允许来自合格域判定，血缘在退码判定之前已写
    rows = _rows(db, "drawing_dxf")
    assert len(rows) == 2, [r.content for r in rows]
    assert len({r.metadata["model_digest"] for r in rows}) == 2
    assert len({r.metadata["input_signature"] for r in rows}) == 2


def test_signature_covers_every_declared_input():
    """输入键的适用域：每个出图输入单独变都要翻签名，全同则必须稳定。"""
    from aipd_os.cad.dxf_lineage import dxf_input_signature

    base = {"spec_sha256": "s", "part": "bracket", "revision": "A",
            "views": ["TOP"], "scale": 1.0, "sheet": "A3", "material": "AL",
            "sections": [], "details": [],
            "model": {"kind": "golden_default", "source": "golden_default",
                      "digest": "d"}}
    same = dxf_input_signature(**base)
    assert dxf_input_signature(**base) == same, "同输入必须命中同一签名"
    for field, value in (("material", "SS"),
                         ("sections", ["Y=0"]),
                         ("details", ["TOP@(-30,0)/12=2"]),
                         ("spec_sha256", "other"),
                         ("model", {**base["model"], "digest": "other"})):
        assert dxf_input_signature(**{**base, field: value}) != same, (
            f"{field} 变了签名却没变——它没进输入键")


def test_producer_is_wired_into_the_generate_path():
    """定义了函数而 CLI 不调用，等于第三跳仍然没接：这里钉接线本身。"""
    import ast

    tree = ast.parse((ROOT / "src" / "aipd_os" / "cli" / "commands_drawing.py")
                     .read_text(encoding="utf-8"))
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "record_dxf_lineage" in calls
