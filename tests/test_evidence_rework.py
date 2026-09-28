"""执行证据的返工执行器（F-REWORK-EVIDENCE 第 71 片）。

第 70 片让证据能被传播标 stale 之后，缺口挪到这里：发现者有了，收口者没有。
这一类制品的"重算"= 用记下来的工作项再执行一次，然后**就地演进这条记录**
（引擎成功时 bump 的是同一条；另起新版是生产面 `cost calc --truth-lineage` 的规则，
两边刻意不同 —— 第 49/53 片同形）。

四条拒绝都必须存在且各自有控制，它们防的是同一件事：**把没收口说成收口**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from aipd_os.cli.main import main  # noqa: E402
from aipd_os.product_truth import ProductTruthStore  # noqa: E402
from aipd_os.product_truth.models import TruthRecord  # noqa: E402
from aipd_os.supervisor.evidence_rework import (  # noqa: E402
    evidence_artifact_kind,
    rework_evidence_artifact,
)

T, P = "default", "P1"


def _store(tmp_path) -> ProductTruthStore:
    return ProductTruthStore(str(tmp_path / "sup.db"), tenant_id=T, project_id=P)


def _evidence(store: ProductTruthStore, **meta) -> str:
    base = {"work_id": "W-001", "run_id": "R-old", "capability": "doc.generate",
            "output_hash": "h-old", "evidence_references": ["a.md"], "gate": "pass"}
    base.update(meta)
    return store.add(TruthRecord(record_type="evidence",
                                 content="doc.generate 执行产出：run=R-old output_hash=h-old",
                                 trust_level="high", metadata=base),
                     tenant_id=T, project_id=P)


def _fresh(**over) -> dict:
    out = {"run_id": "R-new", "output_hash": "h-new",
           "evidence_references": ["a.md", "b.md"], "status": "succeeded",
           "side_effect_mode": "PURE", "gate": "pass"}
    out.update(over)
    return out


def test_happy_path_evolves_the_same_record(tmp_path) -> None:
    store = _store(tmp_path)
    rid = _evidence(store)
    before = store.get(rid)
    out = rework_evidence_artifact(store, rid, rerun=lambda meta: _fresh())
    assert out["ok"] is True and out["outcome"] == "re_evidenced", out
    assert out["from_run_id"] == "R-old" and out["run_id"] == "R-new", out
    after = store.get(rid)
    assert after.record_id == rid, "就地演进，不另起一条"
    assert after.version == before.version, "版本由引擎 bump，执行器不自己加版"
    assert after.content.endswith("run=R-new output_hash=h-new"), after.content
    assert after.metadata["run_id"] == "R-new", after.metadata
    assert after.metadata["rework"]["from_run_id"] == "R-old", after.metadata
    # 正文投影与生产者同一来源：生产者写出来的形状，执行器演进完必须还是那个形状
    assert after.content == "doc.generate 执行产出：run=R-new output_hash=h-new"


def test_trust_follows_the_fresh_gate_not_the_old_one(tmp_path) -> None:
    """重跑后质量门不通过 ⇒ 信任降回 low，不许沿用旧的高（与第 42 片同一上限规则）。"""
    store = _store(tmp_path)
    rid = _evidence(store)
    rework_evidence_artifact(store, rid, rerun=lambda meta: _fresh(gate="review"))
    assert store.get(rid).trust_level == "low", store.get(rid).metadata
    # 第二次得给新的 run_id：同一 run 再"重跑"没有新信息，执行器会按 rerun_same_run 拒
    rework_evidence_artifact(store, rid,
                             rerun=lambda meta: _fresh(run_id="R-new2", gate="pass"))
    assert store.get(rid).trust_level == "high", store.get(rid).metadata


@pytest.mark.parametrize("over,outcome", [
    ({"status": "blocked_external"}, "rerun_not_ok"),
    ({"side_effect_mode": "EXTERNAL_SIDE_EFFECT"}, "not_replayable"),
    ({"run_id": "R-old"}, "rerun_same_run"),
    ({"run_id": ""}, "rerun_missing_run_id"),
])
def test_refusals_keep_the_record_untouched(tmp_path, over, outcome) -> None:
    store = _store(tmp_path)
    rid = _evidence(store)
    before = store.get(rid)
    out = rework_evidence_artifact(store, rid, rerun=lambda meta: _fresh(**over))
    assert out["ok"] is False and out["outcome"] == outcome, out
    after = store.get(rid)
    assert after.content == before.content and after.metadata == before.metadata, \
        "拒掉就是什么都没改，stale 留在原处让下次扫描继续看见"


def test_missing_metadata_is_named_not_guessed(tmp_path) -> None:
    store = _store(tmp_path)
    rid = store.add(TruthRecord(record_type="evidence", content="无来源的证据",
                                 trust_level="low", metadata={"capability": "doc.generate"}),
                    tenant_id=T, project_id=P)
    out = rework_evidence_artifact(store, rid, rerun=lambda meta: _fresh())
    assert out["ok"] is False and out["outcome"] == "missing_metadata", out
    assert sorted(out["missing"]) == ["run_id", "work_id"], out


def test_non_evidence_record_is_not_claimed(tmp_path) -> None:
    store = _store(tmp_path)
    rid = store.add(TruthRecord(record_type="fact", content="一条事实", trust_level="high"),
                    tenant_id=T, project_id=P)
    out = rework_evidence_artifact(store, rid, rerun=lambda meta: _fresh())
    assert out["outcome"] == "not_evidence", out
    assert evidence_artifact_kind(store, rid) is None, "fact 行不该被当成证据类"


def test_kind_axis_does_not_steal_the_four_version_kinds(tmp_path) -> None:
    """两条轴各管各的：有 `metadata["artifact"]` 的仍归原四支，别抢。"""
    store = _store(tmp_path)
    bom = store.add(TruthRecord(record_type="artifact_version", content="一版 BOM",
                                trust_level="high", metadata={"artifact": "bom"}),
                   tenant_id=T, project_id=P)
    ev = _evidence(store)
    assert evidence_artifact_kind(store, bom) is None
    assert evidence_artifact_kind(store, ev) == "evidence"
    assert evidence_artifact_kind(store, "T-404") is None


def test_cli_rework_closes_a_staled_evidence(tmp_path, monkeypatch, capsys) -> None:
    """端到端：propagate 把证据标 stale ⇒ `aipd truth rework` 收得口。

    走的是第 70 片那条路（显式 truth_refs + doc.generate 这个可离线完成的能力），
    所以这里不需要任何假记录：证据、边、任务都由真实执行写出来。
    """
    from aipd_os.product_truth.propagation import PropagationEngine
    from tests.test_supervisor_fact_lineage import _add_fact, _run_doc_generate

    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path / "out"))
    db = tmp_path / "sup.db"
    rid = _add_fact(db, "支架最大载荷 50kg")
    _sup, _wid, results = _run_doc_generate(tmp_path, monkeypatch, {"truth_refs": [rid]})
    evidence_id = results[0]["fact_writeback"]["record_id"]

    store = _store(tmp_path)
    engine = PropagationEngine(store)
    engine.on_upstream_changed(rid, reason="载荷口径改了")
    assert store.get(evidence_id).status == "stale", "前置：证据已被标 stale"
    task_id = [t.to_dict()["task_id"] for t in engine.list_tasks(status="pending")
               if t.to_dict()["truth_id"] == evidence_id][0]

    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--task", task_id, "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, (rc, payload)
    assert payload["ok"] is True and payload["refused"] == [], payload
    assert payload["results"][0]["executor"]["outcome"] == "re_evidenced", payload
    task = engine.get_task(task_id).to_dict()
    assert task["status"] == "succeeded", task
    after = store.get(evidence_id)
    assert after.status == "active", after.status
    assert after.metadata["rework"]["outcome"] == "re_evidenced", after.metadata
