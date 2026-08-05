"""敏感数据掩码与权限测试。"""
from __future__ import annotations

from aipd_os.security import (
    classify_sensitive,
    mask_sensitive,
    can_access,
    require_mask,
)


def test_mask_email_phone_ip():
    text = "reach alice@acme.com or +86-138-0000-1234 at 192.168.1.10"
    masked = mask_sensitive(text)
    assert "alice@acme.com" not in masked
    assert "+86-138-0000-1234" not in masked
    assert "192.168.1.10" not in masked
    assert masked.count("***") >= 3


def test_mask_supplier_quote_value():
    text = "Quoted price is USD 5000 for the injection mold tool."
    masked = mask_sensitive(text, sensitive_values=["USD 5000"])
    assert "USD 5000" not in masked
    # 通过显式敏感值掩码
    assert mask_sensitive("quote 5000 total", sensitive_values=["5000"]) == "quote *** total"


def test_classify_sensitive_categories():
    text = "contact: bob@corp.com, supplier quote 1200, raw experiment_data attached, +86-138-0000-1234"
    cats = classify_sensitive(text)
    assert "email" in cats
    assert "phone" in cats
    assert "contact" in cats
    assert "supplier_quote" in cats
    assert "experiment_data" in cats


def test_can_access_denies_without_permission():
    # fail-closed：granted 未提供时，敏感作用域必须拒绝
    assert can_access("alice", "supplier_quote") is False
    assert can_access("alice", "contact") is False
    assert can_access("alice", "experiment_data") is False


def test_can_access_grants_with_explicit_permission():
    assert can_access("alice", "supplier_quote", granted=["supplier_quote"]) is True


def test_require_mask_sensitive():
    assert require_mask("alice", "supplier_quote") is True
    assert require_mask(None, "supplier_quote") is True
    assert require_mask("alice", "fact") is False
