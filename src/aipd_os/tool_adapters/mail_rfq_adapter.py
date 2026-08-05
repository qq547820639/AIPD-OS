"""RFQ 邮件草稿适配器（'supply.rfq'）。

本地确定性生成 RFQ（询价）邮件草稿。
"""

from __future__ import annotations

from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.tool_adapters._common import meta, token_meta


class MailRfqAdapter(ToolAdapter):
    provider = "local"
    version = "1.0"

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
        result = {"rfq_draft": draft, "_meta": token_meta(subject + body)}
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["MailRfqAdapter"]
