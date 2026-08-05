"""AIPD-OS 结构化日志模块。

提供 JSON-lines 格式的日志记录，输出到 stdout/stderr 以及可选的文件。
日志记录包含时间戳、级别、logger 名、消息与附加字段，便于机器解析与检索。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
        # 附加字段（通过 extra 传入）
        extra = getattr(record, "aipd_fields", None)
        if extra and isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _file_handler(path: Path) -> logging.Handler:
    fh = logging.FileHandler(str(path), encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    return fh


def setup_logging(
    name: str = "aipd",
    level: str = "INFO",
    log_file: Optional[Path] = None,
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

    if force or not _configured_loggers:
        logger.handlers.clear()
        logger.propagate = False

        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(JsonFormatter())
        logger.addHandler(stream)

        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            logger.addHandler(_file_handler(log_file))

        logger.addFilter(_AttachFieldsFilter())
        _configured_loggers.add(name)

    # 避免重复初始化时重复添加 handler
    else:
        logger.handlers.clear()
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(JsonFormatter())
        logger.addHandler(stream)
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            logger.addHandler(_file_handler(log_file))
        logger.addFilter(_AttachFieldsFilter())


class _AttachFieldsFilter(logging.Filter):
    """将 LogRecord 上的 aipd_fields 属性剥离，避免标准 Formatter 报错。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return True


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