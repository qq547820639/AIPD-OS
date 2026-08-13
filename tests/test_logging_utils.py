"""logging_utils 重复装配修复测试（v5.9.2 Q-2）。

验证 ``setup_logging`` 按 name 判定配置状态：
- 同一 name 连续 setup 两次 handler 数不翻倍；
- 不同 name 各自独立配置（b 不被全局状态跳过）；
- ``force=True`` 重建 handler。
"""
from __future__ import annotations

import logging

import pytest

from aipd_os import logging_utils


@pytest.fixture(autouse=True)
def _reset_logging_state():
    """隔离全局配置状态，避免测试间互相污染。"""
    logging_utils._configured_loggers.clear()
    yield
    logging_utils._configured_loggers.clear()


def test_same_name_setup_twice_does_not_double_handlers(tmp_path):
    """同一 name 连续 setup 两次，handler 数量不翻倍。"""
    name = "test-logging-same-name"
    log_file = tmp_path / "a.log"
    logging_utils.setup_logging(name=name, log_file=log_file)
    first = list(logging.getLogger(name).handlers)
    logging_utils.setup_logging(name=name, log_file=log_file)
    second = list(logging.getLogger(name).handlers)
    # 1 个 stdout StreamHandler + 1 个 FileHandler
    assert len(first) == 2
    assert len(first) == len(second)
    assert name in logging_utils._configured_loggers


def test_different_names_configured_independently(tmp_path):
    """setup a 之后 b 不被全局状态跳过，b 正常装配。"""
    name_a = "test-logging-name-a"
    name_b = "test-logging-name-b"
    logging_utils.setup_logging(name=name_a, log_file=tmp_path / "a.log")
    assert name_b not in logging_utils._configured_loggers
    logging_utils.setup_logging(name=name_b)
    assert name_b in logging_utils._configured_loggers
    logger_b = logging.getLogger(name_b)
    # 仅 stdout StreamHandler（未传 log_file）
    assert len(logger_b.handlers) == 1
    assert logger_b.propagate is False


def test_force_rebuilds_handlers():
    """force=True 强制清空并重建 handler。"""
    name = "test-logging-force"
    logging_utils.setup_logging(name=name)
    logger = logging.getLogger(name)
    before = list(logger.handlers)
    logging_utils.setup_logging(name=name, force=True)
    after = list(logger.handlers)
    assert len(before) == len(after)
    # 重建后 handler 对象应为全新实例（非同一对象）
    assert all(h1 is not h2 for h1, h2 in zip(before, after))
