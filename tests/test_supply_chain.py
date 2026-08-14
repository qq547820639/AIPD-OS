"""供应链与验证执行器测试（Task 5 / P1-6）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aipd_os.execution.adapter import AdapterError
from aipd_os.state.db import AIPDStateDB
from aipd_os.supply_chain.analysis import (
    analyze_stage,
    create_correction_tasks,
    mark_regression,
    propagate_impact,
    update_facts,
)
from aipd_os.supply_chain.certification import (
    Certification,
    CertificationRegistry,
    expiring_certs,
    import_certificate_file,
)
from aipd_os.supply_chain.lab import import_lab_csv, import_lab_report
from aipd_os.supply_chain.mail import (
    ExternalDependencyError,
    ImapConnector,
    LocalMailService,
    MailAttachment,
    MailError,
    MailMessage,
    SmtpConnector,
    retry_with_backoff,
)
from aipd_os.supply_chain.persistence import SupplyChainStore
from aipd_os.supply_chain.quotes import QuoteRegistry, normalize_quote, parse_quote_file
from aipd_os.supply_chain.stages import (
    extract_root_cause,
    import_stage_report,
    propose_corrective_actions,
    verify_regression,
)
from aipd_os.supply_chain.suppliers import SupplierProfile, SupplierRegistry
from aipd_os.supply_chain.writeback import PhysicalWriteback
from aipd_os.tool_adapters.builtin import build_registry

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
    n = normalize_quote({"moq": "-3", "tooling_fee": "abc", "unit_price": "9.9", "lead_time_days": "2"})  # noqa: E501
    assert n["moq"] == 0  # 负数钳到 0
    assert n["tooling_fee"] == 0.0  # 非法转 0
    assert n["unit_price"] == 9.9
    assert n["lead_time_days"] == 2


def test_quote_registry_versioning_supersedes(tmp_path):
    p = tmp_path / "quote.csv"
    p.write_text(CANONICAL_CSV, encoding="utf-8")
    parsed = parse_quote_file(p)
    reg = QuoteRegistry()
    v1 = reg.add_quote(supplier="Acme", part="Widget-X", data=parsed["records"][0], source_file=str(p))  # noqa: E501
    v2 = reg.add_quote(supplier="Acme", part="Widget-X", data={**parsed["records"][0], "unit_price": 0.9}, source_file=str(p))  # noqa: E501
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


def test_mail_rfq_provider_env_ignored_without_real_smtp(monkeypatch):
    """回归：AIPD_MAIL_PROVIDER 无任何实现读取；未配 AIPD_SMTP_HOST 时必须
    诚实 external_blocked（此前设了 AIPD_MAIL_PROVIDER 就返回"草稿已就绪"）。"""
    monkeypatch.setenv("AIPD_MAIL_PROVIDER", "smtp")
    monkeypatch.delenv("AIPD_SMTP_HOST", raising=False)
    monkeypatch.delenv("AIPD_MAILPIT_SMTP_HOST", raising=False)
    reg = build_registry()
    a = reg.get("supply.rfq")
    with pytest.raises(AdapterError) as ei:
        a.execute({"supplier": "Acme", "part": "Widget-X"})
    assert ei.value.classification == "external_blocked"


def test_mail_rfq_with_real_smtp_sends_and_marks_sent(monkeypatch):
    """回归：配置 AIPD_SMTP_HOST 后真实发送；sent 仅在 send_email 成功后为 True。"""
    from aipd_os.mail import client as mail_client

    seen: dict[str, dict] = {}

    def fake_send(host, port, user, password, from_addr, to_addrs,
                  subject, body, **kw):
        seen["send"] = {"host": host, "to": to_addrs, "subject": subject}
        return "m-1"

    monkeypatch.setattr(mail_client, "send_email", fake_send)
    monkeypatch.setenv("AIPD_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AIPD_SMTP_USER", "buyer")
    monkeypatch.setenv("AIPD_SMTP_PASSWORD", "secret")
    monkeypatch.delenv("AIPD_MAILPIT_SMTP_HOST", raising=False)
    reg = build_registry()
    a = reg.get("supply.rfq")
    out = a.execute({"supplier": "Acme", "part": "Widget-X"})
    assert out["sent"] is True
    assert out["provider"] == "smtp"
    assert out["message_id"] == "m-1"
    assert seen["send"]["host"] == "smtp.example.com"
    assert "Acme" in seen["send"]["to"]


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


def test_lab_report_xlsx_dispatched_to_import_lab_xlsx(tmp_path, monkeypatch):
    """回归：import_lab_report 必须把 .xlsx 派发给 import_lab_xlsx
    （此前 .xlsx 断链：错误信息谎称支持，实际走不到 xlsx 解析器）。"""
    from aipd_os.supply_chain import lab as lab_mod

    def fake_import_lab_xlsx(path, stage):
        return {"format": "xlsx", "stage": stage, "records": []}

    monkeypatch.setattr(lab_mod, "import_lab_xlsx", fake_import_lab_xlsx)
    p = tmp_path / "report.xlsx"
    p.write_bytes(b"PK\x03\x04 fake xlsx")
    out = import_lab_report(p, "dvt")
    assert out["format"] == "xlsx"
    assert out["stage"] == "dvt"


# ======================================================================
# P1-6 新增：邮件连接器 / 报价 XLSX+PDF / 持久化 / 证书到期 / 阶段导入 /
# 根因 / 回写（HOLD）
# ======================================================================


# ---------------------------------------------------------------- 邮件连接器
def test_mail_smtp_imap_are_external_dependency():
    smtp = SmtpConnector()
    imap = ImapConnector()
    assert smtp.external_dependency is True
    assert imap.external_dependency is True
    msg = MailMessage(message_id="x", sender="a@b.c", recipients=["v"], subject="s", body="b")
    with pytest.raises(ExternalDependencyError):
        smtp.send(msg)
    with pytest.raises(ExternalDependencyError):
        imap.read_inbox()
    with pytest.raises(ExternalDependencyError):
        imap.download_attachment("x", "f")


def test_local_mail_draft_approve_send_and_message_id():
    svc = LocalMailService()
    draft = svc.create_rfq_draft("Acme", "Widget-X", quantity=100)
    assert draft.status == "draft"
    assert draft.thread_id == draft.message_id
    # 未审批禁止发送
    r = svc.send(draft.message_id)
    assert r.ok is False and "审批" in r.error
    svc.approve(draft.message_id)
    r = svc.send(draft.message_id)
    assert r.ok is True
    assert svc.get(draft.message_id).status == "sent"
    assert svc.get(draft.message_id).sent_at


def test_local_mail_idempotent_send_dedup():
    svc = LocalMailService()
    draft = svc.create_rfq_draft("Acme", "Widget-X")
    svc.approve(draft.message_id)
    first = svc.send(draft.message_id)
    second = svc.send(draft.message_id)
    assert first.ok and second.ok
    sent = [m for m in svc.all_messages() if m.status == "sent"]
    assert len(sent) == 1  # Message-ID 去重，不重复发送
    assert second.retries_used == 0


def test_local_mail_retry_with_backoff_and_failure_message():
    svc = LocalMailService()
    draft = svc.create_rfq_draft("Acme", "Widget-X")
    svc.approve(draft.message_id)
    res = svc.send(draft.message_id, max_retries=3, should_fail=lambda n: n < 3)
    assert res.ok is True
    assert res.retries_used == 2

    # 全部失败 -> 用户可见失败提示
    draft2 = svc.create_rfq_draft("Beta", "Part-Y")
    svc.approve(draft2.message_id)
    res2 = svc.send(draft2.message_id, max_retries=3, should_fail=lambda n: True)
    assert res2.ok is False
    assert res2.retries_used == 3
    assert "失败" in res2.error and "重试" in res2.error
    assert svc.get(draft2.message_id).status == "failed"


def test_local_mail_inbox_reply_association_and_attachment():
    svc = LocalMailService()
    draft = svc.create_rfq_draft("Acme", "Widget-X")
    svc.approve(draft.message_id)
    svc.send(draft.message_id)

    reply = svc.receive(
        "Acme", subject="Re: RFQ", body="quote attached",
        in_reply_to=draft.message_id,
        attachments=[MailAttachment("quote.csv", b"supplier,part,unit_price\nAcme,X,1.25")],
    )
    assert reply.direction == "inbox"
    assert reply.thread_id == draft.thread_id  # 回信关联到同一线程
    inbox = svc.read_inbox()
    assert len(inbox) == 1
    assert svc.messages_for_thread(draft.thread_id) == [draft, reply]
    assert svc.download_attachment(reply.message_id, "quote.csv") == b"supplier,part,unit_price\nAcme,X,1.25"  # noqa: E501
    with pytest.raises(MailError):
        svc.download_attachment(reply.message_id, "missing.bin")


def test_retry_with_backoff_helper():
    calls = []

    def flaky(attempt):
        calls.append(attempt)
        if attempt < 3:
            raise MailError("boom")
        return "ok"

    assert retry_with_backoff(flaky, attempts=3, base_delay=0.0) == "ok"
    assert calls == [1, 2, 3]


# ---------------------------------------------------------------- 报价 XLSX/PDF
def test_quote_xlsx_parse_or_not_verified(tmp_path):
    p = tmp_path / "quote.xlsx"
    p.write_bytes(b"PK\x03\x04 fake xlsx")
    parsed = parse_quote_file(p)
    assert parsed["format"] == "xlsx"
    if parsed["count"] == 0:
        # openpyxl 缺失或解析失败 -> not_verified
        assert parsed["errors"] and parsed["errors"][0].get("not_verified") is True
    else:
        assert parsed["errors"] == []


def test_quote_pdf_parse_or_not_verified(tmp_path):
    p = tmp_path / "quote.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    parsed = parse_quote_file(p)
    assert parsed["format"] == "pdf"
    if parsed["count"] == 0:
        # pypdf 缺失 -> not_verified（诚实，不虚构）
        assert parsed["errors"] and parsed["errors"][0].get("not_verified") is True
    else:
        assert parsed["errors"] == []


def test_quote_json_parse(tmp_path):
    p = tmp_path / "quote.json"
    p.write_text(json.dumps({"records": [
        {"supplier": "Acme", "part": "X", "moq": "10", "unit_price": "1.5"},
    ]}), encoding="utf-8")
    parsed = parse_quote_file(p)
    assert parsed["format"] == "json"
    assert parsed["count"] == 1
    assert parsed["errors"] == []
    assert parsed["records"][0]["unit_price"] == 1.5


def test_quote_csv_header_missing_columns_reported(tmp_path):
    """回归：CSV 表头缺列必须显式报错，而不是恒返回规范表头掩盖实际文件。"""
    p = tmp_path / "quote.csv"
    p.write_text("supplier,part,unit_price\nAcme,X,1.25\n", encoding="utf-8")
    parsed = parse_quote_file(p)
    assert parsed["format"] == "csv"
    assert parsed["count"] == 1
    assert parsed["header"] == ["supplier", "part", "unit_price"]
    assert parsed["errors"], "缺列必须报错"
    assert "lead_time_days" in parsed["errors"][0]


# ---------------------------------------------------------------- 持久化
def _db(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    return db


def test_supply_chain_persistence_supplier_quote_cert(tmp_path):
    db = _db(tmp_path)
    db.init_project("default", "p1", "proj", "goal")
    store = SupplyChainStore(db, "default")

    store.persist_supplier("p1", supplier_id="S1", name="Acme",
                           certificates=["ISO9001"], qualification="qualified")
    store.persist_quote("p1", quote_id="q1", supplier="Acme", part="X",
                        version=1, data={"unit_price": 1.25}, status="official")
    store.persist_certification("p1", cert_id="C1", subject="Acme", standard="ISO9001",
                                status="verified", expires_at="2030-01-01",
                                evidence_ref="CERT-0001")
    store.persist_evidence_file("p1", str(tmp_path / "quote.csv"), summary="quote")

    suppliers = store.load_suppliers("p1")
    quotes = store.load_quotes("p1")
    certs = store.load_certifications("p1")
    assert len(suppliers) == 1 and suppliers[0]["value"]["qualification"] == "qualified"
    assert len(quotes) == 1 and quotes[0]["value"]["data"]["unit_price"] == 1.25
    assert len(certs) == 1 and certs[0]["value"]["status"] == "verified"
    assert len(db.list_evidence("default", "p1")) == 1


# ---------------------------------------------------------------- 证书到期
def test_certificate_import_and_expiry_reminder(tmp_path):
    p = tmp_path / "cert.json"
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    p.write_text(json.dumps({"cert_id": "C1", "subject": "Acme", "standard": "ISO9001",
                             "expires_at": future}), encoding="utf-8")
    out = import_certificate_file(p)
    assert out["ok"] is True
    assert out["cert"].cert_id == "C1"

    reg = out["registry"]
    expiring = expiring_certs(reg, within_days=30)
    assert any(e["cert"].cert_id == "C1" and e["status"] == "expiring" for e in expiring)

    # 已过期证书
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    reg.register(Certification(cert_id="C2", subject="Beta", standard="IATF16949", expires_at=past))
    expired = expiring_certs(reg, within_days=30)
    assert any(e["cert"].cert_id == "C2" and e["status"] == "expired" for e in expired)


def test_certificate_import_pdf_not_verified(tmp_path):
    p = tmp_path / "cert.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    out = import_certificate_file(p)
    assert out["ok"] is False  # ok=字段完整可验证；PDF 无法解析 → 不冒充已验证
    assert out["registered"] is True  # 已登记（登记 ≠ 已验证）
    assert out["cert"].status == "pending"
    assert any(e.get("not_verified") for e in out["errors"])


def test_expiring_certs_query_does_not_mutate_registry(tmp_path):
    """回归：expiring_certs 查询不得把注册表里的原对象 status 改成 expired。"""
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    reg = CertificationRegistry()
    reg.register(Certification(cert_id="C2", subject="Beta", standard="IATF16949",
                               expires_at=past))
    expired = expiring_certs(reg, within_days=30)
    assert expired and expired[0]["cert"].status == "expired"
    # 注册表原对象未被突变
    assert reg.get("C2").status != "expired"


# ---------------------------------------------------------------- 阶段导入 + 根因
def test_stage_import_root_cause_and_corrective_action(tmp_path):
    lab = (
        "stage,test_item,sample_id,result,pass_fail,notes,root_cause\n"
        "pvt,drop_test,A-1,broken,fail,cracked,焊接开裂\n"
        "pvt,thermal,B-1,105C,pass,ok,\n"
    )
    p = tmp_path / "pvt.csv"
    p.write_text(lab, encoding="utf-8")
    imported = import_stage_report(p, "pvt")
    assert imported["stage"] == "pvt"
    assert imported["count"] == 2

    rc = extract_root_cause(imported["records"], "drop_test")
    assert rc["status"] == "identified"
    assert rc["root_cause"] == "焊接开裂"

    analysis = analyze_stage(imported["records"], "pvt")
    cas = propose_corrective_actions(analysis, "pvt", imported["records"])
    assert len(cas) == 1
    assert cas[0]["test_item"] == "drop_test"
    assert cas[0]["root_cause"]["status"] == "identified"

    # 无 root_cause 字段 -> not_verified（不虚构根因）
    rc2 = extract_root_cause([{"test_item": "drop_test", "pass_fail": "fail"}], "drop_test")
    assert rc2["status"] == "not_verified" and rc2["root_cause"] is None


def test_regression_verification():
    # 此前失败项，本轮通过 -> verified
    records = [
        {"test_item": "drop_test", "result": "ok", "pass_fail": "pass"},
        {"test_item": "drop_test", "result": "ok", "pass_fail": "pass"},
    ]
    out = verify_regression(records, {"drop_test": "fail"}, stage="pvt")
    assert out["verified"] == ["drop_test"]
    assert out["all_verified"] is True

    # 仍失败或无数据 -> not_verified
    out2 = verify_regression([], {"drop_test": "fail"}, stage="pvt")
    assert out2["verified"] == []
    assert out2["not_verified"] == ["drop_test"]
    assert out2["all_verified"] is False
    assert out2["has_evidence"] is False


# ---------------------------------------------------------------- 回写（HOLD）
def test_writeback_physical_missing_keeps_hold(tmp_path):
    db = _db(tmp_path)
    db.init_project("default", "p1", "proj", "goal")
    wb = PhysicalWriteback(db, "default")
    # 无物理数据 -> HOLD
    out = wb.write_stage("p1", "evt", None, gate="G2")
    assert out["hold"]
    assert out["gate_result"] is None
    fact = db.get_fact("default", "p1", out["hold"][0])
    assert fact["value"]["status"] == "HOLD"
    assert fact["value"]["passed_flag"] is False
    assert db.list_risks("default", "p1")  # 未完成风险已登记
    # 门禁保持 HOLD，而非通过
    gate = wb.write_release_gate("p1", "G3", physical_ok=False)
    assert gate["result"] == "HOLD"


def test_writeback_physical_present_writes_truth_and_gate(tmp_path):
    db = _db(tmp_path)
    db.init_project("default", "p1", "proj", "goal")
    wb = PhysicalWriteback(db, "default")
    records = [
        {"test_item": "drop", "result": "ok", "pass_fail": "pass"},
        {"test_item": "drop", "result": "ok", "pass_fail": "pass"},
    ]
    analysis = analyze_stage(records, "pvt")
    report = tmp_path / "pvt.csv"
    report.write_text("stage,test_item,pass_fail\npvt,drop,pass\n", encoding="utf-8")
    out = wb.write_stage("p1", "pvt", analysis, evidence_files=[report], gate="G3")
    assert out["gate_result"] == "PASS"
    assert out["written"]
    assert db.list_gates("default", "p1")[-1]["result"] == "PASS"
    assert db.list_evidence("default", "p1")  # 阶段报告已登记为证据


def test_import_lab_xlsx_direct_parse_or_external_blocked(tmp_path):
    """import_lab_xlsx 直接测试：openpyxl 可用时解析、不可用/坏文件时
    external_blocked（诚实，不伪造解析）。"""
    from aipd_os.supply_chain.lab import import_lab_xlsx
    p = tmp_path / "lab.xlsx"
    p.write_bytes(b"PK\x03\x04 fake xlsx")
    try:
        out = import_lab_xlsx(p, "dvt")
        assert out["format"] == "xlsx"
    except AdapterError as ei:
        assert ei.classification == "external_blocked"
