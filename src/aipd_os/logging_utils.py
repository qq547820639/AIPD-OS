"""AIPD-OS 结构化日志模块。

提供 JSON-lines 格式的日志记录，输出到 stdout/stderr 以及可选的文件。
日志记录包含时间戳、级别、logger 名、消息与附加字段，便于机器解析与检索。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_JSON_FORMAT = "%(json)s"
_configured_loggers: set = set()


class JsonFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # 附加字段（通过 extra 传入）；先做敏感字段脱敏，避免完整凭据入日志
        extra = getattr(record, "aipd_fields", None)
        if extra and isinstance(extra, dict):
            from aipd_os.security.secrets import mask_secret_deep
            payload.update(mask_secret_deep(extra))
        return json.dumps(payload, ensure_ascii=False, default=str)


def _file_handler(path: Path) -> logging.Handler:
    fh = logging.FileHandler(str(path), encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    return fh


def _attach_handlers(logger: logging.Logger, log_file: Path | None) -> None:
    """给 logger 装配标准 handler（清空旧 handler 后重建）。

    装配内容：stdout StreamHandler(JsonFormatter) 与可选 FileHandler
    （自动 mkdir 父目录）；并关闭 propagate。
    """
    logger.handlers.clear()
    logger.propagate = False

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    logger.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.addHandler(_file_handler(log_file))


def setup_logging(
    name: str = "aipd",
    level: str = "INFO",
    log_file: Path | None = None,
    force: bool = False,
) -> None:
    """配置日志器。

    :param name: logger 名称
    :param level: 日志级别（"DEBUG"/"INFO"/"WARNING"/"ERROR"）
    :param log_file: 可选的文件输出路径
    :param force: 是否强制清空并重建 handler
    """
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    # 按 name 判定是否已装配：同一 name 已配置过 → no-op（不重复加 handler）；
    # 不同 name 各自独立装配（互不干扰）；force=True 强制重建。
    if force or name not in _configured_loggers:
        _attach_handlers(logger, log_file)
        _configured_loggers.add(name)


def get_logger(name: str = "aipd") -> logging.Logger:
    """返回一个 logger；若尚未配置则使用默认配置。"""
    if not _configured_loggers:
        setup_logging(name="aipd")
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    """以 INFO 级别记录一条带结构化字段的事件日志。"""
    logger.info(event, extra={"aipd_fields": fields})


__all__ = [
    "JsonFormatter",
    "setup_logging",
    "get_logger",
    "log_event",
]
