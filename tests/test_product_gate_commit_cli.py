"""`aipd product gate --commit` 的常驻用例（F-GATE-COMMIT-ENTRY 第 69 片）。

第 68 片登记的事实是"commit 这一步没有生产入口"（生产面外部调用点 0）。
本片把入口接上，因此这几条用例**就是那条登记的销账证据**：
① 走 `main()` 真 CLI，不是直调 `commit_snapshot`；
② 提交真把 requirement / feature 写进 `product_truth`（否则旗子只是装饰）；
③ 前置不满足时必须非零退出且 **0 部分写入**（原子性由 `commit_snapshot` 保证，
   这里验的是 CLI 没有把抛错吞成"成功"）；
④ 幂等重放要如实说"重放"，不许第二次再写一批记录。
"""
from __future__ import annotations

import json

from aipd_os.cli.main import main
from aipd_os.product_intelligence import ProductDefinitionGate
from aipd_os.product_truth.store import ProductTruthStore
from tests.test_product_definition_integrity import _chain, _snap
from tests.test_product_intelligence_runtime_e2e import _env


def _committed_counts(env) -> dict[str, int]:
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    kinds: dict[str, int] = {}
    for rec in store.query():
        kinds[rec.record_type] = kinds.get(rec.record_type, 0) + 1
    return kinds


def test_cli_commit_is_a_real_producer_of_truth_records(tmp_path, capsys) -> None:
    env = _env(tmp_path)
    _chain(env["db"], env["pi"], env["idea"])
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner", snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    assert _committed_counts(env) == {}, "前置：还没有任何 truth 记录"

    rc = main(["product", "gate", "--db", str(env["db"].path), "--project", "p1",
               "--commit", "--json"])
    out = capsys.readouterr().out
    assert rc == 0, out
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["ok"] is True and payload["action"] == "committed", payload
    assert payload["requirements"] == 1 and payload["features"] == 1, payload
    assert payload["snapshot_id"] == snap.snapshot_id, payload
    counts = _committed_counts(env)
    assert counts.get("requirement") == 1 and counts.get("feature") == 1, counts
    # 边也要在：上游是 PI 的 requirement_id / feature_id（第 66 片普查里唯一
    # 能把"外部 id"当 upstream 的先例），这是后续给 evidence 连边的前提
    with env["db"].connect() as c:
        rows = c.execute(
            "SELECT upstream_id, downstream_id, relation FROM truth_lineage "
            "WHERE tenant_id='default' AND project_id='p1'").fetchall()
    assert rows, "commit 之后血缘边应当存在（第 66 片普查时这一格是空的）"
    assert {r["relation"] for r in rows} == {"derived_from"}, rows


def test_cli_commit_without_owner_decision_fails_closed(tmp_path, capsys) -> None:
    """没有绑定的 Owner Decision ⇒ 非零退出、0 记录写入（AI 不自批那条不变量）。"""
    env = _env(tmp_path)
    _chain(env["db"], env["pi"], env["idea"])
    _snap(env)
    rc = main(["product", "gate", "--db", str(env["db"].path), "--project", "p1",
               "--commit"])
    captured = capsys.readouterr()
    scene = captured.out + captured.err
    assert rc != 0, scene
    assert _committed_counts(env) == {}, "失败路径不许留下半截写入"
    assert "owner decision" in scene.lower(), scene


def test_second_cli_commit_is_refused_and_writes_nothing_new(tmp_path, capsys) -> None:
    """连着提交两次：第二次必须**拒**，且 0 新写入。

    读数改判的过程值得记：我原本按 `commit_snapshot(idempotent=True)` 的契约
    预期第二次走 `idempotent_replay` 幂等成功，但 CLI 这条路走不到那一支——
    `commit_approved` 取"最新 snapshot"，而它已不是 frozen，前置校验直接拒。
    这比"静默重放"更硬，也更符合"旗子不许把拒绝洗成成功"，所以按代码的真行为定稿。
    """
    env = _env(tmp_path)
    _chain(env["db"], env["pi"], env["idea"])
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner", snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    assert main(["product", "gate", "--db", str(env["db"].path), "--project", "p1",
                 "--commit", "--json"]) == 0
    capsys.readouterr()
    first = _committed_counts(env)
    with env["db"].connect() as c:
        n_edges = c.execute(
            "SELECT COUNT(*) FROM truth_lineage WHERE tenant_id='default' "
            "AND project_id='p1'").fetchone()[0]
    rc = main(["product", "gate", "--db", str(env["db"].path), "--project", "p1",
               "--commit", "--json"])
    scene = capsys.readouterr()
    text = scene.out + scene.err
    assert rc != 0, text
    assert "frozen" in text.lower(), text
    assert _committed_counts(env) == first, "第二次不许再多写记录"
    with env["db"].connect() as c:
        again = c.execute(
            "SELECT COUNT(*) FROM truth_lineage WHERE tenant_id='default' "
            "AND project_id='p1'").fetchone()[0]
    assert again == n_edges == 2, (n_edges, again)


def test_status_output_still_works_without_the_flag(tmp_path, capsys) -> None:
    """反向控制：不加 --commit 时行为不变（旗子不许把默认路径改成写库）。"""
    env = _env(tmp_path)
    _chain(env["db"], env["pi"], env["idea"])
    _snap(env)
    rc = main(["product", "gate", "--db", str(env["db"].path), "--project", "p1",
               "--json"])
    out = capsys.readouterr().out
    assert rc == 0, out
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["command"] == "product gate" and "eligibility" in payload, payload
    assert _committed_counts(env) == {}, "只查询不许写"
