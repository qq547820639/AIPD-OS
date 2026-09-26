"""链头那一格：由人**声明**一条 CTQ（关键尺寸合格域），写进 Product Truth。

为什么需要这一件：`record_type="ctq"` 在本仓一直**只有读者**——
`release_manifest._collect_ctq`（发布证据的分母）、`cad/spec_from_truth.py`
（图纸声明的输入）、`cli/commands_drawing.py` 与 `cad/spec_rework.py`（返工重算）
全都 `query(record_type="ctq")`，而全仓（排除 `tests/`）没有任何一处写它。
于是链条的第二跳 `aipd drawing spec` 在真库里根本跑不起来：它的输入只能靠测试种。

为什么不复用 Product Intelligence 的 gate 来产 CTQ：`gate.commit_snapshot`
只写 `requirement` / `feature`（`product_intelligence/gate.py:455,476`），
而 Feature 模型里没有任何公差字段（`product_intelligence/models.py:507-519`）。
让 gate 顺带派生 CTQ 等于**凭空发明上下限**——那是发明工程要求，不是转译要求。
所以这里走"属主自述"：声明人与检验方式必填，信任级由既有推导函数算，不自己升格。

两条纪律值得单独写：
1. **`trust_level` 不许自封。** 沿用 `product_intelligence/gate_criteria._derive_trust`
   （P0-08：Owner 批准本身 ≠ verified）：有验证引用且认识论态非 `U` 才算 `verified`，
   `V/C/E` 给 `medium`，其余 `unverified`。也就是说"我只说一句要求"落库是
   `unverified`，要升到 `verified` 得带 `--test-ref`；
2. **同一个图纸尺寸上抢第二条，在门口就拒。** `spec_from_truth.py` 遇到
   `ctq_duplicate_drawing_feature` 会把**两条一起撤回**（"按遍历顺序挑一个赢家"它不做），
   所以这里提前点名既有记录，比让出图那天两条都消失好。
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aipd_os.product_intelligence.gate_criteria import _derive_trust
from aipd_os.product_truth.models import SourceRef, TruthRecord, now_iso

# 认识论态的取值面**不另立一套**：这就是 `_derive_trust` 自己分支的那五个字母
# （`gate_criteria.py:145-149`）。默认 `A`（断言）与 PI 各模型里的
# `epistemic_status: str = "A"` 同一个缺省。
EPISTEMIC_STATUSES = frozenset({"V", "C", "E", "A", "U"})


class CtqDeclarationError(ValueError):
    """声明不合法。消息里必须写清是**哪一格**、**为什么**，别只说"参数错"。"""


def _clean(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CtqDeclarationError(f"{field} 不能为空：这一格是读者的必填项，缺了就点名不到")
    return text


def _number(value: Any, field: str) -> float:
    """数值参数：CLI 传来的是字符串，库里读回来的可能是数。

    只认"能原样解析成有限数"的输入；`nan`/`inf`/空串/`"8,0"` 一律拒——
    下游 `spec_from_truth._num` 对字符串按"没给"处理，
    这里顺手放宽就会造出一条"记了限值但没人读得出限值"的记录。
    """
    if isinstance(value, bool):
        raise CtqDeclarationError(f"{field} 不能是布尔，拿到 {value!r}")
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = float(text)
        except ValueError:
            raise CtqDeclarationError(
                f"{field} 必须是数，拿到 {value!r}（解析不出数就不写，"
                "下游会把字符串当'没给限值'而不是当 0）") from None
    else:
        raise CtqDeclarationError(f"{field} 必须是数，拿到 {type(value).__name__}")
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise CtqDeclarationError(f"{field} 是 {value!r}：nan/inf 不是合格的极限值")
    return parsed


def identical_declared_ctq(existing: Iterable[Any], *, feature: str, drawing_feature: str,
                           nominal: float, lower_limit: float, upper_limit: float,
                           inspection_method: str) -> Any:
    """在既有 CTQ 里找"同一份声明"（幂等重跑用），找不到返回 None。"""
    for rec in existing:
        meta = rec.metadata or {}
        if str(meta.get("drawing_feature") or "") != drawing_feature:
            continue
        if str(meta.get("feature") or "") != feature:
            continue
        if str(meta.get("inspection_method") or "") != inspection_method:
            continue
        raw: list[Any] = [meta.get(key) for key in ("nominal", "lower_limit",
                                                    "upper_limit")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in raw):
            continue      # 旧记录连数都不是 ⇒ 不是同一份声明，也不许拿它判等
        want = [nominal, lower_limit, upper_limit]
        if [float(v) for v in raw] == [float(v) for v in want]:
            return rec
    return None


def declare_ctq(store: Any, *, feature: str, drawing_feature: str, nominal: Any,
                lower_limit: Any, upper_limit: Any, inspection_method: str,
                declared_by: str, epistemic_status: str = "A",
                test_refs: Iterable[str] = (), note: str | None = None,
                supersedes: str | None = None,
                tenant_id: str | None = None,
                project_id: str | None = None) -> dict[str, Any]:
    """写一条 CTQ，返回 `{record_id, created, trust_level, …}`。

    全量校验在**任何写之前**完成：这条命令要么落一条要么什么都不落，
    不留"记了个半条要求"的中间态。

    `supersedes` 给的是"这条新声明取代的那条旧记录"：旧的那条**不该再占住同一个图纸尺寸**
    （否则 `aipd ctq revise` 会被自己的查重挡住，等于没有修订路径）。它只从查重名单里
    被排除，值本身仍要过同一套门口校验——取代不等于免检。
    """
    feature = _clean(feature, "--feature")
    drawing_feature = _clean(drawing_feature, "--drawing-feature")
    inspection_method = _clean(inspection_method, "--inspection")
    declared_by = _clean(declared_by, "--by")
    epistemic_status = str(epistemic_status or "").strip().upper()
    if epistemic_status not in EPISTEMIC_STATUSES:
        raise CtqDeclarationError(
            f"--epistemic 只认 {'/'.join(sorted(EPISTEMIC_STATUSES))}"
            f"（这是 `_derive_trust` 分支的那五个字母），拿到 {epistemic_status!r}")
    nominal = _number(nominal, "--nominal")
    lower_limit = _number(lower_limit, "--lower")
    upper_limit = _number(upper_limit, "--upper")
    if lower_limit >= upper_limit:
        raise CtqDeclarationError(
            f"下限 {lower_limit:g} 必须严格小于上限 {upper_limit:g}："
            "否则这不是一个可判定的合格域")
    if not (lower_limit <= nominal <= upper_limit):
        raise CtqDeclarationError(
            f"标称 {nominal:g} 不在 [{lower_limit:g}, {upper_limit:g}] 里："
            "标称自己就不合格，画出来的图没有一条能过")
    refs = [str(r).strip() for r in (test_refs or ()) if str(r).strip()]

    scope = {"tenant_id": tenant_id, "project_id": project_id}
    retired = str(supersedes) if supersedes else None
    active = [r for r in store.query(record_type="ctq", **scope)
              if str(r.status) == "active" and str(r.record_id) != retired]
    twin = identical_declared_ctq(active, feature=feature,
                                  drawing_feature=drawing_feature, nominal=nominal,
                                  lower_limit=lower_limit, upper_limit=upper_limit,
                                  inspection_method=inspection_method)
    if twin is not None:
        return {"record_id": str(twin.record_id), "created": False,
                "trust_level": str(twin.trust_level), "feature": feature,
                "drawing_feature": drawing_feature,
                "limits": [lower_limit, upper_limit], "nominal": nominal,
                "inspection_method": inspection_method,
                "epistemic_status": epistemic_status,
                "reason": "同一份声明已经在库里（重跑不另起一条）"}
    for rec in active:
        meta = rec.metadata or {}
        if str(meta.get("drawing_feature") or "") == drawing_feature:
            raise CtqDeclarationError(
                f"图纸尺寸 {drawing_feature} 已经被 CTQ {rec.record_id}"
                f"（{meta.get('feature')}，[{meta.get('lower_limit')}, "
                f"{meta.get('upper_limit')}]）认领。`aipd drawing spec` 遇到同一尺寸上"
                "两条公差会把**两条一起撤回**（它不按遍历顺序挑赢家），"
                "所以这里先在门口拒掉：先处置旧的那条再来")

    trust_level = _derive_trust(epistemic_status, inspection_method, refs)
    record_id = store.add(
        TruthRecord(
            record_type="ctq",
            content=f"CTQ {feature} @ {drawing_feature} "
                    f"[{lower_limit:g}, {upper_limit:g}] 检验 {inspection_method}",
            source=SourceRef(note=f"declared by {declared_by} via "
                                  f"aipd truth ctq add (epistemic={epistemic_status})"),
            trust_level=trust_level,
            metadata={"feature": feature, "drawing_feature": drawing_feature,
                      "nominal": nominal, "lower_limit": lower_limit,
                      "upper_limit": upper_limit,
                      "inspection_method": inspection_method,
                      "declared_by": declared_by,
                      "epistemic_status": epistemic_status,
                      "test_refs": refs, **({"note": note} if note else {})}),
        **scope)
    return {"record_id": record_id, "created": True, "trust_level": trust_level,
            "feature": feature, "drawing_feature": drawing_feature,
            "limits": [lower_limit, upper_limit], "nominal": nominal,
            "inspection_method": inspection_method,
            "epistemic_status": epistemic_status, "test_refs": refs}


def _limits_of(meta: dict[str, Any]) -> dict[str, Any]:
    """一条 CTQ 的"要求内容"快照：修订前后就比这几项，别把时间戳算进去。"""
    return {"nominal": meta.get("nominal"), "lower_limit": meta.get("lower_limit"),
            "upper_limit": meta.get("upper_limit"),
            "inspection_method": meta.get("inspection_method")}


def _snapshot(rec: Any) -> dict[str, Any]:
    meta = dict(rec.metadata or {})
    return {"record_id": str(rec.record_id), "status": str(rec.status),
            "version": int(rec.version), "trust_level": str(rec.trust_level),
            "feature": meta.get("feature"),
            "drawing_feature": meta.get("drawing_feature"),
            **_limits_of(meta),
            "epistemic_status": meta.get("epistemic_status"),
            "declared_by": meta.get("declared_by"),
            "test_refs": list(meta.get("test_refs") or [])}


def _require_ctq(store: Any, record_id: str, tenant_id: str | None,
                 project_id: str | None) -> Any:
    try:
        rec = store.get(record_id, tenant_id=tenant_id, project_id=project_id)
    except KeyError as exc:
        raise CtqDeclarationError(
            f"要处理的 CTQ 记录不存在：{record_id!r}（{exc}）") from exc
    if str(rec.record_type) != "ctq":
        raise CtqDeclarationError(
            f"{record_id} 是 {rec.record_type}，不是 ctq 记录；"
            "修订/停用只对着合格域声明本身")
    return rec


def revise_ctq(store: Any, *, record_id: str, revised_by: str,
               nominal: Any = None, lower_limit: Any = None, upper_limit: Any = None,
               inspection_method: str | None = None,
               epistemic_status: str | None = None,
               test_refs: Iterable[str] | None = None,
               note: str | None = None, tenant_id: str | None = None,
               project_id: str | None = None) -> dict[str, Any]:
    """修订一条已声明的 CTQ：**另起一条新版本**，旧的那条标 `superseded` 并留链。

    形状取自本轮实读的 dbt model versions（"新版本落地、`latest_version` 才是 canonical、
    旧版留在名单里"）+ django-simple-history（"历史行带 user 与 change reason，
    不改写原文"），落在本仓既有的 `superseded` 状态与 `audit_log` 通道上，不引依赖。

    为什么不在原地改值：
    - 原地改就把"谁在什么时候把 8.05 改成 8.10"只剩审计表一份孤证，
      而 `AIPDStateDB.list_audit` 不分作用域且默认 `limit=100`，读者一翻页就丢；
    - `superseded` 在本仓已有确定语义（`release_manifest.py:95-99` 对它只出**非阻断**点名，
      并提醒"确认取代它的那条在名单里"）；改完限值后旧声明会因上游不再 active 而被
      第 57 片的源面判成漂移 ⇒ 返工把声明演进到新版本，链条有**可达的出口**。
      （反过来用 `expired` 会把这条要求永久卡在阻断名单里，那是没有出口的判决。）

    中途失败的方向也是选过的：新记录先落、旧记录后置 `superseded`，
    若两步之间崩了，留下的是"同一图纸尺寸两条 active"——那会被门口查重与
    `spec_from_ctq` 的冲突撤回**响亮地**报出来，不是静默丢要求。
    """
    actor = _clean(revised_by, "--by")
    old = _require_ctq(store, record_id, tenant_id, project_id)
    if str(old.status) != "active":
        raise CtqDeclarationError(
            f"{record_id} 当前状态是 {old.status}，不是 active。"
            "修订只对着今天有效的那条要求；要重开一条已被停用的，请跑 `aipd ctq add`")
    meta = dict(old.metadata or {})
    want = _limits_of(meta)
    new_nominal = want["nominal"] if nominal is None else nominal
    new_lower = want["lower_limit"] if lower_limit is None else lower_limit
    new_upper = want["upper_limit"] if upper_limit is None else upper_limit
    new_inspection = (meta.get("inspection_method") if inspection_method is None
                      else inspection_method)
    new_epistemic = (meta.get("epistemic_status") or "A") if epistemic_status is None \
        else epistemic_status
    refs = ([str(r) for r in (meta.get("test_refs") or [])] if test_refs is None
            else [str(r) for r in test_refs])

    def _same(new: Any, old_value: Any) -> bool:
        """新值与库里那份是否同一件事：数值按 float 比（"8.10" 与 8.1 是一个值），
        其余按字符串比。"""
        try:
            return float(new) == float(old_value)
        except (TypeError, ValueError):
            return str(new if new is not None else "") == str(
                old_value if old_value is not None else "")

    if (_same(new_nominal, want["nominal"])
            and _same(new_lower, want["lower_limit"])
            and _same(new_upper, want["upper_limit"])
            and _same(new_inspection, want["inspection_method"])
            and str(new_epistemic).strip().upper() == str(meta.get("epistemic_status"))
            and sorted(refs) == sorted(str(r) for r in (meta.get("test_refs") or []))):
        # 为什么在这里比而不是靠 declare_ctq 的幂等查重：`supersedes` 会把被修订的
        # 那条从查重名单里摘掉（不摘就永远修订不动自己），于是"改回同一个值"在
        # declare 眼里成了"一条新声明"——实测过：同值 revise 会真的另起一条新版本。
        return {"changed": False, "record_id": str(old.record_id),
                "before": _snapshot(old), "after": _snapshot(old),
                "limits": [want["lower_limit"], want["upper_limit"]],
                "feature": meta.get("feature"),
                "drawing_feature": meta.get("drawing_feature"),
                "trust_level": str(old.trust_level),
                "epistemic_status": str(new_epistemic).strip().upper(),
                "reason": "新值与现值逐项一致，不另起版本（修订要留下变化才有意义）"}

    created = declare_ctq(
        store, feature=str(meta.get("feature") or ""),
        drawing_feature=str(meta.get("drawing_feature") or ""),
        nominal=new_nominal, lower_limit=new_lower, upper_limit=new_upper,
        inspection_method=str(new_inspection or ""), declared_by=actor,
        epistemic_status=str(new_epistemic), test_refs=refs, note=note,
        supersedes=str(old.record_id), tenant_id=tenant_id, project_id=project_id)
    if not created["created"]:
        return {"changed": False, "record_id": created["record_id"],
                "before": _snapshot(old), "after": _snapshot(old),
                "limits": created["limits"], "feature": created["feature"],
                "drawing_feature": created["drawing_feature"],
                "trust_level": created["trust_level"],
                "epistemic_status": str(new_epistemic),
                "reason": created.get("reason") or "新值与现值一致，不另起版本"}

    store.update(old.record_id, status="superseded",
                 metadata={**meta, "superseded_by": str(created["record_id"]),
                           "superseded_at": now_iso(),
                           "superseded_by_actor": actor,
                           **({"superseded_reason": note} if note else {})},
                 tenant_id=tenant_id, project_id=project_id)
    # 新版本号跟着被取代的那条走：`declare_ctq` 一律写 version=1，
    # 不接上的话链上每条都叫 v1，"改了几次"就又要去数审计行才知。
    store.update(created["record_id"], version=int(old.version) + 1,
                 tenant_id=tenant_id, project_id=project_id)
    after = store.get(created["record_id"], tenant_id=tenant_id, project_id=project_id)
    return {"changed": True, "record_id": str(created["record_id"]),
            "superseded": str(old.record_id), "version": int(after.version),
            "trust_level": created["trust_level"], "limits": created["limits"],
            "feature": created["feature"],
            "drawing_feature": created["drawing_feature"],
            "epistemic_status": str(new_epistemic), "test_refs": refs,
            "before": _snapshot(old), "after": _snapshot(after)}


def deprecate_ctq(store: Any, *, record_id: str, by: str, reason: str,
                  replaced_by: str | None = None, tenant_id: str | None = None,
                  project_id: str | None = None) -> dict[str, Any]:
    """停用一条 CTQ：状态 `superseded` + 链上写明"为什么、被谁取代"。

    必须有 `--reason`（"没人说为什么就退掉了要求"是这一族命令最不能留的状态），
    且 `--replaced-by` 给了就得真存在 —— 指向不存在的记录比不写更坏：它会骗过
    `release_manifest.py:95` 那句"确认取代它的那条在名单里"。
    """
    actor = _clean(by, "--by")
    reason = _clean(reason, "--reason")
    rec = _require_ctq(store, record_id, tenant_id, project_id)
    if str(rec.status) not in ("active", "stale"):
        raise CtqDeclarationError(
            f"{record_id} 当前状态是 {rec.status}，已经不在有效名单里，无需停用")
    meta = dict(rec.metadata or {})
    successor = str(replaced_by).strip() if replaced_by else None
    if successor:
        try:
            store.get(successor, tenant_id=tenant_id, project_id=project_id)
        except KeyError as exc:
            raise CtqDeclarationError(
                f"--replaced-by 指向的记录不存在：{successor}（{exc}）。"
                "写一个假的取代关系比不写更坏——门禁的点名会照着它判"
                "「已被取代、不计入分母」") from exc
    store.update(record_id, status="superseded",
                 metadata={**meta, "superseded_at": now_iso(),
                           "superseded_by_actor": actor,
                           "superseded_reason": reason,
                           **({"superseded_by": successor} if successor else {})},
                 tenant_id=tenant_id, project_id=project_id)
    after = store.get(record_id, tenant_id=tenant_id, project_id=project_id)
    return {"deprecated": True, "record_id": str(record_id),
            "replaced_by": successor, "before": _snapshot(rec),
            "after": _snapshot(after), "feature": meta.get("feature"),
            "drawing_feature": meta.get("drawing_feature"),
            "limits": [meta.get("lower_limit"), meta.get("upper_limit")]}
