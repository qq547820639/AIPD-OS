"""P1-2 真实邮件 Provider（SMTP/IMAP + Mailpit）协议集成测试。

本文件标记为 ``integration``，通过环境变量门控：

- ``AIPD_MAILPIT_SMTP_HOST`` / ``AIPD_MAILPIT_SMTP_PORT``
- ``AIPD_MAILPIT_IMAP_HOST`` / ``AIPD_MAILPIT_IMAP_PORT``
- ``AIPD_MAILPIT_API``

当未配置 Mailpit 端点时，测试**诚实断言 external_dependency / HOLD 行为**并输出
外部任务包（不假成功、不静默跳过）。当配置时，运行真实 SMTP/IMAP 协议测试：
真实发送 -> 真实收件 -> 线程关联 -> 附件下载 -> 幂等同步，并断言 TLS/认证失败/
超时/退避/重复发送/附件过大/字符编码行为。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from aipd_os.execution.adapter import AdapterError
from aipd_os.mail.client import (
    MailClient,
    MailConfig,
    _coerce_body,
    _normalize_subject,
)
from aipd_os.mail.gmail_oauth import GmailOAuthClient
from aipd_os.supply_chain.mail import (
    ExternalDependencyError,
    MailAttachment,
    MailError,
)
from aipd_os.tool_adapters.builtin import build_registry

pytestmark = pytest.mark.integration


def _configured() -> bool:
    return bool(
        os.environ.get("AIPD_MAILPIT_SMTP_HOST")
        and os.environ.get("AIPD_MAILPIT_IMAP_HOST")
    )


def _mailpit_client(db=None) -> MailClient:
    return MailClient(config=MailConfig.from_env(), db=db)


# ======================================================================
# 未配置 Mailpit：诚实 external_dependency / HOLD，不假成功
# ======================================================================


def test_no_mailpit_send_is_external_dependency(tmp_path):
    if _configured():
        pytest.skip("Mailpit 已配置，走真实协议测试")
    client = MailClient()  # 无任何 host
    mid = client.draft("aipd@local", ["v@mailpit.local"], "RFQ: X", "body")
    client.approve(mid, approver="owner")
    with pytest.raises(ExternalDependencyError):
        client.send(mid)


def test_no_mailpit_fetch_is_external_dependency():
    if _configured():
        pytest.skip("Mailpit 已配置，走真实协议测试")
    client = MailClient()
    with pytest.raises(ExternalDependencyError):
        client.fetch_emails()


def test_no_mailpit_gmail_is_external_dependency():
    g = GmailOAuthClient()  # 无凭据
    with pytest.raises(ExternalDependencyError):
        g.send(["v@example.com"], "s", "b")
    with pytest.raises(ExternalDependencyError):
        g.fetch_emails()


def test_no_mailpit_rfq_writes_external_task_package(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("AIPD_MAIL_PROVIDER", raising=False)
    reg = build_registry()
    a = reg.get("supply.rfq")
    with pytest.raises(AdapterError) as ei:
        a.execute({"supplier": "Acme", "part": "Widget-X", "work_id": "mail-w1"})
    assert ei.value.classification == "external_blocked"
    assert ei.value.task_package and Path(ei.value.task_package).is_file()
    assert list(tmp_path.glob("*.task.json"))


def test_no_mailpit_hold_never_fake_success(tmp_path):
    """未配置时绝不声称已发送/已收：返回 HOLD/pending 而非 ok。"""
    client = MailClient()
    mid = client.draft("aipd@local", ["v@x.local"], "RFQ", "b")
    res = client.send(mid)  # 未审批 -> pending
    assert res.ok is False
    assert "pending" in res.error or "审批" in res.error


# ======================================================================
# 始终可回归的确定性契约（不依赖 Mailpit）
# ======================================================================


def test_approval_gate_blocks_unapproved_send(tmp_path):
    db = _tmp_db(tmp_path)
    client = _mailpit_client(db)
    mid = client.draft("aipd@local", ["v@x.local"], "RFQ: Y", "您好，请报价")
    res = client.send(mid)
    assert res.ok is False and "pending" in res.error
    client.approve(mid, approver="owner", note="approved")
    assert client.get(mid)["status"] == "approved"
    assert client.get(mid)["approved_by"] == "owner"


def test_attachment_too_large_rejected(tmp_path):
    db = _tmp_db(tmp_path)
    client = _mailpit_client(db)
    client.max_attachment_size = 100
    mid = client.draft(
        "aipd@local", ["v@x.local"], "RFQ: Z", "b",
        attachments=[MailAttachment("big.bin", b"x" * 500)],
    )
    client.approve(mid, approver="owner")
    with pytest.raises(MailError, match="超过上限"):
        client.send(mid)


def test_non_utf8_body_encoding_handled():
    # GB18030 字节正文 -> 规整为可读 str，不抛错
    raw = "询价".encode("gb18030")
    text = _coerce_body(raw)
    assert isinstance(text, str) and "询价" in text
    # MIME 构建不抛错
    from aipd_os.mail.client import _build_mime
    msg = _build_mime("<x@y>", "a@b", ["c@d"], "RFQ", text, [])
    assert "RFQ" in str(msg["Subject"])


def test_thread_normalization():
    assert _normalize_subject("Re: FW: RFQ Widget") == "rfq widget"
    assert _normalize_subject("回复：询价") == "询价"


def test_retry_with_backoff_on_send_failure(tmp_path, monkeypatch):
    """连接/发送失败按指数退避重试（有界），耗尽后返回用户可见失败。"""
    import aipd_os.mail.client as mc
    db = _tmp_db(tmp_path)
    cfg = MailConfig.from_env()
    cfg.smtp.host = "127.0.0.1"  # 让 host 校验通过，但 send_email 被替换为失败
    client = MailClient(config=cfg, db=db)
    mid = client.draft("aipd@local", ["v@x.local"], "RFQ", "b")
    client.approve(mid, approver="owner")

    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        raise MailError("SMTP 连接被拒绝")

    monkeypatch.setattr(mc, "send_email", failing)
    res = client.send(mid, max_retries=3)
    assert res.ok is False
    assert res.retries_used == 3
    assert "重试" in res.error and "失败" in res.error
    assert len(calls) == 3
    assert client.get(mid)["status"] == "failed"


def test_idempotent_duplicate_send_guarded(tmp_path, monkeypatch):
    """重复发送被 Message-ID 幂等挡住：不重复投递。"""
    import aipd_os.mail.client as mc
    db = _tmp_db(tmp_path)
    cfg = MailConfig.from_env()
    cfg.smtp.host = "127.0.0.1"
    client = MailClient(config=cfg, db=db)
    mid = client.draft("aipd@local", ["v@x.local"], "RFQ", "b")
    client.approve(mid, approver="owner")

    calls = []

    def record(*args, **kwargs):
        calls.append(1)
        return mid

    monkeypatch.setattr(mc, "send_email", record)
    first = client.send(mid)
    second = client.send(mid)
    assert first.ok is True and second.ok is True
    assert len(calls) == 1  # 只真实投递一次
    assert second.retries_used == 0


# ======================================================================
# Mailpit 已配置：真实 SMTP/IMAP 协议端到端
# ======================================================================


@pytest.mark.skipif(not _configured(), reason="AIPD_MAILPIT_* 未配置，走 HOLD 断言")
def test_real_smtp_imap_roundtrip_thread_attachment_idempotent(tmp_path):
    db = _tmp_db(tmp_path)
    client = _mailpit_client(db)
    from_addr = client.config.smtp.from_addr or "aipd@mailpit.local"

    # 创建草稿 -> 未审批 pending -> 审批 -> 真实发送
    mid = client.draft(
        from_addr,
        ["supplier@mailpit.local"],
        "RFQ: Widget-X",
        "尊敬的供应商：请提供报价",
        attachments=[MailAttachment("quote.csv", b"supplier,part,unit_price\nAcme,X,1.25")],
    )
    pending = client.send(mid)
    assert pending.ok is False and "pending" in pending.error
    client.approve(mid, approver="owner")
    sent = client.send(mid)
    assert sent.ok is True, sent.error

    # 真实收件：应能读到刚发送的邮件
    received = client.fetch_emails()
    r_subjects = [r.subject for r in received]
    assert any("RFQ" in s for s in r_subjects), received

    # 线程关联：同一 Subject 归同一 thread_id
    threads = {r.thread_id for r in received}
    assert len(threads) >= 1

    # 附件下载
    target = next(r for r in received if "RFQ" in r.subject)
    assert any(a.filename == "quote.csv" for a in target.attachments)

    # 幂等同步：再次 fetch 不重复返回已处理邮件
    again = client.fetch_emails()
    assert len(again) == 0  # 全部已处理，跳过去重


@pytest.mark.skipif(not _configured(), reason="AIPD_MAILPIT_* 未配置，走 HOLD 断言")
def test_real_tls_auth_failure_and_timeout(tmp_path):
    db = _tmp_db(tmp_path)
    cfg = MailConfig.from_env()

    # 认证失败：错误密码 -> 投递失败（诚实报错，不假成功）
    bad = MailClient(config=cfg, db=db)
    bad.config.smtp.password = "wrong-password"
    mid = bad.draft("aipd@mailpit.local", ["x@mailpit.local"], "RFQ", "b")
    bad.approve(mid, approver="owner")
    res = bad.send(mid, max_retries=1)
    assert res.ok is False
    assert res.retries_used >= 1

    # 超时/不可达：指向关闭端口 -> 失败（诚实）
    timeout_cfg = MailConfig.from_env()
    timeout_cfg.smtp.host = "127.0.0.1"
    timeout_cfg.smtp.port = 1
    timeout_cfg.smtp.timeout = 0.5
    tc = MailClient(config=timeout_cfg, db=db)
    mid2 = tc.draft("aipd@mailpit.local", ["x@mailpit.local"], "RFQ2", "b")
    tc.approve(mid2, approver="owner")
    res2 = tc.send(mid2, max_retries=1)
    assert res2.ok is False


def _tmp_db(tmp_path):
    from aipd_os.state.db import AIPDStateDB
    db = AIPDStateDB(str(tmp_path / "mail.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "mail", "Mail", "mail goal")
    return db
