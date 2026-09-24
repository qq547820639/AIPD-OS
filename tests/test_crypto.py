"""加密往返、错误密钥拒绝、以及 XOR 回退的 fail-closed 门控（P0-5）。"""
from __future__ import annotations

import pytest

from aipd_os.state import crypto
from aipd_os.state.crypto import decrypt_secret, encrypt_secret


def test_roundtrip():
    ct = encrypt_secret("supplier quote: 1234", "keyA")
    assert decrypt_secret(ct, "keyA") == "supplier quote: 1234"


def test_roundtrip_first_200_chars():
    text = "x" * 500
    assert decrypt_secret(encrypt_secret(text, "k"), "k") == text


def test_wrong_key_fails():
    ct = encrypt_secret("secret data", "keyA")
    with pytest.raises(Exception):  # noqa: B017 - 错钥解密抛底层异常，宽断言保持原语义
        decrypt_secret(ct, "keyB")


def test_tampered_fails():
    ct = encrypt_secret("data", "keyA")
    with pytest.raises(Exception):  # noqa: B017 - 篡改密文抛底层异常，宽断言保持原语义
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
    with pytest.raises(Exception):  # noqa: B017 - 错钥解密抛底层异常，宽断言保持原语义
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


class TestSaltedKdf:
    """f2：带盐 PBKDF2 派生（F-STATE-08）。

    旧 ``f1`` 的密钥是 ``sha256(口令)``——单轮、无盐：库文件外泄后口令可被离线
    穷举，同一口令还能跨安装用预计算表。f2 把轮数与盐都写进密文，
    将来上调轮数不必迁移数据。
    """

    SALT = bytes.fromhex("00112233445566778899aabbccddeeff")
    PW = "operator-chosen-passphrase"

    def test_roundtrip_and_wrong_key(self):
        ct = crypto.encrypt_secret("sk-live-9", self.PW, self.SALT)
        assert ct.startswith("f2:")
        assert crypto.decrypt_secret(ct, self.PW) == "sk-live-9"
        with pytest.raises(ValueError):
            crypto.decrypt_secret(ct, "wrong-passphrase")

    def test_token_carries_iterations_and_salt(self):
        ct = crypto.encrypt_secret("v", self.PW, self.SALT)
        _, iters, b64salt, _token = ct.split(":")
        assert int(iters) == crypto.PBKDF2_ITERATIONS
        assert crypto.base64.urlsafe_b64decode(b64salt) == self.SALT

    def test_salt_actually_enters_the_key(self):
        """同口令、不同盐 ⇒ 派生出不同的密钥（这才是抗预计算表的那一步）。

        f2 密文自带盐，所以「换个盐就解不开」不是本格式的属性；
        要验的是盐进了密钥推导，而不是被忽略。
        """
        k_a = crypto.derive_field_key(self.PW, self.SALT)
        k_b = crypto.derive_field_key(self.PW, b"\x01" * 16)
        assert k_a != k_b and len(k_a) == 32
        assert k_a != crypto._derive_key(self.PW), "f2 不得退化成旧的无盐 sha256"
        ct_a = crypto.encrypt_secret("v", self.PW, self.SALT)
        ct_b = crypto.encrypt_secret("v", self.PW, b"\x01" * 16)
        assert ct_a != ct_b
        # 用 A 的密钥去解 B 的密文必须失败
        with pytest.raises(ValueError):
            crypto.Fernet(k_b).decrypt(ct_a.split(":", 3)[3].encode("ascii"))

    def test_low_iteration_token_is_refused(self):
        """降级护栏：手改轮数为 1 的密文必须被拒绝，而不是慢慢解出来。"""
        ct = crypto.encrypt_secret("v", self.PW, self.SALT)
        weakened = ct.replace(f"f2:{crypto.PBKDF2_ITERATIONS}:", "f2:1:", 1)
        with pytest.raises(ValueError, match="too few KDF iterations"):
            crypto.decrypt_secret(weakened, self.PW)

    def test_legacy_f1_still_decrypts(self):
        """兼容：升级前写的无盐 f1 必须还能读（否则等于丢数据）。"""
        legacy = crypto.encrypt_secret("old value", self.PW)   # 无盐 → f1
        assert legacy.startswith("f1:")
        assert crypto.decrypt_secret(legacy, self.PW) == "old value"

    def test_derived_key_is_cached_per_salt(self, monkeypatch):
        """每库一份盐 + 进程内缓存：同 (口令, 盐) 只派生一次。"""
        calls = []
        real = crypto.hashlib.pbkdf2_hmac

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        crypto._derived_cache.clear()
        monkeypatch.setattr(crypto.hashlib, "pbkdf2_hmac", counting)
        for _ in range(5):
            crypto.derive_field_key(self.PW, self.SALT)
        assert len(calls) == 1, "缓存未生效：每条字段都要付 129ms 的派生代价"
        crypto.derive_field_key(self.PW, b"\x77" * 16)
        assert len(calls) == 2, "换盐必须重新派生（缓存不能把两个库的密钥混成一把）"


class TestStateFieldEncryption:
    """`AIPDStateDB` 端到端：敏感字段用 f2、盐每库一份且重启后稳定。"""

    PW = "e2e-strong-encryption-key-0123456789abcdef"

    def _db(self, tmp_path, name="s.db"):
        from aipd_os.state.db import AIPDStateDB
        return AIPDStateDB(str(tmp_path / name), encryption_key=self.PW)

    def _raw(self, db):
        with db.connect() as c:
            return c.execute(
                "SELECT value_json FROM facts WHERE key='api_key'").fetchone()[0]

    def test_sensitive_fact_is_f2_and_read_back(self, tmp_path):
        db = self._db(tmp_path)
        db.add_fact("default", "p1", "api_key", "sk-live-secret", "V")
        raw = self._raw(db)
        assert "__encrypted__" in raw and "f2:" in raw
        assert "sk-live-secret" not in raw
        with db.connect() as c:
            row = c.execute("SELECT value_json FROM facts WHERE key='api_key'").fetchone()
        assert db._read_value("api_key", row[0]) == "sk-live-secret"

    def test_salt_is_stable_across_reopen_and_unique_per_db(self, tmp_path):
        a = self._db(tmp_path, "a.db")
        salt_a = a._crypto_salt()
        assert self._db(tmp_path, "a.db")._crypto_salt() == salt_a, (
            "盐变了 ⇒ 重开后再也解不开旧密文")
        assert self._db(tmp_path, "b.db")._crypto_salt() != salt_a, (
            "两库同盐 ⇒ 预计算表仍可跨安装复用")
