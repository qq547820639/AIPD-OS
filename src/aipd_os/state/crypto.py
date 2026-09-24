"""敏感字段加密模块。

优先使用 ``cryptography`` 的 Fernet（AES-128-CBC + HMAC）实现真实加密；
若当前环境未安装 ``cryptography``，加密操作会 **fail-closed**：仅当显式设置
环境变量 ``AIPD_INSECURE_DEV_MODE=1`` 才允许纯 Python 的 XOR + HMAC-SHA256
回退方案。XOR+HMAC **仅限 insecure dev mode，不是 production-safe
encryption-at-rest**：它使用密钥派生字节流做 XOR，密码学强度远低于 Fernet，
只用于开发/测试环境的往返一致性，绝不应用于生产数据保护。

加密串前缀约定：
  - ``f2:<iterations>:<b64salt>:<token>``  **当前写入格式**：
    PBKDF2-HMAC-SHA256 带盐派生（见下）。
  - ``f1:``  Fernet，密钥为无盐单轮 SHA-256 —— 旧数据，只读不解新写。
  - ``x1:``  XOR+HMAC 回退方案（纯 Python，仅 AIPD_INSECURE_DEV_MODE=1）。

**为什么要有 f2**（F-STATE-08）：``_derive_key`` 是 ``sha256(passphrase)``，
单轮、无盐。库文件一旦外泄，攻击者可对人类容易选择的口令做离线穷举
（server 模式只要求长度 ≥16，不保证熵），且同一口令跨安装可被预计算表复用。
f2 改用 ``pbkdf2_hmac(sha256, passphrase, salt, iterations)``，迭代次数随密文
存储（将来上调不必迁移数据）；盐**每库一份**且派生结果按 (密钥, 盐, 轮数)
缓存——本机实测 600k 轮 ≈129ms，若每条密文各派生一次会把这笔代价摊进
每一次字段读写。

解密侧对已存在的 ``f1:`` / ``x1:`` 旧数据保持兼容：无论当前是否安装
cryptography，只要有正确密钥即可解密（用于历史数据迁移，不做新增写入）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from collections import OrderedDict

try:  # cryptography 为可选依赖
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore

    _HAS_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover - 环境回退分支
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore[assignment, misc]
    _HAS_CRYPTOGRAPHY = False


def _insecure_dev_mode_enabled() -> bool:
    """是否显式允许非生产安全回退（AIPD_INSECURE_DEV_MODE=1）。"""
    return os.environ.get("AIPD_INSECURE_DEV_MODE", "") not in ("", "0", "false", "False")


def _derive_key(key: str) -> bytes:
    """把任意长度的密钥字符串派生为 32 字节密钥（**无盐，仅 f1/x1 兼容用**）。

    新写入一律走 :func:`derive_field_key`。
    """
    return hashlib.sha256(key.encode("utf-8")).digest()


PBKDF2_ITERATIONS = 600_000
MIN_KDF_ITERATIONS = 100_000
_KDF_CACHE_MAX = 8
_derived_cache: OrderedDict[tuple[bytes, bytes, int], bytes] = OrderedDict()


def derive_field_key(passphrase: str, salt: bytes,
                     iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """带盐 PBKDF2-HMAC-SHA256 派生 32 字节密钥；按 (密钥, 盐, 轮数) 缓存。

    缓存是「盐每库一份」这一选择的代价控制：同一库内所有字段共用一次派生。
    """
    cache_key = (passphrase.encode("utf-8"), bytes(salt), int(iterations))
    hit = _derived_cache.get(cache_key)
    if hit is not None:
        _derived_cache.move_to_end(cache_key)
        return hit
    dk = hashlib.pbkdf2_hmac("sha256", cache_key[0], cache_key[1],
                             cache_key[2], dklen=32)
    _derived_cache[cache_key] = dk
    while len(_derived_cache) > _KDF_CACHE_MAX:
        _derived_cache.popitem(last=False)
    return dk


def _xore(data: bytes, keybytes: bytes) -> bytes:
    return bytes((data[i] ^ keybytes[i % len(keybytes)]) for i in range(len(data)))


def encrypt_secret(plaintext: str, key: str, salt: bytes | None = None) -> str:
    """加密明文，返回可安全存储/传输的字符串。

    给了 ``salt`` 用当前格式 ``f2:``（带盐 PBKDF2）；不给退回旧的无盐
    ``f1:``——只为没有库级盐可用的调用方保留，``AIPDStateDB`` 总是传盐。
    """
    if _HAS_CRYPTOGRAPHY:
        if salt is not None:
            iters = PBKDF2_ITERATIONS
            k = base64.urlsafe_b64encode(derive_field_key(key, salt, iters))
            token = Fernet(k).encrypt(plaintext.encode("utf-8")).decode("ascii")
            return (f"f2:{iters}:"
                    f"{base64.urlsafe_b64encode(salt).decode('ascii')}:{token}")
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
    if prefix == "f2":
        if not _HAS_CRYPTOGRAPHY:
            raise ValueError("crypto: ciphertext is Fernet but cryptography is unavailable")
        iters_s, _, rest = body.partition(":")
        b64salt, _, token = rest.partition(":")
        try:
            iters = int(iters_s)
        except ValueError:
            raise ValueError(f"crypto: malformed f2 iteration count {iters_s!r}") from None
        if iters < MIN_KDF_ITERATIONS:
            raise ValueError(
                f"crypto: f2 token uses too few KDF iterations ({iters})")
        k = base64.urlsafe_b64encode(
            derive_field_key(key, base64.urlsafe_b64decode(b64salt), iters))
        try:
            return Fernet(k).decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            raise ValueError("crypto: invalid key or corrupted secret") from None
    if prefix == "f1":
        if not _HAS_CRYPTOGRAPHY:
            raise ValueError("crypto: ciphertext is Fernet but cryptography is unavailable")
        k = base64.urlsafe_b64encode(keybytes)
        try:
            return Fernet(k).decrypt(body.encode("ascii")).decode("utf-8")
        except InvalidToken:
            raise ValueError("crypto: invalid key or corrupted secret") from None
    raise ValueError(f"crypto: unknown encryption scheme prefix {prefix!r}")


__all__ = ["encrypt_secret", "decrypt_secret", "derive_field_key",
           "PBKDF2_ITERATIONS", "MIN_KDF_ITERATIONS", "_HAS_CRYPTOGRAPHY"]
