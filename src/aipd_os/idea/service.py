"""IdeaService：封装 AIPDStateDB 之上的 Idea CRUD（v5.8 Commit 9）。

全部操作 tenant+project scoped、audited（写入 audit_log）、versioned
（version_no 乐观锁）。不建第二个 DB —— 复用 AIPDStateDB 的 sqlite 文件
与 ideas 表（migration v2）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB, now_iso

from .models import IDEA_LIFECYCLE_STATUSES, Idea
from .serializers import parse_constraints

# 可编辑字段白名单
_IDEA_EDITABLE = {
    "title", "raw_input", "goal", "problem", "target_user", "desired_outcome",
    "constraints_json", "source", "lifecycle_status",
}


class IdeaNotFoundError(KeyError):
    """在指定 tenant/project scope 下找不到 idea（跨 scope 访问同样拒绝）。"""


class IdeaOptimisticLockError(Exception):
    """idea version_no 乐观锁冲突。"""


class IdeaService:
    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    # ------------------------------------------------------------- helpers
    def _next_id(self, prefix: str = "IDEA") -> str:
        """并发安全 ID：基于 id_sequences 表原子分配（v5.8.1 Commit 7）。

        替代旧的 scan-max（SELECT 全部 → max+1）——多 worker 并发不再产生
        重复 ID / PK 冲突。
        """
        return self._db.next_sequence("idea", prefix)

    @staticmethod
    def _row_to_idea(row: Any) -> Idea:
        d = dict(row)
        return Idea.from_dict(d)

    def _audit(self, actor: str, action: str, idea: Idea, before: Any = None) -> None:
        self._db.add_audit(actor, action, idea.project_id, idea.tenant_id,
                           before=before, after=idea.to_dict())

    # --------------------------------------------------------------- CRUD
    def create(self, idea: Idea, actor: str = "system") -> Idea:
        if idea.idea_id in ("", None):
            idea = Idea(
                idea_id=self._next_id(), tenant_id=idea.tenant_id,
                project_id=idea.project_id, title=idea.title,
                raw_input=idea.raw_input, goal=idea.goal, problem=idea.problem,
                target_user=idea.target_user, desired_outcome=idea.desired_outcome,
                constraints_json=idea.constraints_json, source=idea.source,
                lifecycle_status=idea.lifecycle_status,
                version_no=idea.version_no, created_at=idea.created_at,
                updated_at=idea.updated_at)
        ts = now_iso()
        with self._db.connect() as c:
            c.execute(
                "INSERT INTO ideas(idea_id,project_id,tenant_id,title,raw_input,"
                "goal,problem,target_user,desired_outcome,constraints_json,source,"
                "lifecycle_status,version_no,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (idea.idea_id, idea.project_id, idea.tenant_id, idea.title,
                 idea.raw_input, idea.goal, idea.problem, idea.target_user,
                 idea.desired_outcome, idea.constraints_json, idea.source,
                 idea.lifecycle_status, idea.version_no, ts, ts))
        created = Idea(
            idea_id=idea.idea_id, tenant_id=idea.tenant_id,
            project_id=idea.project_id, title=idea.title, raw_input=idea.raw_input,
            goal=idea.goal, problem=idea.problem, target_user=idea.target_user,
            desired_outcome=idea.desired_outcome,
            constraints_json=idea.constraints_json, source=idea.source,
            lifecycle_status=idea.lifecycle_status, version_no=idea.version_no,
            created_at=ts, updated_at=ts)
        self._audit(actor, "idea.create", created)
        return created

    def get(self, tenant_id: str, project_id: str, idea_id: str) -> Idea:
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM ideas WHERE idea_id=? AND project_id=? AND tenant_id=?",
                (idea_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise IdeaNotFoundError(idea_id)
        return self._row_to_idea(row)

    def update(self, tenant_id: str, project_id: str, idea_id: str,
               expected_version: int, actor: str = "system",
               **fields: Any) -> Idea:
        if not fields:
            raise ValueError("no editable fields provided")
        bad = set(fields) - _IDEA_EDITABLE
        if bad:
            raise ValueError(f"not editable fields: {sorted(bad)}")
        if ("lifecycle_status" in fields
                and fields["lifecycle_status"] not in IDEA_LIFECYCLE_STATUSES):
            raise ValueError(f"invalid lifecycle_status {fields['lifecycle_status']!r}")
        before = self.get(tenant_id, project_id, idea_id)
        set_cols = sorted(fields)
        set_sql = ", ".join([f"{col}=?" for col in set_cols]
                              + ["updated_at=?", "version_no=version_no+1"])
        params = [fields[k] for k in set_cols] + [now_iso()]
        with self._db.connect() as c:
            cur = c.execute(
                f"UPDATE ideas SET {set_sql} "
                "WHERE idea_id=? AND project_id=? AND tenant_id=? AND version_no=?",
                params + [idea_id, project_id, tenant_id, expected_version])
            if cur.rowcount != 1:
                raise IdeaOptimisticLockError(
                    f"idea {idea_id} optimistic-lock conflict (version mismatch)")
        after = self.get(tenant_id, project_id, idea_id)
        self._audit(actor, "idea.update", after, before=before.to_dict())
        return after

    def archive(self, tenant_id: str, project_id: str, idea_id: str,
                expected_version: int, actor: str = "system") -> Idea:
        """归档 Idea（lifecycle_status → archived）。"""
        return self.update(tenant_id, project_id, idea_id, expected_version,
                           actor=actor, lifecycle_status="archived")

    def list(self, tenant_id: str, project_id: str) -> list[Idea]:
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM ideas WHERE project_id=? AND tenant_id=? ORDER BY created_at",
                (project_id, tenant_id)).fetchall()
        return [self._row_to_idea(r) for r in rows]

    def list_ids(self, tenant_id: str, project_id: str) -> list[str]:
        return [i.idea_id for i in self.list(tenant_id, project_id)]

    # ------------------------------------------------------- constraints
    def get_constraints(self, tenant_id: str, project_id: str,
                        idea_id: str) -> list[str]:
        """读取 Idea 的约束列表（经 serializer 解析，兼容旧 repr 遗留数据）。"""
        idea = self.get(tenant_id, project_id, idea_id)
        return parse_constraints(idea.constraints_json)


__all__ = [
    "IdeaService",
    "IdeaNotFoundError",
    "IdeaOptimisticLockError",
]
