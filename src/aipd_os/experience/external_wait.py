"""外部等待视图：把外部依赖等待项按属性分组为人类可读的中文列表。

``external_waiting`` 是 ``CheckpointManager.resume_summary`` 返回的字典列表，
每项含 source_type / source_id / target_type / target_id（如 supplier / lab /
quote / sample / test），可能带 ``note`` 键。本模块确定性地把它们分桶：
  - supplier：供应商 / 报价 / 询价 / 厂商相关；
  - lab：测试验证 / 样品相关；
  - other：带 ``note`` 或其他无法归类的项。
输出不暴露任何内部代号，只呈现自然语言。
"""
from __future__ import annotations

from typing import Any, Dict, List

# 类型 → 人类可读中文
_TYPE_CN = {
    "supplier": "供应商", "quote": "报价", "rfq": "询价", "vendor": "厂商",
    "lab": "测试实验室", "test": "测试", "pvt": "生产验证", "evt": "工程验证",
    "dvt": "设计验证", "sample": "样品",
}

_SUPPLIER_TOKENS = ("supplier", "quote", "rfq", "vendor")
_LAB_TOKENS = ("lab", "test", "pvt", "evt", "dvt", "sample")

_BUCKET_CN = {"supplier": "供应商", "lab": "测试实验室", "other": "其他"}


def _bucket_for(item: Dict[str, Any]) -> str:
    """确定性归类：note → other；否则 supplier 优先，其次 lab，最后 other。"""
    if "note" in item:
        return "other"
    types = [str(item.get("source_type", "")).lower(),
             str(item.get("target_type", "")).lower()]
    if any(any(t in tok for tok in _SUPPLIER_TOKENS) for t in types):
        return "supplier"
    if any(any(t in tok for tok in _LAB_TOKENS) for t in types):
        return "lab"
    return "other"


def _human_line(item: Dict[str, Any], bucket: str) -> str:
    """把一条外部等待项转成自然语言，不暴露内部代号。"""
    if "note" in item:
        note = str(item.get("note", ""))
        if "blocked" in note.lower():
            return "项目因依赖外部方而暂停推进"
        return f"其他事项：{note}"
    src = _TYPE_CN.get(str(item.get("source_type", "")).lower(),
                       str(item.get("source_type", "")))
    tgt = _TYPE_CN.get(str(item.get("target_type", "")).lower(),
                       str(item.get("target_type", "")))
    return f"等待{src}完成{tgt}"


def summarize_external_wait(external_waiting: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把外部等待列表分组为 supplier / lab / other 桶并返回中文摘要。"""
    buckets: Dict[str, List[str]] = {"supplier": [], "lab": [], "other": []}
    for item in external_waiting:
        bucket = _bucket_for(item)
        buckets[bucket].append(_human_line(item, bucket))

    count = len(external_waiting)
    if count == 0:
        summary = "项目当前无外部等待事项。"
    else:
        parts = [f"{_BUCKET_CN[k]} {len(v)} 项" for k, v in buckets.items() if v]
        summary = f"共有 {count} 项外部等待事项（" + "、".join(parts) + "）。"

    return {
        "supplier": buckets["supplier"],
        "lab": buckets["lab"],
        "other": buckets["other"],
        "count": count,
        "summary": summary,
    }


__all__ = ["summarize_external_wait"]