"""公差声明的**生产者**：Product Truth 的 CTQ 记录 → ``--spec`` 吃的那份声明。

F-DRAW-01 第 5 片（也是 `industrialize.release_evidence` 那格限制的收口）。改前
图纸的公差/GD&T 声明只能由人手写一份 JSON，CTQ 与图上特征的对应关系靠人在 spec 里
逐条抄 `ctq_ref`——于是「图纸覆盖 CTQ」这条门禁实际考的是**人抄得对不对**，
而不是产品有没有把要求传到图纸。这一片把抄写这一步变成产品代码。

口径（全部有用例钉住）：

1. **只认显式关联**：CTQ 必须写 ``metadata.drawing_feature``（形如 ``TOP.hole_2``）。
   不按名字、不按直径相近去猜——名字里带 ``Ø6`` 而图上有四个孔的场合，猜就是标错尺寸。
2. **必须有标称值才换算**：``nominal`` 缺位时不能拿「图纸实测值」当标称（那是把
   被检对象当基准），也不能折算成 0 偏差 ⇒ 点名 ``ctq_missing_nominal`` 并拒绝产出。
3. **绝对上下限 → 偏差**：``upper = upper_limit - nominal``、``lower = lower_limit - nominal``
   （非对称照样成立），``ctq_ref`` 写记录 id，供发布门禁做数值一致性核对。
4. **不自相矛盾**：同一 ``drawing_feature`` 被两条 CTQ 认领 ⇒ 两条都不产出并点名，
   不「取后者覆盖前者」。
5. **绝对合格域随行**：spec 条目带 ``limits``（min/max/nominal），出图时拿**投影实测值**
   去比它 ⇒ 「模型几何根本不满足这条 CTQ」能被机器发现（``ctq_window_violation``），
   这一半判据不来自 CTQ 自己，所以不是自证。
6. **半成品不落盘**：只要还有 gap，就不写 spec 文件（写了就是一份看着能用、其实漏标的
   声明），命令判未收口（exit 4）并逐条点名。

选型：形状借 QIF（ISO 23952）的 characteristic「标称＋上下限＋显式几何关联」，
但本轮**未检索到可 pip 安装的 Python 实现**、官方 SDK 源码未读，故不引外部依赖；
STEP AP242 PMI 语义关联是长期路线，但要把产出物从 DXF 换成 STEP，本环境也无法核验渲染，
故不在本片。
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

__all__ = ["spec_from_ctq", "ctq_gap"]


def ctq_gap(kind: str, record_id: Any, detail: str) -> dict[str, Any]:
    return {"kind": kind, "record_id": str(record_id), "detail": detail,
            "blocking": True}


def _num(value: Any) -> float | None:
    """上下限/标称只接受真数；字符串按「没给」处理，不顺手 float() 一个可能是别名的值。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def spec_from_ctq(records: Iterable[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """CTQ 记录 → ``(spec, gaps)``；spec 的形状与手写 ``--spec`` 完全一致。

    ``records`` 直接收 ``ProductTruthStore.query(record_type='ctq', status='active')``
    的返回值（用 ``record_id`` 与 ``metadata`` 两个字段）。
    """
    features: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    claimed: dict[str, str] = {}
    for rec in records:
        meta = getattr(rec, "metadata", None) or {}
        rid = getattr(rec, "record_id", "?")
        feature = meta.get("feature")
        target = meta.get("drawing_feature")
        if not target:
            gaps.append(ctq_gap(
                "ctq_missing_drawing_feature", rid,
                f"CTQ {feature or rid} 没写 metadata.drawing_feature，"
                f"无法确定它约束图上的哪条尺寸（本模块不按名字/直径猜映射）"))
            continue
        target = str(target)
        if target in claimed:
            gaps.append(ctq_gap(
                "ctq_duplicate_drawing_feature", rid,
                f"CTQ {target} 与 CTQ {claimed[target]} 认领同一个图纸特征，"
                f"两条公差不能同时成立，先解决冲突再出声明"))
            # 连先来的那条也撤回：留下它等于「按遍历顺序挑一个赢家」
            features[:] = [f for f in features if f["feature"] != target]
            del claimed[target]
            continue

        nominal = _num(meta.get("nominal"))
        low = _num(meta.get("lower_limit"))
        high = _num(meta.get("upper_limit"))
        if nominal is None or low is None or high is None:
            missing = [name for name, val in (("nominal", nominal),
                                              ("lower_limit", low),
                                              ("upper_limit", high)) if val is None]
            gaps.append(ctq_gap(
                "ctq_missing_limit_value", rid,
                f"CTQ {feature or rid} 缺 {'/'.join(missing)}；"
                f"缺标称值时不拿图纸实测值当标称，也不折算成 0 偏差"))
            continue
        if low > high:
            gaps.append(ctq_gap(
                "ctq_limits_inverted", rid,
                f"CTQ {feature or rid} 的下限 {low:g} 大于上限 {high:g}，"
                f"这不是一个可判定的合格域"))
            continue

        claimed[target] = str(rid)
        entry: dict[str, Any] = {
            "feature": target,
            "tolerance": {"upper": round(high - nominal, 9),
                          "lower": round(low - nominal, 9)},
            # 绝对合格域原样带上：出图时拿**实测值**去比它，才知道模型满不满足这条 CTQ
            "limits": {"min": low, "max": high, "nominal": nominal},
            "ctq_ref": str(rid),
        }
        if feature:
            entry["ctq_feature"] = str(feature)
        features.append(entry)

    # 不推 global_tolerance：`global_tolerance` 会贴到**每一条**没单独声明的尺寸上，
    # 把「封闭环的 CTQ」当全局公差就是给没人声明的特征凭空造公差。
    return {"features": features, "generated_from": "product_truth.ctq"}, gaps

