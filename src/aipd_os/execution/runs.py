"""执行记录存储（RunStore）。

将 :class:`ExecutionRecord` 持久化到 sqlite 的 ``execution_runs`` 表，
并基于规范化 JSON 计算输入/输出内容的 sha256 哈希。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aipd_os.execution.models import ExecutionRecord

_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS execution_runs(
 run_id TEXT PRIMARY KEY,
 work_id TEXT NOT NULL,
 tool TEXT NOT NULL,
 provider TEXT NOT NULL,
 version TEXT NOT NULL,
 input_hash TEXT NOT NULL,
 output_hash TEXT,
 start_time TEXT NOT NULL,
 end_time TEXT,
 duration_ms INTEGER,
 cost REAL NOT NULL DEFAULT 0,
 tokens_in INTEGER NOT NULL DEFAULT 0,
 tokens_out INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL,
 error_classification TEXT,
 retry_lineage_json TEXT NOT NULL DEFAULT '[]',
 evidence_refs_json TEXT NOT NULL DEFAULT '[]',
 error_message TEXT,
 project_id TEXT NOT NULL DEFAULT '',
 tenant_id TEXT NOT NULL DEFAULT 'default',
 adapter_id TEXT NOT NULL DEFAULT '',
 capability TEXT NOT NULL DEFAULT '',
 retry_parent TEXT NOT NULL DEFAULT '',
 fallback_from TEXT NOT NULL DEFAULT '',
 idempotency_key TEXT NOT NULL DEFAULT '',
 side_effect_mode TEXT NOT NULL DEFAULT 'PURE',
 remote_operation_id TEXT NOT NULL DEFAULT '',
 artifacts_json TEXT NOT NULL DEFAULT '[]',
 result_json TEXT NOT NULL DEFAULT '{}');
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(data: Any) -> str:
    """对任意 JSON 可序列化数据计算稳定的 sha256 哈希。"""
    s = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _ensure_columns(c) -> None:
    """就地迁移：CREATE TABLE IF NOT EXISTS 不会给已存在的表补列，
    这里通过 PRAGMA 检查并用 ALTER TABLE 补齐缺失的新增列。"""
    cols = {r[1] for r in c.execute("PRAGMA table_info(execution_runs)").fetchall()}
    for name in ("project_id", "adapter_id", "capability", "retry_parent", "fallback_from",
                 "idempotency_key", "remote_operation_id"):
        if name not in cols:
            c.execute(
                f"ALTER TABLE execution_runs ADD COLUMN {name} TEXT NOT NULL DEFAULT ''"
            )
    if "side_effect_mode" not in cols:
        c.execute(
            "ALTER TABLE execution_runs ADD COLUMN side_effect_mode TEXT NOT NULL DEFAULT 'PURE'"
        )
    if "tenant_id" not in cols:
        # 幂等 scope 需要 tenant_id；历史行默认归入 'default' 租户。
        c.execute(
            "ALTER TABLE execution_runs ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'"
        )


class RunStore:
    """sqlite 持久化的执行记录存储。"""

    def __init__(self, db: str) -> None:
        self.path = Path(db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(_SCHEMA)
            _ensure_columns(c)

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

    def _new_run_id(self) -> str:
        return f"RUN-{uuid.uuid4().hex[:12]}"

    def create_run(
        self,
        work_id: str,
        tool: str,
        provider: str,
        version: str,
        input_hash: str,
        retry_lineage: list[str] | None = None,
        project_id: str = "",
        tenant_id: str = "default",
        adapter_id: str = "",
        capability: str = "",
        retry_parent: str = "",
        fallback_from: str = "",
        idempotency_key: str = "",
        side_effect_mode: str = "PURE",
        remote_operation_id: str = "",
    ) -> str:
        run_id = self._new_run_id()
        ts = _now()
        with self.connect() as c:
            c.execute(
                "INSERT INTO execution_runs(run_id,work_id,tool,provider,version,input_hash,"
                "output_hash,start_time,status,retry_lineage_json,cost,tokens_in,tokens_out,"
                "project_id,tenant_id,adapter_id,capability,retry_parent,fallback_from,"
                "idempotency_key,side_effect_mode,remote_operation_id)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,0,0,0,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    work_id,
                    tool,
                    provider,
                    version,
                    input_hash,
                    None,
                    ts,
                    "running",
                    json.dumps(retry_lineage or [], ensure_ascii=False),
                    project_id,
                    tenant_id,
                    adapter_id,
                    capability,
                    retry_parent,
                    fallback_from,
                    idempotency_key,
                    side_effect_mode,
                    remote_operation_id,
                ),
            )
        return run_id

    def update_run(self, run_id: str, **fields: Any) -> ExecutionRecord:
        """更新运行记录并返回最新 :class:`ExecutionRecord`。"""
        allowed = {
            "work_id",
            "tool",
            "provider",
            "version",
            "input_hash",
            "output_hash",
            "end_time",
            "duration_ms",
            "cost",
            "tokens_in",
            "tokens_out",
            "status",
            "error_classification",
            "error_message",
            "project_id",
            "tenant_id",
            "adapter_id",
            "capability",
            "retry_parent",
            "fallback_from",
            "idempotency_key",
            "side_effect_mode",
            "remote_operation_id",
            "result",
            "artifacts",
            "evidence_references",
        }
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            col = {
                "result": "result_json",
                "artifacts": "artifacts_json",
                "evidence_references": "evidence_refs_json",
            }.get(key, key)
            json_cols = {"result_json", "artifacts_json", "evidence_refs_json"}
            if col in json_cols:
                sets.append(f"{col}=?")
                params.append(json.dumps(value, ensure_ascii=False, default=str))
            else:
                sets.append(f"{col}=?")
                params.append(value)
        if not sets:
            raise ValueError("no fields to update")
        params.append(run_id)
        with self.connect() as c:
            c.execute(f"UPDATE execution_runs SET {', '.join(sets)} WHERE run_id=?", params)
        return self.get_run(run_id)

    def record_retry(self, prev_run_id: str) -> str:
        """将上次尝试标记为 ``retried``，并创建新的尝试记录，返回新 run_id。

        新记录继承相同的 work/tool/scope 信息（tenant_id / project_id /
        idempotency_key / side_effect_mode / capability / remote_operation_id /
        fallback_from），并把上次尝试的 run_id 追加到 retry_lineage 中。
        """
        prev = self.get_run(prev_run_id)
        ts = _now()
        with self.connect() as c:
            c.execute(
                "UPDATE execution_runs SET status='retried',end_time=?,duration_ms=? WHERE run_id=?",
                (ts, 0, prev_run_id),
            )
        lineage = list(prev.retry_lineage) + [prev_run_id]
        return self.create_run(
            prev.work_id,
            prev.tool,
            prev.provider,
            prev.version,
            prev.input_hash,
            retry_lineage=lineage,
            project_id=prev.project_id,
            tenant_id=prev.tenant_id,
            adapter_id=prev.adapter_id,
            capability=prev.capability,
            retry_parent=prev_run_id,
            fallback_from=prev.fallback_from,
            idempotency_key=prev.idempotency_key,
            side_effect_mode=prev.side_effect_mode,
            remote_operation_id=prev.remote_operation_id,
        )

    def get_run(self, run_id: str) -> ExecutionRecord:
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM execution_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return ExecutionRecord.from_db_row(dict(row))

    def list_runs(self, work_id: str | None = None) -> list[ExecutionRecord]:
        with self.connect() as c:
            if work_id is not None:
                rows = c.execute(
                    "SELECT * FROM execution_runs WHERE work_id=? ORDER BY start_time",
                    (work_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM execution_runs ORDER BY start_time"
                ).fetchall()
        return [ExecutionRecord.from_db_row(dict(r)) for r in rows]

    # ------------------------------------------------------------ 幂等查询
    def find_by_idempotency_key(self, key: str, tenant_id: str | None = None,
                                project_id: str | None = None,
                                capability: str | None = None) -> ExecutionRecord | None:
        """按幂等键取最新一条执行记录（无则 None）。

        提供 ``tenant_id`` / ``project_id`` / ``capability`` 时按
        (tenant_id, project_id, capability, idempotency_key) scope 查询——
        幂等去重必须在同一租户+项目+能力内有效，避免跨项目/跨租户误命中。
        全部 scope 参数缺省时保持旧行为（仅按 idempotency_key 全局查询）。
        """
        with self.connect() as c:
            if tenant_id is not None or project_id is not None or capability is not None:
                row = c.execute(
                    "SELECT * FROM execution_runs WHERE idempotency_key=? "
                    "AND tenant_id=? AND project_id=? AND capability=? "
                    "ORDER BY start_time DESC, rowid DESC LIMIT 1",
                    (key, tenant_id or "default", project_id or "",
                     capability or "")).fetchone()
            else:
                row = c.execute(
                    "SELECT * FROM execution_runs WHERE idempotency_key=? "
                    "ORDER BY start_time DESC, rowid DESC LIMIT 1", (key,)).fetchone()
        if row is None:
            return None
        return ExecutionRecord.from_db_row(dict(row))

    def find_by_idempotency_scope(self, key: str, tenant_id: str,
                                  project_id: str, capability: str) -> ExecutionRecord | None:
        """按 (tenant_id, project_id, capability, idempotency_key) scope 查幂等记录。

        Idempotency Scope = (tenant_id, project_id, capability, idempotency_key)。
        """
        return self.find_by_idempotency_key(
            key, tenant_id=tenant_id, project_id=project_id, capability=capability)

    def list_by_idempotency_key(self, key: str) -> list[ExecutionRecord]:
        """按幂等键列出全部执行记录（按开始时间升序）。"""
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM execution_runs WHERE idempotency_key=? ORDER BY start_time",
                (key,)).fetchall()
        return [ExecutionRecord.from_db_row(dict(r)) for r in rows]

    def get_result(self, run_id: str) -> dict[str, Any]:
        """读取运行记录持久化的 result_json；未存储/解析失败返回空 dict。"""
        with self.connect() as c:
            row = c.execute(
                "SELECT result_json FROM execution_runs WHERE run_id=?",
                (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        try:
            return json.loads(row["result_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}


__all__ = ["RunStore", "canonical_hash"]
