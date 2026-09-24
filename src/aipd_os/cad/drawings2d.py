"""二维工程图生成（capability ``cad.2d_drawings``）。

3D B-Rep -> 正投影视图（可见线 + 隐藏线）+ 尺寸 + 标题栏 -> DXF。

本机（OCP 7.7.2 / ezdxf 1.4.2 / py3.9.6）实测结论，不是照抄惯例：

- **投影几何准确**：40×20×10 板的三个正视图并集包围盒分别为
  FRONT 40×10、TOP 40×20、RIGHT 10×20，与模型真实尺寸逐位吻合；
  竖直 Ø6 孔在 TOP 视图被拟合为两个 ``diameter=6.0`` 的闭合圆。
- **不用 OCCT HLR 做可见性判据**：``HLRBRep_Algo`` 的 ``VCompound()`` 在本机
  **没有做遮挡剔除** —— 一个 Plain Box 正视给出 8 条「可见」边，正是全部
  12 条边投影重合后的结果；同一构造 ``HCompound()`` 恒为 0，
  在「开口薄壁盒正视」这种必然存在被完全遮挡边线的构造上也仍是 0
  （``Perspective()`` 为 False，``Add`` 也没有容差重载可用）。
  可见/隐藏一律由 ``classify_view`` 的射线遮挡判定得出。
- **隐藏线的已知边界（相切）**：逐点射线法在「视线与曲面相切」处不可靠。
  竖直孔的筒壁轮廓线 x=±3 从正视看正好与圆柱面相切，实测 -3 侧判为隐藏、
  +3 侧判为不隐藏。真实 CAD 靠曲面分类解决，这里靠**显式声明 + 现状钉住用例**
  解决（见 ``tests/test_cad_drawings2d.py::TestTangencyLimit``）。
- **尺寸数值来自几何测量**（视图并集包围盒 / 检出圆的直径），不来自参数字典——
  参数是「声称」，投影出来的几何才是「画在图上的东西」。尺寸链同样由实测孔心排出来，
  并核对「各段之和 == 总体宽」，写在证据的 ``dimension_chain_check`` 里。
- **公差的符号约定（ezdxf 1.4.2 源码 + 实测，别照抄直觉）**：``set_tolerance(upper, lower)``
  把两个值**原样**写进 ``dimtp``/``dimtm``，而渲染器 ``Tolerance.update_tolerance_text``
  对下偏差取 ``sign_char(dimtm * -1)``——也就是说 ``dimtm`` 存的是「下偏差的相反数」。
  直接把 -0.05 当 lower 传进去，图纸上会打成 ``+0.05``（实测读数）；正确写法是
  ``set_tolerance(upper, -lower)``，本机实测四种形状（对称 ±0.05、非对称 +0.10/-0.02、
  双侧正 +0.05/+0.01、三位小数 0.025）渲染文本全部与声明一致。另外 override 只在
  ``render()`` 时才落到实体上：只 ``set_tolerance`` 不渲染，读回 ``dimtol`` 仍是缺省 0，
  公差会静默消失（实测；``render()`` 内部自带提交，无需额外 ``commit()``）。
- **公差只来自声明**：没有 spec 就一个公差不写；spec 里写了但图上没有的特征进
  ``spec_unmatched_features`` 点名，绝不静默少标。

明确**未实现**（不要当成已具备）：GD&T 形位公差框、公差叠加分析（链已给出但只做
闭合核对、不做统计叠加）、剖视与局部放大、爆炸图、多零件装配图。
见 registry 的 ``current_limitation``。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 视图定义：normal 指向观察者，up 是图纸上的「上」。
STANDARD_VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "FRONT": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "TOP": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "RIGHT": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "REAR": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "LEFT": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "BOTTOM": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
}

# ISO A3 (400x297) 与 A4 (297x210)；图纸单位 mm。
SHEET_SIZES = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}
MARGIN = 10.0
TITLE_BLOCK = (180.0, 50.0)

DEFAULT_DEFLECTION = 0.05        # 曲线离散化弦高（mm）
MAX_SAMPLES_PER_EDGE = 60        # 遮挡判定的每边采样上限（防止大模型爆炸）
OCCLUSION_EPS = 1e-4             # 射线起点沿视线方向外推，避免自交误判

# 图纸证据里声明隐藏线是怎么来的（不假装是 OCCT 的正式 HLR 结果）。
HIDDEN_LINE_METHOD = ("ray-occlusion classification over projected edges; "
                      "OCCT HCompound returned no hidden set in this build")

DIMSTYLE = "EZ_M_100_H25_CM"
DIM_ROW_GAP = 10.0        # 无尺寸链时总体宽尺寸的引出距离
CHAIN_ROW_GAP = 12.0      # 尺寸链行距零件下沿
OVERALL_OUTSIDE_GAP = 30.0  # 有链时总体宽尺寸挪到链的外侧，避免两行重叠
MIN_TOLERANCE_DECIMALS = 2  # 偏差不许因为声明写得粗就被截断显示；只允许显示更多位


@dataclass
class ViewGeometry:
    """一个视图的 2D 结果（坐标单位 = 模型单位，视图局部原点居中于质心）。"""

    name: str
    direction: tuple[float, float, float]
    up: tuple[float, float, float]
    visible: list[list[tuple[float, float]]] = field(default_factory=list)
    hidden: list[list[tuple[float, float]]] = field(default_factory=list)
    circles: list[dict[str, Any]] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # minx, miny, maxx, maxy
    chain_check: dict[str, Any] = field(default_factory=dict)
    dimensions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


def _normalize(vec: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2)
    if n == 0.0:
        raise ValueError("视图方向不能为零向量")
    return (vec[0] / n, vec[1] / n, vec[2] / n)


def view_basis(direction: tuple[float, float, float],
               up: tuple[float, float, float]) -> dict[str, tuple[float, float, float]]:
    """构造右手视图基 (right, up, normal)：normal 指向观察者。

    与 OCCT ``gp_Ax2(origin, normal, xdir)`` 的约定对齐：``Y = N × X``。
    取 ``right = up × normal`` 可保证 (right, up, normal) 右手且不镜像
    （实测：normal=(0,-1,0)、up=(0,0,1) → right=(1,0,0)，前视 x 跨 ±20、y 跨 ±5）。
    """
    from OCP.gp import gp_Vec

    n = gp_Vec(*_normalize(direction))
    u = gp_Vec(*_normalize(up))
    r = u.Crossed(n)
    r.Normalize()
    u2 = n.Crossed(r)
    return {"right": (r.X(), r.Y(), r.Z()),
            "up": (u2.X(), u2.Y(), u2.Z()),
            "normal": (n.X(), n.Y(), n.Z())}


def _dot(p: tuple[float, float, float], axis: tuple[float, float, float]) -> float:
    return p[0] * axis[0] + p[1] * axis[1] + p[2] * axis[2]


def _topo_shape(model: Any) -> Any:
    """把 cadquery Workplane/Shape/TopoDS_Shape 归一成 TopoDS_Shape。"""
    from OCP.TopoDS import TopoDS

    if hasattr(model, "wrapped") and model.wrapped is not None:
        return model.wrapped
    if hasattr(model, "val"):
        return _topo_shape(model.val())
    return TopoDS.Shape(model) if not hasattr(model, "ShapeType") else model


def _discretize(edge: Any, deflection: float) -> list[tuple[float, float, float]]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection

    pts: list[tuple[float, float, float]] = []
    g = GCPnts_QuasiUniformDeflection(BRepAdaptor_Curve(edge), deflection)
    if not g.IsDone():
        return pts
    n = g.NbPoints()
    step = max(1, math.ceil(n / MAX_SAMPLES_PER_EDGE))
    for i in range(1, n + 1, step):
        p = g.Value(i)
        pts.append((p.X(), p.Y(), p.Z()))
    if n > 1:
        last = g.Value(n)
        if pts[-1] != (last.X(), last.Y(), last.Z()):
            pts.append((last.X(), last.Y(), last.Z()))
    return pts


def _iter_edges(shape: Any) -> list[Any]:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_EDGE)
    while exp.More():
        out.append(TopoDS.Edge_s(exp.Current()))
        exp.Next()
    return out


def _shape_intersector(shape: Any) -> Any:
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)
    return inter


def _runs(flags: list[bool]) -> list[tuple[int, int, bool]]:
    """把逐点遮挡判定切成连续段：[(start, end, occluded)]。"""
    out: list[tuple[int, int, bool]] = []
    start = 0
    for i in range(1, len(flags)):
        if flags[i] != flags[start]:
            out.append((start, i - 1, flags[start]))
            start = i
    out.append((start, len(flags) - 1, flags[start]))
    return [(a, b, v) for a, b, v in out if b > a]


def _point_segment_dist(p: tuple[float, float], a: tuple[float, float],
                        b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == dy == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _poly_distance(p: tuple[float, float], poly: list[tuple[float, float]]) -> float:
    """到折线的**线段**距离；量到顶点会把共线段误判成「不重合」。"""
    if len(poly) == 1:
        return math.hypot(p[0] - poly[0][0], p[1] - poly[0][1])
    return min(_point_segment_dist(p, poly[i], poly[i + 1])
               for i in range(len(poly) - 1))


def _coincident(poly: list[tuple[float, float]], others: list[list[tuple[float, float]]],
                tol: float = 1e-2) -> bool:
    """隐藏段是否与某条可见段重合（正方体的前后边投影重合 ⇒ 图纸上只画实线）。"""
    samples = [poly[i] for i in (0, len(poly) // 2, len(poly) - 1)]
    for other in others:
        if len(other) < 2:
            continue
        if all(_poly_distance(p, other) <= tol for p in samples):
            return True
    return False


def classify_view(shape: Any, basis: dict[str, tuple[float, float, float]]
                  ) -> tuple[list[list[tuple[float, float]]],
                             list[list[tuple[float, float]]]]:
    """投影所有边并按遮挡分可见/隐藏。

    不用 ``HLRBRep_Algo`` 的 VCompound 作可见性判据：本机 OCP 7.7.2 实测它
    **没有做遮挡剔除** —— 一个 40×20×10 的 Plain Box 正视给出 8 条「可见」边，
    正是全部 12 条边投影重合后的结果；同一构造下 ``HCompound()`` 恒为 0。
    可见性一律由射线遮挡判定得出。
    """
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

    inter = _shape_intersector(shape)
    nrm, rgt, up = basis["normal"], basis["right"], basis["up"]

    def occluded(p3: tuple[float, float, float]) -> bool:
        # 起点不外推：外推会把自身所在面推到前面，而真正的遮挡面恰在 eps 量级外，
        # 会被同一条 eps 死区误排除（实测隐藏线恒为 0）。只靠 t > eps 跳过自身面。
        inter.Perform(gp_Lin(gp_Pnt(*p3), gp_Dir(*nrm)), OCCLUSION_EPS, 1e9)
        return bool(inter.NbPnt() > 0)

    visible: list[list[tuple[float, float]]] = []
    hidden: list[list[tuple[float, float]]] = []
    for edge in _iter_edges(shape):
        pts3 = _discretize(edge, DEFAULT_DEFLECTION)
        if len(pts3) < 2:
            continue
        flags = [occluded(p) for p in pts3]
        for a, b, is_hidden in _runs(flags):
            poly = [(_dot(pts3[i], rgt), _dot(pts3[i], up)) for i in range(a, b + 1)]
            if is_hidden:
                hidden.append(poly)
            else:
                visible.append(poly)
    hidden = [h for h in hidden if not _coincident(h, visible)]
    hidden = _dedupe(hidden)
    return visible, hidden


def _dedupe(polys: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """同一条边被拆成多段后可能重复出现（实测同一 x=-3 垂线出现两次）。"""
    seen: set[tuple[float, float, float, float]] = set()
    out: list[list[tuple[float, float]]] = []
    for poly in polys:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        key = (round(min(xs), 3), round(max(xs), 3), round(min(ys), 3), round(max(ys), 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(poly)
    return out


def _solve3(a: list[list[float]], b: list[float]) -> list[float] | None:
    """3x3 线性方程组高斯消元；奇异则返回 None。"""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(3):
            if r == col:
                continue
            factor = m[r][col] / m[col][col]
            for c in range(col, 4):
                m[r][c] -= factor * m[col][c]
    return [m[i][3] / m[i][i] for i in range(3)]


def _fit_circle(pts: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """Kåsa 代数圆拟合，返回 (cx, cy, r)；不可拟合时 None。

    不用「包围盒中点 = 圆心」：圆角/倒角投影出的四分之一圆角，其包围盒中点
    并不是圆心，会被误判成孔并标上错误的圆心（实测 4 孔板只认出 2 个真位置）。
    """
    n = len(pts)
    if n < 8:
        return None
    s1x = s1y = sxx = syy = sxy = 0.0
    sxxx = syyy = sxxy = sxyy = 0.0
    for x, y in pts:
        x2, y2 = x * x, y * y
        s1x += x
        s1y += y
        sxx += x2
        syy += y2
        sxy += x * y
        sxxx += x * x2
        syyy += y * y2
        sxxy += x2 * y
        sxyy += x * y2
    mat = [[sxx, sxy, s1x], [sxy, syy, s1y], [s1x, s1y, float(n)]]
    rhs = [-(sxxx + sxyy), -(sxxy + syyy), -(sxx + syy)]
    sol = _solve3(mat, rhs)
    if sol is None:
        return None
    d, e, f = sol
    cx, cy = -d / 2.0, -e / 2.0
    r2 = cx * cx + cy * cy - f
    if r2 <= 0.0:
        return None
    return cx, cy, math.sqrt(r2)


def _angular_span_rad(pts: list[tuple[float, float]], cx: float, cy: float) -> float:
    angles = sorted(math.atan2(y - cy, x - cx) for x, y in pts)
    if len(angles) < 3:
        return 0.0
    gaps = [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
    gaps.append(2.0 * math.pi - (angles[-1] - angles[0]))
    return 2.0 * math.pi - max(gaps)


def detect_circles(polylines: list[list[tuple[float, float]]],
                   tol: float = 1e-2, min_span_deg: float = 300.0,
                   ) -> list[dict[str, Any]]:
    """从投影折线里识别整圆孔（拟合残差小 + 角向覆盖 >= min_span_deg）。

    孔径与圆心都是「图上量出来的」，因此这组用例同时检验模型与图纸是否一致。
    圆角/倒角投出的四分之一弧因角向覆盖不足被排除。
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[float, float, float]] = set()
    for pts in polylines:
        if len(pts) < 8:
            continue
        if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-6:
            continue  # 只看闭合折线
        fit = _fit_circle(pts)
        if fit is None:
            continue
        cx, cy, r = fit
        if r <= 0:
            continue
        slack = max(tol * r, 2.0 * DEFAULT_DEFLECTION)
        if any(abs(math.hypot(x - cx, y - cy) - r) > slack for x, y in pts):
            continue
        if math.degrees(_angular_span_rad(pts, cx, cy)) < min_span_deg:
            continue
        key = (round(cx, 2), round(cy, 2), round(r, 2))
        if key in seen:
            continue
        seen.add(key)
        out.append({"center": [round(cx, 4), round(cy, 4)],
                    "diameter": round(2.0 * r, 4), "closed": True})
    return out


