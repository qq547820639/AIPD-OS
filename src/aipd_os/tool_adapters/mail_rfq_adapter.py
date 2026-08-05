"""RFQ 邮件适配器（'supply.rfq'）。

未配置真实邮件后端（环境变量 AIPD_MAIL_PROVIDER 未设置）时，诚实写出
外部任务包并抛出 ``external_blocked``，绝不声称邮件已发送。配置了后端时
仍生成确定性的 RFQ 草稿并注明 provider。
"""

from __future__ import annotations

from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.tool_adapters._common import env, meta, token_meta


class MailRfqAdapter(ToolAdapter):
    provider = "local"
    version = "1.1"

    def capability_id(self) -> str:
        return "supply.rfq"

    def discover(self) -> Dict[str, Any]:
        return meta(self.capability_id(), "RFQ Draft Composer", self.provider, self.version)

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        if not input.get("supplier"):
            errors.append("'supplier' 必填")
        return errors

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        supplier = input.get("supplier")
        if not supplier:
            raise external_blocked_error(
                "supply.rfq",
                "缺少 supplier，无法生成并发送 RFQ；请补充供应商信息后重试。",
                work_id=input.get("work_id"),
            )

        provider = env("AIPD_MAIL_PROVIDER")
        if not provider:
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
        result = {
            "rfq_draft": draft,
            "provider": provider,
            "sent": False,  # 仅生成草稿，不声称已发送
            "_meta": token_meta(subject + body),
        }
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["MailRfqAdapter"]
