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

第 57 片：一份记录允许有**多个输入面**，且**每个面各自与同一条已存基线比**
----------------------------------------
`drawing_spec` 的输入其实有两处：磁盘上那份声明文件，和**当初喂给生产者的那批 CTQ 记录**。
第 51~54 片只比前者，于是"属主改了 CTQ 限值、没人重出声明"这一整类漂移读成 `in_sync`
（第 56 片 §六 把这件事钉成了缺席断言）。现在两个面一起算，判据形状借 Argo CD
`docs/operator-manual/architecture.md` 实读的那句 "compares the current, live state against
the desired target state"：**两边都现算，基线只存一份**——所以存量记录不需要迁移、不会整片掉进
"没有键"。为什么不新增一列"源面签名"：那要把写侧两条入口（生产者与返工执行器）同时改，
且第 43~56 片的记录会集体变成 `no_record_signature`，把今天的"一致"读数换成"看不见"。

多出来的纪律只有一条，也是最容易做错的一条：**不可判不许跨面折叠**。
- 任一面与基线不一致 ⇒ `drifted`（原因里点名是哪一面）——哪怕另一面算不出来；
- 没有一面有基线 ⇒ `no_record_signature`；只有一部分面有基线且**算得出的面全部一致** ⇒
  仍判 `no_record_signature`（不能因为"文件面自己跟自己合"就宣布这份记录没问题）；
- 有基线但算不出当前值 ⇒ `undecidable`，原因用那一面自己交上来的话。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["IN_SYNC", "DRIFTED", "UNDECIDABLE", "NO_SIGNATURE",
           "Face", "classify_record", "scan_drift"]

IN_SYNC = "in_sync"
DRIFTED = "drifted"
UNDECIDABLE = "undecidable"
NO_SIGNATURE = "no_record_signature"


@dataclass(frozen=True)
class Face:
    """一个输入面：`current` 是当前世界算出的键，`stored` 是记录里存着的那份基线。

    两面**同源于一次生产**才有意义：`drawing_spec` 的文件面与源面共用
    `metadata.spec_sha256` 这一条基线（写声明时文件内容与 CTQ 重算结果本就同一份），
    所以任何一个面与它不等都是"当前输入不再是当初那份"。
    """

    name: str
    current: str | None
    stored: str | None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"face": self.name,
                "current": str(self.current)[:16] if self.current else None,
                "stored": str(self.stored)[:16] if self.stored else None,
                "reason": self.reason}


#: resolver(meta) 回**一组面**。单面制品回一个即可；两面制品（`drawing_spec`）回两个。
#: 两侧都由各类制品自己交出：`drawing_spec` 存的是 `spec_sha256`（没有 input_signature），
#: DXF / bom / bom_cost / quote_batch 存的是 `input_signature`——用一个字段名去兜两类记录，
#: 会把「读不到那份键」与「键确实不同」混成同一种读数。
Resolver = Callable[[dict[str, Any]], Sequence[Face]]


def _reason_with_faces(label: str, faces: Sequence[Face]) -> str:
    parts = [f"{f.name}面：{f.reason or '（未给原因）'}" for f in faces if f.reason]
    return f"{label}（{'；'.join(parts)}）" if parts else label


def classify_record(record: Any, resolver: Resolver) -> dict[str, Any]:
    """把**一条**记录分进四态之一（多面判据见模块 docstring 的那条优先级）。"""
    meta = dict(record.metadata or {})
    artifact = str(meta.get("artifact") or "")
    base = {"record_id": str(record.record_id), "artifact": artifact,
            "status": str(record.status), "faces": []}
    if not artifact:
        return {**base, "artifact": None, "state": UNDECIDABLE,
                "reason": "记录里没有 metadata.artifact，认不出是哪类制品"}
    try:
        faces = list(resolver(meta))
    except Exception as exc:  # noqa: BLE001 - 算不出来是读数，不是崩溃
        return {**base, "state": UNDECIDABLE,
                "reason": f"重算抛了 {type(exc).__name__}: {exc}"}
    if not faces:
        # 判据不开火与判据判"合"在终端上同形，所以这一档单独点名，不进 in_sync。
        return {**base, "state": UNDECIDABLE,
                "reason": "重算器一个面都没交出来（这把尺子对它不开火，不算通过）"}

    differing = [f for f in faces if f.current and f.stored
                 and str(f.current) != str(f.stored)]
    if differing:
        lead = differing[0]
        names = "、".join(f.name for f in differing)
        reason = _reason_with_faces(f"{names}面当前键与记录里那份不一致",
                                    [f for f in faces if f.reason])
        return {**base, "state": DRIFTED, "faces": [f.as_dict() for f in faces],
                "stored_signature": str(lead.stored)[:16],
                "current_signature": str(lead.current)[:16],
                "reason": reason}

    lacking_baseline = [f for f in faces if not f.stored]
    if lacking_baseline:
        return {**base, "state": NO_SIGNATURE, "faces": [f.as_dict() for f in faces],
                "reason": _reason_with_faces(
                    "这条记录里没有可比对的输入键（该轮的生产者还没写这一项）",
                    lacking_baseline)}
    uncomputable = [f for f in faces if not f.current]
    if uncomputable:
        return {**base, "state": UNDECIDABLE, "faces": [f.as_dict() for f in faces],
                "reason": _reason_with_faces("重算器说它拿不齐输入", uncomputable)}

    lead = faces[0]
    return {**base, "state": IN_SYNC, "faces": [f.as_dict() for f in faces],
            "stored_signature": str(lead.stored)[:16],
            "current_signature": str(lead.current)[:16],
            "reason": None}


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
