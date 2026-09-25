"""发布证据读 ECO：交付物哈希必须有**闭合**变更单覆盖（F-C6-ECO 第 27 片）。

上一片让 ECO 能产单，这片让它**说了不算**：`aipd release manifest` 把这份证据里所有
带 `path` + `sha256` 的条目拉出来，逐个问「这个内容是哪张单带来的，那张单复验过了吗」。

四种处置刻意不合成一个百分比（这是这一片的全部要点）：

- `covered`：某张 `VERIFIED` 的单里有一行指到该路径，且那行 `after_sha256` 与实际哈希一致；
- `eco_change_uncovered`（阻断）：有单提到它，但没有一张**批过并复验过**的单的
  `after_sha256` 对得上 ⇒ 内容变了却没提单。被 `REJECTED`/`SUPERSEDED` 的单、
  以及还没批的 `DRAFT`/`PENDING_REVIEW` 都不算覆盖（作废的批件与没生效的草稿都不能背书内容）；
- `eco_change_unverified`（阻断）：哈希对得上，但那几张单还活着且没走到 `VERIFIED`
  ⇒ 未复验的变更进了发布；
- `undetermined`（**不**阻断，只记账）：一条单都没提到它 ⇒ 本仓没有「上一版基线」可比，
  **不知道**它有没有被改过。判成合格是假绿，判成违规是把「没登记」当成「改了没提单」。

`coverage` 三档：`complete`（全都 covered）/ `partial`（没违规但也没全覆盖）/
`incomplete`（有违规）。有单却漏了一条就只敢说 partial —— 路径写法不一致、
或漏算一个侧车，都会让「全部交付物都有闭合单」这句话变成假话。

一条诚实的边界（也写进能力行）：这一格证明的是「内容哈希与某张闭合的单一致」，
**不证明**「自上次发布以来只改了这些」——那需要上一版产物清单当基线，本片未做。

两侧口径**刻意不同**（`TestTheGateReadsIt` 钉住）：生产者（`aipd release manifest`）
把「一条单都没有」记成盲区、**不**阻断，因为它不知道自己漏没漏；发布门
（`production_release_gate` 的 `change_control_closes_deliverables`）把同一份文档读成
**不通过**——「不知道改没改」不该被拿去放行。生产者的 rc 管「这份证据有没有说错话」，
门管「这句话够不够格用来签字」。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os.cad.dfm import generate_dfm_report
from aipd_os.change_orders.eco import (
    DEAD_STATUSES,
    DRAFT,
    ECO_STATUSES,
    PENDING_REVIEW,
    REJECTED,
    VERIFICATION_PENDING,
    VERIFIED,
    EcoStore,
)
from aipd_os.delivery_baseline import write_baseline
from aipd_os.release_manifest import _hashed_artifacts, build_release_manifest
from aipd_os.state.db import AIPDStateDB

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")

TENANT = "default"
DOC = "dfm.md"
SIDECAR = "dfm.md.evidence.json"


@pytest.fixture()
def world(tmp_path):
    """一份 state.db + 一份真 DFM 报告（它自带 sidecar ⇒ 两条带哈希的交付物）。"""
    db_path = tmp_path / "state.db"
    AIPDStateDB(str(db_path)).ensure_default_tenant()
    shape = cadquery.Workplane("XY").box(60, 30, 10).faces(">Z").workplane() \
        .pushPoints([(25.0, 0.0)]).hole(6).solids().val().wrapped
    doc = tmp_path / "dfm.md"
    generate_dfm_report(doc, model=shape, part_name="BRK-1", revision="A",
                        material="6061-T6")
    return {"db": db_path, "doc": doc, "tmp": tmp_path, "shape": shape}


def _build(world, baseline=None):
    doc = build_release_manifest(db_path=world["db"], project_id="default",
                                 dfm_doc=world["doc"],
                                 out_path=world["tmp"] / "evidence.json",
                                 baseline_path=baseline)
    # 交付物集合自己另算一遍：判据读的东西不能由判据自己写出来（那是循环论证）
    doc["_artifacts"] = _hashed_artifacts(
        {k: v for k, v in doc.items() if k not in ("issues", "eco")})
    return doc


def _store(world):
    return EcoStore(AIPDStateDB(str(world["db"])))


#: 推到某个状态要经过的步，每步的 actor 与必需凭据都写在这里（与状态机同源）。
_STEPS = [(PENDING_REVIEW, "zhang", {}),
          ("APPROVED", "li", {}),
          ("IMPLEMENTED", "li", {"evidence_ref": "release v5.7.0",
                                 "effective_at": "2026-09-25T00:00:00+00:00"}),
          ("VERIFIED", "wang", {"evidence_ref": "复验报告 R-12"})]


def _walk_to(status, store, eco_id):
    """按状态机把一张单推到 `status`。

    到不了就抛：这个助手曾把「推到 REJECTED」静默走成「推到 VERIFIED」，
    于是断言变绿而它以为自己在测被否的单。
    """
    for to, actor, kw in _STEPS:
        store.transition(eco_id=eco_id, tenant_id=TENANT, project_id="default",
                         to_status=to, actor=actor, reason=f"推到 {to}", **kw)
        if to == status:
            return
    raise AssertionError(f"_STEPS 走不到 {status}（这条夹具路径没写）")


def _reject(store, eco_id):
    """送审后由**别人**否掉——主干路径不含这一步，所以单独走。"""
    store.transition(eco_id=eco_id, tenant_id=TENANT, project_id="default",
                     to_status=PENDING_REVIEW, actor="zhang", reason="送审")
    store.transition(eco_id=eco_id, tenant_id=TENANT, project_id="default",
                     to_status=REJECTED, actor="li", reason="风险大，不批")


def _order(world, claims, *, status="VERIFIED", reject=False, title="改交付物",
           change="UPDATE"):
    """开一张单，`claims` 是 {object_id: 目标哈希}，再推到 `status`。

    `change="REMOVE"` 那一支交的是**改前**哈希（下线没有 after 可言），
    与仓储层的必填规则同形。
    """
    store = _store(world)
    record = store.create(tenant_id=TENANT, project_id="default", title=title,
                          creator="zhang")
    for object_id, digest in claims.items():
        store.add_affected(eco_id=record["eco_id"], tenant_id=TENANT,
                           project_id="default", object_type="doc", object_id=object_id,
                           change_type=change,
                           before_sha256=digest if change == "REMOVE" else "c" * 64,
                           after_sha256="" if change == "REMOVE" else digest,
                           actor="zhang")
    if reject:
        _reject(store, record["eco_id"])
    elif status != "DRAFT":
        _walk_to(status, store, record["eco_id"])
    return record["eco_id"]


def _cover_all(world, *, status="VERIFIED", prefix="", wrong=None, reject=False):
    """给每条交付物各写一行覆盖声明（哈希取当前实测），可改前缀写法/换错哈希。"""
    digests = dict(_build(world)["_artifacts"])
    digests.update(wrong or {})
    return _order(world, {f"{prefix}{path}": digest for path, digest in digests.items()},
                  status=status, reject=reject)


def _kinds(doc):
    return [i["kind"] for i in doc["issues"]]


def _issue(doc, kind):
    return next(i for i in doc["issues"] if i["kind"] == kind)


class TestBlindUntilAnyOrderExists:
    def test_no_orders_means_undetermined_not_covered(self, world):
        doc = _build(world)
        eco = doc["eco"]
        assert eco["orders"] == 0 and eco["coverage"] == "undetermined"
        assert eco["why"] == "no_change_orders_in_scope"
        assert sorted(eco["undetermined"]) == sorted(doc["_artifacts"])
        assert not any(kind.startswith("eco_") for kind in _kinds(doc)), \
            "盲区不该同时产生一条违规"

    def test_the_artifact_set_is_every_hashed_entry_not_a_hardcoded_pair(self, world):
        doc = _build(world)
        assert sorted(doc["_artifacts"]) == [DOC, SIDECAR], \
            "报告本身与它的凭据侧车都是交付物：少算一条就少核一条"
        assert all(len(h) == 64 for h in doc["_artifacts"].values())


class TestAClosedOrderCovers:
    def test_matching_after_hash_on_a_verified_order_is_coverage(self, world):
        _cover_all(world)
        doc = _build(world)
        assert doc["eco"]["coverage"] == "complete"
        assert sorted(doc["eco"]["covered_paths"]) == [DOC, SIDECAR]
        assert doc["eco"]["uncovered"] == [] and doc["eco"]["unverified"] == []
        assert not any(k.startswith("eco_") for k in _kinds(doc))

    def test_the_sidecar_is_a_separate_claim(self, world):
        """只给报告提单 ⇒ 侧车仍在 undetermined，且整格只能声称 partial。"""
        _order(world, {DOC: _build(world)["_artifacts"][DOC]})
        eco = _build(world)["eco"]
        assert eco["covered"] == 1
        assert eco["uncovered"] == [] and eco["unverified"] == []
        assert eco["coverage"] == "partial", "有单但没全覆盖，不许写 complete"

    def test_path_spelling_is_normalised_before_matching(self, world):
        _cover_all(world, prefix="./")
        assert _build(world)["eco"]["coverage"] == "complete", \
            "『./dfm.md』与『dfm.md』必须认成同一个东西"


class TestChangedWithoutAnOrderIsBlocking:
    def test_a_hash_no_order_claims_is_a_blocking_issue(self, world):
        _cover_all(world, wrong={DOC: "d" * 64})
        doc = _build(world)
        assert "eco_change_uncovered" in _kinds(doc)
        assert doc["ok"] is False and doc["blocking"] is True
        assert _issue(doc, "eco_change_uncovered")["blocking"] is True, \
            "这一条本身必须是阻断项：别的格子的红不能替它作证"
        assert doc["eco"]["uncovered"] == [DOC]
        assert doc["eco"]["coverage"] == "incomplete"
        detail = _issue(doc, "eco_change_uncovered")["detail"]
        assert "ECO-001" in detail and "VERIFIED" in detail \
            and "没有对应的闭合变更单" in detail

    def test_a_rejected_order_can_not_endorse_content(self, world):
        """被否掉的单不能反过来给内容背书——哪怕哈希逐条对得上。"""
        _cover_all(world, reject=True)
        doc = _build(world)
        assert "eco_change_uncovered" in _kinds(doc)
        assert _issue(doc, "eco_change_uncovered")["blocking"] is True
        assert doc["eco"]["uncovered"] == [DOC, SIDECAR]

    def test_a_superseded_order_can_not_endorse_content(self, world):
        first = _cover_all(world, status="DRAFT")
        store = _store(world)
        replacement = store.create(tenant_id=TENANT, project_id="default", title="新单",
                                   creator="zhang")
        store.transition(eco_id=first, tenant_id=TENANT, project_id="default",
                         to_status="SUPERSEDED", actor="zhang", reason="换方案",
                         evidence_ref=replacement["eco_id"])
        assert "eco_change_uncovered" in _kinds(_build(world))


class TestUnverifiedChangeIsBlocking:
    def test_matching_hash_on_an_unverified_order_still_blocks(self, world):
        _cover_all(world, status="IMPLEMENTED")
        doc = _build(world)
        assert "eco_change_unverified" in _kinds(doc) and doc["ok"] is False
        assert _issue(doc, "eco_change_unverified")["blocking"] is True
        eco = doc["eco"]
        assert eco["unverified"] == [DOC, SIDECAR] and eco["covered"] == 0
        assert {o["eco_id"] for o in eco["open_orders"]} == {"ECO-001"} \
            and eco["open_orders"][0]["status"] == "IMPLEMENTED", \
            "未闭合的单要点名到号：只给个数就看不出是哪张卡住了发布"

    def test_approved_but_not_implemented_also_blocks(self, world):
        _cover_all(world, status="APPROVED")
        assert "eco_change_unverified" in _kinds(_build(world))


class TestTheEndorsementBucketsAreExhaustive:
    """每一档状态都得被判定「能不能给内容背书」，加一档不归类就判红。

    `_collect_eco` 只认四个桶：`VERIFIED` 背书 / `VERIFICATION_PENDING` 等复验 /
    `DEAD_STATUSES` 作废 / 还没批的草稿。少一条相交或漏一档，新增的状态就会**悄悄**
    落进「不背书」那一支——它会阻断发布，却没人做过这个决定。
    """

    def test_every_eco_status_is_classified_for_endorsement(self):
        pre_approval = frozenset({DRAFT, PENDING_REVIEW})
        buckets = [frozenset({VERIFIED}), VERIFICATION_PENDING, DEAD_STATUSES,
                   pre_approval]
        for bucket in buckets:
            assert bucket <= ECO_STATUSES, f"{sorted(bucket)} 里有 ECO 不认的状态"
        assert sum(len(b) for b in buckets) == len(ECO_STATUSES), \
            "四个桶必须互不相交且并起来就是全部状态：并集不全=有状态没人归类，" \
            "总数对不上=有状态被归进两个桶（同一档既能背书又能算作废）"

    def test_a_dead_status_is_still_terminal_so_it_leaves_no_open_order(self):
        """作废的单不背书，但也不算「还挂着」——它已经关账了。"""
        from aipd_os.change_orders.eco import TERMINAL_STATUSES

        assert DEAD_STATUSES < TERMINAL_STATUSES
        assert DEAD_STATUSES.isdisjoint(VERIFICATION_PENDING)


class TestClaimsThatShipNothing:
    def test_an_order_about_an_unshipped_file_is_listed_not_punished(self, world):
        _order(world, {"其它项目.dxf": "e" * 64})
        doc = _build(world)
        eco = doc["eco"]
        assert eco["claimed_not_shipped"] == ["其它项目.dxf"], \
            "这一格列的是「声明了但本次没发」的东西，不是与交付物的交集"
        assert sorted(eco["undetermined"]) == [DOC, SIDECAR]
        assert not any(k.startswith("eco_") for k in _kinds(doc)), \
            "单子提到本次没发的文件，既不是覆盖也不是违规"


class TestTheCriterionIsNotDecorative:
    def test_walking_the_order_to_verified_turns_the_issue_off(self, world):
        """同一批内容、同一张单，只差「复验」这一步 ⇒ 判据真的在跟状态走。"""
        eco_id = _order(world, _build(world)["_artifacts"], status="DRAFT")
        _walk_to("IMPLEMENTED", _store(world), eco_id)
        assert "eco_change_unverified" in _kinds(_build(world))
        _store(world).transition(eco_id=eco_id, tenant_id=TENANT, project_id="default",
                                 to_status="VERIFIED", actor="wang", evidence_ref="R-12")
        done = _build(world)
        assert not any(k.startswith("eco_") for k in _kinds(done))
        assert done["eco"]["coverage"] == "complete"

    def test_editing_a_deliverable_after_verification_breaks_coverage(self, world):
        """复验之后又动了文件 ⇒ 立刻不覆盖。这条是「闭合」二字的效力所在。"""
        _cover_all(world)
        assert _build(world)["eco"]["coverage"] == "complete"
        world["doc"].write_text("内容被偷偷改了", encoding="utf-8")
        doc = _build(world)
        assert "eco_change_uncovered" in _kinds(doc)
        assert doc["eco"]["uncovered"] == [DOC], "改的是报告，侧车未受影响"

    def test_the_eco_section_survives_the_json_round_trip(self, world):
        _cover_all(world)
        _build(world)
        on_disk = json.loads((world["tmp"] / "evidence.json").read_text(encoding="utf-8"))
        assert sorted(on_disk["eco"]["covered_paths"]) == [DOC, SIDECAR]
        assert on_disk["eco"]["basis"].startswith("交付物 path+sha256")


def test_hashed_artifact_walker_is_stable_across_shapes():
    """递归收：数组里、嵌套字典里、元组里都算；同一路径重复出现取第一次；空哈希丢。"""
    found = _hashed_artifacts({"a": [{"path": "./x//y.md", "sha256": "1" * 64},
                                     {"path": "x/y.md", "sha256": "2" * 64}],
                               "b": {"c": {"path": "z", "sha256": ""}},
                               "d": ("tuple", {"path": "t", "sha256": "3" * 64})})
    assert found == {"x/y.md": "1" * 64, "t": "3" * 64}, found


GATE = Path(__file__).resolve().parents[1] / "scripts" / "production_release_gate.py"
def _baseline_path(world):
    return world["tmp"] / "baseline.json"
ECO_CHECK = "change_control_closes_deliverables"


def _gate_verdict(world) -> dict:
    """把**真证据文档**交给**真门**读，取它自己算出的那一条判定。

    生产者写完没人读就是装饰（F-EVID-03 同一类缺陷），所以这一格必须穿过子进程
    走一遍真门禁，而不是在测试里复刻判据。
    """
    evidence = world["tmp"] / "evidence.json"
    proc = subprocess.run([sys.executable, str(GATE), "--manifest", str(evidence),
                           "--target", "C6", "--max-evidence-age-hours", "8760"],
                          capture_output=True, text=True, cwd=str(world["tmp"]))
    out = json.loads(proc.stdout)
    return next(c for c in out["evidence_checks"] if c["check"] == ECO_CHECK)


class TestTheGateReadsIt:
    def test_no_orders_passes_the_producer_but_not_the_gate(self, world):
        """盲区在生产者那一侧不阻断，在门那一侧不许读成通过。"""
        doc = _build(world)
        assert not [i for i in doc["issues"] if str(i["kind"]).startswith("eco_")], \
            "生产者：一张单都没有 ⇒ 只记账，不产阻断项"
        chk = _gate_verdict(world)
        assert chk["passed"] is False
        assert "无任何变更单可判 2 条" in chk["detail"], chk

    def test_a_verified_order_per_artifact_turns_the_gate_green(self, world):
        _cover_all(world)
        _build(world)
        chk = _gate_verdict(world)
        assert chk["passed"] is True, chk
        assert "2/2" in chk["detail"], chk

    def test_editing_a_deliverable_after_verification_turns_the_gate_red_again(self, world):
        _cover_all(world)
        _build(world)                      # 盘上那份必须重取：门读的是文件，不是内存
        assert _gate_verdict(world)["passed"] is True
        world["doc"].write_text(world["doc"].read_text(encoding="utf-8") + "\n改一手\n",
                                encoding="utf-8")
        _build(world)
        chk = _gate_verdict(world)
        assert chk["passed"] is False and DOC in chk["detail"], chk


def _snapshot(world, *, extra=(), drop=()):
    """把当前交付物集合落成「上一版基线」。

    `extra` 造「上一版交了、这一版没交」；`drop` 造「这一版新加」。
    返回基线路径，直接喂给 `--baseline`。
    """
    raw = dict(_build(world)["_artifacts"])
    for path in drop:
        raw.pop(path, None)
    for path in extra:
        raw[path] = "f" * 64
    write_baseline(_baseline_path(world), raw, world["tmp"], release="v1")
    return _baseline_path(world)


def _baseline_with_ghost(world, ghost):
    """基线里多一条这次没交的路径（不改生产者，只改基线文件）。"""
    _snapshot(world)
    doc = json.loads(_baseline_path(world).read_text(encoding="utf-8"))
    doc["artifacts"][ghost] = {"sha256": "f" * 64, "semantic_sha256": "e" * 64,
                               "volatile_dropped": []}
    _baseline_path(world).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return _baseline_path(world)


class TestAgainstPreviousRelease:
    """第 28 片：有了上一版清单，「没单提到」才拆得出「证明没改」与「改了没提单」。"""

    def test_an_unchanged_delivery_needs_no_order_at_all(self, world):
        _snapshot(world)
        doc = _build(world, baseline=_baseline_path(world))
        eco = doc["eco"]
        assert eco["baseline_coverage"] == "complete"
        assert eco["unchanged_since_baseline"] == [DOC, SIDECAR]
        assert eco["undetermined"] == [] and eco["coverage"] == "complete"
        assert not [i for i in doc["issues"] if str(i["kind"]).startswith("eco_")], \
            "两份交付物一个字节都没变，要单反而是错的——没有变更可背书"
        assert "证明没改" in eco["not_covered"]

    def test_re_running_the_generator_is_not_an_engineering_change(self, world):
        """整条链重跑一遍（侧车的 generated_at 必变）⇒ 仍判「没改」，不需要单。

        这一条是这片的全部风险所在：判据若按原始字节比，每次重新出证据都会凭空要一张单。
        """
        _snapshot(world)
        generate_dfm_report(world["doc"], model=world["shape"], part_name="BRK-1",
                            revision="A", material="6061-T6")
        doc = _build(world, baseline=_baseline_path(world))
        eco = doc["eco"]
        assert eco["unchanged_since_baseline"] == [DOC, SIDECAR], eco["since_baseline"]
        assert eco["baseline_coverage"] == "complete"

    def test_a_real_edit_without_an_order_now_blocks(self, world):
        _snapshot(world)
        world["doc"].write_text(world["doc"].read_text(encoding="utf-8") + "\n改一行结论\n",
                                encoding="utf-8")
        doc = _build(world, baseline=_baseline_path(world))
        eco = doc["eco"]
        assert eco["since_baseline"]["modified"] == [DOC]
        assert eco["baseline_coverage"] == "incomplete"
        issue = _issue(doc, "eco_change_uncovered")
        assert issue["blocking"] is True
        assert "相对上一版基线是**相对基线变了**" in issue["detail"] \
            and "没有任何变更单提到它" in issue["detail"]

    def test_a_closed_order_clears_the_baseline_violation(self, world):
        _snapshot(world)
        world["doc"].write_text(world["doc"].read_text(encoding="utf-8") + "\n改一行结论\n",
                                encoding="utf-8")
        _cover_all(world)
        eco = _build(world, baseline=_baseline_path(world))["eco"]
        assert eco["baseline_coverage"] == "complete"
        # 侧车**没改** ⇒ 走「基线证明没改」那一支，不需要单；报告改了 ⇒ 必须由单覆盖。
        # 两个桶不能同时收同一条：unchanged 的优先级在判据里排第一。
        assert eco["covered_paths"] == [DOC] and eco["unchanged_since_baseline"] == [SIDECAR]
        assert eco["since_baseline"]["modified"] == [DOC]

    def test_a_deliverable_the_baseline_never_had_counts_as_added(self, world):
        """上一版没有 ⇒ 这一版它是**新增** ⇒ 没单就阻断（不再是 undetermined）。"""
        _snapshot(world, drop=(SIDECAR,))
        doc = _build(world, baseline=_baseline_path(world))
        eco = doc["eco"]
        assert eco["since_baseline"]["added"] == [SIDECAR]
        assert eco["uncovered"] == [SIDECAR] and eco["undetermined"] == []
        assert "新增" in _issue(doc, "eco_change_uncovered")["detail"]

    def test_a_delivery_that_vanished_must_be_claimed_by_a_verified_remove_row(self, world):
        ghost = "assy.step.evidence.json"
        _baseline_with_ghost(world, ghost)
        doc = _build(world, baseline=_baseline_path(world))
        issue = _issue(doc, "eco_deliverable_removed_uncovered")
        assert issue["blocking"] is True and ghost in issue["detail"]
        assert doc["eco"]["baseline_coverage"] == "incomplete"

        _order(world, {ghost: "f" * 64}, change="REMOVE")
        again = _build(world, baseline=_baseline_path(world))
        assert again["eco"]["removed_unclaimed"] == []
        assert "eco_deliverable_removed_uncovered" not in _kinds(again)

    def test_only_a_verified_removal_endorses_a_vanished_delivery(self, world):
        """认领下线这件事，两样都不能少：**行是 REMOVE** 且 **单是 VERIFIED**。

        第 28 片电池的第一轮这条没被测到：把判据放宽成「单里提到过就行」照样全绿
        ——那等于任何一张草稿、任何一条 UPDATE 声明都能替一次下线签字。
        """
        ghost = "assy.step.evidence.json"
        for change, status in (("UPDATE", "VERIFIED"), ("REMOVE", "APPROVED")):
            _baseline_with_ghost(world, ghost)
            _order(world, {ghost: "f" * 64}, change=change, status=status)
            eco = _build(world, baseline=_baseline_path(world))["eco"]
            assert eco["removed_unclaimed"] == [ghost], \
                f"{change}/{status} 不该算认领下线"
            assert eco["baseline_coverage"] == "incomplete"

    def test_a_corrupt_baseline_blocks_instead_of_falling_back_to_absent(self, world):
        """读坏了就退回「没有基线」= 删掉基线文件即可关掉差集判据。所以必须阻断。"""
        _snapshot(world)
        _baseline_path(world).write_text("{这不是 JSON", encoding="utf-8")
        doc = _build(world, baseline=_baseline_path(world))
        assert _issue(doc, "eco_baseline_unreadable")["blocking"] is True
        assert doc["eco"]["baseline_coverage"] == "absent"

    def test_without_a_baseline_the_section_reads_exactly_as_last_slice(self, world):
        doc = _build(world)["eco"]
        assert doc["baseline_coverage"] == "absent"
        assert doc["since_baseline"] is None
        assert doc["unchanged_since_baseline"] == [] and doc["removed_unclaimed"] == []


class TestTheGateReadsTheBaseline:
    def test_an_unclaimed_removal_fails_the_gate(self, world):
        _baseline_with_ghost(world, "assy.step.evidence.json")
        _build(world, baseline=_baseline_path(world))
        chk = _gate_verdict(world)
        assert chk["passed"] is False
        assert "没人认领" in chk["detail"] and "assy.step.evidence.json" in chk["detail"]

    def test_absent_baseline_does_not_newly_fail_the_gate_and_says_so(self, world):
        """没有基线不新增要求（否则只能事后补一百多张单来凑绿），但也不许声称「只改了这些」。"""
        _cover_all(world)
        _build(world)
        chk = _gate_verdict(world)
        assert chk["passed"] is True, chk
        assert "无基线" in chk["detail"] and "**不**声称" in chk["detail"]

    def test_an_unchanged_release_passes_with_zero_orders(self, world):
        """门这一侧也认「基线证明没改」：零张单 + 全部 unchanged ⇒ 过。"""
        _snapshot(world)
        _build(world, baseline=_baseline_path(world))
        chk = _gate_verdict(world)
        assert chk["passed"] is True, chk
        assert "另有 2 条由上一版基线证明语义未变" in chk["detail"]


class TestCliBaselineSurface:
    """命令行这一层：落基线之前要先过「没人放行过的一次运行不许当基准」这道闸。"""

    def _run(self, world, *extra):
        from aipd_os.cli.main import main

        return main(["release", "manifest", "--db", str(world["db"]),
                     "--project", "default", "--dfm-doc", str(world["doc"]),
                     "--out", str(world["tmp"] / "evidence.json")] + list(extra))

    def _base(self, world):
        return world["tmp"] / "baseline.json"

    def test_write_is_refused_while_the_evidence_is_red(self, world, capsys):
        rc = self._run(world, "--write-baseline", str(self._base(world)))
        out = capsys.readouterr().out
        assert rc == 2 and "不落成基线" in out
        assert not self._base(world).exists(), "嘴上拒绝、手上落盘 = 这道闸没生效"

    def test_acknowledged_write_records_that_it_was_not_ready(self, world, capsys):
        rc = self._run(world, "--write-baseline", str(self._base(world)),
                       "--acknowledge-not-ready", "先建基准，缺的 CTQ 下一版补")
        capsys.readouterr()
        assert rc == 4, "承认了也不代替放行：这份证据照旧不 ok"
        doc = json.loads(self._base(world).read_text(encoding="utf-8"))
        assert doc["release_ready"] is False
        assert doc["acknowledgement"].startswith("先建基准")
        assert sorted(doc["artifacts"]) == [DOC, SIDECAR]

    def test_reading_the_baseline_back_reports_everything_unchanged(self, world, capsys):
        self._run(world, "--write-baseline", str(self._base(world)),
                  "--acknowledge-not-ready", "r")
        capsys.readouterr()
        rc = self._run(world, "--baseline", str(self._base(world)))
        out = capsys.readouterr().out
        assert rc == 4 and "证明没改 2" in out, out
        eco = json.loads((world["tmp"] / "evidence.json")
                         .read_text(encoding="utf-8"))["eco"]
        assert eco["baseline_coverage"] == "complete"
