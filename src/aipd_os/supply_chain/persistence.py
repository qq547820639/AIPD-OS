"""供应链记录的持久化：供应商、报价、资质、认证写入既有状态库。

基于 :class:`aipd_os.state.db.AIPDStateDB` 的多租户项目状态库，把供应商 /
报价 / 资质 / 认证记录以事实（facts）与证据（evidence）形式持久化，并支持
按 key 前缀回读。只持久化真实已存在的数据，不虚构任何状态。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aipd_os.state.db import AIPDStateDB

# 事实状态映射：供应链记录 -> AIPD 事实状态（V 已验证 / P 待定 / E 过期）
_QUOTE_FACT_STATUS = {"official": "V", "superseded": "S", "draft": "P"}
_CERT_FACT_STATUS = {"verified": "V", "pending": "P", "expired": "E"}

DEFAULT_TENANT = "default"


class SupplyChainStore:
    """把供应链记录持久化到 AIPDStateDB 的仓储。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = DEFAULT_TENANT) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self._supplier_fact_ids: dict[str, str] = {}

    # ------------------------------------------------------------- 供应商
    def persist_supplier(
        self,
        project_id: str,
        *,
        supplier_id: str,
        name: str,
        certificates: list[str] | None = None,
        qualification: str = "unqualified",
    ) -> str:
        certs = list(certificates or [])
        status = "V" if qualification == "qualified" else "P"
        fact_id = self.db.add_fact(
            self.tenant_id,
            project_id,
            key=f"supplier.{supplier_id}",
            value={
                "supplier_id": supplier_id,
                "name": name,
                "qualification": qualification,
                "certificates": certs,
            },
            status=status,
            source="supply_chain",
            version="1",
        )
        self._supplier_fact_ids[supplier_id] = fact_id
        return fact_id

    def load_suppliers(self, project_id: str) -> list[dict[str, Any]]:
        return [
            f for f in self.db.list_facts(self.tenant_id, project_id)
            if str(f.get("key", "")).startswith("supplier.")
        ]

    # ------------------------------------------------------------- 报价
    def persist_quote(
        self,
        project_id: str,
        *,
        quote_id: str,
        supplier: str,
        part: str,
        version: int,
        data: dict[str, Any],
        status: str = "official",
    ) -> str:
        normalized = dict(data or {})
        fact_status = _QUOTE_FACT_STATUS.get(status, "P")
        return self.db.add_fact(
            self.tenant_id,
            project_id,
            key=f"quote.{supplier}.{part}.v{version}",
            value={
                "quote_id": quote_id,
                "supplier": supplier,
                "part": part,
                "version": version,
                "data": normalized,
            },
            status=fact_status,
            source="supply_chain",
            version=str(version),
        )

    def load_quotes(self, project_id: str) -> list[dict[str, Any]]:
        return [
            f for f in self.db.list_facts(self.tenant_id, project_id)
            if str(f.get("key", "")).startswith("quote.")
        ]

    # ------------------------------------------------------------- 认证
    def persist_certification(
        self,
        project_id: str,
        *,
        cert_id: str,
        subject: str,
        standard: str,
        status: str = "pending",
        expires_at: str | None = None,
        evidence_ref: str | None = None,
    ) -> str:
        fact_status = _CERT_FACT_STATUS.get(status, "P")
        return self.db.add_fact(
            self.tenant_id,
            project_id,
            key=f"cert.{cert_id}",
            value={
                "cert_id": cert_id,
                "subject": subject,
                "standard": standard,
                "status": status,
                "expires_at": expires_at,
                "evidence_ref": evidence_ref,
            },
            status=fact_status,
            source="supply_chain",
            version="1",
        )

    def load_certifications(self, project_id: str) -> list[dict[str, Any]]:
        return [
            f for f in self.db.list_facts(self.tenant_id, project_id)
            if str(f.get("key", "")).startswith("cert.")
        ]

    # ------------------------------------------------------------- 证据
    def persist_evidence_file(
        self,
        project_id: str,
        path: str | Path,
        kind: str = "supply_chain_file",
        summary: str = "",
    ) -> str:
        p = Path(path)
        return self.db.add_evidence(
            self.tenant_id,
            project_id,
            kind=kind,
            title=p.name,
            url=str(p),
            summary=summary,
            metadata={"source": "supply_chain"},
        )

    def link_evidence_to_fact(self, project_id: str, fact_id: str, evidence_id: str) -> None:
        self.db.link_evidence(self.tenant_id, project_id, fact_id, evidence_id)


__all__ = [
    "SupplyChainStore",
    "DEFAULT_TENANT",
    "_QUOTE_FACT_STATUS",
    "_CERT_FACT_STATUS",
]
