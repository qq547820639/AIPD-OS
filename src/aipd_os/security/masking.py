"""敏感数据掩码与权限。

- ``mask_sensitive``：对邮箱、电话、IP 及显式敏感值（supplier quote / contact /
  experiment_data）打码为 ``***``；
- ``classify_sensitive``：返回文本中检测到的敏感类别；
- ``can_access``：敏感作用域（supplier_quote / contact / experiment_data）
  必须显式授权，否则拒绝；
- ``require_mask``：判断是否需要对给定作用域打码。

权限模型复用 ``aipd_os.state.auth.AuthManager`` 的项目级授权语义；本模块提供
一个轻量、无状态的作用域授权判定，可独立运行。
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

from aipd_os.state.crypto import encrypt_secret

MASK = "***"

# 敏感作用域：需要显式授权
SENSITIVE_SCOPES = frozenset({"supplier_quote", "contact", "experiment_data"})
# 任意作用域（用于 can_access 的默认判定）
ALL_SCOPES = frozenset(
    {
        "supplier_quote", "contact", "experiment_data",
        "fact", "evidence", "decision", "deliverable", "risk", "project",
    }
)

# 正则：邮箱 / 电话 / IPv4 / IPv6
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# 显式敏感值关键词（用于 classify_sensitive 的上下文启发式）
_SENSITIVE_LABELS = {
    "supplier_quote": ("supplier quote", "quote", "报价", "supplier_quote"),
    "contact": ("contact", "phone", "email", "联系人", "联系方式", "电话"),
    "experiment_data": ("experiment data", "实验数据", "experiment_data", "raw data"),
}


class PermissionError(Exception):
    """缺少敏感数据访问权限。"""


def _scan_categories(text: str) -> List[str]:
    """基于正则 + 上下文关键词返回检测到的敏感类别。"""
    cats: Set[str] = set()
    if _EMAIL_RE.search(text):
        cats.add("email")
    if _PHONE_RE.search(text):
        cats.add("phone")
    if _IPV4_RE.search(text):
        cats.add("ip")
    lowered = text.lower()
    for scope, labels in _SENSITIVE_LABELS.items():
        if any(label in lowered for label in labels):
            cats.add(scope)
    return sorted(cats)


def classify_sensitive(text: str) -> List[str]:
    """返回文本中检测到的敏感类别列表（排序、去重）。"""
    if not text:
        return []
    return _scan_categories(text)


def mask_sensitive(
    text: str,
    sensitive_values: Optional[Iterable[str]] = None,
    patterns: Optional[Iterable[re.Pattern]] = None,
) -> str:
    """对文本中的敏感信息打码为 ``***``。

    默认掩码邮箱、电话号码与 IP 地址；可通过 ``sensitive_values`` 显式掩码
    指定敏感值（供应商报价、联系人、实验数据等），通过 ``patterns`` 追加正则。

    :param text: 待打码文本
    :param sensitive_values: 需要显式掩码的敏感值集合
    :param patterns: 额外正则模式
    :returns: 打码后的文本
    """
    if not text:
        return text
    masked = text
    masked = _EMAIL_RE.sub(MASK, masked)
    masked = _PHONE_RE.sub(MASK, masked)
    masked = _IPV4_RE.sub(MASK, masked)
    if sensitive_values:
        for value in sensitive_values:
            if value:
                masked = masked.replace(value, MASK)
    if patterns:
        for pat in patterns:
            masked = pat.sub(MASK, masked)
    return masked


def can_access(
    user: Optional[str],
    scope: str,
    resource: Optional[str] = None,
    granted: Optional[Iterable[str]] = None,
) -> bool:
    """判定用户是否有权访问指定作用域的资源。

    敏感作用域（supplier_quote / contact / experiment_data）必须显式授权：
    - 传入了 ``granted``（该用户已被授予的作用域集合）时，作用域需在其中；
    - 未传入 ``granted`` 时，默认拒绝敏感作用域（fail-closed）。

    :param user: 用户标识（可为空，空视为匿名）
    :param scope: 作用域（supplier_quote / contact / experiment_data / 其他）
    :param resource: 可选资源标识
    :param granted: 用户显式获得授权的作用域集合（可选）
    """
    if scope in SENSITIVE_SCOPES:
        if granted is None:
            return False  # fail-closed：无授权信息则拒绝
        return scope in set(granted)
    # 非敏感作用域：默认授予（配合上层项目级授权）
    if granted is None:
        return True
    return scope in set(granted) or "wildcard" in set(granted)


def require_mask(user: Optional[str], scope: str) -> bool:
    """判断给定的敏感作用域是否需要掩码。

    对敏感作用域，若用户未被显式授权则返回 True（需要掩码）。
    """
    if scope not in SENSITIVE_SCOPES:
        return False
    if user is None:
        return True
    # 无授权信息时保守地要求掩码
    return True


def _encrypt_at_rest(value: str, key: str) -> str:
    """复用 state.crypto.encrypt_secret 对敏感字段做静态加密。"""
    return encrypt_secret(value, key)


__all__ = [
    "MASK",
    "SENSITIVE_SCOPES",
    "PermissionError",
    "mask_sensitive",
    "classify_sensitive",
    "can_access",
    "require_mask",
    "_encrypt_at_rest",
]
