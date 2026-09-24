"""GD&T 特征控制框（FCF）：只画声明过的框，框挂在实测特征位置上（capability ``cad.2d_drawings``）。

选型与诚实边界（都做过实测/检索）：

- ezdxf 1.4.2 **有** DXF ``TOLERANCE`` 实体（``AcDbFcf`` 子类，``dimstyle``/``insert``/
  ``content``/``x_axis_vector``；实测存盘读回 1 个实体、``audit()`` 0 错），但 ``Layout``
  上**没有** ``add_tolerance`` 工厂；
- 该实体的 ``content`` 用哪一套转义码（分隔符、直径码、几何特征符号）本轮**没找到权威来源**
  核实（检索命中的是厂商博客/培训文，不足以当编码依据），所以本模块**不宣称**
  「FCF 在 AutoCAD/其他查看器里渲染成什么样」；
- 这里做的是**可回读核验**的那一半：框画成分格矩形 + 每格一条 TEXT + 一条引线连到被测特征，
  同时在图纸证据里留下**结构化**的框内容（特征/符号/公差带/基准链/挂点），
  让下游 CAD 能据此重建语义实体。

符号码位是本仓选定的表（ISO 1101 的符号在字形层面对应这些码位），
不是「渲染已核实」的声明；不在表里的特征（如同轴度）一律判 ``characteristic_unsupported``
而不猜一个近似符号。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# 特征符号表：本仓支持画出并回读的几何特征。second = 是否必须有基准（位置度/轮廓度等
# 是相关要素公差，缺基准就是不完整标注，不静默画个半截框）。
CHARACTERISTICS: dict[str, tuple[str, bool]] = {
    "position": ("⌖", True),
    "perpendicularity": ("⊥", True),
    "parallelism": ("∥", True),
    "angularity": ("∠", True),
    "profile_of_a_line": ("⌒", True),
    "profile_of_a_surface": ("⌓", True),
    "flatness": ("⏥", False),
    "straightness": ("⏤", False),
    "circularity": ("○", False),
    "cylindricity": ("⌭", False),
    "circular_runout": ("↗", True),
}

DIAMETER_SIGN = "⌀"          # U+2300，实测存盘读回原样（DXF TEXT 用码位，不用 %%c）
COMPARTMENT_HEIGHT = 5.0      # 图纸 mm（1:1 时），一格高
CHAR_WIDTH = 2.4              # 每字符近似宽，够判定格宽与回读
MIN_COMPARTMENT_WIDTH = 6.0


def _fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _feature_dim(view: Any, feature: str) -> dict[str, Any] | None:
    if view is None:
        return None
    found: dict[str, Any] | None = None
    for entry in view.dimensions:
        if str(entry.get("feature")) == feature:
            found = dict(entry)
            break
    return found


def _attach_point(view: Any, dim: dict[str, Any]) -> list[float]:
    center = dim.get("center")
    if center:
        return [float(center[0]), float(center[1])]
    return [round((view.bbox[0] + view.bbox[2]) / 2.0, 6),
            round((view.bbox[1] + view.bbox[3]) / 2.0, 6)]


def _issue(kind: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, **fields}


def _zone_text(entry: dict[str, Any]) -> str:
    prefix = DIAMETER_SIGN if entry.get("diametral") else ""
    return f"{prefix}{_fmt(float(entry['zone']))}"


def _compartments(symbol: str, zone: str, datums: Sequence[str]) -> list[str]:
    return [symbol, zone, *datums]


def build_gdt_frames(views: Sequence[Any], spec: dict[str, Any] | None
                     ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """把 spec 里的 ``gdt`` 声明解析成可绘制的框。

    返回 ``(frames, issues, unmatched_features)``。任何一处不成立都**不画**那一个框，
    并把原因结构化返回——不猜符号、不猜基准、不画半截框。
    """
    by_view = {v.name: v for v in views}
    datum_map: dict[str, str] = {}
    for entry in (spec or {}).get("datums") or []:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("feature"):
            continue
        datum_map[str(entry["id"])] = str(entry["feature"])

    frames: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    unmatched: list[str] = []

    for decl in (spec or {}).get("features") or []:
        if not isinstance(decl, dict) or not decl.get("gdt"):
            continue
        feature = str(decl.get("feature") or "")
        view_name, _, local = feature.partition(".")
        view = by_view.get(view_name)
        dim = _feature_dim(view, feature) if (view is not None and local) else None
        if dim is None:
            unmatched.append(feature)
            continue

        for raw in decl["gdt"]:
            entry = raw if isinstance(raw, dict) else {}
            characteristic = str(entry.get("characteristic") or "")
            known = CHARACTERISTICS.get(characteristic)
            if known is None:
                issues.append(_issue("characteristic_unsupported", feature=feature,
                                     characteristic=characteristic))
                continue
            symbol, needs_datum = known
            try:
                zone = float(entry.get("zone"))     # type: ignore[arg-type]
            except (TypeError, ValueError):
                issues.append(_issue("zone_missing", feature=feature,
                                      characteristic=characteristic))
                continue
            if zone <= 0.0:
                issues.append(_issue("zone_not_positive", feature=feature,
                                      characteristic=characteristic, zone=zone))
                continue
            datum_ids = [str(d) for d in (entry.get("datums") or [])]
            if needs_datum and not datum_ids:
                issues.append(_issue("datum_required", feature=feature,
                                      characteristic=characteristic))
                continue

            resolved: list[dict[str, Any]] = []
            broken = False
            for datum_id in datum_ids:
                target = datum_map.get(datum_id)
                if target is None:
                    issues.append(_issue("datum_unresolved", feature=feature,
                                          characteristic=characteristic, datum=datum_id))
                    broken = True
                    continue
                t_view, _, t_local = target.partition(".")
                t_dim = _feature_dim(by_view.get(t_view), target) if t_local else None
                if t_dim is None:
                    issues.append(_issue("datum_feature_missing", feature=feature,
                                          characteristic=characteristic, datum=datum_id,
                                          datum_feature=target))
                    broken = True
                    continue
                resolved.append({"id": datum_id, "feature": target,
                                 "attach": _attach_point(by_view[t_view], t_dim)})
            if broken:
                continue

            comps = _compartments(symbol, _zone_text(entry), datum_ids)
            frames.append({
                "view": view_name,
                "feature": feature,
                "characteristic": characteristic,
                "symbol": symbol,
                "zone": zone,
                "diametral": bool(entry.get("diametral")),
                "datum_refs": datum_ids,
                "datums": resolved,
                "attach": _attach_point(view, dim),
                "compartments": comps,
                "text": "|".join(comps),
                "height_mm": COMPARTMENT_HEIGHT,
            })
    return frames, issues, unmatched


def frame_width(frame: dict[str, Any]) -> float:
    return sum(max(MIN_COMPARTMENT_WIDTH, CHAR_WIDTH * len(str(c)))
               for c in frame["compartments"])


def draw_frame(msp: Any, frame: dict[str, Any], origin: tuple[float, float],
               anchor: tuple[float, float]) -> None:
    """画一个框：每格一个矩形 + 一格一条 TEXT，再加一条引线连到被测特征点。

    ``origin`` 是格序列起点（图纸坐标，已含比例与视图偏移），``anchor`` 是被测特征点。
    """
    from ezdxf.enums import TextEntityAlignment

    x, y = origin
    for comp in frame["compartments"]:
        width = max(MIN_COMPARTMENT_WIDTH, CHAR_WIDTH * len(str(comp)))
        msp.add_lwpolyline([(x, y), (x + width, y), (x + width, y + COMPARTMENT_HEIGHT),
                            (x, y + COMPARTMENT_HEIGHT)], close=True,
                           dxfattribs={"layer": "GDT"})
        msp.add_text(str(comp), dxfattribs={"layer": "GDT", "height": 2.6}) \
           .set_placement((x + width / 2.0, y + COMPARTMENT_HEIGHT / 2.0),
                          align=TextEntityAlignment.MIDDLE_CENTER)
        x += width
    msp.add_line(anchor, (origin[0], origin[1] + COMPARTMENT_HEIGHT / 2.0),
                 dxfattribs={"layer": "GDT"})
