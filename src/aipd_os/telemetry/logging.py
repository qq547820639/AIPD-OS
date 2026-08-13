"""结构化日志（JSON 行，含 trace_id）。

在仓库既有 ``aipd_os.logging_utils`` 基础上，提供带 ``trace_id`` 的 JSON-lines
日志：每次调用可通过 :func:`new_trace_id` 生成并贯穿相关日志记录，便于检索
与追踪单次请求/任务。

可选匿名遥测开关：默认关闭（``AIPD_TELEMETRY_ENABLED=0`` / 未设置时不发送任何数据）。
：class:`TelemetryLogger` 只在开关开启时附带匿名遥测字段。
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from aipd_os.security.secrets import mask_secret_deep

# 匿名遥测开关（默认关闭；仅当显式设为 1/true 才开启）
TELEMETRY_ENV = "AIPD_TELEMETRY_ENABLED"


def telemetry_enabled() -> bool:
    """匿名遥测是否开启（默认关闭）。"""
    return os.environ.get(TELEMETRY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def new_trace_id() -> str:
    """生成一条新的 trace id。"""
    return "tr-" + uuid.uuid4().hex[:16]


class JsonTraceFormatter(logging.Formatter):
    """输出单行 JSON，含 trace_id 与附加字段（敏感字段自动脱敏）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = trace_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "aipd_fields", None)
        if extra and isinstance(extra, dict):
            payload.update(mask_secret_deep(extra))
        return json.dumps(payload, ensure_ascii=False, default=str)


class TelemetryLogger:
    """带 trace_id 与可选匿名遥测字段的结构化 logger。"""

    def __init__(self, name: str = "aipd.telemetry", level: str = "INFO") -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level.upper())
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonTraceFormatter())
            self._logger.addHandler(handler)
            self._logger.propagate = False

    def info(self, event: str, trace_id: str | None = None, **fields: object) -> None:
        self._emit(logging.INFO, event, trace_id, fields)

    def warning(self, event: str, trace_id: str | None = None, **fields: object) -> None:
        self._emit(logging.WARNING, event, trace_id, fields)

    def error(self, event: str, trace_id: str | None = None, **fields: object) -> None:
        self._emit(logging.ERROR, event, trace_id, fields)

    def _emit(self, level: int, event: str, trace_id: str | None,
              fields: dict[str, object]) -> None:
        extra: dict[str, Any] = {"aipd_fields": dict(fields)}
        if trace_id:
            extra["trace_id"] = trace_id
        if telemetry_enabled():
            # 匿名遥测：仅附带非敏感基础信息（版本来源等），不含凭据
            extra["aipd_fields"].setdefault("anon_telemetry", True)
        self._logger.log(level, event, extra=extra)


def get_telemetry_logger(name: str = "aipd.telemetry",
                         level: str = "INFO") -> TelemetryLogger:
    """返回一个 TelemetryLogger 实例。"""
    return TelemetryLogger(name, level)


__all__ = [
    "TELEMETRY_ENV",
    "telemetry_enabled",
    "new_trace_id",
    "JsonTraceFormatter",
    "TelemetryLogger",
    "get_telemetry_logger",
]
