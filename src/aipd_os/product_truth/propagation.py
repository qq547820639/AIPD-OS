"""失效传播 + 有界自动返工。

当上游事实变化 / 过期时，沿血缘图计算下游受影响项并标记 ``stale``；
为每个受影响项生成一个有次数上限的返工任务（``max_rework_attempts``），
超出上限即停止并标记 ``blocked``（防返工风暴）。返工产生新版本并执行验证，
成功后关闭 stale。内置环检测、退避与 attempts 计数，并产出 owner 可读的变更说明。

诚实性（P0-10）：``run_rework`` 必须有真实的 ``rework_fn`` 执行器才会标记
``succeeded`` 并 bump 版本；未提供执行器时直接 ``blocked``，**绝不伪造成功**。

作用域：返工任务表带 ``tenant_id`` / ``project_id``，继承 store 的 scope，
所有 SQL 均按 store scope 过滤。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .lineage import LineageGraph
from .models import ReworkTask, now_iso
from .store import ProductTruthStore

# 默认返工上限（防返工风暴）
DEFAULT_MAX_ATTEMPTS = 3
# 退避基数（秒）：attempt n 的退避 = BACKOFF_BASE * 2**(n-1)
BACKOFF_BASE = 1


class ReworkExhaustedError(Exception):
    """返工次数达到上限，无法继续自动返工。"""


class PropagationEngine:
    """驱动失效传播与有界返工。"""

    def __init__(self, store: ProductTruthStore,
                 lineage: Optional[LineageGraph] = None,
                 default_max_attempts: int = DEFAULT_MAX_ATTEMPTS):
        self._store = store
        self._lineage = lineage or LineageGraph(store)
        self.default_max_attempts = default_max_attempts

    # ------------------------------------------------------------- 失效传播
    def on_upstream_changed(self, upstream_id: str,
                            reason: Optional[str] = None,
                            max_attempts: Optional[int] = None) -> Dict[str, object]:
        """上游 truth 变化/过期时，计算下游受影响项，全部标 stale 并生成返工任务。

        返回 {affected, stale, tasks, explanation}。
        """
        affected = self._lineage.compute_affected(upstream_id)
        stale_ids, tasks = [], []
        cap = max_attempts if max_attempts is not None else self.default_max_attempts
        for rid in affected:
            rec = self._store.get(rid)
            if rec.status != "stale":
                self._store.set_status(rid, "stale")
                stale_ids.append(rid)
            task = self._create_rework(rid, reason or f"upstream {upstream_id} changed",
                                       cap)
            tasks.append(task.to_dict())
        return {
            "affected": affected,
            "stale": stale_ids,
            "tasks": tasks,
            "explanation": self.explain_change(upstream_id, affected, stale_ids),
        }

    def _create_rework(self, truth_id: str, reason: str,
                       max_attempts: int) -> ReworkTask:
        task = ReworkTask(truth_id=truth_id, reason=reason, max_attempts=max_attempts)
        task.task_id = self._next_task_id()
        ts = now_iso()
        task.created_at = ts
        task.updated_at = ts
        tenant = self._store.tenant_id
        project = self._store.project_id
        with self._store.connect() as c:
            c.execute(
                "INSERT INTO rework_tasks(task_id,tenant_id,project_id,truth_id,reason,"
                "attempts,max_attempts,status,backoff_until,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (task.task_id, tenant, project, task.truth_id, task.reason,
                 task.attempts, task.max_attempts, task.status, task.backoff_until, ts, ts))
        return task

    def _next_task_id(self) -> str:
        tenant = self._store.tenant_id
        project = self._store.project_id
        with self._store.connect() as c:
            rows = c.execute(
                "SELECT task_id FROM rework_tasks WHERE tenant_id=? AND project_id=?",
                (tenant, project)).fetchall()
        nums = []
        for r in rows:
            if r["task_id"].startswith("RW-"):
                try:
                    nums.append(int(r["task_id"].rsplit("-", 1)[1]))
                except ValueError:
                    # noqa: EMPTY_EXCEPT - 跳过非数字后缀的既有任务 id（合法 id 过滤）
                    pass
        return f"RW-{max(nums, default=0) + 1:03d}"

    def list_tasks(self, status: Optional[str] = None) -> List[ReworkTask]:
        tenant = self._store.tenant_id
        project = self._store.project_id
        sql = "SELECT * FROM rework_tasks WHERE tenant_id=? AND project_id=?"
        params: List[object] = [tenant, project]
        if status is not None:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at"
        with self._store.connect() as c:
            rows = c.execute(sql, params).fetchall()
        out = []
        for r in rows:
            out.append(ReworkTask(
                task_id=r["task_id"], truth_id=r["truth_id"], reason=r["reason"],
                attempts=r["attempts"], max_attempts=r["max_attempts"],
                status=r["status"], backoff_until=r["backoff_until"],
                created_at=r["created_at"], updated_at=r["updated_at"]))
        return out

    def get_task(self, task_id: str) -> ReworkTask:
        tenant = self._store.tenant_id
        project = self._store.project_id
        with self._store.connect() as c:
            r = c.execute(
                "SELECT * FROM rework_tasks WHERE task_id=? AND tenant_id=? AND project_id=?",
                (task_id, tenant, project)).fetchone()
        if not r:
            raise KeyError(task_id)
        return ReworkTask(
            task_id=r["task_id"], truth_id=r["truth_id"], reason=r["reason"],
            attempts=r["attempts"], max_attempts=r["max_attempts"], status=r["status"],
            backoff_until=r["backoff_until"], created_at=r["created_at"],
            updated_at=r["updated_at"])

    def _set_task(self, task_id: str, **fields: object) -> None:
        allow = {"attempts", "status", "backoff_until", "updated_at"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            return
        ts = now_iso()
        set_sql = ", ".join([f"{k}=?" for k in set_cols] + ["updated_at=?"])
        values = list(fields[k] for k in set_cols) + [ts, task_id,
                                                      self._store.tenant_id,
                                                      self._store.project_id]
        with self._store.connect() as c:
            c.execute(
                f"UPDATE rework_tasks SET {set_sql} "
                "WHERE task_id=? AND tenant_id=? AND project_id=?",
                values)

    # ------------------------------------------------------------- 有界返工
    def run_rework(self, task_id: str,
                   rework_fn: Optional[Callable[[str], bool]] = None) -> Dict[str, object]:
        """执行一次返工尝试。

        - 递增 attempts；若已达到上限 → blocked（抛 ReworkExhaustedError）。
        - ``rework_fn`` 为 None（无返工执行器）时：直接标记 blocked，**绝不
          伪造成功**——不 bump 版本、不标 succeeded。
        - 否则调用 rework_fn(truth_id) 执行验证；返回 True 表示成功：bump
          新版本、关闭 stale、标记 succeeded；False 则退避重试，达到上限即 blocked。
        """
        task = self.get_task(task_id)
        if task.status == "succeeded":
            return {"task": task.to_dict(), "reworked": False, "message": "already succeeded"}
        if task.status == "blocked":
            raise ReworkExhaustedError(
                f"task {task_id} already blocked after {task.attempts} attempts")

        new_attempts = task.attempts + 1
        if new_attempts > task.max_attempts:
            self._set_task(task_id, attempts=new_attempts, status="blocked")
            self._store.set_status(task.truth_id, "blocked")
            raise ReworkExhaustedError(
                f"rework for {task.truth_id} exhausted after {task.max_attempts} attempts")

        if rework_fn is None:
            # 无返工执行器：拒绝假成功（P0-10）。
            self._set_task(task_id, attempts=new_attempts, status="blocked")
            self._store.set_status(task.truth_id, "blocked")
            return {
                "task": self.get_task(task_id).to_dict(),
                "reworked": False, "status": "blocked",
                "reason": "no rework executor provided; refusing fake success",
            }

        self._set_task(task_id, attempts=new_attempts, status="running")
        try:
            ok = rework_fn(task.truth_id)
        except Exception:
            ok = False

        if ok:
            # 返工成功：产生新版本并关闭 stale
            self._store.bump_version(task.truth_id)
            self._set_task(task_id, attempts=new_attempts, status="succeeded")
            return {
                "task": self.get_task(task_id).to_dict(),
                "reworked": True,
                "new_version": self._store.get(task.truth_id).version,
                "status": "succeeded",
            }

        # 失败 → 退避；达到上限则 blocked
        if new_attempts >= task.max_attempts:
            self._set_task(task_id, attempts=new_attempts, status="blocked")
            self._store.set_status(task.truth_id, "blocked")
            explained = self.explain_change(
                task.truth_id, [], [],
                reason=f"rework for {task.truth_id} blocked after {new_attempts} attempts")
            return {
                "task": self.get_task(task_id).to_dict(),
                "reworked": False, "status": "blocked",
                "explanation": explained,
            }
        backoff = BACKOFF_BASE * (2 ** (new_attempts - 1))
        self._set_task(task_id, attempts=new_attempts, status="pending",
                       backoff_until=self._backoff_iso(backoff))
        return {
            "task": self.get_task(task_id).to_dict(),
            "reworked": False, "status": "pending",
            "backoff_seconds": backoff,
        }

    def _backoff_iso(self, seconds: int) -> str:
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    # ----------------------------------------------------------- 变更说明
    def explain_change(self, upstream_id: str, affected: List[str],
                       stale: List[str], reason: Optional[str] = None) -> Dict[str, str]:
        """owner 可读的变更说明：改了什么 / 为何影响 / 计划怎么修 / 需批准什么。"""
        up = self._store.get(upstream_id)
        return {
            "what_changed": f"truth {upstream_id} ({up.record_type}) changed: "
                            f"{up.content[:80]}{'…' if len(up.content) > 80 else ''}",
            "why_affected": (f"{len(affected)} downstream items depend on {upstream_id}: "
                             + ", ".join(affected or ["none"])),
            "fix_plan": f"bounded rework (max {self.default_max_attempts} attempts) will "
                        f"bump versions and re-validate {len(stale)} stale item(s)",
            "approval_needed": (f"owner approval required to accept new versions for: "
                                + ", ".join(stale or ["none"])),
            "reason": reason or "upstream truth changed",
        }

    def pending_approval(self) -> List[Dict[str, object]]:
        """汇总所有需要 owner 批准的解释（面向 blocked 或 pending 任务）。"""
        out = []
        for t in self.list_tasks():
            if t.status in ("pending", "blocked"):
                rec = self._store.get(t.truth_id)
                out.append({
                    "task": t.to_dict(),
                    "explanation": self.explain_change(
                        t.truth_id, [t.truth_id], [t.truth_id], reason=t.reason),
                    "current_status": rec.status,
                })
        return out


__all__ = ["PropagationEngine", "ReworkExhaustedError",
           "DEFAULT_MAX_ATTEMPTS", "BACKOFF_BASE"]