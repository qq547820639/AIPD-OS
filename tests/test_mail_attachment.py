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
