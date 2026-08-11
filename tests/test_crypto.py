"""加密往返、错误密钥拒绝、以及 XOR 回退的 fail-closed 门控（P0-5）。"""
from __future__ import annotations

import pytest

from aipd_os.state.crypto import decrypt_secret, encrypt_secret


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


# ---------------------------------------------------------------- P0-5 fail-closed
def test_encrypt_fails_closed_without_cryptography(monkeypatch):
    """cryptography 不可用且未设置 AIPD_INSECURE_DEV_MODE → 加密必须失败。"""
    import aipd_os.state.crypto as crypto
    monkeypatch.setattr(crypto, "_HAS_CRYPTOGRAPHY", False)
    monkeypatch.delenv("AIPD_INSECURE_DEV_MODE", raising=False)
    with pytest.raises(RuntimeError, match="NOT production-safe"):
        crypto.encrypt_secret("secret data", "keyA")


def test_encrypt_xor_allowed_in_insecure_dev_mode(monkeypatch):
    """显式 AIPD_INSECURE_DEV_MODE=1 时允许 XOR 回退，且往返/错钥语义保持。"""
    import aipd_os.state.crypto as crypto
    monkeypatch.setattr(crypto, "_HAS_CRYPTOGRAPHY", False)
    monkeypatch.setenv("AIPD_INSECURE_DEV_MODE", "1")
    ct = crypto.encrypt_secret("supplier quote: 1234", "keyA")
    assert ct.startswith("x1:")
    assert crypto.decrypt_secret(ct, "keyA") == "supplier quote: 1234"
    with pytest.raises(Exception):
        crypto.decrypt_secret(ct, "keyB")


def test_x1_legacy_decrypts_when_cryptography_available(monkeypatch):
    """历史 x1 旧数据在 cryptography 可用时仍可解密（仅加密侧 fail-closed）。"""
    import aipd_os.state.crypto as crypto
    monkeypatch.setattr(crypto, "_HAS_CRYPTOGRAPHY", False)
    monkeypatch.setenv("AIPD_INSECURE_DEV_MODE", "1")
    ct = crypto.encrypt_secret("legacy x1 value", "legacy-key")
    assert ct.startswith("x1:")
    # 恢复 cryptography 可用环境（清除 insecure dev mode）
    monkeypatch.setattr(crypto, "_HAS_CRYPTOGRAPHY", True)
    monkeypatch.delenv("AIPD_INSECURE_DEV_MODE", raising=False)
    assert crypto.decrypt_secret(ct, "legacy-key") == "legacy x1 value"
