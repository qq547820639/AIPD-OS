"""认证状态生命周期管理。

状态机：pending -> verified -> expired。只有提供了真实证明引用（evidence_ref）
才能进入 verified 状态；绝不虚构"已验证"。到期后自动转为 expired。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

VALID_STATUSES = ("pending", "verified", "expired")


@dataclass
class Certification:
    """一条认证记录。"""

    cert_id: str
    subject: str
    standard: str
    status: str = "pending"
    evidence_ref: Optional[str] = None
    verified_at: Optional[str] = None
    expires_at: Optional[str] = None


def verified(cert: Certification) -> bool:
    """仅当状态为 verified 且存在 evidence_ref 时判定为已验证。"""
    return cert.status == "verified" and bool(cert.evidence_ref)


class CertificationRegistry:
    """登记、查询与流转认证状态的注册表。"""

    def __init__(self) -> None:
        self._certs: Dict[str, Certification] = {}

    def register(self, cert: Certification) -> Certification:
        """登记一条认证；使用其初始状态（默认 pending）。"""
        self._certs[cert.cert_id] = cert
        return cert

    def list(self) -> List[Certification]:
        return list(self._certs.values())

    def get(self, cert_id: str) -> Optional[Certification]:
        return self._certs.get(cert_id)

    def transition(
        self,
        cert_id: str,
        new_status: str,
        evidence_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """将指定认证流转到新状态，并返回结果字典。

        规则：
        - 目标为 verified 时，evidence_ref 必须非空，否则返回错误字典（不虚构已验证）。
        - 一旦 verified，若 expires_at 早于当前时间则自动转为 expired。
        - 认证不存在时返回错误字典。
        """
        cert = self._certs.get(cert_id)
        if cert is None:
            return {"ok": False, "error": f"unknown certification: {cert_id!r}"}

        if new_status == "verified":
            if not evidence_ref:
                return {
                    "ok": False,
                    "error": "cannot verify without evidence_ref",
                    "cert_id": cert_id,
                }
            cert.evidence_ref = evidence_ref
            cert.verified_at = datetime.now().isoformat()

        cert.status = new_status

        # 已验证后若已到期则自动过期
        if cert.status == "verified" and cert.expires_at:
            try:
                expires = datetime.fromisoformat(cert.expires_at)
            except (TypeError, ValueError):
                expires = None
            if expires is not None and expires < datetime.now():
                cert.status = "expired"

        return {"ok": True, "cert_id": cert_id, "status": cert.status}


__all__ = [
    "VALID_STATUSES",
    "Certification",
    "CertificationRegistry",
    "verified",
]