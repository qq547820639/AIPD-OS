"""文档生成适配器（'doc.generate'）。

本地确定性生成结构化 Markdown/JSON 文档，无需外部凭据。
"""

from __future__ import annotations

from typing import Any

from aipd_os.execution.adapter import ToolAdapter, output_dir
from aipd_os.tool_adapters._common import meta, token_meta


class DocumentGenAdapter(ToolAdapter):
    provider = "local"
    version = "1.0"

    def capability_id(self) -> str:
        return "doc.generate"

    def discover(self) -> dict[str, Any]:
        return meta(self.capability_id(), "Document Generator", self.provider, self.version)

    def validate_input(self, input: dict[str, Any]) -> list:
        errors = []
        if not input.get("title"):
            errors.append("'title' 必填")
        return errors

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        title = input.get("title", "Untitled")
        sections = input.get("sections", [])
        lines = [f"# {title}", ""]
        for sec in sections:
            heading = sec.get("heading", "Section") if isinstance(sec, dict) else str(sec)
            body = sec.get("body", "") if isinstance(sec, dict) else ""
            lines.append(f"## {heading}")
            lines.append(body)
            lines.append("")
        markdown = "\n".join(lines).rstrip() + "\n"

        out_dir = output_dir()
        safe = title.replace(" ", "_").replace("/", "_") or "document"
        path = out_dir / f"{safe}.md"
        path.write_text(markdown, encoding="utf-8")

        result = {
            "title": title,
            "format": "markdown",
            "path": str(path),
            "markdown": markdown,
            "sections": sections,
            "_meta": token_meta(markdown),
        }
        return result

    def normalize(self, result: Any) -> dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict) and result.get("path"):
            return [result["path"]]
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        if isinstance(result, dict) and result.get("path"):
            return [result["path"]]
        return []


__all__ = ["DocumentGenAdapter"]
