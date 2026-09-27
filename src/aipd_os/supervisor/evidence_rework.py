"""执行证据（`record_type="evidence"`）的返工执行器（F-REWORK-EVIDENCE 第 71 片）。

第 70 片把证据接进血缘之后，缺口挪到了下一格：改一条上游 truth ⇒ 证据被标 stale，
但 `aipd truth rework` 仍然不认这一类——`artifact_kind()` 只看 `metadata["artifact"]`，
证据行没有这个键，于是它落在「不认识 ⇒ 点名拒」。发现者（传播）与收口者（返工）
又不能是同一句话，所以这一片补执行器。

判据形状沿用已定的三条，不新造：

- **就地演进这一条记录，绝不另起新版**：引擎 `run_rework` 成功时是对**同一条**
  `bump_version(task.truth_id)`；「另起一版 + 旧版 superseded」是生产面 `cost calc` 的规则。
- **正文与 metadata 的投影只有一份来源**：正文走
  `fact_lineage.evidence_content`（与生产者同一个函数）——两边各写一遍时，
  「run 换了正文没换」与「正文换了 run_id 没换」都不会有人红（第 52/53 片同格）。
- **缺输入点名拒、不猜**，且**不可重放的能力直接拒**：
  只有 `side_effect_mode` 落在 `PURE`/`IDEMPOTENT` 的记录才允许再执行一次；
  `EXTERNAL_SIDE_EFFECT`/`NON_RETRYABLE`（发报价邮件那一类）**只能人处置**，
  这里宁可拒也不去碰第二次对外副作用。
- 重跑不走运（blocked_external / 失败）也**不算收口**：把 stale 留在原处，
  让下一次扫描继续看得见它，比标成 succeeded 诚实。
"""
from __future__ import annotations

from typing import Any, Callable

from aipd_os.supervisor.fact_lineage import evidence_content

SUPPORTED_RECORD_TYPE = "evidence"
REWORKABLE_MODES = ("PURE", "IDEMPOTENT")
REQUIRED_META = ("work_id", "run_id", "capability")

__all__ = ["REWORKABLE_MODES", "REQUIRED_META", "SUPPORTED_RECORD_TYPE",
           "evidence_artifact_kind", "make_evidence_rework_fn",
           "rework_evidence_artifact"]


def _fail(truth_id: str, outcome: str, **extra: Any) -> dict[str, Any]:
    return {"truth_id": truth_id, "ok": False, "outcome": outcome, **extra}


def evidence_artifact_kind(store: Any, truth_id: str) -> str | None:
    """给返工用的"制品类别"补第二条轴：证据行没有 `metadata["artifact"]`。

    类别只有两个来源，不猜第三种：`artifact` 键（四类版本记录）
    或 `record_type == "evidence"`（这一类）。两者都没有 ⇒ None ⇒ 照旧点名拒。
    """
    try:
        rec = store.get(truth_id)
    except KeyError:
        return None
    # 只认 record_type=evidence：四类版本记录的 record_type 是 artifact_version，
    # 天然落不进这一档，所以不需要再看 metadata["artifact"]。
    # （这行"让位判据"原本是写的第二道闸——第 71 片电池证明它不开火：
    #  把 `artifact` 键改成任何别的键，38 条用例全绿。删掉，不留没有主人的守卫。）
    return SUPPORTED_RECORD_TYPE if rec.record_type == SUPPORTED_RECORD_TYPE else None


def rework_evidence_artifact(store: Any, truth_id: str, *,
                             rerun: Callable[[dict[str, Any]], dict[str, Any]]
                             ) -> dict[str, Any]:
    """`rerun(meta)` 用记下来的工作项把它再执行一次，回
    ``{"run_id","output_hash","evidence_references","status","side_effect_mode"}``。"""
    from aipd_os.product_truth.models import SourceRef

    try:
        rec = store.get(truth_id)
    except KeyError:
        return _fail(truth_id, "missing_record")
    if rec.record_type != SUPPORTED_RECORD_TYPE:
        return _fail(truth_id, "not_evidence", record_type=rec.record_type)
    meta = dict(rec.metadata or {})
    missing = [k for k in REQUIRED_META if not meta.get(k)]
    if missing:
        return _fail(truth_id, "missing_metadata", missing=missing)
    old_run = str(meta.get("run_id") or "")
    try:
        fresh = rerun(meta) or {}
    except Exception as exc:  # noqa: BLE001 - 重跑炸了就是没收口，原样把原因带回去
        return _fail(truth_id, "rerun_raised", error=f"{type(exc).__name__}: {exc}")
    mode = str(fresh.get("side_effect_mode") or "PURE")
    if mode not in REWORKABLE_MODES:
        return _fail(truth_id, "not_replayable", side_effect_mode=mode,
                     why="对外副作用/不可重试的能力不自动再执行，只能人处置")
    if str(fresh.get("status") or "") not in ("succeeded", "fallback"):
        return _fail(truth_id, "rerun_not_ok", status=str(fresh.get("status") or ""),
                     old_run_id=old_run)
    new_run = str(fresh.get("run_id") or "")
    if not new_run:
        return _fail(truth_id, "rerun_missing_run_id")
    if new_run == old_run:
        # 同一次 run 再执行一遍不会有新信息；真重跑必然给新 run_id（引擎会 bump 版本）
        return _fail(truth_id, "rerun_same_run", run_id=new_run)
    refs = [str(x) for x in (fresh.get("evidence_references") or [])]
    output_hash = fresh.get("output_hash")
    content = evidence_content(str(meta.get("capability")), new_run, output_hash)
    new_meta = dict(meta)
    new_meta.update({"run_id": new_run, "output_hash": output_hash,
                     "evidence_references": refs,
                     "rework": {"from_run_id": old_run,
                                "side_effect_mode": mode,
                                "outcome": "re_evidenced"}})
    trust = "high" if str(fresh.get("gate") or "") == "pass" else "low"
    store.update(truth_id, content=content, metadata=new_meta, trust_level=trust,
                 source=SourceRef(file=refs[0] if refs else None,
                                  note=f"run_id={new_run}"))
    return {"truth_id": truth_id, "ok": True, "outcome": "re_evidenced",
            "from_run_id": old_run, "run_id": new_run, "trust_level": trust,
            "evidence_reference_count": len(refs)}


def make_evidence_rework_fn(supervisor: Any,
                            store: Any) -> Callable[[str], bool]:
    """给引擎的 `rework_fn`：拿工作项重跑一次，成功才回 True。"""

    def _rerun(meta: dict[str, Any]) -> dict[str, Any]:
        out = supervisor.rerun_for_rework(str(meta.get("work_id") or ""))
        if out is None:
            return {"status": "missing_work_item"}
        record = out["record"]
        return {"run_id": record.run_id,
                "output_hash": getattr(record, "output_hash", None),
                "evidence_references": list(getattr(record, "evidence_references", []) or []),
                "status": getattr(record, "status", ""),
                "side_effect_mode": out["side_effect_mode"],
                "gate": (out["gate"] or {}).get("gate")}

    def rework_fn(truth_id: str) -> bool:
        return bool(rework_evidence_artifact(store, truth_id,
                                            rerun=_rerun).get("ok"))

    return rework_fn
