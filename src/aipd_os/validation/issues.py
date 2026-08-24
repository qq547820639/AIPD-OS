"""Canonical Issue / Corrective Action Domain（v5.10 Milestone 2）。

一等实体：
- Issue：验证失败、质量问题或其他需要纠正的事项
- CorrectiveAction：针对 Issue 的纠正措施

Issue 不能通过简单设置 status=CLOSED 绕过验证。
Blocking validation failure 自动形成或关联 blocking issue 时，要求 idempotent。

Issue close 至少要求：
- corrective action/disposition 已记录
- 若需要 revalidation，存在针对正确 artifact revision 的有效新结果
- blocking condition 已解除
- audit trail 完整
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Issue 状态
# ---------------------------------------------------------------------------
ISSUE_OPEN = "OPEN"
ISSUE_IN_PROGRESS = "IN_PROGRESS"
ISSUE_RESOLVED = "RESOLVED"
ISSUE_CLOSED = "CLOSED"
ISSUE_WAIVED = "WAIVED"
ISSUE_STATUSES = frozenset({
    ISSUE_OPEN, ISSUE_IN_PROGRESS, ISSUE_RESOLVED, ISSUE_CLOSED, ISSUE_WAIVED,
})

# Issue 严重程度
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_MAJOR = "MAJOR"
SEVERITY_MINOR = "MINOR"
SEVERITY_INFO = "INFO"
SEVERITIES = frozenset({
    SEVERITY_CRITICAL, SEVERITY_MAJOR, SEVERITY_MINOR, SEVERITY_INFO,
})

# Issue 优先级
PRIORITY_P0 = "P0"
PRIORITY_P1 = "P1"
PRIORITY_P2 = "P2"
PRIORITY_P3 = "P3"
PRIORITIES = frozenset({PRIORITY_P0, PRIORITY_P1, PRIORITY_P2, PRIORITY_P3})

# Corrective Action 状态
ACTION_OPEN = "OPEN"
ACTION_IN_PROGRESS = "IN_PROGRESS"
ACTION_COMPLETED = "COMPLETED"
ACTION_VERIFIED = "VERIFIED"
ACTION_STATUSES = frozenset({
    ACTION_OPEN, ACTION_IN_PROGRESS, ACTION_COMPLETED, ACTION_VERIFIED,
})

# Disposition（处置方式）
DISPOSITION_FIX = "FIX"
DISPOSITION_WAIVE = "WAIVE"
DISPOSITION_DESIGN_CHANGE = "DESIGN_CHANGE"
DISPOSITION_NOT_APPLICABLE = "NOT_APPLICABLE"
DISPOSITIONS = frozenset({
    DISPOSITION_FIX, DISPOSITION_WAIVE,
    DISPOSITION_DESIGN_CHANGE, DISPOSITION_NOT_APPLICABLE,
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _parse_json_list(raw: Any) -> list[str]:
    """兼容 DB 行（json 字符串）与模型 dict（原生 list）。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return []


