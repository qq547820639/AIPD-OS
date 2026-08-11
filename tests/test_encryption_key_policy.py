"""v5.7 Commit 3：Encryption Production Policy 测试。

覆盖：
- 生产 server 模式缺 encryption key → fail-closed（抛 RuntimeError 拒绝启动）；
- 公开默认弱 key（change-me-encryption-key）→ fail-closed；
- 过短 key → fail-closed；
- AIPD_ALLOW_PLAINTEXT_SENSITIVE=1（显式 dev 模式）→ 允许空 key + WARNING；
- 强 key → 敏感字段加密落库（at-rest encrypted）；
- 空 key 本地模式明文存储 + WARNING（兼容，非 server 模式）；
- 本地模式弱 key 仍启用加密（兼容既有行为）。
"""
from __future__ import annotations

import logging
import sqlite3

import pytest

from aipd_os.state.server import StateService

STRONG_KEY = "production-grade-encryption-key-0001"
STRONG_SECRET = "production-grade-secret-value-0001"


def _svc(tmp_path, *, encryption_key: str = "", **kwargs):
    return StateService(
        str(tmp_path / "state.db"),
        encryption_key=encryption_key,
        secret=STRONG_SECRET,
        require_strong_secret=True,
        **kwargs,
    )


def test_server_mode_missing_key_fails_closed(tmp_path):
    """生产 server 模式：encryption_key 缺失 → 拒绝启动。"""
    with pytest.raises(RuntimeError, match="AIPD_ENCRYPTION_KEY"):
        _svc(tmp_path, require_strong_encryption_key=True)


def test_server_mode_public_default_key_fails_closed(tmp_path):
    """生产 server 模式：公开默认弱 key → 拒绝启动。"""
    with pytest.raises(RuntimeError, match="AIPD_ENCRYPTION_KEY"):
        _svc(tmp_path, encryption_key="change-me-encryption-key",
             require_strong_encryption_key=True)


def test_server_mode_short_key_fails_closed(tmp_path):
    """生产 server 模式：过短 key → 拒绝启动。"""
    with pytest.raises(RuntimeError, match="AIPD_ENCRYPTION_KEY"):
        _svc(tmp_path, encryption_key="short",
             require_strong_encryption_key=True)


def test_allow_plaintext_sensitive_env_allows_empty_key(tmp_path, monkeypatch, caplog):
    """AIPD_ALLOW_PLAINTEXT_SENSITIVE=1 → 显式 dev 模式允许空 key + WARNING。"""
    monkeypatch.setenv("AIPD_ALLOW_PLAINTEXT_SENSITIVE", "1")
    with caplog.at_level(logging.WARNING):
        svc = _svc(tmp_path, require_strong_encryption_key=True)
    assert svc.db._encryption_key == ""
    assert any("AIPD_ALLOW_PLAINTEXT_SENSITIVE" in r.message for r in caplog.records)


def test_strong_key_encrypts_sensitive_at_rest(tmp_path):
    """强 key → 敏感字段加密落库，读取可解密。"""
    svc = _svc(tmp_path, encryption_key=STRONG_KEY,
               require_strong_encryption_key=True)
    svc.init_project("default", "p1", "P1", "goal")
    svc.add_fact("default", "p1", "supplier_quote", 1234.5, "V")
    conn = sqlite3.connect(str(svc.db.path))
    raw = conn.execute("SELECT value_json FROM facts").fetchone()[0]
    conn.close()
    assert "__encrypted__" in raw
    assert "1234.5" not in raw  # 明文不应出现在落库 JSON
    assert svc.db.list_facts("default", "p1")[0]["value"] == 1234.5


def test_local_mode_empty_key_plaintext_warns(tmp_path, caplog):
    """本地模式空 key → 敏感字段明文 + WARNING（兼容，非 server 模式）。"""
    with caplog.at_level(logging.WARNING):
        svc = _svc(tmp_path)  # require_strong_encryption_key 默认 False
    assert svc.db._encryption_key == ""
    assert any("plaintext" in r.message for r in caplog.records)

    svc.init_project("default", "p1", "P1", "goal")
    svc.add_fact("default", "p1", "supplier_quote", 1234.5, "V")
    conn = sqlite3.connect(str(svc.db.path))
    raw = conn.execute("SELECT value_json FROM facts").fetchone()[0]
    conn.close()
    assert "__encrypted__" not in raw  # 明文存储
    assert svc.db.list_facts("default", "p1")[0]["value"] == 1234.5


def test_local_mode_weak_key_still_encrypts(tmp_path, caplog):
    """本地模式弱 key（非空）→ 仍启用加密（既有行为兼容）。"""
    with caplog.at_level(logging.WARNING):
        svc = _svc(tmp_path, encryption_key="k")  # 1 字符，弱但非空
    assert svc.db._encryption_key == "k"
    assert any("weak AIPD_ENCRYPTION_KEY" in r.message for r in caplog.records)

    svc.init_project("default", "p1", "P1", "goal")
    svc.add_fact("default", "p1", "supplier_quote", 1234.5, "V")
    conn = sqlite3.connect(str(svc.db.path))
    raw = conn.execute("SELECT value_json FROM facts").fetchone()[0]
    conn.close()
    assert "__encrypted__" in raw
    assert svc.db.list_facts("default", "p1")[0]["value"] == 1234.5


def test_server_mode_strong_key_starts(tmp_path):
    """生产 server 模式：强 key + 强 secret → 正常启动。"""
    svc = _svc(tmp_path, encryption_key=STRONG_KEY,
               require_strong_encryption_key=True)
    tok = svc.auth.issue_token("u")
    assert svc.auth.authenticate("u", tok) is True
