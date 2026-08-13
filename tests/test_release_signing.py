"""发布物签名测试。"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sign_release  # noqa: E402


@pytest.fixture
def key_env(monkeypatch):
    monkeypatch.setenv("AIPD_RELEASE_SIGNING_KEY", "unit-test-key-1234")
    return "unit-test-key-1234"


def _make_artifact(tmp_path: Path) -> Path:
    p = tmp_path / "release.tar.gz"
    p.write_bytes(b"fake-release-bytes-" * 100)
    return p


def test_sha256_stable(tmp_path):
    p = _make_artifact(tmp_path)
    d1 = sign_release.sha256_file(p)
    d2 = sign_release.sha256_file(p)
    assert d1 == d2 == hashlib.sha256(p.read_bytes()).hexdigest()


def test_sign_and_verify(tmp_path, key_env):
    p = _make_artifact(tmp_path)
    info = sign_release.sign_release(str(p))
    assert info["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert info["signature"] == hmac.new(
        key_env.encode(), p.read_bytes(), hashlib.sha256
    ).hexdigest()
    # 产物文件
    assert (tmp_path / "release.tar.gz.sha256").is_file()
    sig_file = tmp_path / "release.tar.gz.sig"
    assert sig_file.is_file()
    assert sign_release.verify_release(str(p)) is True


def test_verify_detects_tampering(tmp_path, key_env):
    p = _make_artifact(tmp_path)
    sign_release.sign_release(str(p))
    # 篡改内容后签名应失效
    p.write_bytes(p.read_bytes() + b"tampered")
    assert sign_release.verify_release(str(p)) is False


def test_requires_key(tmp_path):
    p = _make_artifact(tmp_path)
    os.environ.pop("AIPD_RELEASE_SIGNING_KEY", None)
    with pytest.raises(SystemExit) as exc:
        sign_release.sign_release(str(p))
    assert exc.value.code == 2
