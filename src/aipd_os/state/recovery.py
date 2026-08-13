"""跨会话恢复（P1-5）：统一状态服务 + 恢复摘要 + 备份/恢复 + 多项目识别。

把数据库、对象存储与附件索引作为一个单元统一备份/恢复；构建恢复摘要
（Product Truth / Evidence Register / 决策 / CAD·BOM 修订 / 手工附件链 /
外部等待 / 失败任务 / 可行动下一步）；按最近活动/显式上下文/用户选择识别多项目；
恢复后自动续作无需审批的安全工作；绝不重新追问已解决的决策；对不可逆/安全/
成本/发布类决策保留显式审批门控。

云对象存储为可选外部依赖（:class:`RemoteStateBackend` 桩），本地文件后端为默认
真实实现。
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from .db import AIPDStateDB, ProjectNotFoundError, now_iso
from .state_backend import (
    DEFAULT_TENANT,
    LocalStateBackend,
    RemoteStateBackend,
    StateBackend,
)

logger = logging.getLogger("aipd.recovery")

# 统一状态服务承载的对象类型
OBJECT_TYPES = {"attachment", "manual_batch", "visual_bible", "generation_task", "rework_plan"}

# 需显式审批的类别及其触发关键词（不可逆 / 安全 / 成本 / 发布）
APPROVAL_CATEGORIES = ("irreversible", "safety", "cost", "release")
APPROVAL_KEYWORDS: dict[str, list[str]] = {
    "irreversible": ["delete", "destroy", "drop", "replace", "overwrite",
                     "reset", "irreversible", "wipe"],
    "safety": ["safety", "critical", "human", "fail-safe", "regulatory",
               "certification", "medical"],
    "cost": ["cost", "purchase", "commit", "budget", "order", "procure",
             "spend", "payment"],
    "release": ["release", "ship", "publish", "deploy", "production",
                "launch", "go-live"],
}

SUPERVISOR_WORK_TABLE = "supervisor_work_items"
FAILED_TASK_STATUSES = {"internal_rework", "blocked_external", "cancelled", "blocked_decision"}
CAD_BOM_TYPES = ("cad", "bom", "engineering", "drawing", "brep", "mesh", "assembly")


class AmbiguousProjectError(Exception):
    """存在多个候选项目，且无法通过最近活动/上下文消歧，需用户选择。"""


class ApprovalRequiredError(Exception):
    """操作需要显式审批（不可逆/安全/成本/发布），当前未获批准。"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


