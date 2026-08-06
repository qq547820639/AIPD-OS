"""凭据存储与日志脱敏测试。

AIPD_ACK_SECRET: 本文件包含故意伪造的密钥样例（sk-.../AKIA/ghp_ 等），
仅用于断言脱敏与检测逻辑，非真实凭据；发布 secret 扫描据此视为已承认。
"""
from __future__ import annotations

import json
import logging
import os

import pytest

from aipd_os.logging_utils import JsonFormatter
from aipd_os.security.secrets import (
    SecretStore,
    is_sensitive_var,
    mask_secret,
    mask_secret_deep,
)


def test_mask_secret_keeps_ends_masks_middle():
    assert mask_secret("sk-abcdef1234567890") == "s" + "*" * 17 + "0"
    assert mask_secret("short123") == "s" + "*" * 6 + "3"
    assert "abcdef1234567890" not in mask_secret("sk-abcdef1234567890")


def test_mask_secret_edges():
    assert mask_secret("") == ""
    assert mask_secret(None) == ""
    assert mask_secret("a") == "*"
    assert mask_secret("ab") == "a*"
    assert mask_secret("abc") == "a**"
    assert mask_secret("abcd") == "a***"


def test_is_sensitive_var_detects_suffixes_and_exact():
    assert is_sensitive_var("AIPD_MAIL_PASSWORD") is True
    assert is_sensitive_var("FOO_API_KEY") is True
    assert is_sensitive_var("AIPD_DATA_ENCRYPTION_KEY") is True
    assert is_sensitive_var("MY_TOKEN") is True
    assert is_sensitive_var("AIPD_DB_DIR") is False
    assert is_sensitive_var("log_level") is False


def test_secret_store_registers_without_reading(monkeypatch):
    monkeypatch.setenv("AIPD_MAIL_PASSWORD", "super-secret-pass")
    store = SecretStore()
    store.register("AIPD_MAIL_PASSWORD", "smtp password")

    assert store.is_registered("AIPD_MAIL_PASSWORD")
    assert store.read("AIPD_MAIL_PASSWORD") == "super-secret-pass"
    assert store.masked("AIPD_MAIL_PASSWORD") == "s" + "*" * 15 + "s"
    assert "super-secret-pass" not in store.masked("AIPD_MAIL_PASSWORD")

    # 明文从未写入任何文件；status 只含脱敏值
    for entry in store.status():
        assert "super-secret-pass" not in str(entry)
    samples = store.masked_samples()
    assert "super-secret-pass" not in str(samples)


def test_secret_store_unregistered_env(monkeypatch):
    monkeypatch.delenv("AIPD_MAIL_PASSWORD", raising=False)
    store = SecretStore()
    store.register("AIPD_MAIL_PASSWORD")
    assert store.exposed("AIPD_MAIL_PASSWORD") is False
    assert store.masked("AIPD_MAIL_PASSWORD") is None
    assert store.status()[0]["set"] is False


def test_mask_secret_deep_strips_sensitive_fields():
    data = {
        "api_key": "sk-abcdef1234567890",
        "AIPD_MAIL_PASSWORD": "plainvalue",
        "name": "alice",
        "extra": {"SECRET": "hidden"},
    }
    out = mask_secret_deep(data)
    assert "abcdef1234567890" not in str(out)
    assert "plainvalue" not in str(out)
    assert "hidden" not in str(out)
    assert out["name"] == "alice"
    # 自定义敏感名集合
    out2 = mask_secret_deep({"token": "abc", "note": "x"}, secret_names=["token"])
    assert out2["token"] == "a**"
    assert out2["note"] == "x"


def test_structured_log_masks_credentials():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="call", args=(), exc_info=None)
    record.aipd_fields = {"api_key": "sk-longsecretvalue-123", "message": "hi"}
    out = json.loads(formatter.format(record))
    assert "sk-longsecretvalue-123" not in out["api_key"]
    assert out["api_key"] == "s" + "*" * 20 + "3"
    assert out["message"] == "hi"