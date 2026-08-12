"""Immutable ProductDefinitionSnapshot（v5.9.1 + v5.9.2）。

**职责**：冻结一次 Product Definition 候选状态，供 Gate / Owner Decision /
Commit / Audit 引用。**不是第二个 Truth Store** —— snapshot 存 refs
（``[{id, version}]``）+ 关键统计，不复制对象正文。

**v5.9.2 Snapshot Closed-World（P0-01/02）**：
- :func:`active_definition_set`（``definition_membership_policy_v1``）——
  create_snapshot **只冻结 active definition set**：
  ``selected Opportunity → 其 active/candidate Principles → 其 Requirements →
  其 Features``；排除 archived / superseded / rejected；
- :meth:`is_stale` 比较 **set equality**（P0-01）：snapshot active IDs ==
  current active IDs；任何新增/删除/archive/supersede/selection change/
  version change → STALE（不再只看 refs 存在 + version）；
- ``upstream_basis_hash``（P0-08）：覆盖 upstream lineage basis
  （claims / reviewed relations / insights / selected opportunity / PI
  versions）—— Claim/EvidenceRelation 变化即使传播漏掉，freshness 仍有
  第二道防线；
- immutable：只 INSERT，无 UPDATE content 路径；修改产品定义 → 新 snapshot。

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
from .service import ProductIntelligenceService

# 显式 schema 版本（hash payload 的一部分）
SNAPSHOT_SCHEMA_VERSION = "product_definition_snapshot_v1"
# lifecycle
SNAPSHOT_FROZEN = "frozen"
SNAPSHOT_STALE = "stale"
SNAPSHOT_COMMITTED = "committed"
SNAPSHOT_STATUSES = frozenset({SNAPSHOT_FROZEN, SNAPSHOT_STALE,
                               SNAPSHOT_COMMITTED})

_SELECTION_SELECTED = "selected"
_SELECTION_REJECTED = "rejected"

# 排除生命周期（closed-world：archived/superseded 永不进入 snapshot）
_EXCLUDED_LIFECYCLE = frozenset({"archived", "superseded"})


# ---------------------------------------------------------------------------
# definition_membership_policy_v1（§7：active definition set 唯一来源）
# ---------------------------------------------------------------------------
def active_definition_set(pi: ProductIntelligenceService,
                          tenant_id: str,
                          project_id: str) -> dict[str, Any]:
    """定义 membership policy v1：``selected Opportunity → 其 principles →
    requirements → features``（排除 archived/superseded/rejected）。

    create_snapshot 与 is_stale **共用同一 policy**（两边集合语义一致，
    set equality 才可比）。
    """
    selected = [
        o for o in pi.list_opportunities(tenant_id, project_id)
        if o.lifecycle_status not in _EXCLUDED_LIFECYCLE
        and o.selection_status == _SELECTION_SELECTED]
    if len(selected) > 1:
        raise ValueError(
            "multiple selected Opportunities "
            f"({[o.opportunity_id for o in selected]}); exactly one selected "
            "required (P0-07)")
    opp = selected[0] if selected else None

    principles = [
        p for p in pi.list_principles(tenant_id, project_id)
        if p.lifecycle_status not in _EXCLUDED_LIFECYCLE
        and (opp is not None and p.opportunity_id == opp.opportunity_id)]
    principle_ids = {p.principle_id for p in principles}

    requirements = [
        r for r in pi.list_requirements(tenant_id, project_id)
        if r.lifecycle_status not in _EXCLUDED_LIFECYCLE
        and set(r.source_principle_ids) & principle_ids]
    requirement_ids = {r.requirement_id for r in requirements}

    features = [
        f for f in pi.list_features(tenant_id, project_id)
        if f.lifecycle_status not in _EXCLUDED_LIFECYCLE
        and set(f.source_requirement_ids) & requirement_ids]

    return {"opportunity": opp, "principles": principles,
            "requirements": requirements, "features": features}


def _ref_id(obj: Any) -> str:
    for attr in ("principle_id", "requirement_id", "feature_id",
                 "opportunity_id", "insight_id", "claim_id",
                 "relation_id"):
        val = getattr(obj, attr, None)
        if val:
            return val
    return ""


def _refs(objs: list[Any]) -> list[dict[str, Any]]:
    return [{"id": _ref_id(o), "version": o.version_no} for o in objs]


# ---------------------------------------------------------------------------
# upstream basis（§35：第二道防线）
# ---------------------------------------------------------------------------
def compute_upstream_basis(db: AIPDStateDB, idea_id: str,
                           tenant_id: str, project_id: str,
                           active: dict[str, Any]) -> str:
    """冻结时上游 lineage basis 的 deterministic fingerprint。

    覆盖：claims(id+version) + reviewed relations(id+version+status+type) +
    insights(id+version) + selected opportunity(id+version) + PI versions。
    """
    from aipd_os.idea.claim_service import ClaimService

    claims = ClaimService(db).list(tenant_id, project_id)
    # reviewed relations（直接查 canonical 表；EvidenceRelationService 无
    # 全量 list API）
    with db.connect() as c:
        rows = c.execute(
            "SELECT relation_id, version_no, review_status, relation_type "
            "FROM claim_evidence_relations WHERE project_id=? AND tenant_id=? "
            "AND review_status='reviewed'",
            (project_id, tenant_id)).fetchall()
    pi = active["_pi"]
    insights = pi.list_insights(tenant_id, project_id)

    payload = {
        "schema": "product_definition_upstream_basis_v1",
        "idea_id": idea_id,
        "claims": sorted(
            [{"id": c.claim_id, "version": c.version_no,
              "statement": c.statement} for c in claims],
            key=lambda x: x["id"]),
        "relations": sorted(
            [{"id": r["relation_id"], "version": r["version_no"],
              "review_status": r["review_status"],
              "relation_type": r["relation_type"]} for r in rows],
            key=lambda x: x["id"]),
        "insights": sorted(
            [{"id": i.insight_id, "version": i.version_no}
             for i in insights], key=lambda x: x["id"]),
        "opportunity": (None if active["opportunity"] is None else {
            "id": active["opportunity"].opportunity_id,
            "version": active["opportunity"].version_no}),
        "principles": sorted(
            [{"id": _ref_id(p), "version": p.version_no}
             for p in active["principles"]], key=lambda x: x["id"]),
        "requirements": sorted(
            [{"id": _ref_id(r), "version": r.version_no}
             for r in active["requirements"]], key=lambda x: x["id"]),
        "features": sorted(
            [{"id": _ref_id(f), "version": f.version_no}
             for f in active["features"]], key=lambda x: x["id"]),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    upstream_basis_hash: str = ""
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
            "upstream_basis_hash": self.upstream_basis_hash,
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
            upstream_basis_hash=d.get("upstream_basis_hash", ""),
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
        """从当前 live active definition set 冻结 snapshot（closed-world）。

        只冻结 selected Opportunity → 其 principles → requirements →
        features（排除 archived/superseded/rejected，P0-02）；hash 覆盖
        id+version；upstream_basis_hash 覆盖上游 lineage basis（P0-08）。
        """
        active = active_definition_set(self._pi, tenant_id, project_id)
        active["_pi"] = self._pi
        opp = active["opportunity"]
        principles = active["principles"]
        requirements = active["requirements"]
        features = active["features"]

        ideas = _ideas(self._db, tenant_id, project_id)
        idea_id = ideas[-1].idea_id if ideas else ""

        snap = ProductDefinitionSnapshot(
            snapshot_id="", tenant_id=tenant_id, project_id=project_id,
            idea_id=idea_id,
            opportunity_id=opp.opportunity_id if opp else "",
            opportunity_version=opp.version_no if opp else None,
            principle_refs=_refs(principles),
            requirement_refs=_refs(requirements),
            feature_refs=_refs(features),
            critical_unknown_refs=[
                {"id": _ref_id(r), "version": r.version_no}
                for r in requirements
                if r.criticality == CRITICALITY_CRITICAL
                and r.epistemic_status == "U"],
            conflict_refs=[
                {"id": _ref_id(r), "version": r.version_no}
                for r in requirements
                if r.definition_status == "CONFLICT"],
            source_projection_version=SNAPSHOT_SCHEMA_VERSION,
            created_by=actor,
        )
        snap.snapshot_id = self._db.next_sequence("product_snapshot", "SNAP")
        snap.content_hash = snap.compute_hash()
        snap.upstream_basis_hash = compute_upstream_basis(
            self._db, idea_id, tenant_id, project_id, active)
        snap.created_at = now_iso()
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO product_definition_snapshots(snapshot_id,"
                "project_id,tenant_id,idea_id,opportunity_id,"
                "opportunity_version,principle_refs_json,requirement_refs_json,"
                "feature_refs_json,critical_unknown_refs_json,conflict_refs_json,"
                "source_projection_version,content_hash,upstream_basis_hash,"
                "lifecycle_status,created_at,created_by)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (snap.snapshot_id, snap.project_id, snap.tenant_id,
                 snap.idea_id, snap.opportunity_id, snap.opportunity_version,
                 _json(snap.principle_refs), _json(snap.requirement_refs),
                 _json(snap.feature_refs), _json(snap.critical_unknown_refs),
                 _json(snap.conflict_refs), snap.source_projection_version,
                 snap.content_hash, snap.upstream_basis_hash,
                 snap.lifecycle_status, snap.created_at, snap.created_by))
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
        """P0-01/08：set equality + version + opportunity + basis 变化 →
        STALE。

        - active 集合（同一 membership policy）：ID 集合变化（新增/删除/
          archive/supersede/selection change）→ STALE；
        - 任一 ref version 变化 → STALE；
        - conflict set 变化 → STALE；
        - upstream_basis_hash 变化（Claim/Relation/Insight 上游）→ STALE
          （第二道防线；旧 snapshot basis='' 时跳过）。
        """
        reasons: list[str] = []
        try:
            live_active = active_definition_set(self._pi, tenant_id,
                                                project_id)
        except ValueError as exc:
            return True, [f"active set invalid: {exc}"]
        live_opp = live_active["opportunity"]
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

        # set equality（§9：任何新增/删除都 STALE）
        live_sets = {
            "principle": {_ref_id(p) for p in live_active["principles"]},
            "requirement": {_ref_id(r) for r in live_active["requirements"]},
            "feature": {_ref_id(f) for f in live_active["features"]},
        }
        snap_sets = {
            "principle": {r.get("id") for r in snap.principle_refs
                          if r.get("id")},
            "requirement": {r.get("id") for r in snap.requirement_refs
                            if r.get("id")},
            "feature": {r.get("id") for r in snap.feature_refs
                        if r.get("id")},
        }
        for kind in ("principle", "requirement", "feature"):
            if snap_sets[kind] != live_sets[kind]:
                added = sorted(live_sets[kind] - snap_sets[kind])
                removed = sorted(snap_sets[kind] - live_sets[kind])
                reasons.append(
                    f"active {kind} set changed: +{added} -{removed}")

        # version 变化
        live_objs = {
            "principle": live_active["principles"],
            "requirement": live_active["requirements"],
            "feature": live_active["features"],
        }
        for kind, refs in (("principle", snap.principle_refs),
                           ("requirement", snap.requirement_refs),
                           ("feature", snap.feature_refs)):
            for r in refs:
                obj = _find_by_id(live_objs[kind], r.get("id", ""))
                if obj is not None and obj.version_no != r.get("version"):
                    reasons.append(
                        f"{kind} {r.get('id')} version changed "
                        f"{r.get('version')} -> {obj.version_no}")

        # 冲突集合
        live_conflicts = {
            _ref_id(r) for r in live_active["requirements"]
            if r.definition_status == "CONFLICT"}
        snap_conflicts: set[str] = {r["id"] for r in snap.conflict_refs
                                    if isinstance(r.get("id"), str)}
        if live_conflicts != snap_conflicts:
            reasons.append(
                f"conflict set changed: {sorted(snap_conflicts)} -> "
                f"{sorted(live_conflicts)}")

        # upstream basis（P0-08 第二道防线）
        if snap.upstream_basis_hash:
            active_basis = dict(live_active)
            active_basis["_pi"] = self._pi
            ideas = _ideas(self._db, tenant_id, project_id)
            idea_id = ideas[-1].idea_id if ideas else ""
            current_basis = compute_upstream_basis(
                self._db, idea_id, tenant_id, project_id, active_basis)
            if current_basis != snap.upstream_basis_hash:
                reasons.append("upstream basis changed "
                               "(claim/relation/insight lineage)")
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
    "active_definition_set",
    "compute_upstream_basis",
]
