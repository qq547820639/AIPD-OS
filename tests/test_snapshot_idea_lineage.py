"""Snapshot / Gate 的 idea 归属必须跟着**被选中的机会**走（F-GATE-01）。

回归背景：`create_snapshot()` 取「本项目里最后一个 idea」当 `idea_id`，
而不是选中机会自带的 `Opportunity.idea_id`。单想法项目上两者相同（所以长期
不可见）；一旦项目里有 ≥2 个想法，冻结下来的快照——以及继承其
`snapshot_id/snapshot_hash` 的 Gate 评价与 Owner 批准回执——就把产品定义
归给了一个可能毫不相干的想法，回溯验收随之指向错的源头。
"""
from __future__ import annotations

import pytest

from aipd_os.idea.models import Idea
from aipd_os.idea.service import IdeaService
from aipd_os.product_intelligence import (
    ProductDefinitionGate,
    ProductDefinitionSnapshotService,
)
from tests.test_product_intelligence import _build_chain, env  # noqa: F401


@pytest.fixture()
def chain(env):  # noqa: F811  (pytest 按参数名注入上面导入的 fixture)
    """一条完整链（机会挂在 env['idea'] 上）+ 快照服务。"""
    _build_chain(env)
    env["snaps"] = ProductDefinitionSnapshotService(env["db"])
    return env


def test_snapshot_idea_follows_selected_opportunity(chain):
    older = chain["idea"]
    # 链建好之后再提一个新想法：此时「列表里最后一个」≠「选中机会的想法」
    newer = IdeaService(chain["db"]).create(Idea(
        idea_id="", tenant_id="default", project_id="p1",
        title="后来提的点子", raw_input="与本项目定义无关"))
    snap = chain["snaps"].create_snapshot("default", "p1")
    assert snap.idea_id == older.idea_id, (
        f"快照归给 {snap.idea_id}，选中机会声明的是 {older.idea_id}；"
        f"项目里最新的想法是 {newer.idea_id}")


def test_gate_evaluation_is_bound_to_that_snapshot(chain):
    """归属正确之后，Gate 评价必须按 snapshot_id + hash 精确绑定。"""
    snap = chain["snaps"].create_snapshot("default", "p1")
    gate = ProductDefinitionGate(chain["db"], tenant_id="default",
                                 project_id="p1")
    ev = gate.evaluate_snapshot(snap)
    assert ev.snapshot_id == snap.snapshot_id
    assert ev.snapshot_hash == snap.content_hash
    stored = chain["snaps"].get_snapshot("default", "p1", snap.snapshot_id)
    assert stored.idea_id == chain["idea"].idea_id


def test_single_idea_project_behaves_the_same(chain):
    """反向控制：只有一个想法时两种取法结果相同（解释缺陷为何长期不可见）。"""
    snap = chain["snaps"].create_snapshot("default", "p1")
    assert snap.idea_id == chain["idea"].idea_id


def test_gate_criteria_follow_the_snapshot_idea_not_the_newest(chain):
    """加一个无关的新想法，不得改变这份定义的门结论。

    此前四处判据都取「项目里最后一个 idea」⇒ 新想法一落地，门就去评那个
    尚无证据的 idea，已冻结定义的 READY 会凭空变 BLOCKED。
    """
    from aipd_os.product_intelligence import ProductDefinitionGate
    from aipd_os.product_intelligence.gate_criteria import CRITERION_IDEA_MATURITY

    snaps = chain["snaps"]
    snap = snaps.create_snapshot("default", "p1")
    gate = ProductDefinitionGate(chain["db"], tenant_id="default",
                                 project_id="p1")
    before = gate.evaluate_snapshot(snap)
    IdeaService(chain["db"]).create(Idea(
        idea_id="", tenant_id="default", project_id="p1",
        title="后来提的点子", raw_input="无任何证据"))
    after = gate.evaluate_snapshot(
        snaps.get_snapshot("default", "p1", snap.snapshot_id))
    assert after.result == before.result, (
        f"仅因新增无关想法，门结论从 {before.result} 变成 {after.result}")
    idea_crit = next(c for c in after.criteria_results
                     if c.criterion_id == CRITERION_IDEA_MATURITY)
    assert idea_crit.affected_refs == [chain["idea"].idea_id], (
        f"门在评 {idea_crit.affected_refs}，而本快照属于 "
        f"{chain['idea'].idea_id}")


def test_unrelated_new_idea_does_not_make_snapshot_stale(chain):
    """项目里后加的无关想法不得把已冻结的快照判成 stale（假失效）。

    反向（真变更要判 stale）已由 `tests/test_product_intelligence_impact.py`
    的 claim→全链失效用例覆盖，这里只补「归属猜错导致假 stale」这一面。
    """
    snaps = chain["snaps"]
    snap = snaps.create_snapshot("default", "p1")
    IdeaService(chain["db"]).create(Idea(
        idea_id="", tenant_id="default", project_id="p1",
        title="后来提的点子", raw_input="与本项目定义无关"))
    stale, reasons = snaps.is_stale(snap, "default", "p1")
    assert stale is False, f"仅因新增无关想法就判 stale：{reasons}"
