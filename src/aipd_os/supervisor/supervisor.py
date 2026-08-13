#!/usr/bin/env python3
"""Supervisor：项目级执行监督器（从 scripts/aipd_supervisor.py 迁移，P1-1）。

核心职责：领取工作项 → 检查能力地板 → 执行 → 校验 → 注册能力/血缘 →
独立质量门 → 标记 stale → 返工/推进 → 仅在真实决策点暂停。

v5.7 变更：
- **Canonical Decision 集成（Commit 4）**：Supervisor 不再拥有 decisions 表；
  当构造时传入 ``state_db=AIPDStateDB`` 时，决策写入 canonical decisions
  （tenant+project 有界），返回 canonical decision_id，并把工作项置
  ``blocked_decision``。未提供 state_db 时走 legacy compatibility adapter
  （Supervisor-only 旧 DB 的 decisions 表），绝不破坏旧数据。
- **Multi-project / Tenant Scope（Commit 5）**：构造签名
  ``Supervisor(db, tenant_id='default', project_id=None, state_db=None)``；
  显式 project_id 时只操作该项目，所有表带 tenant_id 作用域；未显式且单项目
  保持兼容；未显式且多项目抛明确错误，不再猜唯一项目。
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("aipd.supervisor")
PHASES = [
    "S0_intake", "S1_theory", "S2_product_definition", "S3_manual",
    "S4_engineering_baseline", "S5_cad", "S6_industrialization",
    "S7_validation", "S8_release",
]
WORK_STATUSES = {
    "queued", "ready", "running", "blocked_external", "blocked_decision",
    "internal_rework", "complete", "cancelled",
}

# 注意：decisions 表不再由 Supervisor 声明（Commit 4）——canonical decisions
# 由 AIPDStateDB（src/aipd_os/state/db.py）拥有。legacy Supervisor-only 旧 DB
# 的 decisions 表由 SUPERVISOR_LEGACY_DECISIONS_SCHEMA 兼容创建。
SCHEMA = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS supervisor_work_items(
 work_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'default',
 phase TEXT NOT NULL, module TEXT NOT NULL, title TEXT NOT NULL, objective TEXT NOT NULL,
 priority INTEGER NOT NULL DEFAULT 50,
 status TEXT NOT NULL DEFAULT 'queued', owner_required INTEGER NOT NULL DEFAULT 0,
 decision_id TEXT, depends_on_json TEXT NOT NULL DEFAULT '[]',
 inputs_json TEXT NOT NULL DEFAULT '{}', outputs_json TEXT NOT NULL DEFAULT '{}',
 acceptance_json TEXT NOT NULL DEFAULT '{}', capability_floor TEXT,
 blocked_reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supervisor_phase_runs(
 run_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'default',
 phase TEXT NOT NULL, status TEXT NOT NULL, entry_checks_json TEXT NOT NULL DEFAULT '{}',
 exit_checks_json TEXT NOT NULL DEFAULT '{}', started_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS supervisor_capabilities(
 capability_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'default',
 name TEXT NOT NULL, provider TEXT, status TEXT NOT NULL, maturity_ceiling TEXT,
 metadata_json TEXT NOT NULL DEFAULT '{}', checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supervisor_reviews(
 review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'default',
 target_type TEXT NOT NULL, target_id TEXT NOT NULL, review_type TEXT NOT NULL,
 result TEXT NOT NULL, findings_json TEXT NOT NULL DEFAULT '[]', reviewer TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supervisor_lineage(
 lineage_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'default',
 upstream_type TEXT NOT NULL, upstream_id TEXT NOT NULL,
 downstream_type TEXT NOT NULL, downstream_id TEXT NOT NULL,
 relation TEXT NOT NULL, version TEXT, created_at TEXT NOT NULL,
 UNIQUE(project_id,upstream_type,upstream_id,downstream_type,downstream_id,relation));
-- v5.7（Commit 5）：supervisor_claims 死表（全仓无读写）重命名为
-- supervisor_assertions；旧 supervisor_claims 表保留不动以兼容历史 DB。
-- 注意：v5.8 Claim 域将建独立 contract，不沿用本表。
CREATE TABLE IF NOT EXISTS supervisor_assertions(
 assertion_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'default',
 claim TEXT NOT NULL, allowed INTEGER NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]',
 reason TEXT, created_at TEXT NOT NULL);
"""

