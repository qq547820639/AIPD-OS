"""加密往返与错误密钥拒绝。"""
from __future__ import annotations

import pytest

from aipd_os.state.crypto import encrypt_secret, decrypt_secret


def test_roundtrip():
    ct = encrypt_secret("supplier quote: 1234", "keyA")
    assert decrypt_secret(ct, "keyA") == "supplier quote: 1234"


def test_roundtrip_first_200_chars():
    text = "x" * 500
    assert decrypt_secret(encrypt_secret(text, "k"), "k") == text


def test_wrong_key_fails():
    ct = encrypt_secret("secret data", "keyA")
    with pytest.raises(Exception):
        decrypt_secret(ct, "keyB")


def test_tampered_fails():
    ct = encrypt_secret("data", "keyA")
    with pytest.raises(Exception):
        decrypt_secret(ct[:-2] + ("==" if not ct.endswith("==") else "@@"), "keyA")
