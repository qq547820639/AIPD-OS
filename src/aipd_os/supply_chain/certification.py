"""认证状态生命周期管理。

状态机：pending -> verified -> expired。只有提供了真实证明引用（evidence_ref）
才能进入 verified 状态；绝不虚构"已验证"。到期后自动转为 expired。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def _now_aware() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expiry(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        try:
            dt = datetime.strptime(str(value), "%Y-%m-%d")
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def import_certificate_file(
    path: Union[str, Path],
    cert_id: Optional[str] = None,
    registry: Optional[CertificationRegistry] = None,
) -> Dict[str, Any]:
    """导入证书文件并登记：支持 JSON / CSV / 文本。

    - JSON：含 ``cert_id``/``subject``/``standard``/``expires_at`` 等字段；
    - CSV：首行表头含 subject/standard/expires_at；
    - 其余格式（PDF 等）或无法解析到期日时，返回 not_verified 结构（不虚构）。

    返回 ``{"ok": bool, "cert": Certification, "errors": [...]}``。
    """
    p = Path(path)
    ext = p.suffix.lower()
    subject = ""
    standard = ""
    expires_at: Optional[str] = None
    exp_source: Optional[str] = None
    errors: List[Dict[str, Any]] = []

    if ext == ".json":
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                subject = str(data.get("subject") or "").strip()
                standard = str(data.get("standard") or "").strip()
                expires_at = data.get("expires_at") or data.get("expiry") or None
                exp_source = str(data.get("expires_at") or data.get("expiry") or "")
                if not cert_id:
                    cert_id = str(data.get("cert_id") or "").strip() or None
        except Exception as exc:  # noqa: BLE001
            errors.append({"error": f"JSON 证书解析失败: {exc}", "not_verified": True})
    elif ext == ".csv":
        import csv as _csv
        try:
            rows = list(_csv.DictReader(p.open("r", encoding="utf-8", newline="")))
            if rows:
                row = rows[0]
                subject = str(row.get("subject") or "").strip()
                standard = str(row.get("standard") or "").strip()
                expires_at = row.get("expires_at") or row.get("expiry") or None
                exp_source = str(expires_at or "")
        except Exception as exc:  # noqa: BLE001
            errors.append({"error": f"CSV 证书解析失败: {exc}", "not_verified": True})
    else:
        errors.append({
            "error": f"不支持解析 {ext or '(无扩展名)'} 证书文件；请提供 JSON/CSV 或经外部工具提取",
            "external_dependency": True,
            "not_verified": True,
        })

    expiry_dt = _parse_expiry(str(expires_at)) if expires_at else None
    if expires_at and expiry_dt is None:
        errors.append({
            "error": f"无法解析到期日 {expires_at!r}; 证书到期状态保持 not_verified",
            "expiry_parse": exp_source,
            "not_verified": True,
        })

    if not cert_id:
        cert_id = f"cert-{Path(p).stem}"
    cert = Certification(
        cert_id=cert_id,
        subject=subject or Path(p).stem,
        standard=standard or "unknown",
        status="pending",
        evidence_ref=str(p),
        expires_at=expiry_dt.isoformat() if expiry_dt else None,
    )
    if not subject or not standard or expiry_dt is None:
        cert.status = "pending"
        if expiry_dt is None:
            errors.append({
                "error": "缺少有效到期日，证书状态保持 pending（未验证）",
                "not_verified": True,
            })
    target = registry or CertificationRegistry()
    target.register(cert)
    return {"ok": bool(cert.evidence_ref), "cert": cert, "errors": errors, "registry": target}


def expiring_certs(
    registry: CertificationRegistry,
    within_days: int = 30,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """返回即将到期（within_days 内）或已经过期的证书。

    每条结果形如 ``{"cert": Certification, "status": "expired"|"expiring",
    "days_left": int}``。未设置到期日的证书不计入（不虚构）。
    """
    ref = now or _now_aware()
    out: List[Dict[str, Any]] = []
    for cert in registry.list():
        dt = _parse_expiry(cert.expires_at)
        if dt is None:
            continue
        days_left = (dt - ref).total_seconds() / 86400.0
        if days_left < 0:
            cert.status = "expired"
            out.append({"cert": cert, "status": "expired", "days_left": int(days_left)})
        elif days_left <= within_days:
            out.append({"cert": cert, "status": "expiring", "days_left": int(days_left)})
    out.sort(key=lambda e: e["days_left"])
    return out


__all__ = [
    "VALID_STATUSES",
    "Certification",
    "CertificationRegistry",
    "verified",
    "import_certificate_file",
    "expiring_certs",
]