# Legacy Supervisor-only DB 的 decisions 表（无 tenant_id；仅当未传 state_db 时使用）。
SUPERVISOR_LEGACY_DECISIONS_TABLE = "decisions"
SUPERVISOR_LEGACY_DECISIONS_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS decisions(
 decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, topic TEXT NOT NULL,
 trigger TEXT, recommendation TEXT, options_json TEXT NOT NULL DEFAULT '[]',
 status TEXT NOT NULL DEFAULT 'proposed', choice TEXT, comment TEXT,
 created_at TEXT NOT NULL, resolved_at TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def jd(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _ensure_supervisor_columns(c) -> None:
    """就地迁移：为已存在的 supervisor 表补齐 tenant_id 列（旧行默认 'default'）。"""
    for table in ("supervisor_work_items", "supervisor_phase_runs",
                  "supervisor_capabilities", "supervisor_reviews",
                  "supervisor_lineage", "supervisor_assertions"):
        exists = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()
        if not exists:
            continue
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if "tenant_id" not in cols:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")


class Supervisor:
    def __init__(self, db, tenant_id="default", project_id=None, state_db=None):
        self.path = Path(db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tenant_id = tenant_id or "default"
        self._project_id = project_id
        self._state_db = state_db
        with self.connect() as c:
            c.executescript(SCHEMA)
            _ensure_supervisor_columns(c)
            if self._state_db is None:
                # Supervisor-only 旧 DB：确保 legacy decisions 表存在（幂等，
                # 已存在的历史表不受影响；canonical 库中为 no-op）。
                c.executescript(SUPERVISOR_LEGACY_DECISIONS_SCHEMA)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    # ------------------------------------------------------------- scope
    def tenant_id(self):
        """当前 Supervisor 的租户作用域。"""
        return self._tenant_id

    def project_id(self):
        """解析当前项目作用域。

        - 显式 ``project_id`` → 只操作该项目；
        - 未显式且 DB 恰好一个项目 → 兼容行为；
        - 未显式且多项目 → 抛明确错误（不再猜唯一项目）。
        """
        if self._project_id is not None:
            return self._project_id
        with self.connect() as c:
            rows = c.execute("SELECT project_id FROM projects").fetchall()
        pids = {r[0] for r in rows}
        if len(pids) == 1:
            return next(iter(pids))
        if len(pids) == 0:
            raise ValueError("no base project found; initialize a project first")
        raise ValueError(
            "project context required: multiple projects exist, specify project_id")

    def _resolve_project_id(self, project_id: str | None) -> str:
        if project_id is not None:
            return project_id
        return self.project_id()

    def _decisions_has_tenant(self, c) -> bool:
        cols = {r[1] for r in c.execute("PRAGMA table_info(decisions)").fetchall()}
        return "tenant_id" in cols

    def _proposed_decision(self, c, pid: str):
        """项目范围内未解决的决策（canonical 或 legacy decisions 表）。"""
        if self._decisions_has_tenant(c):
            return c.execute(
                "SELECT decision_id FROM decisions WHERE project_id=? AND tenant_id=? "
                "AND status='proposed' ORDER BY created_at LIMIT 1",
                (pid, self._tenant_id)).fetchone()
        return c.execute(
            "SELECT decision_id FROM decisions WHERE project_id=? AND status='proposed' "
            "ORDER BY created_at LIMIT 1", (pid,)).fetchone()

    def _decision_status(self, c, did: str, pid: str) -> str | None:
        if self._decisions_has_tenant(c):
            row = c.execute(
                "SELECT status FROM decisions WHERE decision_id=? AND project_id=? "
                "AND tenant_id=?", (did, pid, self._tenant_id)).fetchone()
        else:
            row = c.execute(
                "SELECT status FROM decisions WHERE decision_id=? AND project_id=?",
                (did, pid)).fetchone()
        return row["status"] if row else None

    # ------------------------------------------------------------- lifecycle
    def next_id(self, table, col, prefix):
        with self.connect() as c:
            vals = [r[0] for r in c.execute(
                f"SELECT {col} FROM {table}").fetchall()]
        nums = []
        for v in vals:
            if isinstance(v, str) and v.startswith(prefix + "-"):
                with suppress(ValueError):
                    nums.append(int(v.rsplit("-", 1)[1]))
        return f"{prefix}-{max(nums, default=0) + 1:03d}"

    def init_lifecycle(self):
        pid = self.project_id()
        ts = now()
        with self.connect() as c:
            for i, phase in enumerate(PHASES):
                rid = f"RUN-{i:02d}"
                c.execute(
                    "INSERT OR IGNORE INTO supervisor_phase_runs("
                    "run_id,project_id,tenant_id,phase,status,entry_checks_json,"
                    "exit_checks_json,started_at,completed_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (rid, pid, self._tenant_id, phase,
                     "active" if i == 0 else "planned",
                     "{}", "{}", ts, None))

    def add_work(self, phase, module, title, objective, priority=50,
                 depends=None, inputs=None, acceptance=None,
                 capability_floor=None, owner_required=False):
        if phase not in PHASES:
            raise ValueError(phase)
        pid = self.project_id()
        wid = self.next_id("supervisor_work_items", "work_id", "W")
        ts = now()
        with self.connect() as c:
            c.execute(
                "INSERT INTO supervisor_work_items("
                "work_id,project_id,tenant_id,phase,module,title,objective,"
                "priority,status,owner_required,decision_id,depends_on_json,"
                "inputs_json,outputs_json,acceptance_json,capability_floor,"
                "blocked_reason,attempts,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (wid, pid, self._tenant_id, phase, module, title, objective,
                 priority, "queued", 1 if owner_required else 0, None,
                 jd(depends or []), jd(inputs or {}), "{}",
                 jd(acceptance or {}), capability_floor, None, 0, ts, ts))
        return wid

    def _deps_complete(self, c, deps):
        for dep in deps:
            r = c.execute(
                "SELECT status FROM supervisor_work_items WHERE work_id=?",
                (dep,)).fetchone()
            if not r or r[0] != "complete":
                return False
        return True

    def next_work(self, project_id=None):
        """领取下一个可执行工作项（项目+租户作用域）。

        - 只考虑本项目（``project_id`` / 构造时的显式项目）的工作项；
        - 本项目存在 proposed decision 时，owner_required 工作项被阻塞
          （不会错误执行，也不会阻塞其他项目的项）；
        - ``blocked_decision`` 工作项仅在关联决策已解决/取消后恢复。
        """
        pid = self._resolve_project_id(project_id)
        with self.connect() as c:
            decision = self._proposed_decision(c, pid)
            rows = c.execute(
                "SELECT * FROM supervisor_work_items "
                "WHERE project_id=? AND tenant_id=? AND status IN "
                "('queued','ready','internal_rework','blocked_decision') "
                "ORDER BY priority DESC,created_at",
                (pid, self._tenant_id)).fetchall()
            for r in rows:
                d = dict(r)
                deps = json.loads(d["depends_on_json"])
                if not self._deps_complete(c, deps):
                    continue
                if d["status"] == "blocked_decision":
                    # 仅当关联决策已解决/取消（不再是 proposed）时恢复领取。
                    st = (self._decision_status(c, d.get("decision_id"), pid)
                          if d.get("decision_id") else None)
                    if st == "proposed":
                        continue
                    c.execute(
                        "UPDATE supervisor_work_items SET status='running',"
                        "attempts=attempts+1,updated_at=? "
                        "WHERE work_id=? AND project_id=? AND tenant_id=?",
                        (now(), d["work_id"], pid, self._tenant_id))
                    d["status"] = "running"
                    d["depends_on"] = deps
                    return d
                if d["owner_required"] and decision:
                    c.execute(
                        "UPDATE supervisor_work_items SET "
                        "status='blocked_decision',decision_id=?,updated_at=? "
                        "WHERE work_id=?",
                        (decision[0], now(), d["work_id"]))
                    continue
                c.execute(
                    "UPDATE supervisor_work_items SET status='running',"
                    "attempts=attempts+1,updated_at=? WHERE work_id=?",
                    (now(), d["work_id"]))
                d["status"] = "running"
                d["depends_on"] = deps
                return d
        return None

    def complete(self, wid, outputs=None):
        with self.connect() as c:
            if not c.execute(
                    "SELECT 1 FROM supervisor_work_items WHERE work_id=?",
                    (wid,)).fetchone():
                raise KeyError(wid)
            c.execute(
                "UPDATE supervisor_work_items SET status='complete',"
                "outputs_json=?,updated_at=? WHERE work_id=?",
                (jd(outputs or {}), now(), wid))

    def fail(self, wid, reason, external=False, retry=True):
        st = ("blocked_external" if external
              else ("internal_rework" if retry else "cancelled"))
        with self.connect() as c:
            c.execute(
                "UPDATE supervisor_work_items SET status=?,blocked_reason=?,"
                "updated_at=? WHERE work_id=?",
                (st, reason, now(), wid))

    def register_capability(self, name, status, provider=None,
                            maturity_ceiling=None, metadata=None):
        pid = self.project_id()
        cid = self.next_id("supervisor_capabilities", "capability_id", "CAP")
        ts = now()
        with self.connect() as c:
            c.execute(
                "INSERT INTO supervisor_capabilities("
                "capability_id,project_id,tenant_id,name,provider,status,"
                "maturity_ceiling,metadata_json,checked_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (cid, pid, self._tenant_id, name, provider, status,
                 maturity_ceiling, jd(metadata or {}), ts))
        return cid

    def add_lineage(self, ut, uid, dt, did, relation="derives", version=None):
        with self.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO supervisor_lineage("
                "project_id,tenant_id,upstream_type,upstream_id,downstream_type,"
                "downstream_id,relation,version,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (self.project_id(), self._tenant_id, ut, uid, dt, did,
                 relation, version, now()))

    def review(self, target_type, target_id, review_type, result,
               findings=None, reviewer="AI-independent-auditor"):
        rid = self.next_id("supervisor_reviews", "review_id", "REV")
        with self.connect() as c:
            c.execute(
                "INSERT INTO supervisor_reviews("
                "review_id,project_id,tenant_id,target_type,target_id,"
                "review_type,result,findings_json,reviewer,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rid, self.project_id(), self._tenant_id, target_type, target_id,
                 review_type, result, jd(findings or []), reviewer, now()))
        return rid

    def status(self):
        pid = self.project_id()
        with self.connect() as c:
            counts = {r["status"]: r["n"] for r in c.execute(
                "SELECT status,COUNT(*) n FROM supervisor_work_items "
                "WHERE project_id=? AND tenant_id=? GROUP BY status",
                (pid, self._tenant_id))}
            phases = [dict(r) for r in c.execute(
                "SELECT * FROM supervisor_phase_runs "
                "WHERE project_id=? AND tenant_id=? ORDER BY run_id",
                (pid, self._tenant_id))]
            caps = [dict(r) for r in c.execute(
                "SELECT * FROM supervisor_capabilities "
                "WHERE project_id=? AND tenant_id=? ORDER BY checked_at DESC",
                (pid, self._tenant_id))]
            running = [dict(r) for r in c.execute(
                "SELECT work_id,phase,module,title,status "
                "FROM supervisor_work_items WHERE project_id=? AND tenant_id=? "
                "AND status IN ('running','blocked_decision','blocked_external')",
                (pid, self._tenant_id))]
        return {"work_counts": counts, "phases": phases,
                "capabilities": caps, "active_or_blocked": running}

    def _set_status(self, wid, status, decision_id=None):
        with self.connect() as c:
            if decision_id:
                c.execute(
                    "UPDATE supervisor_work_items SET status=?,decision_id=?,"
                    "updated_at=? WHERE work_id=?",
                    (status, decision_id, now(), wid))
            else:
                c.execute(
                    "UPDATE supervisor_work_items SET status=?,updated_at=? "
                    "WHERE work_id=?",
                    (status, now(), wid))

    def _persist_decision(self, wid, pkg, project_id=None):
        """持久化决策并返回 decision_id（canonical 或 legacy）。

        - 提供 ``state_db`` → 写入 canonical decisions（tenant+project 有界），
          返回 canonical decision_id；项目状态自动置 awaiting_owner_decision。
        - 未提供 state_db → legacy compatibility adapter：写入 Supervisor-only
          旧 DB 的 decisions 表（数据不迁移、不破坏）。
        """
        pid = self._resolve_project_id(project_id)
        topic = pkg["decision"]["topic"]
        recommendation = pkg["recommendation"]
        options = pkg["options"]
        trigger = pkg["decision"].get("category")
        if self._state_db is not None:
            did = self._state_db.propose_decision(
                self._tenant_id, pid, topic, recommendation, options, trigger)
            return did
        with self.connect() as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(decisions)").fetchall()}
            if "tenant_id" in cols:
                # 库已是 canonical decisions（tenant_id NOT NULL）却未传
                # state_db：fail-closed，给可操作错误而非裸 NOT NULL 崩溃。
                raise RuntimeError(
                    "canonical decisions table detected (tenant_id column); pass "
                    "state_db=<AIPDStateDB> to Supervisor to use canonical "
                    "decision integration (legacy insert would violate NOT NULL)")
            did = pkg["decision_id"]
            ts = now()
            c.execute(
                "INSERT INTO decisions(decision_id,project_id,topic,trigger,"
                "recommendation,options_json,status,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (did, pid, topic, trigger, recommendation, jd(options),
                 "proposed", ts))
        return did

    def _register_outputs(self, wid, capability_floor, out):
        try:
            self.register_capability(capability_floor, "available",
                                     provider=out["record"].provider)
        except Exception as exc:  # noqa: BLE001 - 登记失败不中断，但必须记录
            logger.warning(
                "supervisor_register_outputs_failed work_id=%s "
                "capability=%s error=%s", wid, capability_floor, exc)
        self.add_lineage("work_item", wid, "run",
                         out["record"].run_id, "executed_via")

    def _quality_gate(self, wid, record):
        """独立质量门：以独立审计身份复核执行记录，返回门禁结果。"""
        findings = []
        if not getattr(record, "evidence_references", []):
            findings.append("missing evidence references")
        if not getattr(record, "output_hash", None):
            findings.append("missing output hash")
        result = "pass" if not findings else "review"
        try:
            self.review(target_type="run", target_id=record.run_id,
                        review_type="independent_gate", result=result,
                        findings=findings)
        except Exception as exc:  # noqa: BLE001 - 审查落库失败应记录，不中断
            logger.warning(
                "supervisor_gate_review_failed work_id=%s run_id=%s error=%s",
                wid, record.run_id, exc)
        return {"gate": result, "findings": findings}

    def _mark_stale(self, wid):
        """标记依赖本工作项的既有工件为 stale（记录到 lineage）。"""
        stale = []
        with self.connect() as c:
            row = c.execute(
                "SELECT project_id,tenant_id FROM supervisor_work_items "
                "WHERE work_id=?", (wid,)).fetchone()
            pid = row["project_id"] if row else self.project_id()
            tenant = row["tenant_id"] if row else self._tenant_id
            deps = c.execute(
                "SELECT work_id FROM supervisor_work_items "
                "WHERE project_id=? AND tenant_id=? AND status='complete' "
                "AND depends_on_json LIKE ?",
                (pid, tenant, f"%{wid}%")).fetchall()
            for d in deps:
                stale.append(d["work_id"])
        for s in stale:
            self.add_lineage("work_item", wid, "work_item", s,
                             relation="invalidates")
        return {"stale": stale}

    def run_supervisor(self, steps=1, adapter_registry=None, router=None,
                       decision_policy=None, project_id=None):
        """驱动监督器执行：直到需要决策或工作耗尽。

        返回每个步骤的结果列表（complete / internal_rework /
        blocked_external / decision）。每个结果通过 ``steps`` 字段固化执行顺序
        （领取→依赖→能力地板→选择→执行→校验→注册工件→更新事实证据→
        独立质量门→标记 stale→推进/返工→决策暂停）。
        """
        from aipd_os.logging_utils import get_logger, log_event
        logger = get_logger("aipd.supervisor")
        from aipd_os.execution.decision_policy import (
            build_decision_package,
            should_ask_decision,
        )
        from aipd_os.execution.execution_router import ExecutionRouter
        from aipd_os.execution.runs import RunStore
        from aipd_os.tool_adapters.builtin import build_registry
        if adapter_registry is None:
            adapter_registry = build_registry()
        if router is None:
            _store = RunStore(str(self.path.parent / "execution_runs.db"))
            router = ExecutionRouter(
                _store, adapter_registry, get_logger("aipd.router"))
        if decision_policy is None:
            decision_policy = should_ask_decision
        pid = self._resolve_project_id(project_id)
        results = []
        # 工作项处理循环的固定顺序（决策点暂停必须发生在执行之前，
        # 以便 owner_required / decision_policy 命中的工作项不被错误执行）：
        for _ in range(steps):
            item = self.next_work(project_id=pid)
            if item is None:
                log_event(logger, "supervisor_no_work")
                break
            wid = item["work_id"]
            steps_log = ["claim_next_work", "check_dependencies"]
            inputs = json.loads(item["inputs_json"])
            capability_floor = item.get("capability_floor") or inputs.get(
                "capability_floor")
            log_event(logger, "supervisor_step_started", work_id=wid,
                      phase=item.get("phase"), module=item.get("module"),
                      capability_floor=capability_floor)
            if item.get("owner_required") or decision_policy(item, inputs):
                steps_log.append("pause_at_decision")
                pkg = build_decision_package(
                    item, options=item.get("options")
                    or inputs.get("options"))
                did = self._persist_decision(wid, pkg, project_id=pid)
                self._set_status(wid, "blocked_decision", did)
                pkg = dict(pkg)
                pkg["decision_id"] = did
                log_event(logger, "supervisor_decision_required",
                          work_id=wid, decision_id=did)
                results.append({
                    "work_id": wid, "action": "decision",
                    "decision": pkg, "steps": steps_log,
                })
                continue
            steps_log.append("check_capability_floor")
            if not capability_floor or adapter_registry.get(
                    capability_floor) is None:
                reason = ("no capability_floor assigned"
                          if not capability_floor
                          else f"no adapter registered for {capability_floor}")
                self.fail(wid, reason, external=False, retry=True)
                log_event(logger, "supervisor_no_adapter",
                          work_id=wid, reason=reason)
                steps_log.append("create_rework_or_advance")
                results.append({
                    "work_id": wid, "action": "internal_rework",
                    "reason": reason, "steps": steps_log,
                })
                continue
            try:
                steps_log += ["select_primary_tool", "execute",
                              "validate_result"]
                out = router.run(wid, capability_floor, inputs,
                                 context={"work_id": wid, "project_id": pid,
                                          "tenant_id": self._tenant_id})
                record = out["record"]
                if record.status in ("succeeded", "fallback"):
                    self.complete(wid, outputs=out["result"])
                    self._register_outputs(wid, capability_floor, out)
                    qg = self._quality_gate(wid, record)
                    stale = self._mark_stale(wid)
                    steps_log += ["register_artifact",
                                  "update_facts_evidence",
                                  "run_independent_quality_gate",
                                  "mark_stale",
                                  "create_rework_or_advance"]
                    log_event(logger, "supervisor_work_complete",
                              work_id=wid, status=record.status,
                              run_id=record.run_id)
                    results.append({
                        "work_id": wid, "action": "complete",
                        "status": record.status,
                        "record": record.to_dict(), "steps": steps_log,
                        "quality_gate": qg, "stale": stale,
                    })
                elif record.status == "blocked_external":
                    self.fail(wid, record.error_message
                              or "external capability unavailable",
                              external=True, retry=False)
                    log_event(logger, "supervisor_work_blocked_external",
                              work_id=wid, run_id=record.run_id)
                    results.append({
                        "work_id": wid, "action": "blocked_external",
                        "record": record.to_dict(), "steps": steps_log,
                    })
                else:
                    self.fail(wid, record.error_message or "execution failed",
                              external=False, retry=True)
                    log_event(logger, "supervisor_work_failed",
                              work_id=wid, status=record.status,
                              run_id=record.run_id)
                    steps_log.append("create_rework_or_advance")
                    results.append({
                        "work_id": wid, "action": "internal_rework",
                        "status": record.status,
                        "record": record.to_dict(), "steps": steps_log,
                    })
            except Exception as exc:
                self.fail(wid, str(exc), external=False, retry=True)
                log_event(logger, "supervisor_work_error",
                          work_id=wid, error=str(exc))
                steps_log.append("create_rework_or_advance")
                results.append({
                    "work_id": wid, "action": "internal_rework",
                    "error": str(exc), "steps": steps_log,
                })
        return results


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--tenant", default="default")
    p.add_argument("--project")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    s = sub.add_parser("add-work")
    s.add_argument("--phase", required=True)
    s.add_argument("--module", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--objective", required=True)
    s.add_argument("--priority", type=int, default=50)
    s.add_argument("--depends-json", default="[]")
    s.add_argument("--inputs-json", default="{}")
    s.add_argument("--acceptance-json", default="{}")
    s.add_argument("--capability-floor")
    s.add_argument("--owner-required", action="store_true")
    sub.add_parser("next")
    s = sub.add_parser("complete")
    s.add_argument("--work-id", required=True)
    s.add_argument("--outputs-json", default="{}")
    s = sub.add_parser("fail")
    s.add_argument("--work-id", required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--external", action="store_true")
    s.add_argument("--no-retry", action="store_true")
    s = sub.add_parser("register-capability")
    s.add_argument("--name", required=True)
    s.add_argument("--status", required=True)
    s.add_argument("--provider")
    s.add_argument("--maturity-ceiling")
    s.add_argument("--metadata-json", default="{}")
    s = sub.add_parser("lineage")
    s.add_argument("--upstream-type", required=True)
    s.add_argument("--upstream-id", required=True)
    s.add_argument("--downstream-type", required=True)
    s.add_argument("--downstream-id", required=True)
    s.add_argument("--relation", default="derives")
    s.add_argument("--version")
    s = sub.add_parser("run")
    s.add_argument("--steps", type=int, default=1)
    s.add_argument("--project")
    sub.add_parser("status")
    return p


def main():
    a = parser().parse_args()
    s = Supervisor(a.db, tenant_id=a.tenant, project_id=a.project)
    if a.cmd == "init":
        s.init_lifecycle()
        out = {"ok": True}
    elif a.cmd == "add-work":
        out = {"work_id": s.add_work(
            a.phase, a.module, a.title, a.objective, a.priority,
            json.loads(a.depends_json), json.loads(a.inputs_json),
            json.loads(a.acceptance_json), a.capability_floor,
            a.owner_required)}
    elif a.cmd == "next":
        out = {"work": s.next_work(project_id=a.project)}
    elif a.cmd == "complete":
        s.complete(a.work_id, json.loads(a.outputs_json))
        out = {"ok": True}
    elif a.cmd == "fail":
        s.fail(a.work_id, a.reason, a.external, not a.no_retry)
        out = {"ok": True}
    elif a.cmd == "register-capability":
        out = {"capability_id": s.register_capability(
            a.name, a.status, a.provider, a.maturity_ceiling,
            json.loads(a.metadata_json))}
    elif a.cmd == "lineage":
        s.add_lineage(a.upstream_type, a.upstream_id, a.downstream_type,
                      a.downstream_id, a.relation, a.version)
        out = {"ok": True}
    elif a.cmd == "run":
        out = {"results": s.run_supervisor(a.steps, project_id=a.project)}
    elif a.cmd == "status":
        out = s.status()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
