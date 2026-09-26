"""「上游已变、下游还 active」的漂移探测（F-DRIFT 第 51 片）。

第 48/49/50 三片把血缘的写侧与返工的执行侧都接上之后，三轮的 §七 都留下同一句：
**触发靠人给 `--upstream`**。报价换了、BOM 行了、声明文件改了，
下游那条 `artifact_version` 仍然是 `active`，库里没有任何东西自己发现过这件事。

判据形状（本轮真实读到两处一手文档后的择一决定，逐字出处见
`docs/audit/TRUTH_DRIFT_F-DRIFT_2026-09-26.md`）：
- **不新建基线**。dbt 的 `state:*` 是「与上一份 manifest 比」，基线工件本身会比现实更旧；
  Nx 的 `affected` 原文是 "Nx uses the Git history and the project graph" ——
  从**真相源现算**再沿图扩散。本仓每条记录里已经存着上一份 `input_signature`，
  等于**基线就住在记录自己身上**，所以这里走「现算 + 与记录里那份比」这一支
  （键的形状沿用第 46 片实读的 Bazel action key）。
- **三态，且「不可判」不许折叠**。`metadata` 里没有足够输入重算签名的记录
  （第 46 片之前的 DXF、第 48 片的 `bom_cost`——口径五项的值是第 49 片才落进 metadata 的）
  一律进 `undecidable`，既不折进「没漂」也不折进「漂了」；与第 49 片
  执行器 `missing_inputs` 是同一条纪律。把不可判算成没漂，是这一族里最安静的假绿。
- **本模块只读、只分类，不改状态**。自动把 active 打成 stale 会扩大发布门禁的要求面
  （第 44 片那条方向），但一次扫出一大片无人收口的任务是另一件事——
  先把半径量出来，写侧留给下一轮裁决。

签名怎么算（读声明文件、开 BOM 库、取模型摘要）留在 CLI 侧注入：
`product_truth` 层不该知道 `bom.db` 在哪、也不该知道 DXF 的模型是黄金件还是 STEP。
"""
from __future__ import annotations

from typing import Any, Callable

__all__ = ["IN_SYNC", "DRIFTED", "UNDECIDABLE", "NO_SIGNATURE",
           "classify_record", "scan_drift"]

IN_SYNC = "in_sync"
DRIFTED = "drifted"
UNDECIDABLE = "undecidable"
NO_SIGNATURE = "no_record_signature"

#: resolver(meta) 回 **(当前输入算出的键, 记录里存着的那份键, 算不出时的原因)**。
#: 两侧都由各类制品自己交出：`drawing_spec` 存的是 `spec_sha256`（没有 input_signature），
#: DXF / bom / bom_cost 存的是 `input_signature`——用一个字段名去兜两类记录，
#: 会把「读不到那份键」与「键确实不同」混成同一种读数。
Resolver = Callable[[dict[str, Any]], "tuple[str | None, str | None, str | None]"]


def classify_record(record: Any, resolver: Resolver) -> dict[str, Any]:
    """把**一条**记录分进四态之一。"""
    meta = dict(record.metadata or {})
    artifact = str(meta.get("artifact") or "")
    if not artifact:
        return {"record_id": str(record.record_id), "artifact": None,
                "state": UNDECIDABLE, "status": str(record.status),
                "reason": "记录里没有 metadata.artifact，认不出是哪类制品"}
    try:
        current, stored, why = resolver(meta)
    except Exception as exc:  # noqa: BLE001 - 算不出来是读数，不是崩溃
        return {"record_id": str(record.record_id), "artifact": artifact,
                "state": UNDECIDABLE, "status": str(record.status),
                "reason": f"重算抛了 {type(exc).__name__}: {exc}"}
    if not stored:
        return {"record_id": str(record.record_id), "artifact": artifact,
                "state": NO_SIGNATURE, "status": str(record.status),
                "reason": why or "这条记录里没有可比对的输入键（该轮的生产者还没写这一项）"}
    if not current:
        return {"record_id": str(record.record_id), "artifact": artifact,
                "state": UNDECIDABLE, "status": str(record.status),
                "reason": why or "重算器说它拿不齐输入"}
    same = str(current) == str(stored)
    return {"record_id": str(record.record_id), "artifact": artifact,
            "state": IN_SYNC if same else DRIFTED,
            "status": str(record.status),
            "stored_signature": str(stored)[:16],
            "current_signature": str(current)[:16],
            "reason": None if same else "当前输入算出的键与记录里那份不一致"}


def scan_drift(store: Any, *, resolvers: dict[str, Resolver],
               tenant_id: str | None = None,
               project_id: str | None = None) -> dict[str, Any]:
    """扫一遍有效记录，按制品类型给出四态计数与「该 stale 却还是 active」的名单。

    `resolvers` 只覆盖登记过的制品类型；没给 resolver 的类型记 `undecidable`
    并在原因里写明「这一类还没接探测器」，而不是静默跳过——
    静默跳过会让"覆盖率"读成 100%。
    """
    buckets: dict[str, list[dict[str, Any]]] = {
        IN_SYNC: [], DRIFTED: [], UNDECIDABLE: [], NO_SIGNATURE: []}
    for rec in store.query(record_type="artifact_version",
                           tenant_id=tenant_id, project_id=project_id):
        artifact = str((rec.metadata or {}).get("artifact") or "")
        if str(rec.status) not in ("active", "stale"):
            continue                       # superseded/blocked 不参与：它们本来就不是现状
        resolver = resolvers.get(artifact)
        if resolver is None:
            buckets[UNDECIDABLE].append({
                "record_id": str(rec.record_id), "artifact": artifact or None,
                "state": UNDECIDABLE, "status": str(rec.status),
                "reason": "这一类制品还没接漂移探测器"})
            continue
        verdict = classify_record(rec, resolver)
        buckets[verdict["state"]].append(verdict)

    should_be_stale = [r for r in buckets[DRIFTED] if r["status"] == "active"]
    counts = {k: len(v) for k, v in buckets.items()}
    total = sum(counts.values())
    return {"scanned": total, "counts": counts,
            "buckets": buckets, "should_be_stale": should_be_stale,
            "clean": total > 0 and not buckets[DRIFTED],
            "nothing_scanned": total == 0}
