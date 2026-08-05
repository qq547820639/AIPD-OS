"""认证状态生命周期测试（Task 2）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from aipd_os.supply_chain.certification import (
    Certification,
    CertificationRegistry,
    verified,
)


def test_initial_state_is_pending():
    cert = Certification(cert_id="C1", subject="Acme", standard="ISO9001")
    assert cert.status == "pending"
    assert verified(cert) is False


def test_cannot_verify_without_evidence_ref():
    # 诚实护栏：无证明引用不能进入 verified
    reg = CertificationRegistry()
    reg.register(Certification(cert_id="C1", subject="Acme", standard="ISO9001"))
    out = reg.transition("C1", "verified")
    assert out["ok"] is False
    assert reg.get("C1").status == "pending"
    assert verified(reg.get("C1")) is False


def test_verify_with_evidence_ref():
    reg = CertificationRegistry()
    reg.register(Certification(cert_id="C1", subject="Acme", standard="ISO9001"))
    out = reg.transition("C1", "verified", evidence_ref="CERT-2024-001")
    assert out["ok"] is True
    assert out["status"] == "verified"
    cert = reg.get("C1")
    assert verified(cert) is True
    assert reg.get("C1").evidence_ref == "CERT-2024-001"


def test_verified_requires_evidence_ref_after_fact():
    # 即使手动把 status 设为 verified，但缺少 evidence_ref 也不算已验证
    reg = CertificationRegistry()
    cert = Certification(cert_id="C1", subject="Acme", standard="ISO9001", status="verified")
    reg.register(cert)
    assert verified(cert) is False


def test_expired_after_verified_past_expiry():
    past = (datetime.now() - timedelta(days=1)).isoformat()
    reg = CertificationRegistry()
    reg.register(
        Certification(cert_id="C1", subject="Acme", standard="ISO9001", expires_at=past)
    )
    out = reg.transition("C1", "verified", evidence_ref="CERT-2024-001")
    assert out["status"] == "expired"
    assert reg.get("C1").status == "expired"
    assert verified(reg.get("C1")) is False


def test_register_list_get_and_unknown_transition():
    reg = CertificationRegistry()
    reg.register(Certification(cert_id="C1", subject="Acme", standard="ISO9001"))
    reg.register(Certification(cert_id="C2", subject="Beta", standard="IATF16949"))
    assert len(reg.list()) == 2
    assert reg.get("C1").standard == "ISO9001"
    assert reg.get("nope") is None
    out = reg.transition("nope", "verified")
    assert out["ok"] is False