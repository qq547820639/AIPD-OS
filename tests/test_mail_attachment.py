"""P1-3 修复：邮件附件下载（会话内字节保留 + 跨会话诚实提示）。

不依赖 Mailpit，直接构造 :class:`MailClient` 的内存态，验证
:meth:`download_attachment` 的三类行为。
"""
from __future__ import annotations

import pytest

from aipd_os.mail.client import MailClient
from aipd_os.supply_chain.mail import MailAttachment, MailError


def _client_with_received(attachments, meta_attachments=None) -> MailClient:
    client = MailClient()
    client._received_ids["<m1@x>"] = {
        "message_id": "<m1@x>",
        "attachments": (
            meta_attachments if meta_attachments is not None
            else [a.filename for a in attachments]
        ),
        "_attachments": attachments,
    }
    return client


def test_download_attachment_within_session():
    """会话内 fetch 后附件字节保留在 _attachments，可下载。"""
    payload = b"supplier,part,unit_price\nAcme,X,1.25"
    att = MailAttachment("quote.csv", payload)
    client = _client_with_received([att])
    data = client.download_attachment("<m1@x>", "quote.csv")
    assert data == payload


def test_download_attachment_cross_session_hint():
    """跨会话（字节未持久化，仅存文件名）→ 抛明确「重新 fetch」提示。"""
    client = _client_with_received([], meta_attachments=["quote.csv"])
    with pytest.raises(MailError, match="重新 fetch"):
        client.download_attachment("<m1@x>", "quote.csv")


def test_download_attachment_missing():
    """附件名不存在 → 抛「不存在附件」。"""
    client = _client_with_received([MailAttachment("a.csv", b"x")])
    with pytest.raises(MailError, match="不存在附件"):
        client.download_attachment("<m1@x>", "nope.csv")


# ---------------------------------------------------------------- XOAUTH2 认证
def test_send_email_xoauth2_uses_sasl_auth(monkeypatch):
    """回归：auth_mechanism=XOAUTH2 必须走 SMTP.auth（SASL），而非明文 login。"""
    from aipd_os.mail import client as mail_client

    calls: dict[str, list] = {"auth": [], "login": []}

    class _FakeSMTP:
        def __init__(self, *a, **kw):
            pass

        def starttls(self):
            pass

        def auth(self, mechanism, cb):
            calls["auth"].append((mechanism, cb("")))
            return (235, b"ok")

        def login(self, user, password):
            calls["login"].append((user, password))

        def sendmail(self, *a, **kw):
            return {}

        def quit(self):
            pass

    monkeypatch.setattr(mail_client.smtplib, "SMTP", _FakeSMTP)
    token = "user=u\x01auth=Bearer t\x01\x01"
    mail_client.send_email(
        "smtp.gmail.com", 587, "u", token, "u@example.com", ["to@example.com"],
        "s", "b", auth_mechanism="XOAUTH2")
    assert calls["auth"] and calls["auth"][0][1] == token
    assert not calls["login"]


def test_fetch_emails_xoauth2_uses_imap_authenticate(monkeypatch):
    """回归：auth_mechanism=XOAUTH2 必须走 IMAP.authenticate（SASL），而非明文 login。"""
    from aipd_os.mail import client as mail_client

    calls: dict[str, list] = {"authenticate": [], "login": []}

    class _FakeIMAP:
        def __init__(self, *a, **kw):
            pass

        def authenticate(self, mechanism, cb):
            calls["authenticate"].append((mechanism, cb(b"")))
            return ("OK", [b"ok"])

        def login(self, user, password):
            calls["login"].append((user, password))

        def select(self, folder):
            return ("OK", [b"1"])

        def search(self, *a, **kw):
            return ("OK", [b""])

        def fetch(self, *a, **kw):
            return ("OK", [])

        def logout(self):
            pass

    monkeypatch.setattr(mail_client.imaplib, "IMAP4_SSL", _FakeIMAP)
    token = "user=u\x01auth=Bearer t\x01\x01"
    mail_client.fetch_emails(
        "imap.gmail.com", 993, "u", token, auth_mechanism="XOAUTH2")
    assert calls["authenticate"] and calls["authenticate"][0][1] == token.encode()
    assert not calls["login"]


def test_gmail_oauth_send_and_fetch_pass_xoauth2(monkeypatch):
    """GmailOAuthClient 必须把 XOAUTH2 响应串传给 client，并声明 auth_mechanism。"""
    import aipd_os.mail.gmail_oauth as gmail_module
    from aipd_os.mail.gmail_oauth import GmailOAuthClient, _xoauth2_auth

    seen: dict[str, dict] = {}

    def fake_send(host, port, user, password, from_addr, to_addrs,
                  subject, body, **kw):
        seen["send"] = {"password": password, "mechanism": kw.get("auth_mechanism")}
        return "m1"

    def fake_fetch(host, port, user, password, **kw):
        seen["fetch"] = {"password": password, "mechanism": kw.get("auth_mechanism")}
        return []

    # gmail_oauth 在 import 时已绑定函数引用，必须 patch 其模块命名空间
    monkeypatch.setattr(gmail_module, "send_email", fake_send)
    monkeypatch.setattr(gmail_module, "fetch_emails", fake_fetch)
    g = GmailOAuthClient(user="u@example.com", access_token="tok")
    g.send(["to@example.com"], "s", "b")
    g.fetch_emails()
    expected = _xoauth2_auth("u@example.com", "tok")
    assert seen["send"]["password"] == expected
    assert seen["send"]["mechanism"] == "XOAUTH2"
    assert seen["fetch"]["password"] == expected
    assert seen["fetch"]["mechanism"] == "XOAUTH2"
