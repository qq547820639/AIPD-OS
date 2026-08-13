"""可选 Gmail OAuth 提供者客户端（外部依赖门控）。

本模块提供 Gmail OAuth2 的 SMTP/IMAP 发送与收件能力，但**绝不**在没有真实凭据
时把本地邮件替身计为 Gmail 已完成。当缺少有效凭据（access_token / refresh_token
或 client secret）时，所有操作明确触发 :class:`ExternalDependencyError`，诚实
标记为外部依赖，并写出外部任务包（可复用
:func:`aipd_os.execution.adapter.write_external_task`）。

仅依赖标准库；不引入 google-auth 等第三方依赖。OAuth 令牌以 ``XOAUTH2`` 认证
方式传给 ``smtplib.SMTP.auth`` 与 ``imaplib.IMAP4.authenticate``。
"""
from __future__ import annotations

from typing import Any

from aipd_os.mail.client import fetch_emails, send_email
from aipd_os.supply_chain.mail import (
    ExternalDependencyError,
    MailAttachment,
    MailError,
)

SCOPES = "https://mail.google.com/"


def _xoauth2_auth(user: str, access_token: str) -> str:
    """构造 ``XOAUTH2`` 认证字符串。"""
    return "user=" + user + "\x01" + "auth=Bearer " + access_token + "\x01\x01"


class GmailOAuthClient:
    """Gmail OAuth2 提供者客户端。

    无凭据时所有操作为外部依赖，绝不伪造已完成。
    """

    provider = "gmail_oauth"
    external_dependency = True

    def __init__(
        self,
        user: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        smtp_port: int = 587,
        imap_port: int = 993,
    ) -> None:
        self.user = user
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.smtp_port = smtp_port
        self.imap_port = imap_port

    def _require_credentials(self) -> str:
        if not self.user or not self.access_token:
            raise ExternalDependencyError(
                "未提供 Gmail OAuth 凭据（user/access_token），无法以 Gmail 身份"
                "发送或收件；请配置凭据，否则本地邮件替身不得计为 Gmail 已完成。"
            )
        return self.user

    def send(
        self,
        to_addrs: list[str],
        subject: str,
        body: str,
        from_addr: str | None = None,
        attachments: list[MailAttachment] | None = None,
    ) -> dict[str, Any]:
        """以 Gmail OAuth2 身份真实发送。无凭据时抛外部依赖错误。

        认证走真实 ``XOAUTH2`` SASL 机制（``SMTP.auth("XOAUTH2", ...)``），
        而不是把 access_token 当明文密码 ``login``（两者都失败且后者是
        误导性的明文 AUTH）。
        """
        self._require_credentials()
        sender = from_addr or self.user or ""
        message_id = send_email(
            "smtp.gmail.com",
            self.smtp_port,
            self.user,
            self._xoauth2_token(),
            sender,
            [a for a in to_addrs],
            subject,
            body,
            attachments=attachments,
            auth_mechanism="XOAUTH2",
        )
        # 说明：真实投递已由 send_email 完成；此处仅记录结果元数据。
        return {"provider": self.provider, "message_id": message_id, "to": list(to_addrs)}

    def fetch_emails(self, folder: str = "INBOX") -> Any:
        """以 Gmail OAuth2 身份真实收件。无凭据时抛外部依赖错误。

        认证走真实 ``XOAUTH2`` SASL 机制（``IMAP4.authenticate("XOAUTH2", ...)``），
        而不是把 XOAUTH2 串当明文密码 ``login``（后者必然认证失败）。
        """
        self._require_credentials()
        return fetch_emails(
            "imap.gmail.com",
            self.imap_port,
            self.user or "",
            self._xoauth2_token(),
            auth_mechanism="XOAUTH2",
        )

    def _xoauth2_token(self) -> str:
        return _xoauth2_auth(self.user or "", self.access_token or "")


__all__ = [
    "GmailOAuthClient",
    "ExternalDependencyError",
    "MailError",
    "SCOPES",
    "_xoauth2_auth",
]
