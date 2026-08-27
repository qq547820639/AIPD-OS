"""Execution closure 核心数据模型与基础服务（P1-1）。

包含：事件常量、进度事件、取消控制、成本账本、产物校验、
有界自动返工状态机、步骤定义、成熟度门槛校验、面向用户的失败消息，
以及闭环持久化存储（ClosureStore）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
EVENT_START = "start"
EVENT_HEARTBEAT = "heartbeat"
EVENT_PROGRESS = "progress"
EVENT_STEP_START = "step_start"
EVENT_STEP_COMPLETE = "step_complete"
EVENT_COMPLETE = "complete"
EVENT_FAIL = "fail"
EVENT_CANCELLED = "cancelled"
EVENT_TIMED_OUT = "timed_out"
EVENT_ESCALATED = "escalated_user"

RUN_STATUSES = {
    "started", "running", "complete", "failed",
    "cancelled", "timed_out", "escalated_user",
}

REWORK_WORKING = "working"
REWORK_REWORK = "rework"
REWORK_COMPLETE = "complete"
REWORK_ESCALATED = "escalated_user"

MATURITY_ORDER = ["C0", "C1", "C2", "C3"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_monotonic() -> float:
    import time
    return time.monotonic()


def _monotonic_ms() -> int:
    import time
    return int(time.monotonic() * 1000)


def sha256_file(path: str) -> str:
    """计算文件 SHA-256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def maturity_index(level: str | None) -> int:
    """将成熟度层级映射为可比较的整数；未知返回 -1。"""
    if not level:
        return -1
    try:
        return MATURITY_ORDER.index(level)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# 进度事件
# ---------------------------------------------------------------------------
@dataclass
class ProgressEvent:
    """一次进度/心跳事件，带时间戳与序列号。"""

    run_id: str
    seq: int
    kind: str
    timestamp: str = field(default_factory=_now)
    step: str = ""
    message: str = ""
    progress: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 取消控制
# ---------------------------------------------------------------------------
class RunControl:
    """用户取消标志。置位后，在途工作会在下一个检查点停止。"""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def request_cancel(self) -> None:
        self.cancel()

    def is_cancelled(self) -> bool:
        return self._cancelled

    def reset(self) -> None:
        self._cancelled = False


# ---------------------------------------------------------------------------
# 成本账本（诚实：无真实模型时 cost=0、real_model=False）
# ---------------------------------------------------------------------------
class CostLedger:
    """累计 token / 成本 / 工具调用 / 时长。"""

    def __init__(self) -> None:
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost = 0.0
        self.real_model = False
        self.duration_ms = 0

    def record_call(self, tokens_in: int, tokens_out: int, cost: float,
                    real_model: bool, duration_ms: int) -> None:
        self.tokens_in += int(tokens_in or 0)
        self.tokens_out += int(tokens_out or 0)
        self.cost += float(cost or 0.0)
        self.real_model = self.real_model or bool(real_model)
        self.duration_ms += int(duration_ms or 0)

    def snapshot(self) -> dict[str, Any]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_in + self.tokens_out,
            "cost": self.cost,
            "real_model": self.real_model,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# 产物校验
# ---------------------------------------------------------------------------
def _fmt_exts(fmt: str | None) -> list[str]:
    if not fmt:
        return []
    if fmt in ("markdown", "md"):
        return [".md", ".markdown"]
    if fmt == "json":
        return [".json"]
    if fmt in ("png", "image/png"):
        return [".png"]
    if fmt in ("jpg", "jpeg"):
        return [".jpg", ".jpeg"]
    return []


def _check_format(path: str, fmt: str) -> bool:
    """按格式校验文件扩展名/内容。"""
    p = Path(path)
    ext = p.suffix.lower()
    if fmt in ("markdown", "md"):
        return ext in (".md", ".markdown")
    if fmt == "json":
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
            return True
        except Exception:
            return False
    if fmt in ("png", "image/png"):
        with open(path, "rb") as f:
            return f.read(8) == b"\x89PNG\r\n\x1a\n"
    if fmt in ("jpg", "jpeg"):
        with open(path, "rb") as f:
            return f.read(3) in (b"\xff\xd8\xff",)
    return True


