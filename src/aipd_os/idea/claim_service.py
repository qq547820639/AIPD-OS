"""ClaimService：Claim 的 tenant/project/idea scoped CRUD（v5.8 Commit 10）。

- 创建时校验 idea 存在且同 scope（软引用）；
- epistemic_status 校验合法（FACT_STATUSES，含 U/A/E）；
- 全部写操作 audited（audit_log）+ versioned（version_no 乐观锁）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import FACT_STATUSES, AIPDStateDB, now_iso

from .claims import (
    CLAIM_LIFECYCLE_STATUSES,
    CLAIM_TYPES,
    Claim,
)

# 可编辑字段白名单
_CLAIM_EDITABLE = {
    "claim_type", "statement", "epistemic_status", "lifecycle_status",
    "confidence", "source",
}


class ClaimNotFoundError(KeyError):
    """在指定 tenant/project scope 下找不到 claim。"""


class ClaimOptimisticLockError(Exception):
    """claim version_no 乐观锁冲突。"""


class ClaimScopeError(ValueError):
    """跨 scope 访问/引用拒绝（idea 或 evidence 不属于同 tenant+project）。"""


class ClaimService:
    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    # ------------------------------------------------------------- helpers
    def _next_id(self, prefix: str = "CLM") -> str:
        """并发安全 ID：基于 id_sequences 表原子分配（v5.8.1 Commit 7）。"""
        return self._db.next_sequence("claim", prefix)

    @staticmethod
    def _row_to_claim(row: Any) -> Claim:
        return Claim.from_dict(dict(row))

    def _audit(self, actor: str, action: str, claim: Claim, before: Any = None) -> None:
        self._db.add_audit(actor, action, claim.project_id, claim.tenant_id,
                           before=before, after=claim.to_dict())

    def _ensure_idea_in_scope(self, tenant_id: str, project_id: str, idea_id: str) -> None:
        """校验 idea 存在且同 tenant+project（软引用）。"""
        if not idea_id:
            return
        with self._db.connect() as c:
            row = c.execute(
                "SELECT 1 FROM ideas WHERE idea_id=? AND project_id=? AND tenant_id=?",
                (idea_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise ClaimScopeError(
                f"idea {idea_id!r} does not exist in tenant {tenant_id!r}/"
                f"project {project_id!r}")

    # --------------------------------------------------------------- CRUD
    def create(self, claim: Claim, actor: str = "system") -> Claim:
        self._ensure_idea_in_scope(claim.tenant_id, claim.project_id, claim.idea_id)
        if claim.claim_id in ("", None):
            claim = Claim(
                claim_id=self._next_id(), tenant_id=claim.tenant_id,
                project_id=claim.project_id, idea_id=claim.idea_id,
                claim_type=claim.claim_type, statement=claim.statement,
                epistemic_status=claim.epistemic_status,
                lifecycle_status=claim.lifecycle_status,
                confidence=claim.confidence, source=claim.source,
                version_no=claim.version_no, created_at=claim.created_at,
                updated_at=claim.updated_at)
        ts = now_iso()
        with self._db.connect() as c:
            c.execute(
                "INSERT INTO claims(claim_id,project_id,tenant_id,idea_id,claim_type,"
                "statement,epistemic_status,lifecycle_status,confidence,source,"
                "version_no,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (claim.claim_id, claim.project_id, claim.tenant_id, claim.idea_id,
                 claim.claim_type, claim.statement, claim.epistemic_status,
                 claim.lifecycle_status,
                 # v5.8.2 Commit 8：未评分写 NULL（不再落 0.5 哨兵；
                 # 旧库 0.5 读取时仍按 legacy_unscored→None）。
                 claim.confidence,
                 claim.source, claim.version_no, ts, ts))
        created = Claim(
            claim_id=claim.claim_id, tenant_id=claim.tenant_id,
            project_id=claim.project_id, idea_id=claim.idea_id,
            claim_type=claim.claim_type, statement=claim.statement,
            epistemic_status=claim.epistemic_status,
            lifecycle_status=claim.lifecycle_status,
            confidence=claim.confidence, source=claim.source,
            version_no=claim.version_no, created_at=ts, updated_at=ts)
        self._audit(actor, "claim.create", created)
        return created

    def get(self, tenant_id: str, project_id: str, claim_id: str) -> Claim:
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM claims WHERE claim_id=? AND project_id=? AND tenant_id=?",
                (claim_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise ClaimNotFoundError(claim_id)
        return self._row_to_claim(row)

    def update(self, tenant_id: str, project_id: str, claim_id: str,
               expected_version: int, actor: str = "system",
               **fields: Any) -> Claim:
        if not fields:
            raise ValueError("no editable fields provided")
        bad = set(fields) - _CLAIM_EDITABLE
        if bad:
            raise ValueError(f"not editable fields: {sorted(bad)}")
        if "claim_type" in fields and fields["claim_type"] not in CLAIM_TYPES:
            raise ValueError(f"invalid claim_type {fields['claim_type']!r}")
        if "epistemic_status" in fields and fields["epistemic_status"] not in FACT_STATUSES:
            raise ValueError(
                f"invalid epistemic_status {fields['epistemic_status']!r}")
        if ("lifecycle_status" in fields
                and fields["lifecycle_status"] not in CLAIM_LIFECYCLE_STATUSES):
            raise ValueError(
                f"invalid lifecycle_status {fields['lifecycle_status']!r}")
        if "confidence" in fields and fields["confidence"] is not None \
                and not 0.0 <= fields["confidence"] <= 1.0:
            raise ValueError("confidence must be in [0,1] or None (unscored)")
        before = self.get(tenant_id, project_id, claim_id)
        set_cols = sorted(fields)
        # v5.8.2 Commit 8：未评分写 NULL（不再落 0.5 哨兵）
        params: list[Any] = []
        for k in set_cols:
            v = fields[k]
            params.append(v)
        set_sql = ", ".join([f"{col}=?" for col in set_cols]
                              + ["updated_at=?", "version_no=version_no+1"])
        params = params + [now_iso()]
        with self._db.connect() as c:
            cur = c.execute(
                f"UPDATE claims SET {set_sql} "
                "WHERE claim_id=? AND project_id=? AND tenant_id=? AND version_no=?",
                params + [claim_id, project_id, tenant_id, expected_version])
            if cur.rowcount != 1:
                raise ClaimOptimisticLockError(
                    f"claim {claim_id} optimistic-lock conflict (version mismatch)")
        after = self.get(tenant_id, project_id, claim_id)
        self._audit(actor, "claim.update", after, before=before.to_dict())
        return after

    def list(self, tenant_id: str, project_id: str,
             idea_id: str | None = None) -> list[Claim]:
        sql = "SELECT * FROM claims WHERE project_id=? AND tenant_id=?"
        params: list[Any] = [project_id, tenant_id]
        if idea_id is not None:
            sql += " AND idea_id=?"
            params.append(idea_id)
        sql += " ORDER BY created_at"
        with self._db.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [self._row_to_claim(r) for r in rows]


__all__ = [
    "ClaimService",
    "ClaimNotFoundError",
    "ClaimOptimisticLockError",
    "ClaimScopeError",
]
