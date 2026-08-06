"""邮件发送/收件真实客户端（标准库 smtplib/imaplib）。

本包提供真实 SMTP/IMAP 协议能力，绝不伪造结果：
- :mod:`aipd_os.mail.client`：真实 SMTP 发送 / IMAP 收件，附带幂等发送、
  带回退的重试、显式人工审批、审计、附件大小/字符编码校验，并把收发元数据
  写入统一状态服务；
- :mod:`aipd_os.mail.gmail_oauth`：可选 Gmail OAuth 提供者客户端（无凭据时
  诚实标记为外部依赖，不计为已完成）。

未配置任何真实端点时，相关操作抛出 :class:`ExternalDependencyError`
（复用 :mod:`aipd_os.supply_chain.mail` 的同一契约），诚实标记外部依赖。
"""
from __future__ import annotations

from aipd_os.mail.client import (
    DEFAULT_TIMEOUT,
    ImapConfig,
    MailClient,
    MailConfig,
    ReceivedMail,
    SmtpConfig,
    download_attachment_from_bytes,
)
from aipd_os.mail.gmail_oauth import GmailOAuthClient
from aipd_os.supply_chain.mail import (
    ExternalDependencyError,
    MailAttachment,
    MailError,
    SendResult,
    retry_with_backoff,
)

__all__ = [
    "MailClient",
    "MailConfig",
    "SmtpConfig",
    "ImapConfig",
    "ReceivedMail",
    "GmailOAuthClient",
    "DEFAULT_TIMEOUT",
    "download_attachment_from_bytes",
    "MailError",
    "ExternalDependencyError",
    "MailAttachment",
    "SendResult",
    "retry_with_backoff",
]