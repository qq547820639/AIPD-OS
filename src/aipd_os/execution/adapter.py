"""工具适配器抽象基类。

所有具体适配器继承 :class:`ToolAdapter`，实现统一的发现、校验、执行、
失败分类、产物与证据管理接口。外部能力不可用时，适配器必须诚实地面向
``external_blocked`` 分类并写出外部任务包，而不是伪造结果。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_dir() -> Path:
    """返回稳定的输出目录（环境变量 AIPD_OUTPUT_DIR 优先，否则临时目录）。"""
    d = os.environ.get("AIPD_OUTPUT_DIR")
    path = Path(d) if d else Path(tempfile.gettempdir()) / "aipd_os_output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_external_task(
    capability_id: str,
    instructions: str,
    work_id: str | None = None,
    output_dir_path: Path | None = None,
) -> str:
    """写出一份“外部任务包” JSON 文件，供人工或外部工具执行。

    这是诚实性契约：当外部能力不可用时，不伪造结果，而是产出可追踪的
    外部任务包，并标记为 ``external_blocked``。
    """
    base = output_dir_path or output_dir()
    base.mkdir(parents=True, exist_ok=True)
    safe = capability_id.replace(".", "_")
    fname = f"{safe}_{work_id or 'wa'}_{int(time.time() * 1000)}.task.json"
    path = base / fname
    payload = {
        "schema": "aipd_external_task/1.0",
        "capability_id": capability_id,
        "work_id": work_id,
        "kind": "human_or_external_tool",
        "instructions": instructions,
        "created_at": now(),
        "status": "unassigned",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


class AdapterError(Exception):
    """适配器执行失败时抛出。

    :param classification: 错误分类，取值见 ``ERROR_CLASSIFICATIONS``。
    :param task_package: 可选，外部任务包文件路径（外部能力不可用时）。
    """

    def __init__(
        self,
        message: str,
        classification: str = "tool_error",
        task_package: str | None = None,
    ) -> None:
        self.message = message
        self.classification = classification
        self.task_package = task_package
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


def external_blocked_error(
    capability_id: str,
    instructions: str,
    work_id: str | None = None,
) -> AdapterError:
    """构造 external_blocked 错误并写出外部任务包。"""
    pkg = write_external_task(capability_id, instructions, work_id=work_id)
    return AdapterError(
        f"capability {capability_id} 需要外部工具/人工，已写出外部任务包: {pkg}",
        classification="external_blocked",
        task_package=pkg,
    )


class ToolAdapter(ABC):
    """工具适配器抽象基类。"""

    # ---- 元信息 ----
    @abstractmethod
    def capability_id(self) -> str:
        """返回本适配器对应的能力标识，如 'research.search_papers'。"""

    def discover(self) -> dict[str, Any]:
        """返回能力元信息。"""
        return {
            "id": self.capability_id(),
            "name": self.capability_id(),
            "provider": getattr(self, "provider", ""),
            "version": getattr(self, "version", "1.0"),
            "maturity_ceiling": getattr(self, "maturity_ceiling", None),
            "available": getattr(self, "available", True),
        }

    # ---- 输入校验 ----
    def validate_input(self, input: dict[str, Any]) -> list[str]:
        """返回输入校验错误列表；为空表示输入合法。"""
        return []

    # ---- 执行 ----
    @abstractmethod
    def execute(self, input: dict[str, Any]) -> Any:
        """执行工具并返回原始结果。失败时抛出 :class:`AdapterError`。"""

    # ---- 结果处理 ----
    def normalize(self, result: Any) -> dict[str, Any]:
        """将原始结果规范化为结构化 dict。"""
        return result if isinstance(result, dict) else {"result": result}

    def collect_artifacts(self, result: Any) -> list[str]:
        """从结果中收集产物文件路径。"""
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list[str]:
        """持久化证据，返回证据引用列表。默认返回空。"""
        return []

    # ---- 失败分类 ----
    def classify_failure(self, exc: Exception) -> str:
        """将异常映射为错误分类字符串。"""
        if isinstance(exc, AdapterError):
            return exc.classification
        return "tool_error"

    # ---- 重试与降级 ----
    def retry_limits(self) -> int:
        """返回最大尝试次数（含首次）。"""
        return 1

    def fallback_chain(self) -> list[str]:
        """返回降级链（按顺序尝试的能力标识）。"""
        return []

    # ---- 副作用与重试策略 ----
    def side_effect_mode(self) -> str:
        """声明本适配器的副作用模式，决定失败后是否允许自动重试。

        - ``PURE``：无副作用（幂等），失败可安全重试（默认）；
        - ``IDEMPOTENT``：有副作用但自带幂等（重复执行不产生重复效果）；
        - ``EXTERNAL_SIDE_EFFECT``：对外部系统产生副作用（如发送邮件、
          登记外部报价/供应商文件），自动重试可能重复执行 → 禁止重试；
        - ``NON_RETRYABLE``：不可重试。

        取值见 :data:`aipd_os.execution.models.SIDE_EFFECT_MODES`。
        """
        return "PURE"


__all__ = [
    "now",
    "output_dir",
    "write_external_task",
    "AdapterError",
    "external_blocked_error",
    "ToolAdapter",
]
