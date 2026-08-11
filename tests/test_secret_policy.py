"""Change Set 2 密钥策略测试（P0-4）。

覆盖：
- AuthManager 必须显式传入 secret（None → ValueError）；
- server 模式（require_strong_secret=True）：缺 secret / 弱 secret
  （change-me-secret / 长度不足）→ fail-closed 抛 RuntimeError；
- insecure_dev_mode=True：允许弱 secret 且打印 WARNING；
- 显式强 secret（>=16 字符）：生产模式正常启动；
- 本地模式（require_strong_secret=False）：缺/弱 secret 使用随机临时
  secret 并打印 WARNING（保持 CLI/local 兼容）。
"""
from __future__ import annotations

import logging

import pytest

from aipd_os.state.auth import AuthManager
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.server import StateService


def test_auth_manager_requires_secret(tmp_path):
    db = AIPDStateDB(str(tmp_path / "auth.db"))
    db.ensure_default_tenant()
    with pytest.raises(ValueError, match="requires a secret"):
        AuthManager(db)  # secret=None


def test_server_prod_missing_secret_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match="AIPD_SECRET"):
        StateService(str(tmp_path / "s1.db"), secret=None, require_strong_secret=True)


def test_server_prod_weak_secret_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match="AIPD_SECRET"):
        StateService(str(tmp_path / "s2.db"), secret="change-me-secret",
                     require_strong_secret=True)


def test_server_prod_short_secret_fails_closed(tmp_path):
    with pytest.raises(RuntimeError, match="AIPD_SECRET"):
        StateService(str(tmp_path / "s3.db"), secret="short", require_strong_secret=True)


def test_insecure_dev_mode_allows_weak_secret(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        svc = StateService(str(tmp_path / "s4.db"), secret="change-me-secret",
                           insecure_dev_mode=True, require_strong_secret=True)
    tok = svc.auth.issue_token("u")
    assert svc.auth.authenticate("u", tok) is True
    assert any("insecure dev mode" in r.message for r in caplog.records)


def test_strong_secret_accepted_in_prod(tmp_path):
    svc = StateService(str(tmp_path / "s5.db"), secret="a" * 32,
                       require_strong_secret=True)
    tok = svc.auth.issue_token("u")
    assert svc.auth.authenticate("u", tok) is True


def test_local_mode_missing_secret_uses_random_ephemeral(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        svc = StateService(str(tmp_path / "s6.db"), secret=None)
    tok = svc.auth.issue_token("u")
    assert svc.auth.authenticate("u", tok) is True
    assert any("random ephemeral secret" in r.message for r in caplog.records)


def test_local_mode_weak_secret_uses_random_ephemeral(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        StateService(str(tmp_path / "s7.db"), secret="s")
    assert any("random ephemeral secret" in r.message for r in caplog.records)
