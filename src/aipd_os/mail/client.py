"""真实 SMTP/IMAP 邮件客户端（标准库 smtplib/imaplib）。

本模块提供真实邮件发送/收件能力，绝不伪造结果：

- :func:`send_email`：真实建立 SMTP 连接并投递。host 已配置时**不得**直接抛
  :class:`ExternalDependencyError`，必须真正连接并发送；连接/认证/投递失败时
  抛出底层异常（非外部依赖）。
- :func:`fetch_emails`：真实连接 IMAP（``imaplib.IMAP4_SSL``）读取收件箱，
  实现线程关联（In-Reply-To / Subject）、附件解析与按 Message-ID 幂等去重。
- :class:`MailClient`：在其上叠加幂等发送、带回退的重试、显式人工审批、审计、
  附件大小/字符编码校验，并把收发元数据写入统一状态服务
  （:class:`aipd_os.state.db.AIPDStateDB` 事实 + 审计日志）。

未配置任何真实端点时，相关操作抛出 :class:`ExternalDependencyError`，诚实标记
为外部依赖，绝不声称邮件已发送/已收。
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import smtplib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any, Dict, List, Optional

from aipd_os.supply_chain.mail import (
    ExternalDependencyError,
    MailAttachment,
    MailError,
    SendResult,
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024  # 5 MiB
DEFAULT_MAX_RETRIES = 3

# 常见非 UTF-8 回退编码（用于解析历史/境外邮件体）
_FALLBACK_ENCODINGS = ("utf-8", "gb18030", "big5", "iso-8859-1", "latin-1")

_THREAD_PREFIXES = ("re:", "fw:", "fwd:", "回复：", "回复:", "转发：", "转发:", "答复：", "答复:")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_message_id(from_addr: str) -> str:
    domain = from_addr.rsplit("@", 1)[-1] if "@" in from_addr else "local.aipd-os.dev"
    return f"<{uuid.uuid4().hex}@{domain}>"


def _coerce_body(body: Any) -> str:
    """把正文规整为字符串，处理非 UTF-8 字节内容。"""
    if isinstance(body, bytes):
        for enc in _FALLBACK_ENCODINGS:
            try:
                return body.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return body.decode("utf-8", errors="replace")
    if not isinstance(body, str):
        return str(body)
    return body


def _build_mime(
    message_id: str,
    from_addr: str,
    to_addrs: List[str],
    subject: str,
    body: str,
    attachments: Optional[List[MailAttachment]],
) -> EmailMessage:
    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    # 正文统一 UTF-8；EmailMessage.set_content 会自动选择编码并把非 ASCII 正文
    # 编码为 UTF-8，避免 ASCII 回退导致乱码。
    msg.set_content(body)
    for att in attachments or []:
        maintype, _, subtype = att.content_type.partition("/")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            att.data,
            maintype=maintype,
            subtype=subtype,
            filename=att.filename,
        )
    return msg


def send_email(
    host: str,
    port: int,
    user: Optional[str],
    password: Optional[str],
    from_addr: str,
    to_addrs: List[str],
    subject: str,
    body: str,
    attachments: Optional[List[MailAttachment]] = None,
    use_tls: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """真实发送一封邮件，返回分配的 ``Message-ID``。

    host 已配置时**必须**真正建立连接并发送；连接/认证/投递失败时抛出底层
    ``smtplib`` 异常（不吞异常、不降级为 external_dependency）。仅当 host 为空
    时才抛 :class:`ExternalDependencyError`。
    """
    if not host:
        raise ExternalDependencyError("未配置 SMTP host，无法发送邮件（外部依赖）。")
    if not to_addrs:
        raise MailError("缺少收件人（to_addrs 为空），无法发送。")

    message_id = _new_message_id(from_addr)
    msg = _build_mime(message_id, from_addr, to_addrs, subject, body, attachments)

    if port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
        if use_tls:
            server.starttls()
    try:
        if user and password:
            server.login(user, password)
        refused = server.sendmail(from_addr, to_addrs, msg.as_string())
        if refused:
            raise MailError(f"SMTP 部分收件人被拒绝: {refused}")
    finally:
        try:
            server.quit()
        except Exception:
            server.close()
    return message_id


# --------------------------------------------------------------------------- IMAP


@dataclass
class ReceivedMail:
    """一封从真实 IMAP 读取的收件。"""

    message_id: str
    sender: str
    recipients: List[str]
    subject: str
    body: str
    thread_id: str
    in_reply_to: str
    date: str
    attachments: List[MailAttachment] = field(default_factory=list)
    sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipients": list(self.recipients),
            "subject": self.subject,
            "body": self.body,
            "thread_id": self.thread_id,
            "in_reply_to": self.in_reply_to,
            "date": self.date,
            "attachments": [a.filename for a in self.attachments],
            "sha256": self.sha256,
        }


def _decode_header(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for part, enc in value:
            if isinstance(part, bytes):
                parts.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return "".join(parts)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _normalize_subject(subject: str) -> str:
    s = subject.strip().lower()
    while True:
        prev = s
        for p in _THREAD_PREFIXES:
            if s.startswith(p):
                s = s[len(p):].strip()
        if s == prev:
            break
    return s


def _parse_part(part: email.message.Message) -> Optional[bytes]:
    """提取一个 multipart 部分的原始字节（处理传输编码）。"""
    payload = part.get_payload(decode=True)
    if payload is None:
        return None
    return payload


def _parse_message(raw: bytes) -> ReceivedMail:
    msg = email.message_from_bytes(raw)
    message_id = _decode_header(msg.get("Message-ID")).strip() or _new_message_id("imap@local")
    in_reply_to = _decode_header(msg.get("In-Reply-To")).strip()
    subject = _decode_header(msg.get("Subject"))
    sender = _decode_header(msg.get("From"))
    to_header = _decode_header(msg.get("To"))
    recipients = [r.strip() for r in to_header.split(",") if r.strip()]
    date = _decode_header(msg.get("Date"))

    attachments: List[MailAttachment] = []
    body_parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            fname = part.get_filename()
            if fname:
                fname = _decode_header(fname)
                data = _parse_part(part)
                if data is not None:
                    attachments.append(MailAttachment(filename=fname, data=data, content_type=ctype))
            elif ctype in ("text/plain", "text/html"):
                data = _parse_part(part)
                if data is not None:
                    body_parts.append(_coerce_body(data))
    else:
        data = _parse_part(msg)
        if data is not None:
            body_parts.append(_coerce_body(data))

    body = "\n".join(body_parts)
    digest = hashlib.sha256()
    digest.update(raw)
    return ReceivedMail(
        message_id=message_id,
        sender=sender,
        recipients=recipients,
        subject=subject,
        body=body,
        thread_id=in_reply_to or _normalize_subject(subject),
        in_reply_to=in_reply_to,
        date=date,
        attachments=attachments,
        sha256=digest.hexdigest(),
    )


def fetch_emails(
    host: str,
    port: int,
    user: str,
    password: str,
    folder: str = "INBOX",
    since: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> List[ReceivedMail]:
    """真实连接 IMAP 读取收件箱，返回解析后的邮件列表。

    host 已配置时**必须**真正连接并读取；连接/认证失败时抛出底层
    ``imaplib`` 异常。仅当 host 为空时才抛 :class:`ExternalDependencyError`。
    """
    if not host:
        raise ExternalDependencyError("未配置 IMAP host，无法读取收件箱（外部依赖）。")
    conn = imaplib.IMAP4_SSL(host, port, timeout=timeout)
    try:
        conn.login(user, password)
        status, _ = conn.select(folder)
        if status != "OK":
            raise MailError(f"IMAP 无法选择文件夹 {folder!r}: {status}")

        if since:
            typ, data = conn.search(None, f'SINCE "{since}"')
        else:
            typ, data = conn.search(None, "ALL")
        if typ != "OK":
            return []

        results: List[ReceivedMail] = []
        for num in data[0].split():
            typ2, msgdata = conn.fetch(num, "(BODY.PEEK[])")
            if typ2 != "OK" or not msgdata or msgdata[0] is None:
                continue
            raw = msgdata[0][1]
            results.append(_parse_message(raw))
        return results
    finally:
        try:
            conn.logout()
        except Exception:
            conn.shutdown()


def download_attachment_from_bytes(raw: bytes, filename: str) -> bytes:
    """从一封原始邮件的字节中按文件名下载附件。"""
    msg = email.message_from_bytes(raw)
    if msg.is_multipart():
        for part in msg.walk():
            fname = part.get_filename()
            if fname and _decode_header(fname) == filename:
                data = _parse_part(part)
                if data is not None:
                    return data
    raise MailError(f"邮件中不存在附件 {filename!r}")


# ---------------------------------------------------------------------- 配置


@dataclass
class SmtpConfig:
    host: Optional[str] = None
    port: int = 587
    user: Optional[str] = None
    password: Optional[str] = None
    from_addr: str = "aipd@local.aipd-os.dev"
    use_tls: bool = True
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class ImapConfig:
    host: Optional[str] = None
    port: int = 993
    user: Optional[str] = None
    password: Optional[str] = None
    folder: str = "INBOX"
    timeout: float = DEFAULT_TIMEOUT


class MailConfig:
    """SMTP + IMAP 端点配置，支持从环境变量装配。

    优先读取通用 ``AIPD_SMTP_*`` / ``AIPD_IMAP_*``；集成测试可读取
    ``AIPD_MAILPIT_SMTP_HOST/PORT``、``AIPD_MAILPIT_IMAP_HOST/PORT``。
    """

    def __init__(
        self,
        smtp: Optional[SmtpConfig] = None,
        imap: Optional[ImapConfig] = None,
    ) -> None:
        self.smtp = smtp or SmtpConfig()
        self.imap = imap or ImapConfig()

    @classmethod
    def from_env(cls) -> MailConfig:
        import os

        smtp_host = os.environ.get("AIPD_SMTP_HOST") or os.environ.get("AIPD_MAILPIT_SMTP_HOST")
        imap_host = os.environ.get("AIPD_IMAP_HOST") or os.environ.get("AIPD_MAILPIT_IMAP_HOST")
        smtp = SmtpConfig(
            host=smtp_host,
            port=int(os.environ.get("AIPD_SMTP_PORT") or os.environ.get("AIPD_MAILPIT_SMTP_PORT") or 587),
            user=os.environ.get("AIPD_SMTP_USER"),
            password=os.environ.get("AIPD_SMTP_PASSWORD"),
            from_addr=os.environ.get("AIPD_SMTP_FROM", "aipd@local.aipd-os.dev"),
            use_tls=str(os.environ.get("AIPD_SMTP_TLS", "true")).lower() in ("1", "true", "yes"),
        )
        imap = ImapConfig(
            host=imap_host,
            port=int(os.environ.get("AIPD_IMAP_PORT") or os.environ.get("AIPD_MAILPIT_IMAP_PORT") or 993),
            user=os.environ.get("AIPD_IMAP_USER"),
            password=os.environ.get("AIPD_IMAP_PASSWORD"),
        )
        return cls(smtp=smtp, imap=imap)


# ------------------------------------------------------------------ MailClient


class MailClient:
    """在真实传输之上叠加幂等/审批/审计/校验的统一邮件客户端。

    当未提供 ``db``（统一状态服务）时，幂等与审批记录保存在内存中；提供
    :class:`aipd_os.state.db.AIPDStateDB` 时，收发元数据以事实写入，审批写入
    审计日志，实现跨会话可追溯。
    """

    def __init__(
        self,
        config: Optional[MailConfig] = None,
        db: Any = None,
        tenant_id: str = "default",
        project_id: str = "mail",
        max_attachment_size: int = DEFAULT_MAX_ATTACHMENT_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.config = config or MailConfig()
        self.db = db
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.max_attachment_size = max_attachment_size
        self.max_retries = max_retries
        # 内存记录 message_id -> meta；db 存在时同时持久化以保证幂等去重
        self._records: Dict[str, Dict[str, Any]] = {}
        self._sent_ids: Dict[str, bool] = {}
        self._received_ids: Dict[str, Any] = {}

    # ------------------------------------------------------------ 状态持久化
    def _persist(self, direction: str, message_id: str, meta: Dict[str, Any]) -> None:
        self._records[message_id] = meta
        if direction == "inbox":
            self._received_ids[message_id] = meta
        if self.db is not None:
            # 附件字节不落库（仅元数据含附件名/hash），避免把二进制写入 facts
            db_copy = {k: v for k, v in meta.items() if not k.startswith("_")}
            self.db.add_fact(
                self.tenant_id,
                self.project_id,
                key=f"mail.{direction}.{_safe_key(message_id)}",
                value=db_copy,
                status="V",
                source="mail_client",
                version="1",
            )

    def _is_sent(self, message_id: str) -> bool:
        if message_id in self._sent_ids:
            return True
        if self.db is not None:
            prefix = f"mail.outbox.{_safe_key(message_id)}"
            for f in self.db.list_facts(self.tenant_id, self.project_id):
                if str(f.get("key", "")).startswith(prefix) and f.get("value", {}).get("status") == "sent":
                    return True
            return False
        return False

    def _already_received(self, message_id: str) -> bool:
        if message_id in self._received_ids:
            return True
        if self.db is not None:
            prefix = f"mail.inbox.{_safe_key(message_id)}"
            return any(
                str(f.get("key", "")).startswith(prefix)
                for f in self.db.list_facts(self.tenant_id, self.project_id)
            )
        return False

    def _audit(self, actor: str, action: str, after: Any) -> None:
        if self.db is not None:
            self.db.add_audit(
                actor=actor,
                action=action,
                project_id=self.project_id,
                tenant_id=self.tenant_id,
                after=after,
            )

    # ---------------------------------------------------------------- 草稿/审批
    def draft(
        self,
        from_addr: str,
        to_addrs: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[MailAttachment]] = None,
    ) -> str:
        """创建一封待审批草稿，返回 ``Message-ID``。状态为 draft。"""
        message_id = _new_message_id(from_addr)
        meta = {
            "message_id": message_id,
            "direction": "outbox",
            "status": "draft",
            "from": from_addr,
            "to": list(to_addrs),
            "subject": subject,
            "body": body,
            "attachments": [a.filename for a in (attachments or [])],
            "created_at": _now(),
        }
        if attachments:
            meta["_attachments"] = list(attachments)
        # 草稿仅记录在内存（未发送不落库，避免与后续 sent 事实冲突）；
        # 批准由审计日志记录，真实发送时再写入状态服务。
        self._records[message_id] = meta
        return message_id

    def approve(self, message_id: str, approver: str = "owner", note: str = "") -> Dict[str, Any]:
        """显式审批草稿：记录谁批准、何时批准（审计），状态置为 approved。"""
        meta = self._records.get(message_id)
        if meta is None:
            raise KeyError(f"未知 message_id: {message_id!r}")
        if meta.get("status") == "sent":
            raise MailError(f"邮件 {message_id} 已发送，无法重复审批。")
        meta["status"] = "approved"
        meta["approved_by"] = approver
        meta["approved_at"] = _now()
        meta["approval_note"] = note
        self._audit(approver, "mail.approve", {"message_id": message_id, "at": meta["approved_at"]})
        return meta

    def send(
        self,
        message_id: str,
        approver: Optional[str] = None,
        approval_note: str = "",
        max_retries: Optional[int] = None,
    ) -> SendResult:
        """发送一封已审批的邮件。

        - 未审批（draft）时**不发送**，返回 ``pending`` 供 owner 审批；
        - 幂等：Message-ID 已发送过则直接返回成功，不重复发送；
        - 附件过大直接拒绝并报错；
        - 连接/投递失败按指数退避重试（有界），耗尽后标记失败并向用户给出
          可见的失败提示。
        """
        meta = self._records.get(message_id)
        if meta is None:
            raise KeyError(f"未知 message_id: {message_id!r}")

        # 幂等：Message-ID 去重
        if self._is_sent(message_id):
            return SendResult(ok=True, message_id=message_id, retries_used=0)

        # 显式人工审批门控
        if meta.get("status") != "approved":
            return SendResult(
                ok=False,
                message_id=message_id,
                error=(
                    f"邮件 {message_id} 尚未批准（status={meta.get('status')}），"
                    f"等待 owner 审批后方可发送；当前状态: pending。"
                ),
            )

        # 附件大小校验
        for att in meta.get("_attachments", []):
            if len(att.data) > self.max_attachment_size:
                raise MailError(
                    f"附件 {att.filename} 大小 {len(att.data)} 字节超过上限 "
                    f"{self.max_attachment_size} 字节，已拒绝发送。"
                )

        cfg = self.config.smtp
        if not cfg.host:
            raise ExternalDependencyError(
                "未配置真实 SMTP host，无法发送（外部依赖）；请配置 SMTP 或改用 Mailpit。"
            )

        retries_used = 0
        last_error = ""
        limit = max_retries if max_retries is not None else self.max_retries
        for attempt in range(1, limit + 1):
            try:
                delivered_id = send_email(
                    cfg.host,
                    cfg.port,
                    cfg.user,
                    cfg.password,
                    meta.get("from", cfg.from_addr),
                    meta.get("to", []),
                    meta.get("subject", ""),
                    meta.get("body", ""),
                    attachments=meta.get("_attachments"),
                    use_tls=cfg.use_tls,
                    timeout=cfg.timeout,
                )
                meta["status"] = "sent"
                meta["sent_at"] = _now()
                meta["message_id"] = delivered_id
                self._sent_ids[message_id] = True
                self._persist("outbox", message_id, meta)
                self._audit(
                    approver or meta.get("approved_by", "owner"),
                    "mail.sent",
                    {"message_id": message_id, "subject": meta.get("subject")},
                )
                return SendResult(ok=True, message_id=message_id, retries_used=attempt - 1)
            except (MailError, smtplib.SMTPException, OSError) as exc:
                last_error = str(exc)
                retries_used = attempt
                meta["error"] = last_error
                if attempt < limit:
                    import time

                    time.sleep(0.05 * (2 ** (attempt - 1)))

        meta["status"] = "failed"
        failure = (
            f"邮件 {message_id}（主题：{meta.get('subject')}，收件人：{'、'.join(meta.get('to', []))}）"
            f"发送失败：已重试 {retries_used} 次（最后原因：{last_error}）。"
            f"请检查收件人/连接后重试。"
        )
        return SendResult(ok=False, message_id=message_id, error=failure, retries_used=retries_used)

    # ---------------------------------------------------------------- 收件
    def fetch_emails(
        self,
        folder: Optional[str] = None,
        since: Optional[str] = None,
    ) -> List[ReceivedMail]:
        """真实 IMAP 收件：线程关联 + 附件下载 + 幂等同步（Message-ID 去重）。

        已处理过的 Message-ID 不重复返回/重复写状态服务。
        """
        cfg = self.config.imap
        if not cfg.host:
            raise ExternalDependencyError(
                "未配置真实 IMAP host，无法读取收件箱（外部依赖）；请配置 IMAP 或改用 Mailpit。"
            )
        raw_list = fetch_emails(
            cfg.host,
            cfg.port,
            cfg.user or "",
            cfg.password or "",
            folder=folder or cfg.folder,
            since=since,
            timeout=cfg.timeout,
        )

        # 线程关联：维护 subject -> thread_id 映射，复用已解析的线索
        subject_map: Dict[str, str] = {}

        def resolve_thread(mail: ReceivedMail) -> str:
            if mail.in_reply_to:
                return mail.in_reply_to
            key = _normalize_subject(mail.subject)
            if key in subject_map:
                return subject_map[key]
            subject_map[key] = mail.message_id
            return mail.message_id

        out: List[ReceivedMail] = []
        for mail in raw_list:
            if self._already_received(mail.message_id):
                continue  # 幂等：已处理的不重复处理
            mail.thread_id = resolve_thread(mail)
            meta = mail.to_dict()
            meta["direction"] = "inbox"
            meta["status"] = "received"
            self._persist("inbox", mail.message_id, meta)
            self._audit("mail-client", "mail.received", {"message_id": mail.message_id})
            out.append(mail)
        return out

    def download_attachment(self, message_id: str, filename: str) -> bytes:
        """下载某封已收邮件的附件字节；不存在则抛 :class:`MailError`。"""
        meta = self._received_ids.get(message_id)
        if meta is None and self.db is not None:
            prefix = f"mail.inbox.{_safe_key(message_id)}"
            for f in self.db.list_facts(self.tenant_id, self.project_id):
                if str(f.get("key", "")).startswith(prefix):
                    meta = f.get("value")
                    break
        if meta is None:
            raise MailError(f"未知收件 message_id: {message_id!r}")
        for att in meta.get("_attachments", []):
            if att.filename == filename:
                return att.data
        raise MailError(f"邮件 {message_id} 中不存在附件 {filename!r}")

    # ---------------------------------------------------------------- 查询
    def get(self, message_id: str) -> Dict[str, Any]:
        if message_id in self._records:
            return self._records[message_id]
        if self.db is not None:
            for f in self.db.list_facts(self.tenant_id, self.project_id):
                if (_safe_key(f.get("value", {}).get("message_id", ""))
                        == _safe_key(message_id)) or _safe_key(str(f.get("key", ""))).endswith(_safe_key(message_id)):
                    return f.get("value", {})
        raise KeyError(f"未知 message_id: {message_id!r}")

    def all_records(self) -> List[Dict[str, Any]]:
        return list(self._records.values())


def _safe_key(message_id: str) -> str:
    """把 Message-ID 规整为可作事实 key 的安全串。"""
    import urllib.parse

    return urllib.parse.quote(message_id, safe="").replace(".", "_").replace("-", "_")


__all__ = [
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_ATTACHMENT_SIZE",
    "DEFAULT_MAX_RETRIES",
    "SmtpConfig",
    "ImapConfig",
    "MailConfig",
    "ReceivedMail",
    "MailClient",
    "send_email",
    "fetch_emails",
    "download_attachment_from_bytes",
    "ExternalDependencyError",
    "MailError",
    "MailAttachment",
    "SendResult",
]
