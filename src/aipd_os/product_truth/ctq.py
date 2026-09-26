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
from aipd_os.product_truth.models import SourceRef, TruthRecord

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
                tenant_id: str | None = None,
                project_id: str | None = None) -> dict[str, Any]:
    """写一条 CTQ，返回 `{record_id, created, trust_level, …}`。

    全量校验在**任何写之前**完成：这条命令要么落一条要么什么都不落，
    不留"记了个半条要求"的中间态。
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
    active = [r for r in store.query(record_type="ctq", **scope)
              if str(r.status) == "active"]
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
