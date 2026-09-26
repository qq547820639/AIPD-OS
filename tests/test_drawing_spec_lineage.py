"""CTQ → 图纸声明的血缘生产者（F-LINEAGE-PROD 第 43 片）。

改前 `truth_lineage` 在生产侧只有 `product_intelligence/gate.commit_snapshot` 一个写者
（PI 需求/Feature → truth 记录），**CTQ 与图纸之间没人连边**，于是
`aipd truth propagate --upstream <CTQ>` 走到第二跳就断：改了 CTQ，
那份已经按旧 CTQ 出好的公差声明不会被打 stale。

这里钉的是三件事：
1. `aipd drawing spec` 成功落盘时，按声明里**实际引用到**的 ctq_ref 写
   `artifact_version` 记录 + `ctq → 声明` 边；
2. 有了这条边，传播第二跳**真的到得了**（第 2 条用例是这根轴存在的理由，
   没有它，其余各条只是在测自己写的表）；
3. 写边的生产者集合是**两向棘轮**：新增一个未登记的 `add_edge` 调用点要红，
   把本轮这个删掉也要红。
"""
from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore, TruthRecord
from aipd_os.product_truth.propagation import PropagationEngine

ROOT = Path(__file__).resolve().parent.parent
T = "default"
P = "LINEAGE-TEST"

HOLE = {"feature": "hole_Ø6", "drawing_feature": "TOP.hole_1", "nominal": 6.0,
        "lower_limit": 5.95, "upper_limit": 6.05, "inspection_method": "CMM"}
HOLE2 = {"feature": "hole_Ø4", "drawing_feature": "TOP.hole_2", "nominal": 4.0,
         "lower_limit": 3.95, "upper_limit": 4.05, "inspection_method": "CMM"}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    from aipd_os.state.db import AIPDStateDB

    state = AIPDStateDB(path)
    state.ensure_default_tenant()
    state.init_project(T, P, "spec lineage 测试", "evidence")
    return path


def _seed(db_path, *metas):
    store = ProductTruthStore(str(db_path), tenant_id=T, project_id=P)
    return [store.add(TruthRecord(record_type="ctq",
                                  content=f"CTQ {m.get('feature', i)}",
                                  trust_level="verified", metadata=dict(m)),
                      tenant_id=T, project_id=P)
            for i, m in enumerate(metas, start=1)]


def _spec(db_path, tmp_path, name="spec.json"):
    out = tmp_path / name
    rc = main(["drawing", "spec", "--db", str(db_path), "--project", P,
               "--out", str(out), "--json"])
    return rc, out


def _edges(db_path):
    store = ProductTruthStore(str(db_path), tenant_id=T, project_id=P)
    graph = LineageGraph(store, tenant_id=T, project_id=P)
    return {(e["upstream_id"], e["downstream_id"], e["relation"])
            for e in graph.edges(tenant_id=T, project_id=P)}


def _versions(db_path):
    store = ProductTruthStore(str(db_path), tenant_id=T, project_id=P)
    return store.query(record_type="artifact_version", tenant_id=T, project_id=P)


