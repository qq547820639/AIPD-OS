"""可插拔邮件连接器与本地确定性邮件服务。

本模块只实现真实、确定性的契约与本地测试替身，不伪造真实发送结果：

- :class:`MailConnector` 是发送/读取的统一抽象契约；
- :class:`SmtpConnector`（发送）与 :class:`ImapConnector`（读取）是真实外部
  能力的连接器契约，均标记 ``external_dependency=True``；未配置真实服务器时
  它们会抛出 :class:`ExternalDependencyError`，绝不声称邮件已发送；
- :class:`LocalMailService` 是确定性的本地测试替身，支持 RFQ 草稿、显式审批、
  发送、Message-ID / 线程追踪、收件箱读取、供应商回信关联、附件下载、
  幂等发送（Message-ID 去重）、带回退的重试与对用户的失败提示。
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

DOMAIN = "local.aipd-os.dev"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MailError(Exception):
    """邮件相关错误基类。"""


class ExternalDependencyError(MailError):
    """真实邮件后端不可用（外部依赖）。

    捕获真实 SMTP/IMAP 尚未配置或无法连接的情况，诚实标记为外部依赖。
    """

    external_dependency = True

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class MailAttachment:
    """一封邮件附带的二进制附件。"""

    filename: str
    data: bytes
    content_type: str = "application/octet-stream"


@dataclass
class MailMessage:
    """一封邮件/消息的规范化表示。"""

    message_id: str
    sender: str
    recipients: List[str]
    subject: str
    body: str
    thread_id: str = ""
    in_reply_to: str = ""
    attachments: List[MailAttachment] = field(default_factory=list)
    status: str = "draft"  # draft / approved / sent / failed
    direction: str = "outbox"  # outbox / inbox
    created_at: str = field(default_factory=_now)
    sent_at: str = ""
    retries: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipients": list(self.recipients),
            "subject": self.subject,
            "body": self.body,
            "thread_id": self.thread_id,
            "in_reply_to": self.in_reply_to,
            "attachments": [a.filename for a in self.attachments],
            "status": self.status,
            "direction": self.direction,
            "created_at": self.created_at,
            "sent_at": self.sent_at,
            "retries": self.retries,
            "error": self.error,
        }


@dataclass
class SendResult:
    """一次发送尝试的结果。"""

    ok: bool
    message_id: str
    external_dependency: bool = False
    error: str = ""
    retries_used: int = 0


class MailConnector(ABC):
    """统一邮件连接器契约。

    真实后端（SMTP/IMAP）与本地测试替身都实现同一组方法，便于在运行时替换。
    """

    external_dependency: bool = True

    @abstractmethod
    def send(self, message: MailMessage, **kwargs: Any) -> SendResult:
        """发送一封已就绪的邮件，返回 :class:`SendResult`。"""

    def read_inbox(self, **kwargs: Any) -> List[MailMessage]:
        """读取收件箱；真实 IMAP 未配置时抛外部依赖错误。"""
        raise ExternalDependencyError("真实 IMAP 未配置，无法读取收件箱（外部依赖）")

    def download_attachment(self, message_id: str, filename: str, **kwargs: Any) -> bytes:
        """下载指定邮件的附件；真实 IMAP 未配置时抛外部依赖错误。"""
        raise ExternalDependencyError("真实 IMAP 未配置，无法下载附件（外部依赖）")


class SmtpConnector(MailConnector):
    """真实 SMTP 发送连接器（外部依赖）。

    需要真实 SMTP 服务器配置（host/端口/凭据）。未配置 host 时，:meth:`send`
    抛出 :class:`ExternalDependencyError`，绝不伪造"已发送"。
    """

    external_dependency = True

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 25,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send(self, message: MailMessage, **kwargs: Any) -> SendResult:
        if not self.host:
            raise ExternalDependencyError(
                "未配置真实 SMTP 服务器（host 为空），无法发送邮件；"
                "请配置 SMTP 或改用 LocalMailService 进行本地确定性验证。"
            )
        # 真实 SMTP 发送属于外部依赖，未接入真实凭据的本地机器上不执行。
        raise ExternalDependencyError(
            f"真实 SMTP 发送为外部依赖（host={self.host}:{self.port}），"
            "本地机器未验证真实投递；请勿将本地结果视为已送达。"
        )


class ImapConnector(MailConnector):
    """真实 IMAP 读取连接器（外部依赖）。

    需要真实 IMAP 服务器配置。未配置 host 时，读取/下载附件均抛出
    :class:`ExternalDependencyError`。
    """

    external_dependency = True

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 993,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password

    def send(self, message: MailMessage, **kwargs: Any) -> SendResult:
        # IMAP 连接器只负责读取，不负责发送。
        raise ExternalDependencyError("IMAP 连接器不执行发送；发送请使用 SMTP 或 LocalMailService。")

    def read_inbox(self, **kwargs: Any) -> List[MailMessage]:
        if not self.host:
            raise ExternalDependencyError(
                "未配置真实 IMAP 服务器（host 为空），无法读取收件箱；"
                "请配置 IMAP 或改用 LocalMailService。"
            )
        raise ExternalDependencyError(
            f"真实 IMAP 读取为外部依赖（host={self.host}:{self.port}），"
            "本地机器未连接邮件服务器，无法读取真实收件箱。"
        )

    def download_attachment(self, message_id: str, filename: str, **kwargs: Any) -> bytes:
        raise ExternalDependencyError("真实 IMAP 附件下载为外部依赖，本地未验证。")


def retry_with_backoff(
    fn: Callable[[int], Any],
    attempts: int = 3,
    base_delay: float = 0.1,
    on_error: Optional[Callable[[int, Exception], None]] = None,
) -> Any:
    """带指数退避的重试执行器。

    :param fn: 接收 ``attempt``（从 1 开始）并执行；抛异常则重试。
    :param attempts: 最大尝试次数（含首次）。
    :param base_delay: 首次退避间隔（秒），按 ``base_delay * (2 ** (attempt-1))`` 递增。
    :param on_error: 每次失败回调 ``(attempt, exception)``。
    :raises MailError: 所有尝试均失败时抛出最后一次异常。
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(attempt)
        except MailError as exc:
            last_error = exc
            if on_error:
                on_error(attempt, exc)
            if attempt == attempts:
                break
            time.sleep(base_delay * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error


class LocalMailService(MailConnector):
    """确定性本地邮件服务（测试替身）。

    在同一进程内模拟：RFQ 草稿 -> 显式审批 -> 发送（幂等）-> 收件箱读取 ->
    供应商回信关联 -> 附件下载，并支持带回退的重试与对用户的失败提示。

    所有行为都是确定性的，不触及真实网络；``external_dependency=False``。
    """

    external_dependency = False

    def __init__(self, local_address: str = f"rfq@{DOMAIN}") -> None:
        self._local_address = local_address
        self._messages: List[MailMessage] = []
        self._by_id: Dict[str, MailMessage] = {}
        self._sent_message_ids: set = set()
        self._seq = 0

    # ------------------------------------------------------------------ 内建
    def _new_message_id(self) -> str:
        self._seq += 1
        return f"AIPD-{self._seq:04d}-{uuid.uuid4().hex[:6]}@{DOMAIN}"

    def _register(self, message: MailMessage) -> MailMessage:
        self._messages.append(message)
        self._by_id[message.message_id] = message
        return message

    def get(self, message_id: str) -> MailMessage:
        if message_id not in self._by_id:
            raise KeyError(f"未知 message_id: {message_id!r}")
        return self._by_id[message_id]

    def all_messages(self) -> List[MailMessage]:
        return list(self._messages)

    # ---------------------------------------------------------- RFQ 草稿
    def create_rfq_draft(
        self,
        supplier: str,
        part: str,
        quantity: int = 1,
        due_date: str = "待定",
        subject: Optional[str] = None,
        sender: Optional[str] = None,
    ) -> MailMessage:
        """创建一封 RFQ 询价草稿（默认状态 draft，未发送）。"""
        message_id = self._new_message_id()
        subject = subject or f"RFQ: {part} for {supplier}"
        body = (
            f"尊敬的 {supplier}：\n\n"
            f"我方拟就 {part}（数量 {quantity}，交付 {due_date}）发起询价（RFQ）。\n"
            f"请提供报价、交期与最小起订量。\n\n此致敬礼\nAIPD-OS 采购"
        )
        msg = MailMessage(
            message_id=message_id,
            sender=sender or self._local_address,
            recipients=[supplier],
            subject=subject,
            body=body,
            thread_id=message_id,  # 草稿即线程根
            status="draft",
            direction="outbox",
        )
        return self._register(msg)

    def approve(self, message_id: str) -> MailMessage:
        """显式审批草稿：仅 approved 状态才允许后续发送。"""
        msg = self.get(message_id)
        if msg.status == "sent":
            raise ValueError(f"邮件 {message_id} 已发送，无法重复审批")
        msg.status = "approved"
        return msg

    # ---------------------------------------------------------- 发送（幂等+重试）
    def send(
        self,
        message: Any,
        max_retries: int = 3,
        base_delay: float = 0.0,
        should_fail: Optional[Callable[[int], bool]] = None,
    ) -> SendResult:
        """发送一封已审批的邮件。

        兼容两种调用方式：传入 ``message_id: str`` 或直接传入
        :class:`MailMessage`。

        - 幂等：若该 message_id 已发送，直接返回既有成功结果，不重复发送；
        - 未审批（draft）的邮件拒绝发送并给出明确失败提示；
        - 带回退的重试：``should_fail(attempt)`` 返回真时计为重试失败，
          直至耗尽 ``max_retries`` 次后标记 failed 并返回用户可见的失败信息。
        """
        message_id = message.message_id if isinstance(message, MailMessage) else message
        msg = self.get(message_id)

        # 幂等：Message-ID 去重
        if message_id in self._sent_message_ids:
            return SendResult(ok=True, message_id=message_id, retries_used=0)

        if msg.status not in ("approved", "sent"):
            return SendResult(
                ok=False,
                message_id=message_id,
                error=f"邮件 {message_id} 尚未审批（状态: {msg.status}），禁止发送；请先审批后再试。",
            )

        last_error = ""
        retries_used = 0
        for attempt in range(1, max_retries + 1):
            try:
                if should_fail and should_fail(attempt):
                    raise MailError(f"第 {attempt} 次发送失败（注入故障）")
                msg.status = "sent"
                msg.sent_at = _now()
                msg.retries = attempt - 1
                self._sent_message_ids.add(message_id)
                return SendResult(ok=True, message_id=message_id, retries_used=attempt - 1)
            except MailError as exc:
                last_error = str(exc)
                retries_used = attempt
                msg.retries = attempt
                msg.error = last_error
                if attempt < max_retries:
                    time.sleep(base_delay * (2 ** (attempt - 1)))

        msg.status = "failed"
        failure = (
            f"邮件 {message_id}（主题：{msg.subject}，收件人：{'、'.join(msg.recipients)}）"
            f"发送失败：已重试 {retries_used} 次（最后原因：{last_error}）。"
            f"请检查收件人/连接后重试。"
        )
        msg.error = failure
        return SendResult(ok=False, message_id=message_id, error=failure, retries_used=retries_used)

    # ---------------------------------------------------------- 收件箱
    def read_inbox(self, **kwargs: Any) -> List[MailMessage]:
        """读取收件箱（本地模拟：direction=inbox 的消息）。"""
        return [m for m in self._messages if m.direction == "inbox"]

    def receive(
        self,
        sender: str,
        recipients: Optional[List[str]] = None,
        subject: str = "",
        body: str = "",
        in_reply_to: Optional[str] = None,
        attachments: Optional[List[MailAttachment]] = None,
    ) -> MailMessage:
        """模拟一封供应商/外部回信进入收件箱。

        通过 ``in_reply_to`` 关联到既有线程：若可解析到既有消息，则复用其
        ``thread_id``，否则新建线程。
        """
        message_id = self._new_message_id()
        thread_id = message_id
        if in_reply_to:
            ref = self._by_id.get(in_reply_to)
            if ref:
                thread_id = ref.thread_id or ref.message_id
        msg = MailMessage(
            message_id=message_id,
            sender=sender,
            recipients=recipients or [self._local_address],
            subject=subject,
            body=body,
            thread_id=thread_id,
            in_reply_to=in_reply_to or "",
            attachments=list(attachments or []),
            status="received",
            direction="inbox",
        )
        return self._register(msg)

    def download_attachment(self, message_id: str, filename: str, **kwargs: Any) -> bytes:
        """下载指定收件箱邮件的附件字节；附件不存在则抛 :class:`MailError`。"""
        msg = self.get(message_id)
        for att in msg.attachments:
            if att.filename == filename:
                return att.data
        raise MailError(
            f"邮件 {message_id} 中不存在附件 {filename!r}；可用附件："
            f"{', '.join(a.filename for a in msg.attachments) or '无'}。"
        )

    def messages_for_thread(self, thread_id: str) -> List[MailMessage]:
        return [m for m in self._messages if m.thread_id == thread_id]


__all__ = [
    "_now",
    "MailError",
    "ExternalDependencyError",
    "MailAttachment",
    "MailMessage",
    "SendResult",
    "MailConnector",
    "SmtpConnector",
    "ImapConnector",
    "retry_with_backoff",
    "LocalMailService",
]
