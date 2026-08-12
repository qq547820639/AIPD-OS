"""Immutable ProductDefinitionSnapshot（v5.9.1，§10-12/30）。

**职责**：冻结一次 Product Definition 候选状态，供 Gate / Owner Decision /
Commit / Audit 引用。**不是第二个 Truth Store** —— snapshot 存 refs
（``[{id, version}]``）+ 关键统计，不复制对象正文。

- immutable：只 INSERT，无 UPDATE 路径；产品定义修改 → 创建新 snapshot；
- deterministic hash：SHA-256(canonical JSON)，schema 显式版本
  （``product_definition_snapshot_v1``）；**hash 覆盖 id + version** ——
  同 id 更新后 version 变化 → hash 变化 → stale 检测真实；
- stale 检测：opportunity 选择 / 任一 ref version / 冲突集合 与 live 对比；
  旧 snapshot 标记 stale 后，其旧审批立即不再有效（P0-02/30）。

数据流（§12）：Projection → create_snapshot() → immutable Snapshot →
evaluate(snapshot) → OwnerDecision(snapshot) → commit(snapshot)。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from aipd_os.state.db import AIPDStateDB, now_iso

from .models import CRITICALITY_CRITICAL
from .service import (
    ProductIntelligenceService,
)

# 显式 schema 版本（hash payload 的一部分）
SNAPSHOT_SCHEMA_VERSION = "product_definition_snapshot_v1"
# lifecycle
SNAPSHOT_FROZEN = "frozen"
SNAPSHOT_STALE = "stale"
SNAPSHOT_COMMITTED = "committed"
SNAPSHOT_STATUSES = frozenset({SNAPSHOT_FROZEN, SNAPSHOT_STALE,
                               SNAPSHOT_COMMITTED})

_SELECTION_SELECTED = "selected"


@dataclass
class ProductDefinitionSnapshot:
    """冻结的 Product Definition 候选（不可变）。"""

    snapshot_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    idea_id: str = ""
    opportunity_id: str = ""
    opportunity_version: int | None = None
    principle_refs: list[dict[str, Any]] = field(default_factory=list)
    requirement_refs: list[dict[str, Any]] = field(default_factory=list)
    feature_refs: list[dict[str, Any]] = field(default_factory=list)
    critical_unknown_refs: list[dict[str, Any]] = field(default_factory=list)
    conflict_refs: list[dict[str, Any]] = field(default_factory=list)
    source_projection_version: str = SNAPSHOT_SCHEMA_VERSION
    content_hash: str = ""
    lifecycle_status: str = SNAPSHOT_FROZEN
    created_at: str | None = None
    created_by: str = "system"

    def __post_init__(self) -> None:
        if self.lifecycle_status not in SNAPSHOT_STATUSES:
            raise ValueError(
                f"invalid snapshot lifecycle_status {self.lifecycle_status!r}")

    # ------------------------------------------------------------- content
    def content_payload(self) -> dict[str, Any]:
        """canonical hash payload（**覆盖 id + version**，不只有 id）。"""
        return {
            "schema": SNAPSHOT_SCHEMA_VERSION,
            "idea_id": self.idea_id,
            "opportunity": {
                "id": self.opportunity_id,
                "version": self.opportunity_version,
            },
            "principles": sorted(self.principle_refs,
                                 key=lambda r: r.get("id", "")),
            "requirements": sorted(self.requirement_refs,
                                   key=lambda r: r.get("id", "")),
            "features": sorted(self.feature_refs,
                               key=lambda r: r.get("id", "")),
            "critical_unknowns": sorted(self.critical_unknown_refs,
                                        key=lambda r: r.get("id", "")),
            "conflicts": sorted(self.conflict_refs,
                                key=lambda r: r.get("id", "")),
            "source_projection_version": self.source_projection_version,
        }

    def compute_hash(self) -> str:
        """deterministic SHA-256：sort_keys + stable arrays + 显式 schema。"""
        canonical = json.dumps(self.content_payload(), ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_hash(self) -> bool:
        return self.compute_hash() == self.content_hash

    # ------------------------------------------------------------ io
    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "idea_id": self.idea_id,
            "opportunity_id": self.opportunity_id,
            "opportunity_version": self.opportunity_version,
            "principle_refs": self.principle_refs,
            "requirement_refs": self.requirement_refs,
            "feature_refs": self.feature_refs,
            "critical_unknown_refs": self.critical_unknown_refs,
            "conflict_refs": self.conflict_refs,
            "source_projection_version": self.source_projection_version,
            "content_hash": self.content_hash,
            "lifecycle_status": self.lifecycle_status,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProductDefinitionSnapshot:
        return cls(
            snapshot_id=d["snapshot_id"],
            tenant_id=d.get("tenant_id", "default"),
            project_id=d.get("project_id", "default"),
            idea_id=d.get("idea_id", ""),
            opportunity_id=d.get("opportunity_id", ""),
            opportunity_version=d.get("opportunity_version"),
            principle_refs=_parse_refs(d.get("principle_refs_json")
                                       or d.get("principle_refs")),
            requirement_refs=_parse_refs(d.get("requirement_refs_json")
                                         or d.get("requirement_refs")),
            feature_refs=_parse_refs(d.get("feature_refs_json")
                                     or d.get("feature_refs")),
            critical_unknown_refs=_parse_refs(
                d.get("critical_unknown_refs_json")
                or d.get("critical_unknown_refs")),
            conflict_refs=_parse_refs(d.get("conflict_refs_json")
                                      or d.get("conflict_refs")),
            source_projection_version=d.get("source_projection_version",
                                            SNAPSHOT_SCHEMA_VERSION),
            content_hash=d.get("content_hash", ""),
            lifecycle_status=d.get("lifecycle_status", SNAPSHOT_FROZEN),
            created_at=d.get("created_at"),
            created_by=d.get("created_by", "system"),
        )


def _parse_refs(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [dict(r) for r in raw]
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [dict(r) for r in parsed] if isinstance(parsed, list) else []


class SnapshotNotFoundError(KeyError):
    """找不到 snapshot。"""


class SnapshotImmutableError(RuntimeError):
    """snapshot 不可变：禁止 UPDATE content。"""


class ProductDefinitionSnapshotService:
    """snapshot 的冻结 / 读取 / stale 检测（tenant+project scoped）。"""

    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db
        self._pi = ProductIntelligenceService(db)

    # ------------------------------------------------------------ freeze
    def create_snapshot(self, tenant_id: str, project_id: str,
                        actor: str = "system") -> ProductDefinitionSnapshot:
        """从当前 live Projection 冻结 snapshot。

        数据源 = live 对象（版本化 refs）；hash 覆盖 id+version。
        """
        ideas = _ideas(self._db, tenant_id, project_id)
        idea_id = ideas[-1].idea_id if ideas else ""
        opps = [o for o in self._pi.list_opportunities(tenant_id, project_id)
                if o.lifecycle_status != "archived"
                and o.selection_status == _SELECTION_SELECTED]
        if len(opps) > 1:
            raise ValueError(
                "cannot freeze snapshot: multiple selected opportunities "
                f"({[o.opportunity_id for o in opps]}); exactly one selected "
                "required (P0-07)")
        opp = opps[0] if opps else None
        principles = self._pi.list_principles(tenant_id, project_id)
        requirements = self._pi.list_requirements(tenant_id, project_id)
        features = self._pi.list_features(tenant_id, project_id)

        def refs(objs: list[Any]) -> list[dict[str, Any]]:
            return [{"id": o.requirement_id if hasattr(o, "requirement_id")
                     else getattr(o, _id_attr(o), ""), "version": o.version_no}
                    for o in objs]

        def _id_attr(o: Any) -> str:
            for attr in ("principle_id", "feature_id"):
                if hasattr(o, attr):
                    return attr
            return ""

        snap = ProductDefinitionSnapshot(
            snapshot_id="", tenant_id=tenant_id, project_id=project_id,
            idea_id=idea_id,
            opportunity_id=opp.opportunity_id if opp else "",
            opportunity_version=opp.version_no if opp else None,
            principle_refs=refs(principles),
            requirement_refs=refs(requirements),
            feature_refs=refs(features),
            critical_unknown_refs=[
                {"id": r.requirement_id, "version": r.version_no}
                for r in requirements
                if r.criticality == CRITICALITY_CRITICAL
                and r.epistemic_status == "U"],
            conflict_refs=[
                {"id": r.requirement_id, "version": r.version_no}
                for r in requirements
                if r.definition_status == "CONFLICT"],
            source_projection_version=SNAPSHOT_SCHEMA_VERSION,
            created_by=actor,
        )
        snap.snapshot_id = self._db.next_sequence("product_snapshot", "SNAP")
        snap.content_hash = snap.compute_hash()
        snap.created_at = now_iso()
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO product_definition_snapshots(snapshot_id,"
                "project_id,tenant_id,idea_id,opportunity_id,"
                "opportunity_version,principle_refs_json,requirement_refs_json,"
                "feature_refs_json,critical_unknown_refs_json,conflict_refs_json,"
                "source_projection_version,content_hash,lifecycle_status,"
                "created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (snap.snapshot_id, snap.project_id, snap.tenant_id,
                 snap.idea_id, snap.opportunity_id, snap.opportunity_version,
                 _json(snap.principle_refs), _json(snap.requirement_refs),
                 _json(snap.feature_refs), _json(snap.critical_unknown_refs),
                 _json(snap.conflict_refs), snap.source_projection_version,
                 snap.content_hash, snap.lifecycle_status, snap.created_at,
                 snap.created_by))
            self._db.add_audit(actor, "product_definition_snapshot.create",
                               project_id, tenant_id, after=snap.to_dict())
        return snap

    # ------------------------------------------------------------- query
    def get_snapshot(self, tenant_id: str, project_id: str,
                     snapshot_id: str) -> ProductDefinitionSnapshot:
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM product_definition_snapshots WHERE "
                "snapshot_id=? AND project_id=? AND tenant_id=?",
                (snapshot_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise SnapshotNotFoundError(snapshot_id)
        return ProductDefinitionSnapshot.from_dict(dict(row))

    def list_snapshots(self, tenant_id: str,
                       project_id: str) -> list[ProductDefinitionSnapshot]:
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM product_definition_snapshots WHERE "
                "project_id=? AND tenant_id=? ORDER BY created_at",
                (project_id, tenant_id)).fetchall()
        return [ProductDefinitionSnapshot.from_dict(dict(r)) for r in rows]

    def latest_snapshot(self, tenant_id: str,
                        project_id: str) -> ProductDefinitionSnapshot | None:
        snaps = self.list_snapshots(tenant_id, project_id)
        return snaps[-1] if snaps else None

    # ------------------------------------------------------------- stale
    def is_stale(self, snap: ProductDefinitionSnapshot,
                 tenant_id: str, project_id: str) -> tuple[bool, list[str]]:
        """snapshot 与 live 对比：机会选择 / ref version / 冲突集合变化 →
        stale（旧审批立即失效，P0-30）。"""
        reasons: list[str] = []
        opps = [o for o in self._pi.list_opportunities(tenant_id, project_id)
                if o.lifecycle_status != "archived"
                and o.selection_status == _SELECTION_SELECTED]
        live_opp = opps[0] if len(opps) == 1 else None
        if live_opp is None:
            if snap.opportunity_id:
                reasons.append("selected opportunity no longer exists")
        elif live_opp.opportunity_id != snap.opportunity_id:
            reasons.append(
                f"selected opportunity changed: {snap.opportunity_id} -> "
                f"{live_opp.opportunity_id}")
        elif snap.opportunity_version is not None and \
                live_opp.version_no != snap.opportunity_version:
            reasons.append(
                f"selected opportunity version changed: "
                f"{snap.opportunity_version} -> {live_opp.version_no}")

        live: dict[str, list[Any]] = {
            "principle": list(self._pi.list_principles(tenant_id, project_id)),
            "requirement": list(self._pi.list_requirements(tenant_id,
                                                           project_id)),
            "feature": list(self._pi.list_features(tenant_id, project_id)),
        }
        for kind, refs in (("principle", snap.principle_refs),
                           ("requirement", snap.requirement_refs),
                           ("feature", snap.feature_refs)):
            for r in refs:
                obj = _find_by_id(live[kind], r.get("id", ""))
                if obj is None:
                    reasons.append(f"{kind} {r.get('id')} no longer exists")
                elif obj.version_no != r.get("version"):
                    reasons.append(
                        f"{kind} {r.get('id')} version changed "
                        f"{r.get('version')} -> {obj.version_no}")
        # 冲突集合（新冲突 / 旧冲突消失 → snapshot 需重评）
        live_conflicts = {
            r.requirement_id for r in live["requirement"]
            if r.definition_status == "CONFLICT"}
        snap_conflicts: set[str] = {r["id"] for r in snap.conflict_refs
                                    if isinstance(r.get("id"), str)}
        if live_conflicts != snap_conflicts:
            reasons.append(
                f"conflict set changed: {sorted(snap_conflicts)} -> "
                f"{sorted(live_conflicts)}")
        return bool(reasons), reasons

    def mark_stale(self, snap: ProductDefinitionSnapshot, actor: str = "system",
                   reason: str = "") -> ProductDefinitionSnapshot:
        """把 snapshot 标记 STALE（immutable content 不修改；只改生命周期
        状态位）。"""
        with self._db.transaction() as c:
            c.execute(
                "UPDATE product_definition_snapshots SET lifecycle_status=? "
                "WHERE snapshot_id=? AND project_id=? AND tenant_id=? "
                "AND lifecycle_status='frozen'",
                (SNAPSHOT_STALE, snap.snapshot_id, snap.project_id,
                 snap.tenant_id))
            self._db.add_audit(actor, "product_definition_snapshot.stale",
                               snap.project_id, snap.tenant_id,
                               after={"snapshot_id": snap.snapshot_id,
                                      "reason": reason})
        snap.lifecycle_status = SNAPSHOT_STALE
        return snap


def _ideas(db: AIPDStateDB, tenant_id: str, project_id: str) -> list[Any]:
    from aipd_os.idea.service import IdeaService
    return IdeaService(db).list(tenant_id, project_id)


def _find_by_id(objs: list[Any], obj_id: str) -> Any | None:
    for o in objs:
        for attr in ("requirement_id", "principle_id", "feature_id"):
            if getattr(o, attr, None) == obj_id:
                return o
    return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = [
    "ProductDefinitionSnapshot",
    "ProductDefinitionSnapshotService",
    "SnapshotNotFoundError",
    "SnapshotImmutableError",
    "SNAPSHOT_SCHEMA_VERSION",
    "SNAPSHOT_FROZEN",
    "SNAPSHOT_STALE",
    "SNAPSHOT_COMMITTED",
]