def _bbox(polylines: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    pts = [p for poly in polylines for p in poly]
    if not pts:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def build_view(model: Any, name: str,
               direction: tuple[float, float, float],
               up: tuple[float, float, float],
               include_hidden: bool = True) -> ViewGeometry:
    shape = _topo_shape(model)
    basis = view_basis(direction, up)
    visible, hidden = classify_view(shape, basis)
    if not include_hidden:
        hidden = []
    bbox = _bbox(visible + hidden)
    circles = detect_circles(visible)
    view = ViewGeometry(name=name, direction=direction, up=up,
                        visible=visible, hidden=hidden, circles=circles, bbox=bbox)
    view.dimensions = _measure_dimensions(view)
    view.chain_check = _chain_check(view, view.dimensions)
    return view


def _measure_dimensions(view: ViewGeometry) -> list[dict[str, Any]]:
    """尺寸来自投影几何的测量值：总体宽/高 + 检出孔的直径 + 由孔心排出的尺寸链。

    每条尺寸都带一个跨视图唯一的 ``feature`` 名（``TOP.hole_2``）：同一模型的
    ``overall_width`` 在前视是 100、在右视是 10，不带视图前缀的公差声明会贴错尺寸。
    """
    dims: list[dict[str, Any]] = []
    if view.width > 0:
        dims.append({"kind": "overall_width", "feature": f"{view.name}.overall_width",
                     "value": round(view.width, 3), "unit": "mm", "tolerance": None,
                     "source": "view bbox (projected geometry)"})
    if view.height > 0:
        dims.append({"kind": "overall_height", "feature": f"{view.name}.overall_height",
                     "value": round(view.height, 3), "unit": "mm", "tolerance": None,
                     "source": "view bbox (projected geometry)"})
    holes = _holes_in_measured_order(view)
    for idx, c in enumerate(holes, start=1):
        dims.append({"kind": "hole_diameter", "feature": f"{view.name}.hole_{idx}",
                     "value": c["diameter"], "unit": "mm", "tolerance": None,
                     "center": c["center"], "closed": c["closed"],
                     "source": "circle fit on projected edges"})
    dims.extend(_chain_dimensions(view, holes))
    return dims


def _holes_in_measured_order(view: ViewGeometry) -> list[dict[str, Any]]:
    """孔的编号按实测位置（先 x 后 y）排，不按检出/打孔顺序。"""
    return sorted(view.circles, key=lambda c: (c["center"][0], c["center"][1]))


def _chain_dimensions(view: ViewGeometry,
                      holes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """「左沿→孔心…→右沿」的尺寸链；段值由实测孔心相减得出。

    少于两个不同的 x 位置时不给链：那会画出一段零长尺寸，是不成立的链而不是信息。
    """
    marks = sorted({round(c["center"][0], 6) for c in holes})
    if len(marks) < 2:
        return []
    stations = [view.bbox[0], *marks, view.bbox[2]]
    dims: list[dict[str, Any]] = []
    for idx in range(len(stations) - 1):
        lo, hi = stations[idx], stations[idx + 1]
        dims.append({"kind": "chain", "feature": f"{view.name}.chain_{idx + 1}",
                     "value": round(hi - lo, 3), "unit": "mm", "tolerance": None,
                     "from_x": lo, "to_x": hi,
                     "source": "hole centers from projected geometry"})
    return dims


def _chain_check(view: ViewGeometry, dims: list[dict[str, Any]]) -> dict[str, Any]:
    """核对「图上印出来的各段之和」是否等于「图上印出来的总体宽」。

    用四舍五入后的显示值而非原始浮点相减——要抓的正是标注本身不闭合。
    """
    chain = [d for d in dims if d["kind"] == "chain"]
    overall = next((d["value"] for d in dims if d["kind"] == "overall_width"), None)
    check: dict[str, Any] = {
        "segments": len(chain),
        "sum": None,
        "overall_width": overall,
        "delta": None,
        "basis": "printed chain segments vs printed overall width",
    }
    if not chain or overall is None:
        check["reason"] = "无可排列的孔心，链不成立" if not chain else "视图没有总体宽尺寸"
        return check
    total = round(sum(d["value"] for d in chain), 6)
    check["sum"] = total
    check["delta"] = round(total - overall, 6)
    check["reason"] = ""
    return check


def _tolerance_decimals(upper: float, lower: float) -> int:
    """显示位数按声明里写得最细的那一侧来，且不低于 2 位。"""
    def places(value: float) -> int:
        text = repr(abs(float(value)))
        return len(text.split(".")[1]) if "." in text else 0

    return max(places(upper), places(lower), MIN_TOLERANCE_DECIMALS)


def _declared_tolerance(raw: Any, where: str) -> dict[str, float]:
    """声明的公差必须是显式的上/下偏差；不猜、不给缺省。"""
    if not isinstance(raw, dict):
        raise ValueError(f"{where} 的 tolerance 必须是 {{'upper': …, 'lower': …}}，"
                         f"实得 {raw!r}")
    try:
        upper = float(raw["upper"])
        lower = float(raw["lower"])
    except KeyError as exc:
        raise ValueError(f"{where} 的 tolerance 缺少 {exc.args[0]}，"
                         f"不做缺省推断") from exc
    if lower > upper:
        raise ValueError(f"{where} 的下偏差 {lower} 大于上偏差 {upper}")
    return {"upper": upper, "lower": lower}


def resolve_spec_tolerances(views: list[ViewGeometry],
                            spec: dict[str, Any] | None) -> dict[str, Any]:
    """把 spec 声明的公差贴到实测出来的尺寸上；没声明就一个都不贴。

    返回写进图纸证据的统计：贴了几处、声明了但图上没有的特征是哪些。
    """
    declared: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for entry in (spec or {}).get("features") or []:
        if not isinstance(entry, dict) or not entry.get("feature"):
            raise ValueError(f"spec.features 每一项都要有 'feature'，实得 {entry!r}")
        name = str(entry["feature"])
        if name in declared:
            raise ValueError(f"spec 里特征 {name} 重复声明")
        # ``ctq_ref`` 是可选的**显式**溯源指针（指向 Product Truth 的 CTQ 记录 id）；
        # 不猜、不按名字模糊匹配——没有它就是"这条公差暂无权威出处"。
        declared[name] = {"tolerance": _declared_tolerance(entry.get("tolerance"), name),
                          "ctq_ref": entry.get("ctq_ref")}
        order.append(name)
    glob_raw = (spec or {}).get("global_tolerance")
    glob = _declared_tolerance(glob_raw, "global_tolerance") if glob_raw else None

    matched: set[str] = set()
    applied = 0
    for view in views:
        for dim in view.dimensions:
            entry = declared.get(str(dim["feature"]))
            if entry is not None:
                matched.add(str(dim["feature"]))
                tolerance = entry["tolerance"]
            else:
                tolerance, entry = glob, None
            if tolerance is None:
                continue
            dim["tolerance"] = {"upper": tolerance["upper"], "lower": tolerance["lower"]}
            ref = (entry or {}).get("ctq_ref")
            if ref:
                dim["ctq_ref"] = str(ref)
            applied += 1
    return {
        "tolerance_applied": applied,
        "spec_declared_features": order,
        "spec_unmatched_features": [n for n in order if n not in matched],
        "global_tolerance_declared": glob is not None,
    }


def _fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def write_dxf(views: list[ViewGeometry], path: Path, *,
              part_name: str, revision: str, scale: float = 1.0,
              material: str = "-", sheet: str = "A3",
              provenance: dict[str, Any] | None = None,
              spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """把视图排到图纸上并写 DXF；返回机器可核验的实体统计。

    ``spec`` 是**唯一**的公差来源；不传则整张图不含任何公差。
    """
    import ezdxf

    spec_stats = resolve_spec_tolerances(views, spec)
    width, height = SHEET_SIZES[sheet]
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    for name, color, lt in (("OUTLINE", 7, "Continuous"),
                            ("HIDDEN", 8, "DASHED"),
                            ("DIMENSION", 3, "Continuous"),
                            ("TEXT", 7, "Continuous"),
                            ("FRAME", 7, "Continuous")):
        if name not in doc.layers:
            doc.layers.add(name, color=color)
        if lt != "Continuous" and lt not in [t.dxf.name for t in doc.linetypes]:
            doc.linetypes.add(lt, pattern=[0.5, 0.25, -0.25])

    # 图框
    msp.add_lwpolyline([(MARGIN, MARGIN), (width - MARGIN, MARGIN),
                        (width - MARGIN, height - MARGIN), (MARGIN, height - MARGIN)],
                       close=True, dxfattribs={"layer": "FRAME"})

    # 排布：单行从左到右，超宽自动换行
    slot_w = (width - 2 * MARGIN - TITLE_BLOCK[0]) / 3.0
    per_row = max(1, int(slot_w // 90.0)) or 3
    placed: list[dict[str, Any]] = []
    for idx, view in enumerate(views):
        row, col = divmod(idx, per_row)
        ox = MARGIN + 20.0 + col * slot_w
        oy = height - MARGIN - 40.0 - row * 100.0
        cx = ox + slot_w / 2.0
        cy = oy - (view.height * scale) / 2.0
        _draw_view(msp, view, cx, cy, scale)
        label = f"{view.name}  1:{_fmt(1.0 / scale)}"
        msp.add_text(label, dxfattribs={"layer": "TEXT", "height": 4.0}) \
           .set_placement((cx - 10.0, oy + 6.0))
        placed.append({"view": view.name, "origin": [round(cx, 2), round(cy, 2)],
                       "size_mm": [round(view.width * scale, 3), round(view.height * scale, 3)],
                       "visible_polylines": len(view.visible),
                       "hidden_polylines": len(view.hidden),
                       "chain_check": view.chain_check,
                       "dimensions": view.dimensions})

    _draw_title_block(msp, width, height, part_name, revision, scale, material,
                      sheet, provenance or {})

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.dxfversion = "AC1024"
    doc.saveas(str(path))
    counts: dict[str, int] = {}
    for e in msp:
        counts[e.dxftype()] = counts.get(e.dxftype(), 0) + 1
    return {"sheet": sheet, "sheet_size_mm": [width, height], "scale": scale,
            "views": placed, "entity_counts": counts,
            "dimension_chain_check": {v["view"]: v["chain_check"] for v in placed},
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **spec_stats}


def _set_dim_tolerance(dim: Any, tolerance: dict[str, float] | None) -> None:
    """把声明的偏差落到 DXF（必须在 ``render()`` 之前调用）。

    ``dimtm`` 存的是下偏差的**相反数**——ezdxf 渲染时对 dimtm 再取负打符号，
    原样传 -0.05 会打成 "+0.05"（实测）。只 set 不 render 时 override 根本不落到
    实体上（实测读回 dimtol 缺省 0），所以公差静默消失的唯一防线是照常 render。
    """
    if not tolerance:
        return
    upper = float(tolerance["upper"])
    lower = float(tolerance["lower"])
    dim.set_tolerance(upper, -lower, dec=_tolerance_decimals(upper, lower))


def _linear_dim(msp: Any, base: tuple[float, float], p1: tuple[float, float],
                p2: tuple[float, float], text: str,
                tolerance: dict[str, float] | None) -> None:
    dim = msp.add_linear_dim(base=base, p1=p1, p2=p2, text=text, dimstyle=DIMSTYLE)
    _set_dim_tolerance(dim, tolerance)
    dim.render()


def _draw_view(msp: Any, view: ViewGeometry, cx: float, cy: float, scale: float) -> None:
    off_x = cx - (view.width * scale) / 2.0 - view.bbox[0] * scale
    off_y = cy - (view.height * scale) / 2.0 - view.bbox[1] * scale

    def place(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * scale + off_x, y * scale + off_y) for x, y in poly]

    for poly in view.visible:
        pts = place(poly)
        if len(pts) == 2:
            msp.add_line(pts[0], pts[1], dxfattribs={"layer": "OUTLINE"})
        elif len(pts) > 2:
            msp.add_lwpolyline(pts, dxfattribs={"layer": "OUTLINE"})
    for poly in view.hidden:
        pts = place(poly)
        if len(pts) < 2:
            continue
        if len(pts) == 2:
            msp.add_line(pts[0], pts[1], dxfattribs={"layer": "HIDDEN"})
        else:
            msp.add_lwpolyline(pts, dxfattribs={"layer": "HIDDEN"})

    # 尺寸全部来自投影测量值：总体宽/高 + 由孔心排出的尺寸链 + 孔径
    dims = view.dimensions
    chain = [d for d in dims if d["kind"] == "chain"]
    w = next((d for d in dims if d["kind"] == "overall_width"), None)
    h = next((d for d in dims if d["kind"] == "overall_height"), None)
    bottom = off_y + view.bbox[1] * scale
    if chain:
        base_y = bottom - CHAIN_ROW_GAP
        for seg in chain:
            p1 = (off_x + seg["from_x"] * scale, bottom)
            p2 = (off_x + seg["to_x"] * scale, bottom)
            _linear_dim(msp, (p1[0], base_y), p1, p2, _fmt(seg["value"]), seg["tolerance"])
    if w:
        gap = OVERALL_OUTSIDE_GAP if chain else DIM_ROW_GAP
        p1 = (off_x + view.bbox[0] * scale, bottom)
        p2 = (off_x + view.bbox[2] * scale, bottom)
        _linear_dim(msp, (p1[0], p1[1] - gap), p1, p2, _fmt(w["value"]), w["tolerance"])
    if h:
        p1 = (off_x + view.bbox[2] * scale, bottom)
        p2 = (off_x + view.bbox[2] * scale, off_y + view.bbox[3] * scale)
        dim = msp.add_linear_dim(base=(p1[0] + DIM_ROW_GAP, p1[1]), p1=p1, p2=p2,
                                 text=_fmt(h["value"]), dimstyle=DIMSTYLE)
        _set_dim_tolerance(dim, h["tolerance"])
        dim.render()
    for c in [d for d in dims if d["kind"] == "hole_diameter"]:
        ctr = c["center"]
        dia = msp.add_diameter_dim(center=(ctr[0] * scale + off_x, ctr[1] * scale + off_y),
                                   radius=c["value"] * scale / 2.0, angle=45,
                                   text=f"%%c{_fmt(c['value'])}")
        _set_dim_tolerance(dia, c["tolerance"])
        dia.render()


def _draw_title_block(msp: Any, width: float, height: float, part: str, rev: str,
                      scale: float, material: str, sheet: str,
                      provenance: dict[str, Any]) -> None:
    x0, y0 = width - MARGIN - TITLE_BLOCK[0], MARGIN
    x1, y1 = x0 + TITLE_BLOCK[0], y0 + TITLE_BLOCK[1]
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                       dxfattribs={"layer": "FRAME"})
    rows = [("PART", part), ("REV", rev), ("SCALE", f"1:{_fmt(1.0 / scale)}"),
            ("MATL", material), ("SHEET", sheet),
            ("PROVENANCE", str(provenance.get("source_hash", "-"))[:28]),
            ("TOOL", str(provenance.get("tool", "-"))[:28]),
            ("DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))]
    for i, (label, value) in enumerate(rows):
        yy = y1 - (i + 1) * (TITLE_BLOCK[1] / (len(rows) + 0.5))
        msp.add_text(label, dxfattribs={"layer": "TEXT", "height": 2.6}) \
           .set_placement((x0 + 2.0, yy))
        msp.add_text(value, dxfattribs={"layer": "TEXT", "height": 2.6}) \
           .set_placement((x0 + 30.0, yy))


def generate_drawing(model: Any, out_path: Path | str, *,
                     part_name: str, revision: str = "A",
                     views: tuple[str, ...] = ("FRONT", "TOP", "RIGHT"),
                     scale: float = 1.0, material: str = "-",
                     sheet: str = "A3",
                     provenance: dict[str, Any] | None = None,
                     spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """端到端：模型 -> 视图 -> DXF -> 证据字典（含哈希与实体统计）。

    ``spec`` 只用于声明公差（``{"features": [{"feature": "TOP.hole_2",
    "tolerance": {"upper": 0.05, "lower": -0.05}}], "global_tolerance": {...}}``），
    尺寸值一律来自几何测量，spec 不参与测量。
    """
    path = Path(out_path)
    built: list[ViewGeometry] = []
    for name in views:
        if name not in STANDARD_VIEWS:
            raise ValueError(f"未知视图 {name}；可用：{sorted(STANDARD_VIEWS)}")
        direction, up = STANDARD_VIEWS[name]
        built.append(build_view(model, name, direction, up))
    evidence = write_dxf(built, path, part_name=part_name, revision=revision,
                         scale=scale, material=material, sheet=sheet,
                         provenance=provenance, spec=spec)
    evidence.update(provenance or {})
    evidence.update({"part": part_name, "revision": revision,
                     "generated_at": datetime.now(timezone.utc).isoformat(),
                     "hidden_line_method": HIDDEN_LINE_METHOD})
    sidecar = path.with_suffix(".evidence.json")
    sidecar.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    evidence["evidence_file"] = str(sidecar)
    return evidence
