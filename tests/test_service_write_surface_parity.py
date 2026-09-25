"""第 38 片：服务写面与库层的形参必须对得上（CTQ 的公差/条件从前录不进去）。

实测前提（2026-09-26，不截断的量具：`inspect.signature` 逐对比较，
比较对象是 `AIPDStateDB` 与 `StateService` 两边**同名**的 `add_*`）：

| 库层收 | 服务面以前不转 |
|--------|----------------|
| `add_fact(tolerance, conditions, version)` | 多租户这条路上录不进公差与条件 |
| `add_evidence(accessed_at)` | 访问时间落到 `created_at`（库里 `accessed_at or ts`）|
| `add_risk(trigger)` | 触发条件录不进去；第 34/37 片刚把 `owner` 接上，`trigger` 仍差一格 |

CTQ 的语义正是「目标值 + 公差 + 条件」，第 18/20 片还拿它生成图纸公差：
写面缺这两格，等于「Product Truth 可经多租户服务录入」这句话只有一半是真的。

另两处顺手量到、**不是缺陷**，记下来免得下次再查：
`add_deliverable` 的创建参数叫 `dtype` 而 `update_deliverable` 白名单里叫 `type`
（那是形参名与列名不同，不是能力缺口）；`id_sequences` 的播种名覆盖也不是缺口
（`next_sequence` 走 UPSERT，首次调用自行建行）。

本片做两件事：把三处补齐并转发；再装一把常驻对账，让「库层加了参数而服务面没跟上」
当场可红——写面收下却不转发（第 37 片 `owner` 差点中的那一枪）与签名漏参数是同一件事的两面，
所以两条各配自己的最小对照。
"""
from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.server import StateService

#: 两层同名的写入口（实测 4 个，由 `test_the_ratchet_covers_every_shared_writer_not_just_three`
#: 现算比对）：对账面就是这几个，多一个少一个都会当场红。`add_deliverable` 本来就对齐，
#: 仍留在对账面上——它是最容易被下一次改动撞歪的一个。
COVERED_METHODS = ("add_deliverable", "add_evidence", "add_fact", "add_risk")

_TABLE = {"add_fact": ("facts", "fact_id"),
          "add_evidence": ("evidence", "evidence_id"),
          "add_risk": ("risks", "risk_id")}

#: 每个方法一次「每格都给不同值」的完整调用，以及**期望落在哪一列**。
FULL_CALLS = {
    "add_fact": dict(
        args=("default", "P-SVC", "product_goal", "峰值 12 N", "C"),
        kwargs=dict(unit="N", source="truth", confidence=0.8,
                    tolerance="±0.05", conditions="23℃/50%RH", version="CTQ-v3"),
        expect={"unit": "N", "tolerance": "±0.05", "conditions": "23℃/50%RH",
                "version": "CTQ-v3", "confidence": 0.8, "source": "truth"}),
    "add_evidence": dict(
        args=("default", "P-SVC", "vendor-datasheet", "厂商页 A-7"),
        kwargs=dict(url="https://example.invalid/a7", identifier="A-7",
                    quality="primary", summary="额定寿命 20k h",
                    metadata={"page": 7}, accessed_at="2026-05-04T00:00:00+00:00"),
        expect={"accessed_at": "2026-05-04T00:00:00+00:00", "quality": "primary",
                "identifier": "A-7", "metadata_json": '{"page": 7}'}),
    "add_risk": dict(
        args=("default", "P-SVC", "交期不稳"),
        kwargs=dict(probability="medium", impact="high", mitigation="双供应商",
                    status="open", trigger="来料延迟 > 2 周", owner="li"),
        expect={"trigger": "来料延迟 > 2 周", "owner": "li",
                "probability": "medium", "mitigation": "双供应商"}),
}


def _svc(tmp_path: Path) -> StateService:
    svc = StateService(str(tmp_path / "svc.db"), encryption_key="k",
                       secret="test-secret")
    svc.db.ensure_default_tenant()
    svc.db.init_project("default", "P-SVC", "写面对账", "slice 38")
    svc.auth_register("u-li", "default", "li", "pw", project_id="P-SVC")
    return svc


def _row(svc: StateService, method: str, oid: str) -> dict:
    table, key = _TABLE[method]
    with svc.db.connect() as c:
        c.row_factory = sqlite3.Row
        row = c.execute(f"SELECT * FROM {table} WHERE {key}=?", (oid,)).fetchone()
    return dict(row)


