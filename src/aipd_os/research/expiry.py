"""证据过期传播：把过期的证据影响的 Product Truth 事实标记为 stale。

- 给定证据过期日期（evidence_id -> expiry），找出其关联的事实（fact_evidence）；
- 将受影响事实状态更新为 ``R``（Retired：曾有效、现因上游变化而过时），并把
  过期信息写入证据 metadata；
- 不删除任何数据，仅标记，保证可追溯。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, cast

# facts 表既有状态位：见 aipd_os.state.db 的 FACT_STATUSES。
# 此前复用 "S"（Simulation）标记 stale，语义冲突；统一改为 "R"（Retired，
# 正式 epistemic 语义：曾有效、现已退役/不再有效），与 Simulation 彻底分离。
STALE_STATUS = "R"

# 过期元数据 key（写入 evidence.metadata_json）
_EXPIRY_META_KEY = "expired_at"
_EXPIRY_REASON_KEY = "expiry_reason"


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    return dt.isoformat()


def mark_evidence_expired(db: Any, tenant_id: str, project_id: str,
                          evidence_id: str, expired_at: datetime | None = None,
                          reason: str = "source superseded") -> dict[str, Any]:
    """把单条证据标记为过期，并传播到其关联事实。

    返回 {"evidence_id", "stale_fact_ids", "expired_at"}。
    """
    evidence = _find_evidence(db, tenant_id, project_id, evidence_id)
    meta = dict(evidence.get("metadata_json") or {})
    meta[_EXPIRY_META_KEY] = _iso(expired_at)
    meta[_EXPIRY_REASON_KEY] = reason
    db.update_evidence_metadata(tenant_id, project_id, evidence_id, meta)

    stale_fact_ids = _stale_linked_facts(db, tenant_id, project_id, evidence_id)
    return {
        "evidence_id": evidence_id,
        "stale_fact_ids": stale_fact_ids,
        "expired_at": _iso(expired_at),
    }


def expire_evidence_list(db: Any, tenant_id: str, project_id: str,
                         expiries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量过期：输入 [{"evidence_id": ..., "expires_at": <iso|None>, "reason": ...}]。"""
    results = []
    for e in expiries:
        eid = e.get("evidence_id")
        if not eid:
            continue
        dt = None
        raw = e.get("expires_at")
        if raw:
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                dt = None
        results.append(
            mark_evidence_expired(db, tenant_id, project_id, eid, dt, e.get("reason", "source superseded"))  # noqa: E501
        )
    return results


def _find_evidence(db: Any, tenant_id: str, project_id: str, evidence_id: str) -> dict[str, Any]:
    for ev in db.list_evidence(tenant_id, project_id):
        if ev.get("evidence_id") == evidence_id:
            raw = ev.get("metadata_json")
            if isinstance(raw, str):
                try:
                    ev["metadata_json"] = json.loads(raw)
                except (ValueError, TypeError):
                    ev["metadata_json"] = {}
            return cast(dict[str, Any], ev)
    raise KeyError(evidence_id)


def _stale_linked_facts(db: Any, tenant_id: str, project_id: str, evidence_id: str) -> list[str]:
    """把关联该证据的事实标记为 stale，返回受影响 fact_id 列表。"""
    stale = []
    for fact in db.list_facts(tenant_id, project_id):
        linked = db.list_evidence_for_fact(tenant_id, project_id, fact["fact_id"])
        if any(ev.get("evidence_id") == evidence_id for ev in linked):
            db.update_fact(
                tenant_id, project_id, fact["fact_id"],
                expected_version=fact["version_no"],
                status=STALE_STATUS,
            )
            stale.append(fact["fact_id"])
    return stale


__all__ = ["mark_evidence_expired", "expire_evidence_list", "STALE_STATUS"]
