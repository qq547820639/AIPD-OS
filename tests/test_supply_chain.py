"""供应链与验证执行器测试（Task 5）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.execution.adapter import AdapterError
from aipd_os.tool_adapters.builtin import build_registry
from aipd_os.supply_chain.quotes import normalize_quote, parse_quote_file, QuoteRegistry
from aipd_os.supply_chain.suppliers import SupplierProfile, SupplierRegistry
from aipd_os.supply_chain.lab import import_lab_csv, import_lab_report
from aipd_os.supply_chain.analysis import (
    analyze_stage,
    create_correction_tasks,
    mark_regression,
    update_facts,
    propagate_impact,
)

CANONICAL_CSV = (
    "supplier,part,moq,tooling_fee,unit_price,lead_time_days\n"
    "Acme,Widget-X,100,500.5,1.25,14\n"
    "Acme,Widget-Y,50,0,0.99,7\n"
)


def test_parse_normalize_canonical_csv_quote(tmp_path):
    p = tmp_path / "quote.csv"
    p.write_text(CANONICAL_CSV, encoding="utf-8")
    parsed = parse_quote_file(p)
    assert parsed["format"] == "csv"
    assert parsed["count"] == 2
    rec = parsed["records"][0]
    assert rec["supplier"] == "Acme"
    assert rec["part"] == "Widget-X"
    assert rec["moq"] == 100
    assert rec["tooling_fee"] == 500.5
    assert rec["unit_price"] == 1.25
    assert rec["lead_time_days"] == 14
    # 字符串数值被强制转数值
    rec2 = parsed["records"][1]
    assert rec2["moq"] == 50
    assert rec2["unit_price"] == 0.99

    # 通过 QuoteRegistry 登记后可按 official 取回
    reg = QuoteRegistry()
    reg.add_quote(supplier="Acme", part="Widget-X", data=parsed["records"][0], source_file=str(p))
    official = reg.get_official("Acme", "Widget-X")
    assert official.status == "official"
    assert official.data["unit_price"] == 1.25


def test_parse_quote_unsupported_extension(tmp_path):
    p = tmp_path / "quote.txt"
    p.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="csv"):
        parse_quote_file(p)


def test_normalize_quote_coercion():
    n = normalize_quote({"moq": "-3", "tooling_fee": "abc", "unit_price": "9.9", "lead_time_days": "2"})
    assert n["moq"] == 0  # 负数钳到 0
    assert n["tooling_fee"] == 0.0  # 非法转 0
    assert n["unit_price"] == 9.9
    assert n["lead_time_days"] == 2


def test_quote_registry_versioning_supersedes(tmp_path):
    p = tmp_path / "quote.csv"
    p.write_text(CANONICAL_CSV, encoding="utf-8")
    parsed = parse_quote_file(p)
    reg = QuoteRegistry()
    v1 = reg.add_quote(supplier="Acme", part="Widget-X", data=parsed["records"][0], source_file=str(p))
    v2 = reg.add_quote(supplier="Acme", part="Widget-X", data={**parsed["records"][0], "unit_price": 0.9}, source_file=str(p))
    assert v1.version == 1
    assert v2.version == 2
    assert v1.status == "superseded"
    assert v2.status == "official"
    official = reg.get_official("Acme", "Widget-X")
    assert official is v2
    assert official.data["unit_price"] == 0.9


def test_quote_registry_no_official_raises():
    reg = QuoteRegistry()
    with pytest.raises(KeyError):
        reg.get_official("Acme", "Widget-X")


def test_supplier_qualify_requires_cert():
    reg = SupplierRegistry()
    reg.add(SupplierProfile(supplier_id="S1", name="Acme", certificates=["ISO9001"]))
    assert reg.qualify("S1", "ISO9001") is True
    assert reg.qualify("S1", "IATF16949") is False  # 证书缺失 -> 不合格
    assert reg.qualify("S2", "ISO9001") is False  # 供应商不存在


LAB_CSV = (
    "stage,test_item,sample_id,result,pass_fail,notes\n"
    "evt,drop_test,A-1,ok,pass,passed\n"
    "evt,drop_test,A-2,broken,fail,cracked\n"
    "evt,thermal,B-1,105C,pass,ok\n"
)


def test_lab_import_analysis_and_tasks(tmp_path):
    p = tmp_path / "lab.csv"
    p.write_text(LAB_CSV, encoding="utf-8")
    imported = import_lab_csv(p, "evt")
    assert imported["count"] == 3
    analysis = analyze_stage(imported["records"], "evt")
    assert analysis["total"] == 3
    assert analysis["passed"] == 2
    assert analysis["failed"] == 1
    failing = analysis["failing_items"]
    assert len(failing) == 1
    assert failing[0]["test_item"] == "drop_test"

    tasks = create_correction_tasks(analysis, "evt")
    assert len(tasks) == 1
    assert tasks[0]["type"] == "correction"
    assert tasks[0]["stage"] == "evt"
    assert tasks[0]["test_item"] == "drop_test"
    assert tasks[0]["action"] in ("rerun", "redesign")


def test_mark_regression():
    analysis = {
        "items": [
            {"test_item": "drop_test", "status": "fail"},
            {"test_item": "thermal", "status": "pass"},
        ]
    }
    baseline = {"drop_test": "pass", "thermal": "fail"}
    out = mark_regression(analysis, baseline)
    assert out["regressions"] == ["drop_test"]
    assert out["improved"] == ["thermal"]


def test_update_facts_merges_verification():
    analysis = analyze_stage(import_lab_csv_and_records(), "evt")
    facts = {"name": "proj"}
    facts = update_facts(facts, analysis, "evt")
    assert facts["verification"]["evt"]["passed"] == 2
    assert facts["verification"]["evt"]["failed"] == 1
    assert facts["verification"]["evt"]["total"] == 3
    assert facts["verification"]["evt"]["passed_flag"] is False


def import_lab_csv_and_records():
    import tempfile
    from pathlib import Path as P
    tmp = P(tempfile.gettempdir()) / "aipd_os_trivial_lab.csv"
    tmp.write_text(LAB_CSV, encoding="utf-8")
    return import_lab_csv(tmp, "evt")["records"]


def test_propagate_impact_marks_stale():
    bom = [
        {"part": "Widget-X", "params": ["thermal"]},
        {"part": "Gear-Y", "params": ["drop_test"]},
        {"part": "Unrelated-Z", "params": ["color"]},
    ]
    affected = ["drop_test", "thermal"]
    stale = propagate_impact({}, bom, affected)
    parts = sorted(s["part"] for s in stale)
    assert parts == ["Gear-Y", "Widget-X"]
    assert all(s["stale"] is True for s in stale)
    assert len(stale) == 2


def test_mail_rfq_no_provider_writes_task_package(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("AIPD_MAIL_PROVIDER", raising=False)
    reg = build_registry()
    a = reg.get("supply.rfq")
    with pytest.raises(AdapterError) as ei:
        a.execute({"supplier": "Acme", "part": "Widget-X", "work_id": "w1"})
    assert ei.value.classification == "external_blocked"
    assert ei.value.task_package and Path(ei.value.task_package).is_file()
    assert list(tmp_path.glob("*.task.json"))


def test_mail_rfq_with_provider_makes_draft(monkeypatch):
    monkeypatch.setenv("AIPD_MAIL_PROVIDER", "smtp")
    reg = build_registry()
    a = reg.get("supply.rfq")
    out = a.execute({"supplier": "Acme", "part": "Widget-X"})
    assert out["provider"] == "smtp"
    assert out["sent"] is False
    assert "Acme" in out["rfq_draft"]["to"]


def test_no_official_quote_and_no_executed_lab_not_passed(tmp_path):
    # 未收到报价时不能取到 official 报价
    reg = QuoteRegistry()
    reg.add_quote(supplier="Acme", part="Widget-X", data={"unit_price": 5}, status="draft")
    with pytest.raises(KeyError):
        reg.get_official("Acme", "Widget-X")

    # 无已执行数据的实验室不能被标记为通过
    analysis = analyze_stage([], "evt")
    assert analysis["passed"] == 0
    assert analysis["failed"] == 0
    assert not analysis["passed"]
    facts = update_facts({}, analysis, "evt")
    assert facts["verification"]["evt"]["passed_flag"] is False


def test_lab_report_pdf_external_blocked(tmp_path):
    p = tmp_path / "report.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(AdapterError) as ei:
        import_lab_report(p, "evt")
    assert ei.value.classification == "external_blocked"