def _write(svc: StateService, method: str, **extra) -> dict:
    case = FULL_CALLS[method]
    kwargs = dict(case["kwargs"])
    kwargs.update(extra.pop("kwargs", {}))
    for drop in extra.get("drop", ()):
        kwargs.pop(drop, None)
    oid = getattr(svc, method)(*case["args"], **kwargs, actor="u-li")
    return _row(svc, method, oid)


class TestEveryFieldLands:
    @pytest.mark.parametrize("method", sorted(FULL_CALLS))
    def test_each_service_parameter_reaches_its_column(self, tmp_path, method):
        """逐列断言，而不是只断「没报错」：不转发时列会静默留 NULL/默认。"""
        row = _write(_svc(tmp_path), method)
        for column, want in FULL_CALLS[method]["expect"].items():
            assert row[column] == want, f"{method} 的 {column} 没落到盘上：{row[column]!r}"

    @pytest.mark.parametrize("method", sorted(FULL_CALLS))
    def test_dropping_a_forward_makes_that_column_read_back_empty(
            self, tmp_path, method):
        """最小对照的另一半：把这一格从调用里抽掉，落盘就必须不是那个值。

        只有上一条开火、这一条**不开火**，才说明读回来的是真转发而不是永远绿。
        """
        # 逐列都抽一遍代价高；每格抽最贵的那一列，另两列由上一条钉。
        key_column = {"add_fact": "tolerance", "add_evidence": "accessed_at",
                      "add_risk": "trigger"}[method]
        row = _write(_svc(tmp_path), method, drop=(key_column,))
        want = FULL_CALLS[method]["expect"][key_column]
        if key_column == "accessed_at":
            assert row[key_column] != want, "库层对空 accessed_at 兜底 created_at，仍须看得见"
        else:
            assert row[key_column] is None, f"{key_column} 不该有值：{row[key_column]!r}"


class TestSignaturesStayAligned:
    """签名层：库层每个 `add_*` 形参都得在服务面同名方法上能看见。

    这把尺子与上面那对行为断言各管一面：**收下不转发**行为断言看得见、签名看不见；
    **根本没这个形参**签名看得见。缺一面就有一面漏。
    """

    @staticmethod
    def _business_params(fn) -> set[str]:
        return {p for p in inspect.signature(fn).parameters
                if p not in ("self", "tenant_id", "project_id", "actor")}

    def test_service_covers_every_db_write_parameter(self):
        offenders = {}
        for method in COVERED_METHODS:
            missing = (self._business_params(getattr(AIPDStateDB, method))
                       - self._business_params(getattr(StateService, method)))
            if missing:
                offenders[method] = sorted(missing)
        assert not offenders, f"这些字段只能从库层进、多租户写面录不进去：{offenders}"

    def test_the_ratchet_covers_every_shared_writer_not_just_three(self):
        """对账面不许只有我点名的三个：凡是两层同名的 `add_*` 都要比。"""
        shared = [n for n in dir(StateService)
                  if n.startswith("add_") and callable(getattr(StateService, n))
                  and hasattr(AIPDStateDB, n)]
        # 清单本身也要对账：两层同名的写入口多了，就必须显式决定要不要纳入对账面。
        assert set(shared) == set(COVERED_METHODS), (
            f"两层同名的写入口不再是这三个：{sorted(shared)}")
        offenders = {}
        for method in shared:
            missing = (self._business_params(getattr(AIPDStateDB, method))
                       - self._business_params(getattr(StateService, method)))
            if missing:
                offenders[method] = missing
        assert not offenders, f"新增的同名写入口没对齐：{offenders}"

    def test_an_unforwarded_parameter_still_shows_in_the_row(self, tmp_path):
        """反向对照（签名查不到「收下不转发」，那一面归行为断言）：
        直接调库层与走服务面对同一格的结果必须一致。"""
        svc = _svc(tmp_path)
        via_service = svc.add_fact("default", "P-SVC", "k1", "v", "C",
                                   tolerance="±1", conditions="常温", actor="u-li")
        via_db = svc.db.add_fact("default", "P-SVC", "k2", "v", "C",
                                 tolerance="±1", conditions="常温")
        a = _row(svc, "add_fact", via_service)
        b = _row(svc, "add_fact", via_db)
        assert (a["tolerance"], a["conditions"]) == (b["tolerance"], b["conditions"])


def test_metadata_json_is_the_serialised_mapping_not_a_replacement(tmp_path):
    """`metadata` 这格是 JSON 列：读回来要能 `json.loads`，且与原字典相等。"""
    row = _write(_svc(tmp_path), "add_evidence")
    assert json.loads(row["metadata_json"]) == {"page": 7}
