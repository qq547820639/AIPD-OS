#!/usr/bin/env python3
"""P2-M10：状态基础设施性能验证量具（含棘轮门禁）。

覆盖 P2 收敛路径引入/改动的热路径：迁移、连接工厂、事务批处理边界、
Outbox 追加与 claim、stale 传播、Readiness 快照、漂移扫描（第 55 片加：
`scan_drift` 的单条成本与"记录变多后单条成本是否被放大"）。

设计取舍（对齐 pytest-benchmark 的思路，零新增依赖）：
- 每个场景多轮（rounds）独立建库，取 ms/op 或 ops/s 的 min/median/mean/max/stdev；
- 门禁用 **相对阈值**（median 对比基线劣化超过 tolerance_pct 即失败），
  不用绝对毫秒数——CI 机器差异太大，绝对阈值只会制造抖动；
- 另设 `comparative` 场景：同一轮内测量两个实现，要求 speedup 不低于
  require_ratio——这类比值在单机内稳定，可以直接当硬门禁。

用法::

    python scripts/state_perf_gate.py                     # 测量 + 对比基线门禁
    python scripts/state_perf_gate.py --json out.json     # 另外写出报告
    python scripts/state_perf_gate.py --update-baseline   # 采集/收紧基线
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

DEFAULT_BASELINE = _ROOT / "docs" / "audit" / "state_perf_baseline.json"

# ── 场景定义 ──────────────────────────────────────────────────
# metric: "ms_per_op"（越小越好）或 "ops_per_s"（越大越好）
# kind:   "absolute"（与基线比相对劣化） | "comparative"（轮内比值门禁）


@dataclass
class Scenario:
    name: str
    kind: str
    metric: str
    fn: Callable[[Path], Any]
    ops: float = 1.0
    tolerance_pct: float = 35.0
    require_ratio: float = 0.0
    note: str = ""


@dataclass
class Measurement:
    name: str
    kind: str
    metric: str
    samples: list[float] = field(default_factory=list)
    note: str = ""

    def stats(self) -> dict[str, Any]:
        s = sorted(self.samples)
        out: dict[str, Any] = {
            "kind": self.kind,
            "metric": self.metric,
            "rounds": len(s),
            "min": round(s[0], 4),
            "median": round(statistics.median(s), 4),
            "mean": round(statistics.fmean(s), 4),
            "max": round(s[-1], 4),
        }
        if len(s) > 1:
            out["stdev"] = round(statistics.pstdev(s), 4)
        return out


def _fresh_state(workdir: Path, project_id: str = "P-PERF"):
    """建一个已迁移、带默认租户与一个项目的 canonical state.db。"""
    from aipd_os.state.db import AIPDStateDB

    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    db = AIPDStateDB(str(workdir / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", project_id, "perf", "perf goal")
    return db


def _fact_status() -> str:
    from aipd_os.state.db import FACT_STATUSES

    return sorted(FACT_STATUSES)[0]


# ── 场景实现 ──────────────────────────────────────────────────

def sc_migrate_cold(workdir: Path) -> float:
    """v0 → HEAD 全量迁移（冷启动）。"""
    from aipd_os.state import migrations as mig

    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    path = str(workdir / "state.db")
    start = time.perf_counter()
    mig.migrate(path)
    return (time.perf_counter() - start) * 1000.0


def sc_migrate_noop(workdir: Path) -> float:
    """已最新库上的 migrate()：必须是廉价的 no-op。"""
    from aipd_os.state import migrations as mig

    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    path = str(workdir / "state.db")
    mig.migrate(path)
    start = time.perf_counter()
    applied = mig.migrate(path)
    elapsed = (time.perf_counter() - start) * 1000.0
    assert applied == [], f"no-op migrate 却应用了版本：{applied}"
    return elapsed


def sc_connect_overhead(workdir: Path) -> float:
    """ConnectionFactory 相对裸 sqlite3.connect 的开销（µs/op，100 次）。"""
    from aipd_os.state.connection import ConnectionFactory

    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "state.db"
    factory = ConnectionFactory(path)
    with factory.transaction() as c:
        c.execute("CREATE TABLE probe (id TEXT PRIMARY KEY)")
    n = 100
    start = time.perf_counter()
    for _ in range(n):
        conn = factory.connect()
        conn.close()
    return (time.perf_counter() - start) / n * 1e6


def sc_fact_batched(workdir: Path) -> float:
    """P2-M4 事务边界策略：N 条写落在同一事务内（ops/s）。"""
    db = _fresh_state(workdir)
    n = 400
    status = _fact_status()
    start = time.perf_counter()
    with db.transaction():
        for i in range(n):
            db.add_fact("default", "P-PERF", f"k{i}", {"v": i}, status)
    return n / (time.perf_counter() - start)


def sc_fact_autocommit(workdir: Path) -> float:
    """对照：无外层事务时每条 add_fact 自开连接 + 自 commit（ops/s）。"""
    db = _fresh_state(workdir)
    n = 100
    status = _fact_status()
    start = time.perf_counter()
    for i in range(n):
        db.add_fact("default", "P-PERF", f"k{i}", {"v": i}, status)
    return n / (time.perf_counter() - start)


def sc_outbox_append(workdir: Path) -> float:
    """单事务内追加 1000 条 outbox 事件（ops/s）。"""
    from aipd_os.state.connection import ConnectionFactory
    from aipd_os.state.outbox import OutboxRepository

    db = _fresh_state(workdir)
    factory = ConnectionFactory(db.path)
    n = 1000
    with factory.transaction() as conn:
        repo = OutboxRepository(conn)
        start = time.perf_counter()
        for i in range(n):
            repo.append_event(f"evt-{i}", "default", "P-PERF",
                              "Issue", f"ISS-{i}", "test.event", {"i": i})
        return n / (time.perf_counter() - start)


def sc_outbox_claim(workdir: Path) -> float:
    """在 5000 条积压上 claim_available(limit=100)（ms/op）。"""
    from aipd_os.state.connection import ConnectionFactory
    from aipd_os.state.outbox import OutboxRepository

    db = _fresh_state(workdir)
    factory = ConnectionFactory(db.path)
    with factory.transaction() as conn:
        repo = OutboxRepository(conn)
        for i in range(5000):
            repo.append_event(f"evt-{i}", "default", "P-PERF",
                              "Issue", f"ISS-{i}", "test.event", {"i": i})
    with factory.connection() as conn:
        repo = OutboxRepository(conn)
        samples = []
        for batch in range(10):
            start = time.perf_counter()
            claimed = repo.claim_available(f"w-{batch}", limit=100, lease_seconds=600)
            samples.append((time.perf_counter() - start) * 1000.0)
            assert len(claimed) == 100
        conn.commit()
    return max(samples)


def sc_changes_list(workdir: Path) -> float:
    """审计读路径：2 万条 changes 上按 (tenant, project) 取最近 100 条（ms/op）。

    v17 之前该查询是全表 SCAN + 临时 B-tree 排序；这里用 LIMIT 有界返回，
    把「排序/扫描成本」与「结果物化成本」分开，避免把空结果集误当加速。
    """
    db = _fresh_state(workdir)
    with db.transaction() as c:
        c.executemany(
            "INSERT INTO changes(project_id,tenant_id,object_type,object_id,"
            "action,after_json,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
            [("P-PERF", "default", "fact", f"F-{i}", "create", "{}", "seed",
              f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00") for i in range(20000)],
        )
    samples = []
    for _ in range(5):
        with db.connect() as c:
            start = time.perf_counter()
            rows = c.execute(
                "SELECT * FROM changes WHERE tenant_id=? AND project_id=? "
                "ORDER BY created_at DESC LIMIT 100",
                ("default", "P-PERF")).fetchall()
            samples.append((time.perf_counter() - start) * 1000.0)
    assert len(rows) == 100
    return max(samples)


def sc_stale_fanout(workdir: Path) -> float:
    """500 条下游依赖的 BOM 变更传播（ms/op，含 outbox 记录）。"""
    from aipd_os.state.stale_propagation import StalePropagationService

    db = _fresh_state(workdir)
    for i in range(500):
        db.add_dependency("default", "P-PERF", "bom", "BOM-1",
                          "cost_snapshot", f"COST-{i}")
    svc = StalePropagationService(db)
    start = time.perf_counter()
    result = svc.propagate_bom_change(
        "default", "P-PERF", "BOM-1", {"quantity": 1}, {"quantity": 2})
    elapsed = (time.perf_counter() - start) * 1000.0
    assert result["propagated"] and len(result["affected"]) == 500, result
    return elapsed


def sc_snapshot_create(workdir: Path) -> float:
    """Readiness 快照写入 200 条（ops/s）。"""
    from aipd_os.state.connection import ConnectionFactory
    from aipd_os.validation.readiness_snapshot_repo import (
        ReadinessSnapshotRepository,
        compute_input_fingerprint,
    )

    db = _fresh_state(workdir)
    factory = ConnectionFactory(db.path)
    n = 200
    dims = [{"dimension": f"d{i}", "status": "HOLD"} for i in range(8)]
    with factory.transaction() as conn:
        repo = ReadinessSnapshotRepository(conn)
        start = time.perf_counter()
        for i in range(n):
            repo.create(
                snapshot_id=f"snap-{i}", tenant_id="default", project_id="P-PERF",
                overall_status="HOLD", dimension_results=dims, blockers=[],
                warnings=[], missing_evidence=["x"], stale_dependencies=[],
                remediation_actions=[],
                input_fingerprint=compute_input_fingerprint({"i": i}),
            )
        return n / (time.perf_counter() - start)


def sc_readiness_evaluate(workdir: Path) -> float:
    """无输入时的 Readiness 评估（ops/s，全维 HOLD 的诚实降级路径）。"""
    from aipd_os.validation.issues import IssueService
    from aipd_os.validation.readiness import ReadinessService
    from aipd_os.validation.service import ValidationService

    db = _fresh_state(workdir)
    svc = ReadinessService(ValidationService(db), IssueService(db))
    n = 500
    start = time.perf_counter()
    for _ in range(n):
        report = svc.evaluate("default", "P-PERF")
    elapsed = time.perf_counter() - start
    assert report.overall_status == "HOLD", report.overall_status
    return n / elapsed


def sc_nested_txn_overhead(workdir: Path) -> float:
    """同库可重入事务：深度 1 vs 深度 20 的单次开销差（µs，越小越好）。"""
    from aipd_os.state.connection import ConnectionFactory

    db = _fresh_state(workdir)
    factory = ConnectionFactory(db.path)
    n = 200

    def depth(d: int) -> float:
        start = time.perf_counter()
        for _ in range(n):
            outer = factory.transaction()
            outer.__enter__()
            stack = [outer]
            for _ in range(d - 1):
                inner = factory.transaction()
                inner.__enter__()
                stack.append(inner)
            for ctx in reversed(stack):
                ctx.__exit__(None, None, None)
        return (time.perf_counter() - start) / n * 1e6

    one = depth(1)
    twenty = depth(20)
    return (twenty - one) / 19.0


def sc_batch_vs_autocommit(workdir: Path) -> float:
    """轮内比值门禁：同一事务批处理必须显著快于逐条自提交。"""
    from aipd_os.state.connection import ConnectionFactory

    db = _fresh_state(workdir)
    status = _fact_status()
    n = 150
    factory = ConnectionFactory(db.path)

    with factory.transaction() as conn:
        conn.execute("DELETE FROM facts")
        conn.execute("DELETE FROM changes")
    start = time.perf_counter()
    with db.transaction():
        for i in range(n):
            db.add_fact("default", "P-PERF", f"b{i}", {"v": i}, status)
    batched = time.perf_counter() - start

    with factory.transaction() as conn:
        conn.execute("DELETE FROM facts")
        conn.execute("DELETE FROM changes")
    start = time.perf_counter()
    for i in range(n):
        db.add_fact("default", "P-PERF", f"a{i}", {"v": i}, status)
    autocommit = time.perf_counter() - start
    return batched / autocommit  # < 1 表示批处理更快


def _seed_truth_specs(workdir: Path, n: int, project_id: str):
    """用**生产血缘助手**造 n 条有效 `drawing_spec` 版本记录（每条配一份磁盘声明）。

    不手写 INSERT：`record_spec_lineage` 与 `aipd drawing spec` 走的是同一个函数，
    手写记录会造出一条生产路径 never 产生的形状（第 46 片就是这么抓到签名漏吃模型的）。
    """
    from aipd_os.cad.spec_from_truth import spec_from_ctq
    from aipd_os.cad.spec_lineage import record_spec_lineage, render_spec_text
    from aipd_os.product_truth import ProductTruthStore
    from aipd_os.product_truth.models import TruthRecord
    from aipd_os.state.db import AIPDStateDB

    path = workdir / "state.db"
    workdir.mkdir(parents=True, exist_ok=True)
    db = AIPDStateDB(str(path))
    db.ensure_default_tenant("default")
    db.init_project("default", project_id, "perf", "perf goal")
    store = ProductTruthStore(str(path), tenant_id="default", project_id=project_id)
    for i in range(n):
        ctq = store.add(
            TruthRecord(record_type="ctq", content=f"CTQ {i}", trust_level="verified",
                        metadata={"feature": f"hole_{i}",
                                  "drawing_feature": f"TOP.hole_{i}",
                                  "nominal": 8.0, "lower_limit": 7.95,
                                  "upper_limit": 8.05,
                                  "inspection_method": "CMM"}),
            tenant_id="default", project_id=project_id)
        # 第 57 片：声明正文改由生产函数 `spec_from_ctq` 生成（理由见
        # `tests/test_state_perf_gates.py::_seed_specs` 里那段注释）。
        spec, gaps = spec_from_ctq([store.get(ctq)])
        assert not gaps, gaps
        out = workdir / f"spec-{i}.json"
        out.write_text(render_spec_text(spec), encoding="utf-8")
        record_spec_lineage(store, spec, path=out,
                            tenant_id="default", project_id=project_id)
    return store, path


def _scan_once(store, db_path: Path, project_id: str) -> tuple[float, int]:
    """跑一次 `scan_drift`（与 `aipd truth drift` 同一个入口），返回 (µs, 扫到几条)。"""
    from aipd_os.cli.commands_drift import build_resolvers
    from aipd_os.product_truth.drift import scan_drift

    resolvers = build_resolvers(str(db_path), project_id, "default")
    start = time.perf_counter()
    report = scan_drift(store, resolvers=resolvers,
                        tenant_id="default", project_id=project_id)
    elapsed = (time.perf_counter() - start) * 1e6
    return elapsed, int(report["scanned"])


def sc_drift_scan_us_per_record(workdir: Path) -> float:
    """200 条制品版本记录的漂移扫描，摊到每条记录的 µs（越小越好）。

    钉前提而不是只读数：`scanned` 必须等于种下的条数，且全部读成 `in_sync`——
    有漂移的那一遍走的是另一条分支，混进来就把"扫描成本"读成了"判决成本"。
    """
    n = 200
    store, path = _seed_truth_specs(workdir, n, "P-DRIFT-SCAN")
    elapsed, scanned = _scan_once(store, path, "P-DRIFT-SCAN")
    assert scanned == n, f"种了 {n} 条却扫到 {scanned} 条"
    return elapsed / n


def sc_drift_scan_scaling_ratio(workdir: Path) -> float:
    """轮内比值：记录数 ×10 时，单条成本不得跟着涨（抓"每条都重开一次贵东西"）。

    用比值而不是绝对毫秒数当硬门禁：绝对值受机器负载影响，本文件的绝对场景只做棘轮。
    """
    small_n, large_n = 20, 200
    store_s, path_s = _seed_truth_specs(workdir, small_n, "P-DRIFT-S")
    us_small, scanned_s = _scan_once(store_s, path_s, "P-DRIFT-S")
    assert scanned_s == small_n, scanned_s
    store_l, path_l = _seed_truth_specs(workdir, large_n, "P-DRIFT-L")
    us_large, scanned_l = _scan_once(store_l, path_l, "P-DRIFT-L")
    assert scanned_l == large_n, scanned_l
    return (us_large / scanned_l) / (us_small / scanned_s)


SCENARIOS: list[Scenario] = [

    Scenario("migrate_cold_ms", "absolute", "ms", sc_migrate_cold,
             note="v0→HEAD 全量迁移"),
    Scenario("migrate_noop_ms", "absolute", "ms", sc_migrate_noop,
             note="已最新库上的 migrate()"),
    Scenario("connect_overhead_us", "absolute", "us", sc_connect_overhead,
             note="ConnectionFactory.connect() 单次成本"),
    Scenario("fact_batched_ops_s", "absolute", "ops/s", sc_fact_batched,
             tolerance_pct=40.0, note="单事务 400 条 add_fact"),
    Scenario("fact_autocommit_ops_s", "absolute", "ops/s", sc_fact_autocommit,
             tolerance_pct=40.0, note="逐条自提交 100 条 add_fact"),
    Scenario("outbox_append_ops_s", "absolute", "ops/s", sc_outbox_append,
             note="单事务追加 1000 事件"),
    Scenario("outbox_claim_batch_ms", "absolute", "ms", sc_outbox_claim,
             tolerance_pct=50.0, note="5000 积压上 claim(limit=100)"),
    Scenario("changes_recent_100_ms", "absolute", "ms", sc_changes_list,
             tolerance_pct=50.0, note="2 万条审计上按 scope 取最近 100 条"),
    Scenario("stale_fanout_500_ms", "absolute", "ms", sc_stale_fanout,
             tolerance_pct=50.0, note="500 依赖的 BOM→cost 传播"),
    Scenario("snapshot_create_ops_s", "absolute", "ops/s", sc_snapshot_create,
             note="readiness_snapshots 写入"),
    Scenario("readiness_evaluate_ops_s", "absolute", "ops/s", sc_readiness_evaluate,
             note="全维 HOLD 路径评估"),
    Scenario("nested_txn_marginal_us", "absolute", "us", sc_nested_txn_overhead,
             tolerance_pct=60.0, note="每增加一层重入事务的边际成本"),
    Scenario("batch_over_autocommit_ratio", "comparative", "ratio",
             sc_batch_vs_autocommit, require_ratio=0.34,
             note="批处理耗时 / 逐条自提交耗时（<=0.34 即至少 3x 收益）"),
    Scenario("drift_scan_us_per_record", "absolute", "us",
             sc_drift_scan_us_per_record, tolerance_pct=60.0,
             note="200 条有效制品版本记录的漂移扫描，摊到每条的 µs"),
    Scenario("drift_scan_scaling_ratio", "comparative", "ratio",
             sc_drift_scan_scaling_ratio, require_ratio=2.0,
             note="记录 20→200 时单条成本的比值。两侧实测：合规侧 median 0.76~1.03"
                  "（重启后负载下有单轮冲到 6.44 的离群，但判决取 median）；"
                  "注入 N+1 median 2.94~5.99 ⇒ 阈值 2.0 落在两侧中间（两侧余量不对称，"
                  "所以这档只当趋势件，硬约束在 tests/test_state_perf_gates.py 的形状用例）"),
]


def run(scenarios: list[Scenario], rounds: int) -> dict[str, Measurement]:
    results: dict[str, Measurement] = {}
    for sc in scenarios:
        m = Measurement(name=sc.name, kind=sc.kind, metric=sc.metric, note=sc.note)
        for r in range(rounds):
            workdir = Path(tempfile.mkdtemp(prefix=f"aipdperf-{sc.name}-{r}-"))
            try:
                value = sc.fn(workdir)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
            m.samples.append(round(float(value), 4))
        results[sc.name] = m
    return results


def judge(results: dict[str, Measurement], baseline: dict[str, Any],
          scenarios: list[Scenario]) -> list[str]:
    failures: list[str] = []
    base_entries = baseline.get("scenarios", {})
    for sc in scenarios:
        measured = results[sc.name].stats()["median"]
        entry = base_entries.get(sc.name)
        if entry is None:
            failures.append(f"{sc.name}: 基线缺失该场景（先 --update-baseline 采集）")
            continue
        ref = float(entry["median"])
        if sc.kind == "comparative":
            if measured > sc.require_ratio:
                failures.append(
                    f"{sc.name}: 比值 {measured:.4f} > 要求 {sc.require_ratio:.4f}"
                    f"（{sc.note}）")
            continue
        worse = measured > ref if sc.metric in ("ms", "us", "ratio") else measured < ref
        if not worse:
            continue
        if sc.metric in ("ms", "us", "ratio"):
            drift_pct = (measured - ref) / ref * 100.0 if ref else 100.0
        else:
            drift_pct = (ref - measured) / ref * 100.0 if ref else 100.0
        if drift_pct > sc.tolerance_pct:
            failures.append(
                f"{sc.name}: median {measured:g} {sc.metric} vs 基线 {ref:g} "
                f"劣化 {drift_pct:.1f}% > 容差 {sc.tolerance_pct:g}%")
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--json", type=Path, default=None, help="另写出完整报告")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--only", default="", help="逗号分隔场景名子集")
    args = ap.parse_args(argv)

    import sqlite3

    print(f"# AIPD-OS P2-M10 状态性能量具  "
          f"(python {sys.version.split()[0]}, sqlite {sqlite3.sqlite_version}, "
          f"rounds={args.rounds})")

    scenarios = SCENARIOS
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        scenarios = [s for s in SCENARIOS if s.name in wanted]
        missing = wanted - {s.name for s in scenarios}
        if missing:
            print(f"未知场景：{sorted(missing)}")
            return 2

    results = run(scenarios, args.rounds)
    report = {
        "engine": "scripts/state_perf_gate.py",
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "rounds": args.rounds,
        "scenarios": {name: m.stats() for name, m in results.items()},
    }
    for name, m in results.items():
        s = m.stats()
        print(f"{name:32s} median={s['median']:>10g} "
              f"min={s['min']:>10g} max={s['max']:>10g} "
              f"stdev={s.get('stdev', 0):>8g}  [{m.metric}]  {m.note}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print(f"\n报告已写出：{args.json}")

    if args.update_baseline:
        payload = {"schema_version": 1, "scenarios": {}}
        if args.baseline.exists():
            payload = json.loads(args.baseline.read_text(encoding="utf-8"))
        payload.setdefault("scenarios", {})
        for name, s in report["scenarios"].items():
            payload["scenarios"][name] = {"median": s["median"], "metric": s["metric"]}
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
        print(f"基线已更新：{args.baseline}")
        return 0

    if not args.baseline.exists():
        print(f"\n基线不存在：{args.baseline}（先 --update-baseline 采集）")
        return 2
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    failures = judge(results, baseline, scenarios)
    if failures:
        print("\n性能门禁失败：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n性能门禁：PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