class TestSpecWritesItsOwnLineage:
    def test_success_path_records_one_version_and_one_edge(self, tmp_path, db):
        rid = _seed(db, HOLE)[0]
        rc, out = _spec(db, tmp_path)
        assert rc == 0 and out.exists()

        versions = _versions(db)
        assert len(versions) == 1, f"应恰有一条 artifact_version，实际 {len(versions)}"
        rec = versions[0]
        assert rec.metadata["ctq_refs"] == [rid]
        assert rec.metadata["path"] == str(out)
        # 哈希取自正文：同一内容重跑命中同一行（见幂等用例）
        assert rec.source.file == str(out)
        # 上限 high：正文哈希是自证的，"生成过程对不对"没有独立复核
        assert rec.trust_level == "high"
        assert (rid, rec.record_id, "affects") in _edges(db)

    def test_the_second_hop_of_propagation_really_reaches(self, tmp_path, db):
        """这条用例是本片存在的理由：改了 CTQ，声明要被打 stale 并生成返工任务。"""
        rid = _seed(db, HOLE)[0]
        _spec(db, tmp_path)
        version_id = _versions(db)[0].record_id

        store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
        report = PropagationEngine(store).on_upstream_changed(rid)
        assert version_id in report["affected"], \
            f"第二跳仍然断着：affected={report['affected']}"
        assert version_id in report["stale"]
        assert store.get(version_id, tenant_id=T, project_id=P).status == "stale"
        assert [t["truth_id"] for t in report["tasks"]] == [version_id]

    def test_only_referenced_ctq_gets_an_edge(self, tmp_path, db):
        """函数级选择性：库里有一条**活着但没参与这份声明**的 CTQ ⇒ 不许连它。

        为什么在函数级测：CLI 成功落盘时"被引用的"恰好等于"全部 active"
        （没被引用的那条会先造成 gap ⇒ 整条命令 HOLD），所以走 CLI 打不出这个差别。
        差别只在"手写/复用的 spec"或将来 gap 语义变松时才暴露——那正是连错边的代价。
        """
        from aipd_os.cad.spec_lineage import record_spec_lineage

        used, unused = _seed(db, HOLE, HOLE2)[:2]
        store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
        spec = json.loads(json.dumps(
            {"features": [{"feature": "TOP.hole_1", "ctq_ref": used,
                           "tolerance": {"upper": 0.05, "lower": -0.05}}]}))
        out = tmp_path / "handwritten.json"
        out.write_text(json.dumps(spec), encoding="utf-8")
        result = record_spec_lineage(store, spec, path=out)

        assert result["ctq_refs"] == [used] and result["edges"] == 1
        edges = _edges(db)
        assert (used, result["record_id"], "affects") in edges
        assert not any(u == unused for u, _d, _r in edges), \
            "给没参与的 CTQ 连边＝让传播去打扰无关要求"

        report = PropagationEngine(store).on_upstream_changed(unused)
        assert result["record_id"] not in report["affected"]

    def test_hold_writes_neither_file_nor_lineage(self, tmp_path, db):
        bad = {k: v for k, v in HOLE.items() if k != "drawing_feature"}
        _seed(db, bad)
        out = tmp_path / "never.json"
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(out)]) == 4
        assert not out.exists()
        assert _versions(db) == []
        assert _edges(db) == set()

    def test_same_content_is_one_version_and_changed_ctq_is_another(self, tmp_path, db):
        _seed(db, HOLE)
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(tmp_path / "s.json")]) == 0
        first = _versions(db)
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(tmp_path / "s.json")]) == 0
        assert len(_versions(db)) == len(first) == 1, "内容没变不该另起一版"
        assert len(_edges(db)) == 1

        store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
        ctq = store.query(record_type="ctq", tenant_id=T, project_id=P)[0]
        meta = dict(ctq.metadata)
        meta["nominal"] = 6.2
        meta["lower_limit"], meta["upper_limit"] = 6.15, 6.25
        store.update(ctq.record_id, tenant_id=T, project_id=P, metadata=meta)
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(tmp_path / "s.json")]) == 0
        versions = _versions(db)
        assert len(versions) == 2, "声明正文变了就该另起一版"
        assert len({v.record_id for v in versions}) == 2

    def test_lineage_failure_is_not_reported_as_success(self, tmp_path, db, monkeypatch,
                                                        capsys):
        """写不进血缘 ⇒ 判未收口（exit 4），不许"文件写了就算成"。"""
        import aipd_os.cad.spec_lineage as sl

        rid = _seed(db, HOLE)[0]
        monkeypatch.setattr(sl, "record_spec_lineage",
                            lambda *a, **k: (_ for _ in ()).throw(
                                sqlite3.OperationalError("夹具：库锁住")))
        rc, out = _spec(db, tmp_path)
        assert rc == 4
        assert out.exists(), "声明本身是完整的，本轮不撤回它——但结果必须判未收口"
        payload = json.loads(capsys.readouterr().out)
        assert "OperationalError" in payload["lineage_error"]
        # 退码与 --json 的 ok 必须同向：ok:true + rc 4 是最坏的一种不一致
        assert payload["ok"] is False
        assert payload["lineage"] is None
        assert _versions(db) == []
        assert _edges(db) == set()
        assert rid


