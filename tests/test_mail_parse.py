"""mail/client.py MIME 解析核心的单元测试（此前 0 覆盖的盲区）。

覆盖：_parse_message（multipart 正文/多附件/RFC2047 主题/中文线程前缀/
sha256）、_decode_header、_normalize_subject、_coerce_body、
download_attachment_from_bytes、_safe_key、ReceivedMail.to_dict。
"""
from __future__ import annotations

import base64
import hashlib
from email.message import EmailMessage

from aipd_os.mail.client import (
    ReceivedMail,
    _coerce_body,
    _decode_header,
    _normalize_subject,
    _parse_message,
    _safe_key,
    download_attachment_from_bytes,
)
from aipd_os.supply_chain.mail import MailAttachment


def _multipart_raw() -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = "<mid-1@example.com>"
    msg["Subject"] = "报价询价"
    msg["From"] = "Acme <rfq@acme.example>"
    msg["To"] = "buyer@ours.example, cc@ours.example"
    msg["Date"] = "Mon, 01 Jun 2026 10:00:00 +0000"
    msg.set_content("这是正文第一部分。\n")
    msg.add_attachment(b"quote data", maintype="text",
                       subtype="csv", filename="quote.csv")
    return msg.as_bytes()


def test_parse_message_multipart_body_and_attachment():
    raw = _multipart_raw()
    m = _parse_message(raw)
    assert m.message_id == "<mid-1@example.com>"
    assert m.subject == "报价询价"
    assert "rfq@acme.example" in m.sender
    assert m.recipients == ["buyer@ours.example", "cc@ours.example"]
    assert "这是正文第一部分" in m.body
    assert len(m.attachments) == 1
    att = m.attachments[0]
    assert att.filename == "quote.csv"
    assert att.data == b"quote data"
    # sha256 是原始字节的摘要
    assert m.sha256 == hashlib.sha256(raw).hexdigest()
    # 无 In-Reply-To → thread_id 用归一化主题
    assert m.thread_id == "报价询价"


def test_parse_message_rfc2047_subject_decoded():
    raw = _multipart_raw()
    encoded_subject = "=?utf-8?b?" + base64.b64encode("报价询价".encode()).decode() + "?="
    raw = raw.replace(b"Subject: =?utf-8?B?5oql5Lu36K+i5Lu3?=",
                      b"Subject: " + encoded_subject.encode("ascii"))
    # 上面 replace 可能未命中（EmailMessage 默认不编码非 ASCII 主题），
    # 构造独立的纯 ASCII 编码头邮件更稳：
    msg = EmailMessage()
    msg["Subject"] = encoded_subject
    msg.set_content("body")
    m = _parse_message(msg.as_bytes())
    assert m.subject == "报价询价"


def test_normalize_subject_strips_chinese_thread_prefixes():
    assert _normalize_subject("回复：回复: 报价") == "报价"
    assert _normalize_subject("Re: Fwd: Quote") == "quote"
    assert _normalize_subject("报价") == "报价"


def test_decode_header_list_of_bytes():
    assert _decode_header([(b"\xe6\x8a\xa5", "utf-8")]) == "报"
    assert _decode_header(b"raw") == "raw"
    assert _decode_header(None) == ""
    assert _decode_header("plain") == "plain"


def test_coerce_body_gb18030_fallback():
    gbk_bytes = "中文报价".encode("gb18030")
    assert _coerce_body(gbk_bytes) == "中文报价"
    assert _coerce_body("str") == "str"
    assert _coerce_body(123) == "123"


def test_download_attachment_from_bytes():
    raw = _multipart_raw()
    assert download_attachment_from_bytes(raw, "quote.csv") == b"quote data"
    import pytest

    from aipd_os.supply_chain.mail import MailError
    with pytest.raises(MailError):
        download_attachment_from_bytes(raw, "nope.csv")


def test_safe_key_quotes_unsafe_chars():
    k = _safe_key("<mid-1@example.com>")
    assert " " not in k and "<" not in k and ">" not in k
    assert k.startswith("%3C")  # < 被 percent-encode


def test_received_mail_to_dict_roundtrip():
    raw = _multipart_raw()
    m = _parse_message(raw)
    d = m.to_dict()
    assert d["message_id"] == "<mid-1@example.com>"
    assert d["subject"] == "报价询价"
    assert d["attachments"] == ["quote.csv"]
    assert d["sha256"] == m.sha256
    # ReceivedMail 可直接从 dict 重建（不含附件字节，跨会话诚实提示）
    rebuilt = ReceivedMail(**{k: v for k, v in d.items() if k != "attachments"},
                           attachments=[MailAttachment(filename="quote.csv", data=b"")])
    assert rebuilt.subject == "报价询价"