def _parse_audit_trail(raw: Any) -> list[dict[str, Any]]:
    """解析审计轨迹（DB json 字符串或原生 list[dict]）。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [dict(x) if isinstance(x, dict) else {} for x in raw]
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, list):
        return [dict(x) if isinstance(x, dict) else {} for x in parsed]
    return []


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    """验证失败、质量问题或其他需要纠正的事项。

    核心字段：
    - tenant_id, project_id：作用域
    - issue_id：标识
    - title, description：描述
    - source_object_type/id：来源对象
    - validation_result_ref：关联验证结果
    - severity, priority：严重程度和优先级
    - blocking_release：是否阻塞发布
    - status：状态
    - owner：负责人
    - root_cause：根因
    - disposition：处置方式
    - version/audit：版本和审计
    """

    issue_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    title: str = ""
    description: str = ""
    source_object_type: str = ""
    source_object_id: str = ""
    validation_result_ref: str = ""
    severity: str = SEVERITY_MAJOR
    priority: str = PRIORITY_P1
    blocking_release: bool = False
    status: str = ISSUE_OPEN
    owner: str = ""
    opened_at: str | None = None
    resolved_at: str | None = None
    closed_at: str | None = None
    root_cause: str = ""
    disposition: str = ""
    corrective_action_refs: list[str] = field(default_factory=list)
    revalidation_required: bool = False
    revalidation_result_ref: str = ""
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"invalid severity {self.severity!r}")
        if self.priority not in PRIORITIES:
            raise ValueError(f"invalid priority {self.priority!r}")
        if self.status not in ISSUE_STATUSES:
            raise ValueError(f"invalid status {self.status!r}")

    def can_close(self) -> tuple[bool, str]:
        """检查 Issue 是否可以关闭。

        返回 (can_close, reason)。
        """
        if self.status == ISSUE_CLOSED:
            return False, "already closed"
        if self.status == ISSUE_WAIVED:
            return True, "waived"
        if not self.disposition:
            return False, "disposition not recorded"
        if self.revalidation_required and not self.revalidation_result_ref:
            return False, "revalidation required but no result recorded"
        if self.blocking_release and self.status != ISSUE_RESOLVED:
            return False, "blocking issue not resolved"
        return True, "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "title": self.title,
            "description": self.description,
            "source_object_type": self.source_object_type,
            "source_object_id": self.source_object_id,
            "validation_result_ref": self.validation_result_ref,
            "severity": self.severity, "priority": self.priority,
            "blocking_release": self.blocking_release,
            "status": self.status, "owner": self.owner,
            "opened_at": self.opened_at, "resolved_at": self.resolved_at,
            "closed_at": self.closed_at, "root_cause": self.root_cause,
            "disposition": self.disposition,
            "corrective_action_refs": self.corrective_action_refs,
            "revalidation_required": self.revalidation_required,
            "revalidation_result_ref": self.revalidation_result_ref,
            "audit_trail": self.audit_trail,
            "version": self.version,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Issue:
        return cls(
            issue_id=data["issue_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            source_object_type=data.get("source_object_type", ""),
            source_object_id=data.get("source_object_id", ""),
            validation_result_ref=data.get("validation_result_ref", ""),
            severity=data.get("severity", SEVERITY_MAJOR),
            priority=data.get("priority", PRIORITY_P1),
            blocking_release=bool(data.get("blocking_release", False)),
            status=data.get("status", ISSUE_OPEN),
            owner=data.get("owner", ""),
            opened_at=data.get("opened_at"),
            resolved_at=data.get("resolved_at"),
            closed_at=data.get("closed_at"),
            root_cause=data.get("root_cause", ""),
            disposition=data.get("disposition", ""),
            corrective_action_refs=_parse_json_list(
                data.get("corrective_action_refs_json")
                or data.get("corrective_action_refs")),
            revalidation_required=bool(data.get("revalidation_required", False)),
            revalidation_result_ref=data.get("revalidation_result_ref", ""),
            audit_trail=_parse_audit_trail(
                data.get("audit_trail_json")
                or data.get("audit_trail")),
            version=data.get("version", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# CorrectiveAction
# ---------------------------------------------------------------------------

@dataclass
class CorrectiveAction:
    """针对 Issue 的纠正措施。

    核心字段：
    - action_id：标识
    - issue_id：关联 Issue
    - description：措施描述
    - affected_objects：受影响对象
    - change：变更内容
    - revalidation_requirement：重新验证要求
    - verification_result_ref：验证结果引用
    - status：状态
    """

    action_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    issue_id: str = ""
    description: str = ""
    affected_objects: list[str] = field(default_factory=list)
    change: str = ""
    revalidation_requirement: str = ""
    verification_result_ref: str = ""
    status: str = ACTION_OPEN
    owner: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    verified_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ACTION_STATUSES:
            raise ValueError(f"invalid status {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "issue_id": self.issue_id,
            "description": self.description,
            "affected_objects": self.affected_objects,
            "change": self.change,
            "revalidation_requirement": self.revalidation_requirement,
            "verification_result_ref": self.verification_result_ref,
            "status": self.status, "owner": self.owner,
            "started_at": self.started_at, "completed_at": self.completed_at,
            "verified_at": self.verified_at,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorrectiveAction:
        return cls(
            action_id=data["action_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            issue_id=data.get("issue_id", ""),
            description=data.get("description", ""),
            affected_objects=_parse_json_list(
                data.get("affected_objects_json")
                or data.get("affected_objects")),
            change=data.get("change", ""),
            revalidation_requirement=data.get("revalidation_requirement", ""),
            verification_result_ref=data.get("verification_result_ref", ""),
            status=data.get("status", ACTION_OPEN),
            owner=data.get("owner", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            verified_at=data.get("verified_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# IssueService
# ---------------------------------------------------------------------------

class IssueService:
    """Issue / Corrective Action 服务。

    通过 AIPDStateDB 的 issues / corrective_actions 表存储。
    不创建新的独立数据库。
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Issue CRUD
    # ------------------------------------------------------------------

    def create_issue(
        self,
        tenant_id: str,
        project_id: str,
        title: str,
        description: str = "",
        severity: str = SEVERITY_MAJOR,
        priority: str = PRIORITY_P1,
        blocking_release: bool = False,
        source_object_type: str = "",
        source_object_id: str = "",
        validation_result_ref: str = "",
        owner: str = "",
    ) -> Issue:
        """创建 Issue。

        Idempotent：相同 validation_result_ref 不会创建重复 Issue。
        """
        # 检查是否已存在关联同一 validation_result_ref 的 Issue
        if validation_result_ref:
            existing = self._find_by_validation_ref(
                tenant_id, project_id, validation_result_ref)
            if existing:
                return existing

        now = _now_iso()
        issue = Issue(
            issue_id=_new_id("issue"),
            tenant_id=tenant_id,
            project_id=project_id,
            title=title,
            description=description,
            severity=severity,
            priority=priority,
            blocking_release=blocking_release,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            validation_result_ref=validation_result_ref,
            owner=owner,
            opened_at=now,
            audit_trail=[{"action": "created", "at": now, "by": "system"}],
            created_at=now,
            updated_at=now,
        )

        import json as _json
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO issues "
                "(issue_id, tenant_id, project_id, title, description, "
                "source_object_type, source_object_id, validation_result_ref, "
                "severity, priority, blocking_release, status, owner, "
                "opened_at, resolved_at, closed_at, root_cause, disposition, "
                "corrective_action_refs_json, revalidation_required, "
                "revalidation_result_ref, audit_trail_json, version, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (issue.issue_id, issue.tenant_id, issue.project_id,
                 issue.title, issue.description, issue.source_object_type,
                 issue.source_object_id, issue.validation_result_ref,
                 issue.severity, issue.priority, int(issue.blocking_release),
                 issue.status, issue.owner, issue.opened_at, issue.resolved_at,
                 issue.closed_at, issue.root_cause, issue.disposition,
                 _json.dumps(issue.corrective_action_refs),
                 int(issue.revalidation_required),
                 issue.revalidation_result_ref,
                 _json.dumps(issue.audit_trail),
                 issue.version, issue.created_at, issue.updated_at),
            )
        return issue

    def get_issue(self, tenant_id: str, project_id: str,
                  issue_id: str) -> Issue | None:
        """获取 Issue。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM issues "
                "WHERE tenant_id=? AND project_id=? AND issue_id=?",
                (tenant_id, project_id, issue_id),
            ).fetchone()
        if row is None:
            return None
        return Issue.from_dict(dict(row))

    def list_issues(self, tenant_id: str, project_id: str,
                    status: str | None = None,
                    blocking_only: bool = False) -> list[Issue]:
        """列出 Issue。"""
        query = "SELECT * FROM issues WHERE tenant_id=? AND project_id=?"
        params: list[Any] = [tenant_id, project_id]
        if status:
            query += " AND status=?"
            params.append(status)
        if blocking_only:
            query += " AND blocking_release=1"
        query += " ORDER BY created_at DESC"

        with self._db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Issue.from_dict(dict(r)) for r in rows]

    def update_issue_status(
        self,
        tenant_id: str,
        project_id: str,
        issue_id: str,
        new_status: str,
        reason: str = "",
        actor: str = "system",
    ) -> Issue | None:
        """更新 Issue 状态。

        关闭时检查 can_close() 条件。
        """
        if new_status not in ISSUE_STATUSES:
            raise ValueError(f"invalid status {new_status!r}")

        issue = self.get_issue(tenant_id, project_id, issue_id)
        if issue is None:
            return None

        # 尝试关闭时检查条件
        if new_status == ISSUE_CLOSED:
            can, why = issue.can_close()
            if not can:
                raise ValueError(f"cannot close issue: {why}")

        now = _now_iso()
        audit_entry = {"action": f"status_{new_status}", "at": now,
                       "by": actor, "reason": reason}
        issue.audit_trail.append(audit_entry)
        issue.status = new_status
        issue.updated_at = now

        if new_status == ISSUE_RESOLVED:
            issue.resolved_at = now
        elif new_status == ISSUE_CLOSED:
            issue.closed_at = now

        import json as _json
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE issues SET status=?, resolved_at=?, closed_at=?, "
                "audit_trail_json=?, updated_at=? "
                "WHERE tenant_id=? AND project_id=? AND issue_id=?",
                (issue.status, issue.resolved_at, issue.closed_at,
                 _json.dumps(issue.audit_trail), issue.updated_at,
                 tenant_id, project_id, issue_id),
            )
        return issue

    def set_disposition(
        self,
        tenant_id: str,
        project_id: str,
        issue_id: str,
        disposition: str,
        root_cause: str = "",
        revalidation_required: bool = False,
        actor: str = "system",
    ) -> Issue | None:
        """设置 Issue 的处置方式。"""
        if disposition not in DISPOSITIONS:
            raise ValueError(f"invalid disposition {disposition!r}")

        issue = self.get_issue(tenant_id, project_id, issue_id)
        if issue is None:
            return None

        now = _now_iso()
        issue.disposition = disposition
        issue.root_cause = root_cause
        issue.revalidation_required = revalidation_required
        issue.updated_at = now
        issue.audit_trail.append({
            "action": "set_disposition", "at": now, "by": actor,
            "disposition": disposition, "root_cause": root_cause,
        })

        import json as _json
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE issues SET disposition=?, root_cause=?, "
                "revalidation_required=?, audit_trail_json=?, updated_at=? "
                "WHERE tenant_id=? AND project_id=? AND issue_id=?",
                (issue.disposition, issue.root_cause,
                 int(issue.revalidation_required),
                 _json.dumps(issue.audit_trail), issue.updated_at,
                 tenant_id, project_id, issue_id),
            )
        return issue

    def _find_by_validation_ref(
        self, tenant_id: str, project_id: str, ref: str,
    ) -> Issue | None:
        """按 validation_result_ref 查找已有 Issue（idempotency）。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM issues "
                "WHERE tenant_id=? AND project_id=? AND validation_result_ref=? "
                "AND status NOT IN ('CLOSED','WAIVED') "
                "LIMIT 1",
                (tenant_id, project_id, ref),
            ).fetchone()
        if row is None:
            return None
        return Issue.from_dict(dict(row))

    # ------------------------------------------------------------------
    # CorrectiveAction CRUD
    # ------------------------------------------------------------------

    def create_action(
        self,
        tenant_id: str,
        project_id: str,
        issue_id: str,
        description: str,
        change: str = "",
        revalidation_requirement: str = "",
        owner: str = "",
    ) -> CorrectiveAction:
        """创建纠正措施。"""
        now = _now_iso()
        action = CorrectiveAction(
            action_id=_new_id("caction"),
            tenant_id=tenant_id,
            project_id=project_id,
            issue_id=issue_id,
            description=description,
            change=change,
            revalidation_requirement=revalidation_requirement,
            owner=owner,
            started_at=now,
            created_at=now,
            updated_at=now,
        )

        import json as _json
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO corrective_actions "
                "(action_id, tenant_id, project_id, issue_id, description, "
                "affected_objects_json, change, revalidation_requirement, "
                "verification_result_ref, status, owner, started_at, "
                "completed_at, verified_at, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (action.action_id, action.tenant_id, action.project_id,
                 action.issue_id, action.description,
                 _json.dumps(action.affected_objects),
                 action.change, action.revalidation_requirement,
                 action.verification_result_ref, action.status, action.owner,
                 action.started_at, action.completed_at, action.verified_at,
                 action.created_at, action.updated_at),
            )

            # 关联到 Issue（追加 action_id 到 corrective_action_refs_json）
            row = conn.execute(
                "SELECT corrective_action_refs_json FROM issues "
                "WHERE tenant_id=? AND project_id=? AND issue_id=?",
                (tenant_id, project_id, issue_id),
            ).fetchone()
            existing_refs: list[str] = []
            if row and row[0]:
                try:
                    existing_refs = json.loads(row[0])
                except (ValueError, TypeError):
                    existing_refs = []
            if action.action_id not in existing_refs:
                existing_refs.append(action.action_id)
            conn.execute(
                "UPDATE issues SET corrective_action_refs_json=? "
                "WHERE tenant_id=? AND project_id=? AND issue_id=?",
                (_json.dumps(existing_refs),
                 tenant_id, project_id, issue_id),
            )
        return action

    def get_action(self, tenant_id: str, project_id: str,
                   action_id: str) -> CorrectiveAction | None:
        """获取纠正措施。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM corrective_actions "
                "WHERE tenant_id=? AND project_id=? AND action_id=?",
                (tenant_id, project_id, action_id),
            ).fetchone()
        if row is None:
            return None
        return CorrectiveAction.from_dict(dict(row))

    def list_actions(self, tenant_id: str, project_id: str,
                     issue_id: str | None = None) -> list[CorrectiveAction]:
        """列出纠正措施。"""
        with self._db.connect() as conn:
            if issue_id:
                rows = conn.execute(
                    "SELECT * FROM corrective_actions "
                    "WHERE tenant_id=? AND project_id=? AND issue_id=? "
                    "ORDER BY created_at",
                    (tenant_id, project_id, issue_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM corrective_actions "
                    "WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                    (tenant_id, project_id),
                ).fetchall()
        return [CorrectiveAction.from_dict(dict(r)) for r in rows]

    def complete_action(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
        verification_result_ref: str = "",
    ) -> CorrectiveAction | None:
        """完成纠正措施。"""
        now = _now_iso()
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE corrective_actions SET status=?, completed_at=?, "
                "verification_result_ref=?, updated_at=? "
                "WHERE tenant_id=? AND project_id=? AND action_id=?",
                (ACTION_COMPLETED, now, verification_result_ref, now,
                 tenant_id, project_id, action_id),
            )
            row = conn.execute(
                "SELECT * FROM corrective_actions "
                "WHERE tenant_id=? AND project_id=? AND action_id=?",
                (tenant_id, project_id, action_id),
            ).fetchone()
        if row is None:
            return None
        return CorrectiveAction.from_dict(dict(row))

    def verify_action(
        self,
        tenant_id: str,
        project_id: str,
        action_id: str,
    ) -> CorrectiveAction | None:
        """验证纠正措施（确认 revalidation 通过）。"""
        now = _now_iso()
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE corrective_actions SET status=?, verified_at=?, "
                "updated_at=? "
                "WHERE tenant_id=? AND project_id=? AND action_id=?",
                (ACTION_VERIFIED, now, now, tenant_id, project_id, action_id),
            )
            row = conn.execute(
                "SELECT * FROM corrective_actions "
                "WHERE tenant_id=? AND project_id=? AND action_id=?",
                (tenant_id, project_id, action_id),
            ).fetchone()
        if row is None:
            return None
        return CorrectiveAction.from_dict(dict(row))


__all__ = [
    "ISSUE_OPEN", "ISSUE_IN_PROGRESS", "ISSUE_RESOLVED", "ISSUE_CLOSED",
    "ISSUE_WAIVED", "ISSUE_STATUSES",
    "SEVERITY_CRITICAL", "SEVERITY_MAJOR", "SEVERITY_MINOR", "SEVERITY_INFO",
    "SEVERITIES",
    "PRIORITY_P0", "PRIORITY_P1", "PRIORITY_P2", "PRIORITY_P3", "PRIORITIES",
    "ACTION_OPEN", "ACTION_IN_PROGRESS", "ACTION_COMPLETED", "ACTION_VERIFIED",
    "ACTION_STATUSES",
    "DISPOSITION_FIX", "DISPOSITION_WAIVE", "DISPOSITION_DESIGN_CHANGE",
    "DISPOSITION_NOT_APPLICABLE", "DISPOSITIONS",
    "Issue", "CorrectiveAction", "IssueService",
]