def verify_file(path: str, fmt: str | None = None,
                expected_sha256: str | None = None,
                non_empty: bool = True) -> dict[str, Any]:
    """校验单个产物文件：存在性 / 非空 / 格式 / SHA-256。"""
    p = Path(path)
    exists = p.exists()
    size = p.stat().st_size if exists else 0
    empty = not (exists and size > 0)
    fmt_ok = True
    if exists and fmt:
        fmt_ok = _check_format(path, fmt)
    actual_sha = None
    sha_ok = True
    if exists and expected_sha256:
        actual_sha = sha256_file(path)
        sha_ok = actual_sha == expected_sha256
    if exists and not actual_sha:
        # 未提供 expected_sha256 时才计算一次哈希（此前对已计算的 actual_sha
        # 再哈希一遍，大产物文件双倍 IO）。
        actual_sha = sha256_file(path)
    ok = bool(exists) and (not non_empty or not empty) and fmt_ok and sha_ok
    return {
        "path": path, "exists": exists, "size": size, "non_empty": not empty,
        "format_ok": fmt_ok,
        "sha256": actual_sha,
        "sha256_ok": sha_ok, "ok": ok,
    }


class ArtifactVerifier:
    """产物集合校验入口：存在性 / 格式 / SHA-256 / 语义。"""

    def verify(self, step: ClosureStep, produced: list[str],
               result: dict[str, Any]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for p in produced:
            checks.append(verify_file(p, non_empty=True))
        for spec in (step.expected_artifacts or []):
            path = spec.get("path")
            if not path:
                candidates = [p for p in produced
                              if Path(p).suffix.lower() in _fmt_exts(spec.get("format"))]
                if not candidates:
                    checks.append({"path": "(missing)", "exists": False, "size": 0,
                                   "non_empty": False, "format_ok": False,
                                   "sha256": None, "sha256_ok": False, "ok": False})
                    continue
                path = candidates[0]
            checks.append(verify_file(
                path, fmt=spec.get("format"), expected_sha256=spec.get("sha256"),
                non_empty=bool(spec.get("non_empty", True))))
        if step.semantic_check is not None:
            try:
                ok, message, findings = step.semantic_check(result, produced)
            except Exception as exc:  # noqa: BLE001
                ok, message, findings = False, str(exc), [str(exc)]
            checks.append({"type": "semantic", "ok": bool(ok), "message": message,
                           "findings": findings or []})
        return checks

    @staticmethod
    def all_ok(checks: list[dict[str, Any]]) -> bool:
        return all(c.get("ok", False) for c in checks)


# ---------------------------------------------------------------------------
# 有界自动返工状态机
# ---------------------------------------------------------------------------
class ReworkMachine:
    """有界自动返工状态机。

    working -> (失败可重试) rework -> working ... 超出上限 -> escalated_user。
    成功 -> complete。返工次数受 ``max_attempts`` 上界约束，杜绝无限循环。
    """

    def __init__(self, max_attempts: int = 3) -> None:
        if max_attempts < 0:
            raise ValueError("max_attempts must be >= 0")
        self.max_attempts = max_attempts
        self.attempts = 0
        self.state = REWORK_WORKING
        self.last_classification: str | None = None
        self.last_message = ""

    def record_success(self) -> str:
        self.state = REWORK_COMPLETE
        return self.state

    def record_failure(self, classification: str, message: str = "") -> str:
        self.attempts += 1
        self.last_classification = classification
        self.last_message = message
        if self.attempts > self.max_attempts:
            self.state = REWORK_ESCALATED
            return "escalate"
        self.state = REWORK_REWORK
        return "rework"

    def can_retry(self) -> bool:
        return self.attempts <= self.max_attempts

    def snapshot(self) -> dict[str, Any]:
        return {"state": self.state, "attempts": self.attempts,
                "max_attempts": self.max_attempts,
                "last_classification": self.last_classification,
                "last_message": self.last_message}


# ---------------------------------------------------------------------------
# Step 定义
# ---------------------------------------------------------------------------
@dataclass
class ClosureStep:
    """闭环中的一个执行步骤。"""

    step_id: str
    capability_id: str
    inputs: dict[str, Any]
    context: dict[str, Any] | None = None
    expected_artifacts: list[dict[str, Any]] | None = None
    semantic_check: Callable[[dict[str, Any], list[str]], tuple] | None = None
    write_back: dict[str, Any] | None = None
    depends_on: list[str] | None = None


# ---------------------------------------------------------------------------
# 成熟度门槛校验
# ---------------------------------------------------------------------------
class MaturityFloorError(Exception):
    """成熟度门槛不满足。"""

    def __init__(self, capability_id: str, required: str | None,
                 actual: str | None, reason: str) -> None:
        self.capability_id = capability_id
        self.required = required
        self.actual = actual
        self.reason = reason
        super().__init__(f"maturity floor not met for {capability_id}: {reason}")


def check_maturity_floor(registry: Any, capability_id: str,
                         required_floor: str | None) -> dict[str, Any]:
    """校验能力是否满足成熟度门槛（校验真实成熟度上限，而非仅适配器存在）。"""
    adapter = registry.get(capability_id)
    if adapter is None:
        return {"ok": False, "capability_id": capability_id, "required": required_floor,
                "actual": None, "reason": "capability_missing: no adapter registered"}
    meta = adapter.discover()
    actual = meta.get("maturity_ceiling")
    if required_floor is None or required_floor == "":
        return {"ok": True, "capability_id": capability_id, "required": None,
                "actual": actual, "reason": "no floor required"}
    if not actual:
        return {"ok": False, "capability_id": capability_id, "required": required_floor,
                "actual": None,
                "reason": "adapter exists but declares no real maturity_ceiling"}
    if maturity_index(actual) < maturity_index(required_floor):
        return {"ok": False, "capability_id": capability_id, "required": required_floor,
                "actual": actual,
                "reason": f"maturity ceiling {actual} < required {required_floor}"}
    return {"ok": True, "capability_id": capability_id, "required": required_floor,
            "actual": actual, "reason": "ok"}


# ---------------------------------------------------------------------------
# 面向非技术用户的失败消息
# ---------------------------------------------------------------------------
def build_failure_message(failure: dict[str, Any]) -> dict[str, str]:
    """为失败构建面向非技术用户的可读消息。"""
    stage = failure.get("step") or "执行过程"
    reason = failure.get("reason") or "未知原因"
    saved = failure.get("saved") or "尚未保存新的有效结果"
    next_step = failure.get("next_step") or "请检查后重试，或联系支持人员"
    kind = failure.get("kind", "失败")
    return {
        "summary": f"「{failure.get('work_id', '本次任务')}」在{stage}时{kind}。",
        "where": f"失败位置：{stage}",
        "reason": f"原因：{reason}",
        "saved": f"已保存：{saved}",
        "next_step": f"下一步：{next_step}",
        "run_id": failure.get("run_id", ""),
    }


# ---------------------------------------------------------------------------
# ClosureStore：进度 / 心跳 / 检查点 / 工具调用 / stale 依赖 持久化
# ---------------------------------------------------------------------------
_CLOSURE_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS closure_runs(
  run_id TEXT PRIMARY KEY,
  work_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  current_step TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  heartbeat_at TEXT,
  reason TEXT);
CREATE TABLE IF NOT EXISTS closure_events(
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT '',
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  step TEXT,
  message TEXT,
  progress REAL,
  timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS closure_checkpoints(
  checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT '',
  step_id TEXT NOT NULL,
  data_json TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS closure_tool_calls(
  call_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT '',
  seq INTEGER NOT NULL,
  step_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  status TEXT NOT NULL,
  duration_ms INTEGER,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0,
  real_model INTEGER NOT NULL DEFAULT 0,
  timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS closure_dependencies(
  dep_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT '',
  upstream_step TEXT NOT NULL,
  downstream_step TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'derives');
CREATE TABLE IF NOT EXISTS closure_stale(
  stale_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT '',
  step_id TEXT NOT NULL,
  artifact_path TEXT,
  reason TEXT NOT NULL,
  marked_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_closure_runs_tenant
  ON closure_runs(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_closure_runs_project
  ON closure_runs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_closure_events_tenant
  ON closure_events(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS idx_closure_checkpoints_tenant
  ON closure_checkpoints(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS idx_closure_tool_calls_tenant
  ON closure_tool_calls(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS idx_closure_stale_tenant
  ON closure_stale(tenant_id, project_id, run_id);
"""


def _migrate_closure_tenant_scope(conn: sqlite3.Connection) -> None:
    """P2-M2: 幂等补齐所有 closure 表的 tenant_id/project_id 列。

    历史 closure DB 只有 closure_runs.project_id，其他表无 tenant scope。
    此函数对所有 closure 表执行幂等 ALTER TABLE + CREATE INDEX。
    """
    _CHILD_TABLES = [
        "closure_events",
        "closure_checkpoints",
        "closure_tool_calls",
        "closure_dependencies",
        "closure_stale",
    ]
    # closure_runs tenant_id 已在 schema 中，但历史 DB 可能缺失
    runs_cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(closure_runs)").fetchall()}
    if "tenant_id" not in runs_cols:
        conn.execute(
            "ALTER TABLE closure_runs ADD COLUMN "
            "tenant_id TEXT NOT NULL DEFAULT 'default'")

    # 子表补齐 tenant_id + project_id
    for table in _CHILD_TABLES:
        cols = {r[1] for r in conn.execute(
            f"PRAGMA table_info({table})").fetchall()}
        if "tenant_id" not in cols:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                "tenant_id TEXT NOT NULL DEFAULT 'default'")
        if "project_id" not in cols:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                "project_id TEXT NOT NULL DEFAULT ''")

    # 确保索引存在
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_closure_runs_tenant "
        "ON closure_runs(tenant_id, project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_closure_events_tenant "
        "ON closure_events(tenant_id, project_id, run_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_closure_checkpoints_tenant "
        "ON closure_checkpoints(tenant_id, project_id, run_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_closure_tool_calls_tenant "
        "ON closure_tool_calls(tenant_id, project_id, run_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_closure_stale_tenant "
        "ON closure_stale(tenant_id, project_id, run_id)")


class ClosureStore:
    """sqlite 持久化的闭环存储。"""

    def __init__(self, db: str) -> None:
        self.path = Path(db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(_CLOSURE_SCHEMA)
            # P2-M2: 幂等补齐 tenant_id/project_id 列（历史 closure DB 无此列）
            _migrate_closure_tenant_scope(c)

    @contextmanager
    def connect(self):
        from aipd_os.state.connection import ConnectionFactory
        factory = ConnectionFactory(self.path)
        with factory.transaction() as c:
            yield c

    # ---- runs ----
    def create_run(self, work_id: str, project_id: str = "",
                   tenant_id: str = "default") -> str:
        run_id = f"CL-{uuid.uuid4().hex[:12]}"
        ts = _now()
        with self.connect() as c:
            c.execute(
                "INSERT INTO closure_runs"
                "(run_id,work_id,tenant_id,project_id,status,started_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (run_id, work_id, tenant_id, project_id, "started", ts, ts))
        return run_id

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"status", "current_step", "updated_at", "heartbeat_at", "reason"}
        sets, params = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        if "updated_at" not in fields:
            sets.append("updated_at=?")
            params.append(_now())
        params.append(run_id)
        with self.connect() as c:
            c.execute(f"UPDATE closure_runs SET {', '.join(sets)} WHERE run_id=?", params)
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM closure_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return dict(row)

    # ---- events ----
    def _next_seq(self, c: sqlite3.Connection, run_id: str) -> int:
        row = c.execute(
            "SELECT COALESCE(MAX(seq),0) AS m FROM closure_events WHERE run_id=?",
            (run_id,)).fetchone()
        return int(row["m"]) + 1

    def emit_event(self, run_id: str, kind: str, step: str = "",
                   message: str = "", progress: float | None = None) -> ProgressEvent:
        with self.connect() as c:
            seq = self._next_seq(c, run_id)
            ts = _now()
            c.execute(
                "INSERT INTO closure_events(run_id,seq,kind,step,message,progress,timestamp)"
                " VALUES(?,?,?,?,?,?,?)",
                (run_id, seq, kind, step, message, progress, ts))
        return ProgressEvent(run_id=run_id, seq=seq, kind=kind, timestamp=ts,
                             step=step, message=message, progress=progress)

    def list_events(self, run_id: str) -> list[ProgressEvent]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM closure_events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [ProgressEvent(run_id=r["run_id"], seq=r["seq"], kind=r["kind"],
                              timestamp=r["timestamp"], step=r["step"] or "",
                              message=r["message"] or "", progress=r["progress"])
                for r in rows]

    # ---- checkpoints ----
    def save_checkpoint(self, run_id: str, step_id: str, data: Any) -> int:
        with self.connect() as c:
            cur = c.execute(
                "INSERT INTO closure_checkpoints(run_id,step_id,data_json,created_at)"
                " VALUES(?,?,?,?)",
                (run_id, step_id, json.dumps(data, ensure_ascii=False, default=str), _now()))
            return int(cur.lastrowid)

    def latest_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM closure_checkpoints WHERE run_id=? "
                "ORDER BY checkpoint_id DESC LIMIT 1", (run_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["data"] = json.loads(d["data_json"])
        return d

    # ---- tool calls ----
    def log_tool_call(self, run_id: str, step_id: str, tool: str, status: str,
                      duration_ms: int, tokens_in: int = 0, tokens_out: int = 0,
                      cost: float = 0.0, real_model: bool = False) -> int:
        with self.connect() as c:
            seq = self._next_seq(c, run_id)
            cur = c.execute(
                "INSERT INTO closure_tool_calls(run_id,seq,step_id,tool,status,duration_ms,"
                "tokens_in,tokens_out,cost,real_model,timestamp) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, seq, step_id, tool, status, duration_ms, tokens_in, tokens_out,
                 cost, 1 if real_model else 0, _now()))
            return int(cur.lastrowid)

    def list_tool_calls(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM closure_tool_calls WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()  # noqa: E501
        return [dict(r) for r in rows]

    # ---- dependencies / stale ----
    def add_dependency(self, run_id: str, upstream: str, downstream: str,
                       input_hash: str) -> None:
        with self.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO closure_dependencies(run_id,upstream_step,"
                "downstream_step,input_hash,relation) VALUES(?,?,?,?,?)",
                (run_id, upstream, downstream, input_hash, "derives"))

    def list_dependencies(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM closure_dependencies WHERE run_id=? "
                "ORDER BY upstream_step,downstream_step", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def add_stale(self, run_id: str, step_id: str, artifact_path: str = "",
                  reason: str = "") -> None:
        with self.connect() as c:
            c.execute(
                "INSERT INTO closure_stale(run_id,step_id,artifact_path,reason,marked_at)"
                " VALUES(?,?,?,?,?)",
                (run_id, step_id, artifact_path, reason, _now()))

    def list_stale(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM closure_stale WHERE run_id=? ORDER BY stale_id", (run_id,)).fetchall()  # noqa: E501
        return [dict(r) for r in rows]


__all__ = [
    "EVENT_START", "EVENT_HEARTBEAT", "EVENT_PROGRESS", "EVENT_STEP_START",
    "EVENT_STEP_COMPLETE", "EVENT_COMPLETE", "EVENT_FAIL", "EVENT_CANCELLED",
    "EVENT_TIMED_OUT", "EVENT_ESCALATED", "RUN_STATUSES",
    "ProgressEvent", "CostLedger", "RunControl", "ReworkMachine", "ClosureStep",
    "ArtifactVerifier", "verify_file", "sha256_file", "check_maturity_floor",
    "MaturityFloorError", "maturity_index", "build_failure_message",
    "ClosureStore",
]