class TestProducerRatchet:
    """`truth_lineage` 的边只能由 `LineageGraph.add_edge` 写，生产者集合是登记过的。

    两向：多一个未登记的文件要红；把本轮新加的那个删掉也要红。
    筛法用 AST 的属性调用点，不按名字子串——`LineageGraph.add_edge` 内部还会调
    canonical 那张表的 `add_edge`，那是**另一个写者**（写 canonical lineage），
    所以判据分两层：先数 SQL 写入口，再数调用点。
    """

    TRUTH_SQL_WRITERS = ["src/aipd_os/product_truth/lineage.py"]
    REGISTERED_PRODUCERS = {
        "src/aipd_os/cad/spec_lineage.py",              # 第 43 片：CTQ → 图纸声明
        "src/aipd_os/cad/spec_rework.py",               # 第 45 片：返工重算后补同一类边
        "src/aipd_os/product_intelligence/gate.py",     # PI 需求/Feature → truth
        "src/aipd_os/product_truth/lineage.py",         # 自身：canonical 镜像
        "src/aipd_os/idea/decomposer.py",               # 以下三处写 canonical，
        "src/aipd_os/idea/evidence_relations.py",       # 不是 truth_lineage，
        "src/aipd_os/product_intelligence/service.py",  # 但同样是 add_edge 调用点
    }

    def _call_sites(self):
        sites = set()
        for path in (ROOT / "src" / "aipd_os").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "add_edge"):
                    sites.add(str(path.relative_to(ROOT)))
        return sites

    def test_only_one_sql_write_entry_into_truth_lineage(self):
        """所有边都必须走 `LineageGraph.add_edge`：绕过去的那条路不会被环检测看到。"""
        writers = set()
        for path in (ROOT / "src" / "aipd_os").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "INTO truth_lineage" in text:
                writers.add(str(path.relative_to(ROOT)))
        assert writers == set(self.TRUTH_SQL_WRITERS), writers

    def test_edge_call_sites_are_exactly_the_registered_producers(self):
        found = self._call_sites()
        assert found, "AST 一个调用点都没读到——这把尺子读空了，不是生产者消失了"
        assert found == self.REGISTERED_PRODUCERS, (
            f"新增/消失的 add_edge 调用点：{sorted(found ^ self.REGISTERED_PRODUCERS)}；"
            "写 truth_lineage 的要同步改本登记与登记册，写 canonical 的要说明是哪张表")

    def test_the_cad_producer_is_wired_into_the_cli(self):
        """判据本身要能开火：CLI 里必须真的调用它（不是只在模块里定义了函数）。"""
        tree = ast.parse((ROOT / "src/aipd_os/cli/commands_drawing.py").read_text(
            encoding="utf-8"))
        calls = {n.func.id for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "record_spec_lineage" in calls, "生产者没接线就是死代码"

    def test_registry_row_states_the_new_producer(self):
        from aipd_os.registry_data import CAPABILITIES

        row = next(r for r in CAPABILITIES
                   if r.get("id") == "product_truth.impact_propagation")
        limitation = str(row.get("current_limitation") or "")
        assert "drawing spec" in limitation or "图纸声明" in limitation, \
            "CTQ→图纸 这段现在有人写了，登记里那句「没有生产者」要改判"
        assert "artifact_version" in limitation, "要写清生产者产出的是什么"
        assert json.dumps(row, ensure_ascii=False)  # 行仍是可序列化的登记
