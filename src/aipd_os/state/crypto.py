"""敏感字段加密模块。

优先使用 ``cryptography`` 的 Fernet（AES-128-CBC + HMAC）实现真实加密；
若当前环境未安装 ``cryptography``，加密操作会 **fail-closed**：仅当显式设置
环境变量 ``AIPD_INSECURE_DEV_MODE=1`` 才允许纯 Python 的 XOR + HMAC-SHA256
回退方案。XOR+HMAC **仅限 insecure dev mode，不是 production-safe
encryption-at-rest**：它使用密钥派生字节流做 XOR，密码学强度远低于 Fernet，
只用于开发/测试环境的往返一致性，绝不应用于生产数据保护。

加密串前缀约定：
  - ``f1:``  Fernet 加密（cryptography 可用）
  - ``x1:``  XOR+HMAC 回退方案（纯 Python，仅 AIPD_INSECURE_DEV_MODE=1）

解密侧对已存在的 ``x1:`` 旧数据保持兼容：无论当前是否安装 cryptography，
只要有正确密钥即可解密（用于历史数据迁移，不做新增写入）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

try:  # cryptography 为可选依赖
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore

    _HAS_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover - 环境回退分支
    Fernet = None  # type: ignore
    InvalidToken = Exception
    _HAS_CRYPTOGRAPHY = False


def _insecure_dev_mode_enabled() -> bool:
    """是否显式允许非生产安全回退（AIPD_INSECURE_DEV_MODE=1）。"""
    return os.environ.get("AIPD_INSECURE_DEV_MODE", "") not in ("", "0", "false", "False")


def _derive_key(key: str) -> bytes:
    """把任意长度的密钥字符串派生为 32 字节固定长度密钥。"""
    return hashlib.sha256(key.encode("utf-8")).digest()


def _xore(data: bytes, keybytes: bytes) -> bytes:
    return bytes((data[i] ^ keybytes[i % len(keybytes)]) for i in range(len(data)))


def encrypt_secret(plaintext: str, key: str) -> str:
    """加密明文，返回可安全存储/传输的字符串。"""
    if _HAS_CRYPTOGRAPHY:
        k = base64.urlsafe_b64encode(_derive_key(key))
        return "f1:" + Fernet(k).encrypt(plaintext.encode("utf-8")).decode("ascii")
    # 纯 Python 回退：XOR + HMAC 完整性校验（仅限 insecure dev mode，fail-closed）
    if not _insecure_dev_mode_enabled():
        raise RuntimeError(
            "cryptography unavailable; XOR fallback is NOT production-safe. "
            "Set AIPD_INSECURE_DEV_MODE=1 to allow.")
    keybytes = _derive_key(key)
    data = plaintext.encode("utf-8")
    xored = _xore(data, keybytes)
    mac = hmac.new(keybytes, xored, hashlib.sha256).hexdigest()
    return "x1:" + mac + ":" + base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_secret(token: str, key: str) -> str:
    """解密 encrypt_secret 的产物。密钥错误或数据被篡改时抛异常。"""
    prefix, _, body = token.partition(":")
    keybytes = _derive_key(key)
    if prefix == "x1":
        mac, _, b64 = body.partition(":")
        xored = base64.urlsafe_b64decode(b64)
        expected = hmac.new(keybytes, xored, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("crypto: invalid key or corrupted secret")
        data = _xore(xored, keybytes)
        return data.decode("utf-8")
    if prefix == "f1":
        if not _HAS_CRYPTOGRAPHY:
            raise ValueError("crypto: ciphertext is Fernet but cryptography is unavailable")
        k = base64.urlsafe_b64encode(keybytes)
        try:
            return Fernet(k).decrypt(body.encode("ascii")).decode("utf-8")
        except InvalidToken:
            raise ValueError("crypto: invalid key or corrupted secret") from None
    raise ValueError(f"crypto: unknown encryption scheme prefix {prefix!r}")


__all__ = ["encrypt_secret", "decrypt_secret", "_HAS_CRYPTOGRAPHY"]