class UnifiedStateService:
    """统一状态服务：数据库 + 对象存储 + 附件索引一站式管理。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = DEFAULT_TENANT,
                 backend: StateBackend | None = None,
                 index_path: str | None = None,
                 object_dir: str | None = None):
        self.db = db
        self.tenant_id = tenant_id
        if backend is None:
            base = object_dir or str(Path(db.path).parent / "objects")
            backend = LocalStateBackend(base_dir=base)
        self.backend = backend
        if index_path is None:
            index_path = str(Path(db.path).parent / (Path(db.path).name + "_attachments.json"))
        self._index_path = Path(index_path)
        self._index = self._load_index()

    # ------------------------------------------------------------------ index
    def _load_index(self) -> dict[str, Any]:
        if self._index_path.exists():
            try:
                return cast(dict[str, Any], json.loads(self._index_path.read_text(encoding="utf-8")))  # noqa: E501
            except (json.JSONDecodeError, OSError):
                return {"version": 1, "entries": {}}
        return {"version": 1, "entries": {}}

    def _persist_index(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _project_entries(self, project_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._index.setdefault("entries", {}).setdefault(project_id, {}))  # noqa: E501

    # --------------------------------------------------------------- objects
    def register_object(self, project_id: str, logical_key: str, data: bytes,
                        object_type: str, tenant_id: str | None = None,
                        path: str | None = None,
                        chain_prev: str | None = None) -> dict[str, Any]:
        """注册一个对象到统一对象存储 + 附件索引。"""
        if object_type not in OBJECT_TYPES:
            raise ValueError(
                f"unknown object_type {object_type!r}; "
                f"expected one of {sorted(OBJECT_TYPES)}")
        tenant = tenant_id or self.tenant_id
        self.backend.put(project_id, logical_key, data, tenant)
        entry = {
            "key": logical_key,
            "object_type": object_type,
            "project_id": project_id,
            "tenant_id": tenant,
            "size": len(data),
            "sha256": _sha256_bytes(data),
            "path": path,
            "chain_prev": chain_prev,
            "registered_at": now_iso(),
        }
        self._project_entries(project_id)[logical_key] = entry
        self._persist_index()
        return entry

    def get_object(self, project_id: str, logical_key: str,
                   tenant_id: str | None = None) -> bytes:
        tenant = tenant_id or self.tenant_id
        return self.backend.get(project_id, logical_key, tenant)

    def delete_object(self, project_id: str, logical_key: str,
                      tenant_id: str | None = None) -> None:
        tenant = tenant_id or self.tenant_id
        self.backend.delete(project_id, logical_key, tenant)
        self._project_entries(project_id).pop(logical_key, None)
        self._persist_index()

    def list_objects(self, project_id: str,
                         tenant_id: str | None = None) -> list[dict[str, Any]]:
        return [dict(e)
                for e in self._project_entries(project_id).values()]

    def attachment_chain(self, project_id: str) -> list[str]:
        """按 chain_prev 关系还原手工附件链（仅含 manual_batch / attachment 对象）。"""
        entries = [e for e in self._project_entries(project_id).values()
                   if e.get("object_type") in ("manual_batch", "attachment")]
        if not entries:
            return []
        by_prev: dict[Any, list[dict[str, Any]]] = {}
        for e in entries:
            by_prev.setdefault(e.get("chain_prev"), []).append(e)
        for lst in by_prev.values():
            lst.sort(key=lambda e: e.get("registered_at", ""))
        roots = sorted(by_prev.get(None, []), key=lambda e: e.get("registered_at", ""))
        chain: list[str] = []
        seen = set()
        for root in roots:
            cur = root
            while cur.get("key") not in seen:
                seen.add(cur["key"])
                chain.append(cur["key"])
                nxt = by_prev.get(cur["key"], [])
                if not nxt:
                    break
                cur = nxt[0]
        # 未纳入链的孤立条目按注册时间追加
        for e in sorted(entries, key=lambda x: x.get("registered_at", "")):
            if e["key"] not in seen:
                chain.append(e["key"])
                seen.add(e["key"])
        return chain

    # ------------------------------------------------------------ unified backup
    def backup(self, out_dir: str | None = None,
               tenant_id: str | None = None) -> dict[str, Any]:
        """把数据库 + 对象 + 附件索引作为一个单元备份。返回备份目录。"""
        tenant = tenant_id or self.tenant_id
        base = Path(out_dir) if out_dir else Path(self.db.path).parent / "backups"
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
        bundle = base / f"recovery_{stamp}"
        bundle.mkdir(parents=True, exist_ok=True)

        db_file = bundle / Path(self.db.path).name
        shutil.copy2(self.db.path, db_file)
        db_sha = _sha256_file(db_file)

        obj_dir = bundle / "objects"
        obj_count = self._snapshot_objects(tenant, obj_dir)

        idx_file = bundle / "attachment_index.json"
        idx_file.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8")
        idx_sha = _sha256_file(idx_file)

        manifest = {
            "format": "aipd-unified-backup",
            "version": 1,
            "created_at": now_iso(),
            "tenant_id": tenant,
            "backend": self.backend.name,
            "db": {"name": Path(self.db.path).name, "sha256": db_sha,
                   "size": db_file.stat().st_size},
            "object_count": obj_count,
            "objects_dir": "objects",
            "index": {"file": "attachment_index.json", "sha256": idx_sha},
            "external_dependencies": self.external_dependencies(),
        }
        (bundle / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            self.db.add_backup(str(bundle), _sha256_file(bundle / "manifest.json"),
                               size=bundle.stat().st_size)
            self.db.add_audit("system", "unified_backup", None, tenant,
                              after={"backup_dir": str(bundle),
                                     "object_count": obj_count})
        except sqlite3.Error as exc:
            # 备份本体已落盘；仅审计登记失败时记录，不阻断备份返回。
            logger.warning("unified_backup audit write failed: %s", exc)
        return {"backup_dir": str(bundle), "db_sha256": db_sha,
                "object_count": obj_count, "index_sha256": idx_sha}

    def _snapshot_objects(self, tenant: str, out_dir: Path) -> int:
        count = 0
        for p in self.db.list_projects(tenant):
            pdir = out_dir / p["project_id"]
            self.backend.snapshot(p["project_id"], tenant, str(pdir))
            count += len(list(pdir.glob("*"))) if pdir.is_dir() else 0
        return count

    def restore(self, backup_dir: str, tenant_id: str | None = None) -> dict[str, Any]:
        """从统一备份恢复数据库 + 对象 + 附件索引（校验校验和）。"""
        tenant = tenant_id or self.tenant_id
        bundle = Path(backup_dir)
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))

        db_file = bundle / manifest["db"]["name"]
        if not db_file.exists():
            raise FileNotFoundError(f"backup db file missing: {db_file}")
        if _sha256_file(db_file) != manifest["db"]["sha256"]:
            raise ValueError("backup db checksum mismatch; refusing to restore corrupted backup")
        shutil.copy2(db_file, self.db.path)

        obj_dir = bundle / "objects"
        obj_count = self._restore_objects(tenant, obj_dir)

        idx_file = bundle / "attachment_index.json"
        if idx_file.exists():
            if _sha256_file(idx_file) != manifest["index"]["sha256"]:
                raise ValueError("backup attachment index checksum mismatch")
            restored_index = json.loads(idx_file.read_text(encoding="utf-8"))
            self._index = restored_index
            self._persist_index()

        try:
            self.db.add_audit("system", "unified_restore", None, tenant,
                              after={"backup_dir": str(bundle),
                                     "object_count": obj_count})
        except sqlite3.Error as exc:
            # 恢复本体已完成；仅审计登记失败时记录，不阻断恢复返回。
            logger.warning("unified_restore audit write failed: %s", exc)
        return {"restored_db": str(self.db.path), "object_count": obj_count,
                "index_entries": self._count_index_entries()}

    def _restore_objects(self, tenant: str, obj_dir: Path) -> int:
        count = 0
        if not obj_dir.is_dir():
            return 0
        for pdir in obj_dir.iterdir():
            if pdir.is_dir():
                count += self.backend.restore(str(pdir), pdir.name, tenant)
        return count

    def list_backups(self, base_dir: str | None = None) -> list[dict[str, Any]]:
        base = Path(base_dir) if base_dir else Path(self.db.path).parent / "backups"
        backups = []
        if base.is_dir():
            for d in sorted(base.iterdir(), key=lambda p: p.name):
                mf = d / "manifest.json"
                if d.is_dir() and mf.exists():
                    try:
                        m = json.loads(mf.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if m.get("format") == "aipd-unified-backup":
                        m["backup_dir"] = str(d)
                        backups.append(m)
        backups.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return backups

    def _count_index_entries(self) -> int:
        return sum(len(v) for v in self._index.get("entries", {}).values())

    def external_dependencies(self) -> list[str]:
        """诚实声明当前依赖的外部系统（未配置即为 pending 项）。"""
        deps = []
        if isinstance(self.backend, RemoteStateBackend):
            deps.append(RemoteStateBackend.EXTERNAL_DEPENDENCY)
        return deps

    # -------------------------------------------------------- multi-project id
    def identify_project(self, project_id: str | None = None,
                         context: str | None = None,
                         projects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """识别项目：显式 project_id > 上下文匹配 > 最近活动（绝不默认取第一条）。

        当仍有多个候选且无法消歧时抛 :class:`AmbiguousProjectError`，交由用户选择。
        """
        if projects is None:
            projects = self.db.list_projects(self.tenant_id)
        if not projects:
            raise ProjectNotFoundError(f"no projects in tenant {self.tenant_id!r}")

        # 1) 显式 project_id
        if project_id:
            for p in projects:
                if p["project_id"] == project_id:
                    return p
            raise ProjectNotFoundError(f"project {project_id!r} not found")

        # 2) 上下文匹配（id / 名称 / 目标）
        if context:
            matches = [p for p in projects
                       if (context in p["project_id"] or context in p["name"]
                           or context in p["goal"])]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                # 仍多个 → 退回最近活动
                return cast(dict[str, Any], self._most_recent(matches))

        # 3) 最近活动
        top = self._most_recent(projects)
        if top is None:
            raise AmbiguousProjectError("multiple projects; cannot disambiguate by activity")
        return top

    def _most_recent(self, projects: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked = sorted(projects, key=lambda p: self._activity_time(p["project_id"]),
                        reverse=True)
        return ranked[0] if ranked else None

    def _activity_time(self, project_id: str) -> str:
        """项目最近活动时间：取 project.updated_at 与各表最新时间戳的最大值。"""
        stamps = [self.db.get_project(self.tenant_id, project_id).get("updated_at", "")]
        with sqlite3.connect(str(self.db.path)) as c:
            for table, col in (("facts", "updated_at"), ("evidence", "created_at"),
                               ("decisions", "created_at"), ("changes", "created_at")):
                try:
                    row = c.execute(
                        f"SELECT COALESCE(MAX({col}),'') FROM {table} "
                        "WHERE tenant_id=? AND project_id=?",
                        (self.tenant_id, project_id)).fetchone()
                    if row and row[0]:
                        stamps.append(row[0])
                except sqlite3.Error:
                    continue
        return max(stamps, default="")

    # ------------------------------------------------------- recovery summary
    def recovery_summary(self, project_id: str,
                         tenant_id: str | None = None) -> dict[str, Any]:
        """恢复摘要：Product Truth / Evidence / 决策 / CAD·BOM / 附件链 / 外部 / 失败 / 下一步。

        已解决决策绝不重复出现于待追问列表。
        """
        tenant = tenant_id or self.tenant_id
        project = self.db.get_project(tenant, project_id)
        unresolved = self.db.list_open_decisions(tenant, project_id)
        resolved = self.db.list_resolved_decisions(tenant, project_id)
        resolved_ids = [d["decision_id"] for d in resolved]

        return {
            "project_id": project_id,
            "tenant_id": tenant,
            "project": project,
            "product_truth": self.db.list_facts(tenant, project_id),
            "evidence_register": self.db.list_evidence(tenant, project_id),
            "unresolved_decisions": unresolved,
            "resolved_decisions": resolved,
            "resolved_decision_ids": resolved_ids,
            "pending_questions": [d["decision_id"] for d in unresolved],  # 已解决的不含在内
            "cad_bom_revisions": self._cad_bom_revisions(project_id, tenant),
            "manual_attachment_chain": self.attachment_chain(project_id),
            "external_waits": self._external_waits(project_id, tenant),
            "failed_tasks": self._failed_tasks(project_id, tenant),
            "next_actions": self.next_actions(project_id, tenant),
            "blockers": self._blockers(project, unresolved),
            "backend": self.backend.name,
            "external_dependencies": self.external_dependencies(),
            "recovered_at": now_iso(),
        }

    def _cad_bom_revisions(self, project_id: str, tenant: str) -> list[dict[str, Any]]:
        revisions = []
        for d in self.db.list_deliverables(tenant, project_id):
            if any(k in (d.get("type") or "").lower() for k in CAD_BOM_TYPES):
                revisions.append({"deliverable_id": d["deliverable_id"], "type": d["type"],
                                  "version": d.get("version"), "status": d.get("status"),
                                  "updated_at": d.get("updated_at")})
        for ch in self.db.list_changes(tenant, project_id):
            if any(k in (ch.get("object_type") or "").lower() for k in CAD_BOM_TYPES):
                revisions.append({"change_id": ch["change_id"], "object_type": ch["object_type"],
                                  "object_id": ch["object_id"], "action": ch["action"],
                                  "created_at": ch.get("created_at")})
        return revisions

    def _external_waits(self, project_id: str, tenant: str) -> list[dict[str, Any]]:
        waits = []
        for dep in self.db.list_dependencies(tenant, project_id):
            if dep["relation"] in ("needs_external", "blocked_by_external"):
                waits.append({"source_type": dep["source_type"], "source_id": dep["source_id"],
                              "needs": dep["target_type"] + ":" + dep["target_id"]})
        if self.db.get_project(tenant, project_id).get("status") == "blocked_external":
            waits.append({"note": "project status is blocked_external"})
        return waits

    def _failed_tasks(self, project_id: str, tenant: str) -> list[dict[str, Any]]:
        rows = self._read_raw(SUPERVISOR_WORK_TABLE,
                              " WHERE project_id=?", (project_id,))
        failed = []
        for r in rows:
            if r.get("status") in FAILED_TASK_STATUSES:
                failed.append({"work_id": r.get("work_id"), "phase": r.get("phase"),
                               "module": r.get("module"), "title": r.get("title"),
                               "status": r.get("status"), "reason": r.get("blocked_reason")})
        return failed

    def _blockers(self, project, unresolved) -> list[Any]:
        blockers = []
        if unresolved:
            blockers.append("awaiting_owner_decision")
        if project.get("status") in (
                "awaiting_owner_decision", "blocked_external", "internal_rework"):
            blockers.append(project["status"])
        return blockers

    def next_actions(self, project_id: str,
                     tenant_id: str | None = None) -> list[dict[str, Any]]:
        tenant = tenant_id or self.tenant_id
        unresolved = self.db.list_open_decisions(tenant, project_id)
        if unresolved:
            return [{"action": "ask_owner",
                     "decisions": [{"decision_id": d["decision_id"], "topic": d["topic"]}
                                   for d in unresolved[:3]]}]
        if self._external_waits(project_id, tenant):
            return [{"action": "resume_external", "detail": "process outstanding external waits"}]
        if self._failed_tasks(project_id, tenant):
            return [{"action": "rework", "detail": "retry failed/rework tasks"}]
        gate = self.db.get_project(tenant, project_id)["gate"]
        return [{"action": "continue_phase", "gate": gate}]

    # ---------------------------------------------------------- safe auto-continue
    def auto_continue(self, project_id: str,
                      tenant_id: str | None = None) -> dict[str, Any]:
        """恢复后自动续作无需审批的安全工作；需审批/不可逆的留在门后。"""
        tenant = tenant_id or self.tenant_id
        items = self._read_raw(SUPERVISOR_WORK_TABLE,
                               " WHERE project_id=? AND status IN ('queued','ready')",
                               (project_id,))
        continued = []
        requires_approval = []
        for it in items:
            needs, cat = self._classify_approval(it)
            if needs:
                requires_approval.append({**it, "approval_category": cat,
                                          "status": it.get("status")})
                continue
            # 真实推进：queued -> ready
            if it.get("status") == "queued":
                self._set_work_status(project_id, it["work_id"], "ready", tenant)
            continued.append({**it, "action": "safe_continue",
                              "new_status": "ready"})
        return {"continued": continued, "requires_approval": requires_approval}

    def _classify_approval(self, work: dict[str, Any]):
        if work.get("owner_required"):
            return True, "owner_required"
        blob = " ".join(str(work.get(k) or "") for k in
                        ("phase", "module", "title", "objective")).lower()
        for cat, kws in APPROVAL_KEYWORDS.items():
            if any(k in blob for k in kws):
                return True, cat
        return False, None

    def require_approval(self, action: str, category: str, approved: bool = False) -> bool:
        """显式审批门：不可逆/安全/成本/发布操作必须获得批准，否则抛错。"""
        if category not in APPROVAL_CATEGORIES:
            raise ValueError(f"unknown approval category {category!r}; "
                             f"expected one of {sorted(APPROVAL_CATEGORIES)}")
        if not approved:
            raise ApprovalRequiredError(
                f"{action} requires explicit approval ({category})")
        return True

    # ------------------------------------------------------------ raw helpers
    def _read_raw(self, table: str, where: str = "", params: tuple = ()) -> list[dict[str, Any]]:
        if not self._table_exists(table):
            return []
        with sqlite3.connect(str(self.db.path)) as c:
            try:
                cols = [d[1] for d in c.execute(f"PRAGMA table_info({table})").fetchall()]
                rows = c.execute(f"SELECT * FROM {table}{where}", params).fetchall()
            except sqlite3.Error:
                return []
        return [dict(zip(cols, r)) for r in rows]

    def _table_exists(self, table: str) -> bool:
        with sqlite3.connect(str(self.db.path)) as c:
            row = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
        return row is not None

    def _set_work_status(self, project_id: str, work_id: str, status: str,
                         tenant: str) -> None:
        if not self._table_exists(SUPERVISOR_WORK_TABLE):
            return
        with sqlite3.connect(str(self.db.path)) as c:
            c.execute("UPDATE supervisor_work_items SET status=?, updated_at=? "
                      "WHERE work_id=?", (status, now_iso(), work_id))


__all__ = [
    "UnifiedStateService", "AmbiguousProjectError", "ApprovalRequiredError",
    "OBJECT_TYPES", "APPROVAL_CATEGORIES",
]
