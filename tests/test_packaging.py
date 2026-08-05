"""打包与基础模块的冒烟测试。"""

from __future__ import annotations

import aipd_os
from aipd_os import __version__
from aipd_os.config import Settings, get_settings, reload_settings
from aipd_os.logging_utils import get_logger, log_event


def test_version() -> None:
    assert __version__ == "5.2.0"
    assert aipd_os.__version__ == "5.2.0"


def test_config_imports_and_defaults() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.mode in {"local", "server"}
    assert settings.retention_days > 0


def test_config_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIPD_LOG_LEVEL", "DEBUG")
    settings = reload_settings()
    assert settings.log_level == "DEBUG"


def test_logging_event() -> None:
    logger = get_logger("aipd.tests")
    log_event(logger, "test_event", foo="bar", n=1)
    assert logger.name == "aipd.tests"