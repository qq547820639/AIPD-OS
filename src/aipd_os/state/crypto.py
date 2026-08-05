"""敏感字段加密模块。

优先使用 ``cryptography`` 的 Fernet（AES-128-CBC + HMAC）实现真实加密；
若当前环境未安装 ``cryptography``，则回退到纯 Python 的 XOR + HMAC-SHA256
方案（带消息认证码，密钥错误/数据被篡改会抛异常）。两种方案都保证：
  1) 加密/解密往返一致；
  2) 使用错误密钥时解密失败（FERNET 抛 InvalidToken，回退方案抛 ValueError）。

加密串前缀约定：
  - ``f1:``  Fernet 加密（cryptography 可用）
  - ``x1:``  XOR+HMAC 回退方案（纯 Python）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Optional

try:  # cryptography 为可选依赖
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore

    _HAS_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover - 环境回退分支
    Fernet = None  # type: ignore
    InvalidToken = Exception
    _HAS_CRYPTOGRAPHY = False


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
    # 纯 Python 回退：XOR + HMAC 完整性校验
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
