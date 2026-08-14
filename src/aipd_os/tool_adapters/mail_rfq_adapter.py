"""RFQ 邮件适配器（'supply.rfq'）。

未配置真实 SMTP（``AIPD_SMTP_HOST`` / ``AIPD_MAILPIT_SMTP_HOST``）时，诚实写出
外部任务包并抛出 ``external_blocked``，绝不声称邮件已发送。配置了真实 SMTP 时
经 ``aipd_os.mail.client.send_email`` 真实发送，``sent`` 仅在真实投递成功后为
True（发送失败上抛 external_blocked，不伪装已发送）。
"""

from __future__ import annotations

from typing import Any

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.tool_adapters._common import env, meta, token_meta


class MailRfqAdapter(ToolAdapter):
    provider = "local"
    version = "1.1"

    def capability_id(self) -> str:
        return "supply.rfq"

    def discover(self) -> dict[str, Any]:
        return meta(self.capability_id(), "RFQ Draft Composer", self.provider, self.version)

    def validate_input(self, input: dict[str, Any]) -> list:
        errors = []
        if not input.get("supplier"):
            errors.append("'supplier' 必填")
        return errors

    def side_effect_mode(self) -> str:
        """RFQ 涉及外部邮件/询价副作用：自动重试可能重复对外发送 → 禁止重试。"""
        return "EXTERNAL_SIDE_EFFECT"

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        supplier = input.get("supplier")
        if not supplier:
            raise external_blocked_error(
                "supply.rfq",
                "缺少 supplier，无法生成并发送 RFQ；请补充供应商信息后重试。",
                work_id=input.get("work_id"),
            )

        # 真实 SMTP 判定与实现一致（此前读 AIPD_MAIL_PROVIDER——该变量无任何
        # 实现读取，配置了也不发送；现在读实现真实读取的 AIPD_SMTP_HOST 等）。
        smtp_host = env("AIPD_SMTP_HOST") or env("AIPD_MAILPIT_SMTP_HOST")
        if not smtp_host:
            part = input.get("part", "指定零件")
            qty = input.get("quantity", 1)
            due = input.get("due_date", "待定")
            instructions = (
                f"请向供应商 {supplier} 就 {part}（数量 {qty}，交付 {due}）"
                f"发送询价（RFQ），索取报价、交期与最小起订量。"
            )
            raise external_blocked_error(
                "supply.rfq",
                instructions,
                work_id=input.get("work_id"),
            )

        part = input.get("part", "指定零件")
        qty = input.get("quantity", 1)
        due = input.get("due_date", "待定")
        subject = f"RFQ: {part} for {supplier}"
        body = (
            f"尊敬的 {supplier}：\n\n"
            f"我方拟就 {part}（数量 {qty}，交付 {due}）发起询价（RFQ）。\n"
            f"请提供报价、交期与最小起订量。\n\n此致敬礼\nAIPD-OS 采购"
        )
        draft = {"subject": subject, "body": body, "to": supplier, "part": part}
        # 真实发送：成功才 sent=True；任何失败诚实上抛 external_blocked
        try:
            from aipd_os.mail.client import send_email  # noqa: PLC0415
            user = env("AIPD_SMTP_USER")
            password = env("AIPD_SMTP_PASSWORD")
            port = int(env("AIPD_SMTP_PORT") or env("AIPD_MAILPIT_SMTP_PORT") or 587)
            message_id = send_email(
                smtp_host, port, user or "", password or "",
                env("AIPD_SMTP_FROM") or "aipd@local.aipd-os.dev",
                [supplier], subject, body)
        except Exception as exc:  # noqa: BLE001 - 发送失败诚实上报，绝不伪装已发送
            raise external_blocked_error(
                "supply.rfq",
                f"RFQ 真实发送失败（{exc}）；未声称已发送，请人工补发或重试。",
                work_id=input.get("work_id"),
            ) from exc
        result = {
            "rfq_draft": draft,
            "provider": "smtp",
            "sent": True,
            "message_id": message_id,
            "_meta": token_meta(subject + body),
        }
        return result

    def normalize(self, result: Any) -> dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["MailRfqAdapter"]
