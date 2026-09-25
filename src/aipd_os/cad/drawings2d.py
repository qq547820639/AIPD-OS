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

- **GD&T 特征控制框**按 ``--spec`` 声明绘制（见 ``cad.gdt``）：分格框线 + 每格 TEXT +
  引线，引线终点取**实测**孔心；基准解析不了就点名并判未收口，不画半截框。
- **一维公差叠加**（见 ``cad.stackup``）：各段公差带之和超过封闭环自己声明的带 ⇒ 图纸
  自相矛盾。缺任何一环声明判「不可判定」，不按 0 折算，也不猜功能限值。
- **剖视**走真布尔切割（``section_view``：半空间 cut + 剖面材料区量积 + DXF ``HATCH``
  ANSI31）。剖面区只取「法向平行 **且** 面心落在剖切平面上」的面——实测只筛法向会把
  后外壁（100×10=1000mm²）当成剖面，凭空多出一块材料。

剖视的**剖切符号**（母视图上的剖切线 + 指向保留侧的短划 + 两端字母 + 剖面标题 «A-A»）
由 ``assign_section_letters`` 真画：位置由「剖切平面在母视图投影面上的交线」算出
（``a·u + b·v = offset``），视线与法向平行的视图不是母视图、剖视图自己不标，
空剖视不编号也不标符号。

**局部放大图**（``detail_view``）是母视图**已判定可见/隐藏**折线与放大圆的二维裁剪：
裁剪区间由 ``|a+t(b-a)-c|<=R`` 的一元二次方程闭式解出，所以「裁掉什么」可机器核。
放大图**不自己量尺寸**——它只继承母视图里测点落在圆内的尺寸（``inherited_from``），
且保留母视图的特征名，否则按名建立的 CTQ 溯源会整条断掉。总尺寸（``overall_*``）
一律不继承：裁剪窗的大小不是零件的尺寸。空放大图（圆内什么图线都没有）不编号、
不在母视图上画圈，与空剖视同一条规矩。

明确**未实现**（不要当成已具备）：爆炸图与装配约束/配合；阶梯剖/旋转剖；
叠加未做三维/角度与分布型统计（Cpk）；GD&T 用的是 drawn 几何
而非 DXF ``TOLERANCE`` 语义实体（其 ``content`` 转义码无权威来源，见 ``cad.gdt`` docstring）。
多零件装配图在 ``aipd_os.cad.assembly``（逐件投影 + 序号球标 + 明细表，
走本模块的 ``write_dxf``，但装配视图上不接受剖视与局部放大）；
放大图不重投影（FreeCAD TechDraw 走的是「圆柱与实体求交后重新投影」），
这一取舍的理由与后果见 ``docs/audit/CAD_DETAIL_VIEWS_F-DRAW-01_2026-09-24.md``。
见 registry 的 ``current_limitation``。
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
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

# 剖视：轴向 -> (保留侧的单位法向, 观察方向=指向观察者, 图纸上的「上」)。
# 约定：切去 ``dot(p,n) < offset`` 的一侧，观察者站在被切掉那一侧看剖面，
# 因此 ``normal`` 指向观察者时正好是剖面的外法向（``SECTION_BASIS[axis]`` 的
# 观察方向 = -n）。实测：Y 轴剖切与 FRONT 用同一组基 ⇒ 剖面无缩短。
SECTION_AXIS_NORMAL = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
SECTION_BASIS = {
    "X": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "Y": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "Z": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
}
SECTION_PLANE_TOL = 1e-6       # 判定「这个面就落在剖切平面上」
SECTION_KEEP_LABEL = {"X": "x>=", "Y": "y>=", "Z": "z>="}
SECTION_LETTERS = "ABCDEFGHJKL"   # 剖切符号字母；按惯例跳过 I
SECTION_OVERHANG = 4.0            # 剖切线向母视图轮廓两端各伸出的余量（图纸 mm）
SECTION_TICK = 2.5                # 端部短划长度，指向被保留的一侧
SECTION_LETTER_HEIGHT = 3.5       # 字母字高
DETAIL_NUMBER_HEIGHT = 3.5        # 母视图上放大编号的字高
DETAIL_STATION_TOL = 1e-6         # 「这个测点算不算落在放大圆内」的数值容差

DIMSTYLE = "EZ_M_100_H25_CM"
DIM_ROW_GAP = 10.0        # 无尺寸链时总体宽尺寸的引出距离
CHAIN_ROW_GAP = 12.0      # 尺寸链行距零件下沿
OVERALL_OUTSIDE_GAP = 30.0  # 有链时总体宽尺寸挪到链的外侧，避免两行重叠
MIN_TOLERANCE_DECIMALS = 2  # 偏差不许因为声明写得粗就被截断显示；只允许显示更多位
CTQ_WINDOW_TOL = 1e-6  # 实测值与 CTQ 合格域边界之间的数值容差（圆拟合/离散化噪声量级）


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
    cut_regions: list[list[tuple[float, float]]] = field(default_factory=list)
    section_of: dict[str, Any] | None = None
    nested_region_wires: int = 0
    section_problems: list[str] = field(default_factory=list)
    section_warnings: list[str] = field(default_factory=list)
    section_letter: str = ""
    label: str = ""
    section_symbols: list[dict[str, Any]] = field(default_factory=list)
    detail_of: dict[str, Any] | None = None
    detail_factor: float = 1.0
    detail_problems: list[str] = field(default_factory=list)
    detail_markers: list[dict[str, Any]] = field(default_factory=list)
    assembly: dict[str, Any] | None = None
    # 装配侧往视图上再画一层（球标）时挂进来的回调：``(msp, view, scale, place)``。
    # 走这个钩子而不是让本模块 import 装配模块 —— 依赖只能单向（装配 → 图纸），
    # 反向那条边会被 tests/test_import_cycles.py 判成环。
    render_overlay: Any = None

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


def parse_section_spec(spec: str) -> tuple[str, float]:
    """解析 ``--section "Y=0"``；轴不认识或偏移不是数就抛 ValueError（不外推）。"""
    axis, sep, raw = str(spec).partition("=")
    axis = axis.strip().upper()
    if not sep or axis not in SECTION_AXIS_NORMAL:
        raise ValueError(f"剖切写法必须是 X/Y/Z=偏移，实得 {spec!r}")
    try:
        offset = float(raw.strip() or "0.0")
    except ValueError as exc:
        raise ValueError(f"剖切偏移不是数：{spec!r}") from exc
    return axis, offset


def _section_line_in_view(view: ViewGeometry, axis: str,
                          offset: float) -> dict[str, Any] | None:
    """剖切平面在某个视图投影面上的交线（视图局部坐标）；不是母视图时返回 ``None``。

    投影是正交的：点 ``p`` 映成 ``(p·right, p·up)``。剖切平面 ``p·n̂ = offset`` 投出来
    是直线 ``a·u + b·v = offset``，其中 ``a = right·n̂``、``b = up·n̂``。
    视线与法向平行（``a = b = 0``）时该平面「铺满」这个视图，画不出交线——
    也就是**这个视图不是母视图**，所以返回 None 而不是硬画一条。
    """
    n = SECTION_AXIS_NORMAL[axis]
    basis = view_basis(view.direction, view.up)
    right, upv = basis["right"], basis["up"]
    a = sum(r * k for r, k in zip(right, n))
    b = sum(r * k for r, k in zip(upv, n))
    s_len = math.hypot(a, b)
    if s_len < 1e-9:
        return None
    px, py = offset * a / (s_len * s_len), offset * b / (s_len * s_len)
    dx, dy = b / s_len, -a / s_len
    corners = [(view.bbox[0], view.bbox[1]), (view.bbox[2], view.bbox[1]),
               (view.bbox[2], view.bbox[3]), (view.bbox[0], view.bbox[3])]
    half = max(abs((cx - px) * dx + (cy - py) * dy) for cx, cy in corners)
    reach = half + SECTION_OVERHANG
    return {"from": [px - reach * dx, py - reach * dy],
            "to": [px + reach * dx, py + reach * dy],
            "dir": [dx, dy], "kept_side": [a / s_len, b / s_len]}


def assign_section_letters(views: list[ViewGeometry]) -> dict[str, str]:
    """给剖视按出现顺序编号 A、B、…，并把剖切符号算到它该出现的母视图上。

    符号落在**所有**视线与剖切面垂直的视图上（一张图可能同时有 TOP 和 BOTTOM 两个母视图）；
    母视图缺席时不硬画，证据里也就没有那条符号——宁可少标，不可错标。
    """
    letters: dict[str, str] = {}
    for view in views:
        if not view.section_of:
            continue
        if not view.cut_regions:
            # 空剖视不编号也不标符号：给一刀什么都没切到的剖视标 «B-B»，
            # 等于图纸声称「这里有一张剖视」而它不存在。原因由 section_problems 说。
            continue
        if len(letters) >= len(SECTION_LETTERS):
            view.section_problems.append(
                f"剖视数量超过可用字母数 {len(SECTION_LETTERS)}，这张剖视没有编号")
            continue
        letter = SECTION_LETTERS[len(letters)]
        letters[view.name] = letter
        view.section_letter = letter
        view.label = f"{letter}-{letter}"
    for view in views:
        if view.section_of or view.detail_of:
            # 派生视图（剖视、放大图）都不是母视图：在它上面再画一刀的剖切线，
            # 读图的人会以为那是另一处实体。
            continue
        for sec in views:
            if not sec.section_of or not sec.section_letter:
                continue
            line = _section_line_in_view(view, str(sec.section_of["axis"]),
                                         float(sec.section_of["offset"]))
            if line is None:
                continue
            view.section_symbols.append({
                "letter": sec.section_letter, "axis": str(sec.section_of["axis"]),
                "offset": float(sec.section_of["offset"]), "of": sec.name, "ticks": 2,
                "from": [round(line["from"][0], 6), round(line["from"][1], 6)],
                "to": [round(line["to"][0], 6), round(line["to"][1], 6)],
                "kept_side": [round(line["kept_side"][0], 6),
                              round(line["kept_side"][1], 6)],
            })
    return {name: letter for name, letter in letters.items()}


def section_view(model: Any, name: str, axis: str, offset: float = 0.0,
                 include_hidden: bool = True) -> ViewGeometry:
    """真做半空间布尔切割，再按剖切面方向投影，并量出剖面上的材料区。

    材料区 = **既满足法向平行、又满足面心落在剖切平面上**的那些面的外环投影。
    只按法向筛会把与剖面平行的外壁（实测本件 100×10=1000mm²）当成剖面，
    凭空多出一块材料 —— 所以第二道距离筛选不能省。
    """
    import cadquery as cq

    axis = str(axis).strip().upper()
    if axis not in SECTION_AXIS_NORMAL:
        raise ValueError(f"未知剖切轴 {axis!r}；可用：{sorted(SECTION_AXIS_NORMAL)}")
    n = SECTION_AXIS_NORMAL[axis]
    direction, up = SECTION_BASIS[axis]

    shape = _topo_shape(model)
    solid = shape if isinstance(shape, cq.Solid) else cq.Solid(shape)
    bb = solid.BoundingBox()
    diag = max(math.sqrt(bb.xlen ** 2 + bb.ylen ** 2 + bb.zlen ** 2), 1.0)
    big = 10.0 * diag
    idx = {"X": 0, "Y": 1, "Z": 2}[axis]
    low = [bb.xmin, bb.ymin, bb.zmin]
    high = [bb.xmax, bb.ymax, bb.zmax]
    corner = list(low)
    corner[idx] = offset - big
    size = [2.0 * big, 2.0 * big, 2.0 * big]
    size[idx] = big
    for k in (0, 1, 2):
        if k != idx:
            pad = (high[k] - low[k]) + 2.0 * big
            corner[k] = low[k] - big
            size[k] = pad
    cutter = cq.Solid.makeBox(size[0], size[1], size[2], cq.Vector(*corner))
    cut = solid.cut(cutter)

    basis = view_basis(direction, up)
    right, upv = basis["right"], basis["up"]

    def project(p: Any) -> tuple[float, float]:
        x, y, z = (p[0], p[1], p[2]) if isinstance(p, tuple) else (p.x, p.y, p.z)
        return (x * right[0] + y * right[1] + z * right[2],
                x * upv[0] + y * upv[1] + z * upv[2])

    view = build_view(cut, name, direction, up, include_hidden=include_hidden)
    regions: list[list[tuple[float, float]]] = []
    problems: list[str] = []
    nested = 0
    warnings: list[str] = []
    matched = 0
    for face in cut.Faces():
        normal = face.normalAt()
        parallel = abs(normal.x * n[0] + normal.y * n[1] + normal.z * n[2])
        centre_along = (face.Center().x * n[0] + face.Center().y * n[1]
                        + face.Center().z * n[2])
        if parallel < 1.0 - SECTION_PLANE_TOL or abs(centre_along - offset) > SECTION_PLANE_TOL:
            continue
        wires = face.Wires()
        if not wires:
            continue
        matched += 1
        projected = [(_projected_wire(w, project), w) for w in wires]
        outer_pair, _ = max(projected, key=lambda pair: _polygon_area(pair[0][0]))
        poly, closed = outer_pair
        if not closed:
            centre = face.Center()
            problems.append(f"材料区（面心 ({centre.x:g}, {centre.y:g}, {centre.z:g})）"
                            f"的边界接不成闭合环，已跳过填充")
            continue
        regions.append(poly)
        if len(wires) > 1:
            nested += len(wires) - 1
            # 这是**告警**不是阻断：图能交付，只是面积按高估算，与「什么都没切到」不同档
            warnings.append(f"材料区含 {len(wires) - 1} 个内环，本轮只填外边界，"
                            f"孔/槽面积会被高估")

    if not regions:
        if matched:
            problems.append(f"剖切平面 {axis}={offset:g} 切到 {matched} 个材料面，"
                            f"但边界都接不成闭合环，未填剖面线")
        else:
            problems.append(f"剖切平面 {axis}={offset:g} 没切到任何材料")
    view.cut_regions = regions
    view.nested_region_wires = nested
    view.section_problems = problems
    view.section_warnings = warnings
    view.section_of = {"axis": axis, "offset": float(offset),
                       "kept": f"{SECTION_KEEP_LABEL[axis]}{float(offset):g}",
                       "normal": [n[0], n[1], n[2]]}
    return view


def parse_detail_spec(spec: str) -> tuple[str, tuple[float, float], float, float]:
    """解析 ``--detail "TOP@(-30,0)/12=2"`` = 母视图 @ 圆心 / 半径 = 放大倍数。

    圆心与半径都用**母视图的局部坐标与模型单位**（与证据里 ``center`` 同一套数），
    所以看图人可以从证据的孔心直接抄一个圆心出来。倍数是**相对母视图印出的比例**，
    不是绝对比例：``--scale 0.5 --detail ...=2`` 得到的是 1:1 的放大图。
    """
    text = str(spec).strip()
    parent, sep, rest = text.partition("@")
    parent = parent.strip()
    if not sep or not parent:
        raise ValueError(f"局部放大写法必须是 母视图@(u,v)/半径=放大倍数，实得 {spec!r}")
    circle_part, eq, factor_raw = rest.partition("=")
    if not eq:
        raise ValueError(f"局部放大缺放大倍数（如 ...=2）：{spec!r}")
    centre_part, slash, radius_raw = circle_part.partition("/")
    if not slash:
        raise ValueError(f"局部放大缺半径（写法 .../半径=倍数）：{spec!r}")
    bits = centre_part.strip().strip("()").split(",")
    if len(bits) != 2:
        raise ValueError(f"放大圆心要两个数 (u,v)，实得 {centre_part!r}")
    try:
        u, v = float(bits[0]), float(bits[1])
        radius = float(radius_raw.strip())
        factor = float(factor_raw.strip())
    except ValueError as exc:
        raise ValueError(f"局部放大的坐标/半径/倍数都得是数：{spec!r}") from exc
    if radius <= 0.0:
        raise ValueError(f"放大圆半径必须大于 0，实得 {radius:g}：{spec!r}")
    if factor <= 1.0:
        raise ValueError(f"放大倍数必须大于 1（等于 1 就不叫局部放大），实得 {factor:g}"
                         f"：{spec!r}")
    return parent, (u, v), radius, factor


def _circle_hit_interval(a: tuple[float, float], b: tuple[float, float],
                         center: tuple[float, float],
                         radius: float) -> tuple[float, float] | None:
    """线段 a→b 落在圆内的参数区间 ``[t0, t1]``；圆外或只碰一点返回 ``None``。

    解 ``|a + t(b-a) - c|² = R²``。判别式 < 0 时整条要么全内要么全外，
    用**起点到圆心的距离**判是哪一种——不看起点就会把全内的线段整条丢掉。
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - center[0], a[1] - center[1]
    qa = dx * dx + dy * dy
    if qa <= 0.0:
        return None
    qb = 2.0 * (fx * dx + fy * dy)
    qc = fx * fx + fy * fy - radius * radius
    disc = qb * qb - 4.0 * qa * qc
    if disc < 0.0:
        return (0.0, 1.0) if qc < 0.0 else None
    root = math.sqrt(disc)
    t0 = max(0.0, min(1.0, (-qb - root) / (2.0 * qa)))
    t1 = max(0.0, min(1.0, (-qb + root) / (2.0 * qa)))
    if t1 - t0 <= 0.0:
        return None          # 相切：零长度不算一段
    return t0, t1


def _lerp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def clip_polyline_to_circle(poly: list[tuple[float, float]],
                            center: tuple[float, float],
                            radius: float) -> list[list[tuple[float, float]]]:
    """折线 ∩ 圆：按**原顺序**返回圆内的若干段（整圆在内仍闭合）。

    与 ``_chain_loop`` 同一条纪律：只接得住连续段，接不上就另起一段，
    绝不把两段不相干的线首尾缝成一条。
    """
    pieces: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for i in range(len(poly) - 1):
        hit = _circle_hit_interval(poly[i], poly[i + 1], center, radius)
        if hit is None:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = []
            continue
        p0 = _lerp(poly[i], poly[i + 1], hit[0])
        p1 = _lerp(poly[i], poly[i + 1], hit[1])
        if not cur or not _same(cur[-1], p0):
            if len(cur) >= 2:
                pieces.append(cur)
            cur = [p0]
        if not _same(cur[-1], p1):
            cur.append(p1)
    if len(cur) >= 2:
        pieces.append(cur)
    return pieces


def _inside(point: tuple[float, float], center: tuple[float, float],
            radius: float) -> bool:
    return (math.hypot(point[0] - center[0], point[1] - center[1])
            <= radius + DETAIL_STATION_TOL)


def _inherited_dimensions(parent: ViewGeometry, center: tuple[float, float],
                          radius: float) -> list[dict[str, Any]]:
    """母视图里**测点落在放大圆内**的尺寸才带得进来；名字保持 ``TOP.hole_1`` 不变。

    ``overall_width`` / ``overall_height`` 永不继承：放大图量出来的是**裁剪窗**，
    把它标成零件尺寸就是凭空造一条不存在的尺寸。链尺寸要求两端都落在某个孔心上
    （以零件边缘为锚的那两段不算），所以边缘段不会跑到放大图上。
    """
    stations: dict[float, list[tuple[float, float]]] = {}
    for c in parent.circles:
        key = round(float(c["center"][0]), 6)
        stations.setdefault(key, []).append((float(c["center"][0]),
                                             float(c["center"][1])))
    kept: list[dict[str, Any]] = []
    for dim in parent.dimensions:
        kind = str(dim.get("kind"))
        if kind == "hole_diameter":
            points = [(float(dim["center"][0]), float(dim["center"][1]))]
        elif kind == "chain":
            left = stations.get(round(float(dim["from_x"]), 6))
            right = stations.get(round(float(dim["to_x"]), 6))
            if not left or not right:
                continue
            points = [*left, *right]
        else:
            continue
        if not all(_inside(p, center, radius) for p in points):
            continue
        entry = dict(dim)
        entry["inherited_from"] = parent.name
        kept.append(entry)
    return kept


def detail_view(parent: ViewGeometry, name: str, center: tuple[float, float],
                radius: float, factor: float) -> ViewGeometry:
    """把母视图裁一块放大：二维裁剪**已判定可见/隐藏**的折线，不重新投影。

    放大图用的是母视图同一套视图基（``direction`` / ``up``）与同一套局部坐标，
    所以圆内几何与母视图逐毫米对得上；孔整圆在内时仍被 ``detect_circles`` 认成孔，
    被圆边裁成开弧时**不会**（开弧量不出圆心，标出来就是假尺寸）。
    """
    center = (float(center[0]), float(center[1]))
    radius = float(radius)
    factor = float(factor)
    visible = [seg for poly in parent.visible
               for seg in clip_polyline_to_circle(poly, center, radius)]
    hidden = [seg for poly in parent.hidden
              for seg in clip_polyline_to_circle(poly, center, radius)]
    view = ViewGeometry(
        name=name, direction=parent.direction, up=parent.up, visible=visible,
        hidden=hidden, circles=detect_circles(visible), bbox=_bbox(visible + hidden),
        detail_of={"parent": parent.name, "center": [center[0], center[1]],
                   "radius": radius, "factor": factor},
        detail_factor=factor)
    view.dimensions = _inherited_dimensions(parent, center, radius)
    view.chain_check = _chain_check(view, view.dimensions)
    if not visible and not hidden:
        view.detail_problems.append(
            f"放大圆 ({center[0]:g}, {center[1]:g}) R={radius:g} 在 {parent.name} 上"
            f"没圈到任何图线（要么圆心写错，要么那处本来没有几何）")
    return view


def _ratio_text(scale: float) -> str:
    """比例写法：放大就 ``k:1``，缩小就 ``1:k``——把 0.5 印成 "1:2" 而不是 "1:0.5"。"""
    return f"{_fmt(scale)}:1" if scale >= 1.0 else f"1:{_fmt(1.0 / scale)}"


def assign_detail_numbers(views: list[ViewGeometry], scale: float) -> dict[str, int]:
    """给放大图按出现顺序编号 1、2、…，并在母视图上挂裁剪圈。

    与剖视同一条件：**空放大图不编号、不画圈**——图纸不该声称有一张读得清的详图
    而它什么都没有。字母给剖视、数字给放大图，两套互不占用。
    """
    by_name = {v.name: v for v in views}
    numbers: dict[str, int] = {}
    for view in views:
        if not view.detail_of or view.detail_problems:
            continue
        number = len(numbers) + 1
        numbers[view.name] = number
        drawn = scale * view.detail_factor
        view.label = f"DETAIL {number}  {_ratio_text(drawn)}"
        parent = by_name.get(str(view.detail_of["parent"]))
        if parent is not None:
            parent.detail_markers.append({
                "number": number, "of": view.name,
                "center": list(view.detail_of["center"]),
                "radius": float(view.detail_of["radius"]),
            })
    return numbers


def _polygon_area(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    total = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _same(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


def _chain_loop(segments: list[list[tuple[float, float]]]
                ) -> tuple[list[tuple[float, float]], bool]:
    """把无序的边段接成一条闭合环。

    OCP 给的 wire.Edges() **不是**按绕行顺序排的（实测第 1 条边终点接不上第 2 条边起点），
    直接顺次拼接会得到自交的折线、shoelace 面积算出 0 或半值。接不上就返回 ``(部分, False)``，
    由调用方如实报「这一区没填」，不静默填一个错多边形。
    """
    segs = [s for s in segments if len(s) >= 2]
    if not segs:
        return [], False
    loop = list(segs[0])
    rest = segs[1:]
    while rest:
        for i, seg in enumerate(rest):
            if _same(seg[0], loop[-1]):
                loop.extend(seg[1:])
            elif _same(seg[-1], loop[-1]):
                loop.extend(list(reversed(seg))[1:])
            elif _same(seg[-1], loop[0]):
                loop = seg[:-1] + loop
            elif _same(seg[0], loop[0]):
                loop = list(reversed(seg))[:-1] + loop
            else:
                continue
            rest.pop(i)
            break
        else:
            return loop, False
    out: list[tuple[float, float]] = []
    for pt in loop:
        if out and _same(out[-1], pt):
            continue
        out.append(pt)
    if len(out) >= 3 and not _same(out[0], out[-1]):
        out.append(out[0])
    return out, len(out) >= 4


def _projected_wire(wire: Any, project: Any) -> tuple[list[tuple[float, float]], bool]:
    segments = []
    for edge in wire.Edges():
        pts = [project(p) for p in _discretize(edge.wrapped, DEFAULT_DEFLECTION)]
        if len(pts) >= 2:
            segments.append(pts)
    return _chain_loop(segments)


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


def _declared_limits(raw: Any, where: str) -> dict[str, float] | None:
    """声明里可选的**绝对合格域** ``{"min": …, "max": …}``，用来反查实测值。

    不传就是「这条声明只给偏差、不给绝对域」——不做 ``标称 = 实测`` 的推断，
    因为那等于让被检对象给自己定基准。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{where} 的 limits 必须是 {{'min': …, 'max': …}}，实得 {raw!r}")
    try:
        low = float(raw["min"])
        high = float(raw["max"])
    except KeyError as exc:
        raise ValueError(f"{where} 的 limits 缺少 {exc.args[0]}，不做缺省推断") from exc
    if low > high:
        raise ValueError(f"{where} 的合格域下限 {low} 大于上限 {high}")
    return {"min": low, "max": high}


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
        if "tolerance" not in entry:
            continue   # 只声明 GD&T 框、不声明尺寸公差的条目：交给 build_gdt_frames 处理
        name = str(entry["feature"])
        if name in declared:
            raise ValueError(f"spec 里特征 {name} 重复声明")
        # ``ctq_ref`` 是可选的**显式**溯源指针（指向 Product Truth 的 CTQ 记录 id）；
        # 不猜、不按名字模糊匹配——没有它就是"这条公差暂无权威出处"。
        declared[name] = {"tolerance": _declared_tolerance(entry.get("tolerance"), name),
                          "ctq_ref": entry.get("ctq_ref"),
                          "limits": _declared_limits(entry.get("limits"), name)}
        order.append(name)
    glob_raw = (spec or {}).get("global_tolerance")
    glob = _declared_tolerance(glob_raw, "global_tolerance") if glob_raw else None

    matched: set[str] = set()
    applied = 0
    limit_issues: list[dict[str, Any]] = []
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
            limits = (entry or {}).get("limits")
            if limits:
                # 实测值来自投影几何、合格域来自 CTQ：两者独立，这一判据不是自证。
                value = float(dim["value"])
                if not (limits["min"] - CTQ_WINDOW_TOL <= value
                        <= limits["max"] + CTQ_WINDOW_TOL):
                    limit_issues.append({
                        "kind": "ctq_window_violation", "feature": str(dim["feature"]),
                        "measured": round(value, 6), "min": limits["min"],
                        "max": limits["max"], "ctq_ref": str(ref or ""), "blocking": True})
            applied += 1
    return {
        "tolerance_applied": applied,
        "spec_declared_features": order,
        "spec_unmatched_features": [n for n in order if n not in matched],
        "global_tolerance_declared": glob is not None,
        "spec_limit_issues": limit_issues,
    }


def _fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def write_dxf(views: list[ViewGeometry], path: Path, *,
              part_name: str, revision: str, scale: float = 1.0,
              material: str = "-", sheet: str = "A3",
              provenance: dict[str, Any] | None = None,
              spec: dict[str, Any] | None = None,
              layout_hook: Any = None,
              extra_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """把视图排到图纸上并写 DXF；返回机器可核验的实体统计。

    ``spec`` 是**唯一**的公差来源；不传则整张图不含任何公差。
    ``layout_hook(msp, sheet_wh) -> dict`` 给装配侧用：它在图框内画明细表并返回
    要并进证据的键。本模块**不认识**「明细表/球标」这些概念，也不 import 装配模块
    ——依赖只允许 装配 → 图纸 一个方向（反向会被无环门判红）。
    """
    import ezdxf

    from aipd_os.cad.stackup import view_stackup

    spec_stats = resolve_spec_tolerances(views, spec)
    stackups = {v.name: view_stackup(v.dimensions, v.name) for v in views}
    from aipd_os.cad.gdt import build_gdt_frames

    gdt_frames, gdt_issues, gdt_unmatched = build_gdt_frames(views, spec)
    section_letters = assign_section_letters(views)
    detail_numbers = assign_detail_numbers(views, scale)
    width, height = SHEET_SIZES[sheet]
    doc = ezdxf.new("R2010", setup=True)
    # 剖切线惯用点划线；没有 PHANTOM 就用虚线，绝不引用文档里不存在的线型
    cut_line_linetype = "PHANTOM" if doc.linetypes.has_entry("PHANTOM") else "DASHED"
    msp = doc.modelspace()
    for name, color, lt in (("OUTLINE", 7, "Continuous"),
                            ("HIDDEN", 8, "DASHED"),
                            ("DIMENSION", 3, "Continuous"),
                            ("TEXT", 7, "Continuous"),
                            ("GDT", 6, "Continuous"),
                            ("HATCH", 3, "Continuous"),
                            ("SECTION", 1, "Continuous"),
                            ("DETAIL", 5, "Continuous"),
                            ("BALLOON", 4, "Continuous"),
                            # 明细表由 ezdxf 的 TablePainter 画，它用的就是这两个层名；
                            # 不预先建层，别的软件会读到未定义的图层引用
                            ("TABLECONTENT", 7, "Continuous"),
                            ("TABLEGRID", 7, "Continuous"),
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
        # 放大图按「全局比例 × 自己的倍数」画，其余视图 detail_factor 恒为 1
        sc = scale * view.detail_factor
        cx = ox + slot_w / 2.0
        cy = oy - (view.height * sc) / 2.0
        _draw_view(msp, view, cx, cy, sc,
                   [f for f in gdt_frames if f["view"] == view.name],
                   cut_line_linetype)
        if not view.detail_of:   # 放大图的比例写在自己的标题里，别拿全局比例贴它
            msp.add_text(f"{view.name}  1:{_fmt(1.0 / sc)}",
                         dxfattribs={"layer": "TEXT", "height": 4.0}) \
               .set_placement((cx - 10.0, oy + 6.0))
        if view.label:      # 剖面标题 «A-A» / 放大图标题 «DETAIL 1  2:1»
            msp.add_text(view.label, dxfattribs={"layer": "TEXT", "height": 4.0}) \
               .set_placement((cx - 6.0, oy - view.height * sc - 10.0))
        placed.append({"view": view.name, "origin": [round(cx, 2), round(cy, 2)],
                       "size_mm": [round(view.width * sc, 3), round(view.height * sc, 3)],
                       "drawn_scale": sc,
                       "visible_polylines": len(view.visible),
                       "hidden_polylines": len(view.hidden),
                       "chain_check": view.chain_check,
                       "section_of": view.section_of,
                       "cut_regions": len(view.cut_regions),
                       "material_area_mm2": round(sum(_polygon_area(r)
                                                      for r in view.cut_regions), 6),
                       "section_empty": bool(view.section_of) and not view.cut_regions,
                       "section_problems": list(view.section_problems),
                       "section_warnings": list(view.section_warnings),
                       "label": view.label,
                       "section_symbols": [dict(sym) for sym in view.section_symbols],
                       "detail_of": view.detail_of,
                       "detail_empty": bool(view.detail_of) and bool(view.detail_problems),
                       "detail_markers": [dict(m) for m in view.detail_markers],
                       "assembly_parts": ([dict(p) for p in view.assembly["parts"]]
                                           if view.assembly else None),
                       "segments": ([dict(s) for s in view.assembly["segments"]]
                                    if view.assembly else None),
                       "balloons": ([dict(b) for b in view.assembly["balloons"]]
                                    if view.assembly else None),
                       "balloon_view": (bool(view.assembly["balloon_view"])
                                        if view.assembly else None),
                       "envelope": (list(view.assembly["envelope"])
                                    if view.assembly else None),
                       "overlap_area_mm2": (view.assembly["overlap_area_mm2"]
                                            if view.assembly else None),
                       # 爆炸事实：不给 exploded 就分不出「没摆开」与「摆了但看不出」
                       "exploded": (bool(view.assembly["exploded"])
                                    if view.assembly else None),
                       "connectors": ([dict(c) for c in view.assembly["connectors"]]
                                      if view.assembly else None),
                       "dimensions": view.dimensions})

    assembly_views = [v for v in views if v.assembly]
    hook_evidence: dict[str, Any] = {}
    if layout_hook is not None:
        hook_evidence = layout_hook(msp, (width, height)) or {}
    assembly_warnings = sorted(
        {str(msg) for v in assembly_views if v.assembly
         for msg in v.assembly.get("warnings") or []})

    _draw_title_block(msp, width, height, part_name, revision, scale, material,
                      sheet, provenance or {})

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.dxfversion = "AC1024"
    doc.saveas(str(path))
    counts: dict[str, int] = {}
    for e in msp:
        counts[e.dxftype()] = counts.get(e.dxftype(), 0) + 1
    evidence: dict[str, Any] = {
        "sheet": sheet, "sheet_size_mm": [width, height], "scale": scale,
        "views": placed, "entity_counts": counts,
        "dimension_chain_check": {v["view"]: v["chain_check"] for v in placed},
        "stackup_check": stackups,
        "stackup_inconsistent": any(
            s["verdict"] == "inconsistent" for s in stackups.values()),
        "stackup_undecidable": sorted(
            name for name, s in stackups.items()
            if s["verdict"] in ("insufficient_data", "no_closing_tolerance")),
        "gdt_frames": gdt_frames,
        "gdt_issues": gdt_issues,
        "gdt_issue_kinds": sorted({str(i["kind"]) for i in gdt_issues}),
        "gdt_unmatched_features": gdt_unmatched,
        "section_issues": sorted({msg for v in placed for msg in v["section_problems"]}),
        "section_letters": section_letters,
        "section_warnings": sorted({m for v in placed for m in v["section_warnings"]}),
        "detail_numbers": detail_numbers,
        "detail_issues": sorted({msg for view in views
                                 for msg in view.detail_problems}),
        # 这三条默认值代表「这张图不是装配图」；装配侧由 extra_evidence / layout_hook
        # 覆盖，本模块不自己拼装配结构（那需要 import 装配模块，就是环）
        "assembly": None,
        "parts_list": None,
        "bom": None,
        "assembly_issues": sorted({str(msg) for view in assembly_views if view.assembly
                                   for msg in view.assembly.get("issues") or []}),
        "assembly_warnings": assembly_warnings,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        **spec_stats}
    evidence.update(extra_evidence or {})
    evidence.update(hook_evidence or {})
    return evidence


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


def _draw_view(msp: Any, view: ViewGeometry, cx: float, cy: float, scale: float,
               frames: list[dict[str, Any]] | None = None,
               symbol_linetype: str = "DASHED") -> None:
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

    for poly in view.cut_regions:
        pts = place(poly)
        if len(pts) >= 3:
            hatch = msp.add_hatch(dxfattribs={"layer": "HATCH", "color": 7})
            hatch.paths.add_polyline_path(pts, is_closed=True)
            hatch.set_pattern_fill("ANSI31", scale=1.0)

    if frames:
        from aipd_os.cad.gdt import draw_frame

        cursor_y = off_y + view.bbox[3] * scale + 10.0
        for frame in frames:
            origin = (off_x + view.bbox[2] * scale + 10.0, cursor_y)
            anchor = (frame["attach"][0] * scale + off_x,
                      frame["attach"][1] * scale + off_y)
            draw_frame(msp, frame, origin, anchor)
            cursor_y += 14.0

    _draw_section_symbols(msp, view, place, scale, symbol_linetype)
    _draw_detail_marks(msp, view, place, scale)
    if view.render_overlay is not None:
        # 与图线共用同一个 place：自己再算偏移会飞到视图外面
        view.render_overlay(msp, view, scale, place)


def _draw_detail_marks(msp: Any, view: ViewGeometry, place: Any, scale: float) -> None:
    """放大标记：母视图上的裁剪圈 + 圈外编号，以及放大图自己的边界圈。

    两处都用 ``place``：母视图的圈用母视图的放置（半径 × 母视图比例），放大图的圈用
    放大图的放置（同一套局部坐标、半径 × 放大后的比例），所以圈与图线**必然**同心同尺——
    看图人拿尺量母视图那个圈，量出来的就是证据里写的半径。
    """
    for mark in view.detail_markers:
        centre = place([(float(mark["center"][0]), float(mark["center"][1]))])[0]
        radius = float(mark["radius"]) * scale
        msp.add_circle(centre, radius, dxfattribs={"layer": "DETAIL", "color": 5})
        height = DETAIL_NUMBER_HEIGHT * scale
        msp.add_text(str(mark["number"]), dxfattribs={"layer": "DETAIL",
                                                      "height": height}) \
           .set_placement((centre[0] + radius * 0.7071 + height * 0.3,
                           centre[1] + radius * 0.7071))
    if view.detail_of and not view.detail_problems:
        # 空放大图连自己的边界圈都不画：画了就是声称这张详图成立
        centre = place([(float(view.detail_of["center"][0]),
                         float(view.detail_of["center"][1]))])[0]
        msp.add_circle(centre, float(view.detail_of["radius"]) * scale,
                       dxfattribs={"layer": "DETAIL", "color": 5})


def _draw_section_symbols(msp: Any, view: ViewGeometry, place: Any, scale: float,
                          linetype: str) -> None:
    """画剖切符号：剖切线 + 两端指向保留侧的短划 + 两端字母。

    线型由调用方给（PHANTOM 优先，文档里没有时退回 DASHED）：引用不存在的 linetype
    会让 DXF 在别的软件里被判损坏，所以宁可换线型也不硬写名字。
    """
    for sym in view.section_symbols:
        kept = sym["kept_side"]
        p1 = place([tuple(sym["from"])])[0]
        p2 = place([tuple(sym["to"])])[0]
        msp.add_line(p1, p2, dxfattribs={"layer": "SECTION", "linetype": linetype,
                                         "color": 1})
        for end in (p1, p2):
            tip = (end[0] + kept[0] * SECTION_TICK * scale,
                   end[1] + kept[1] * SECTION_TICK * scale)
            msp.add_line(end, tip, dxfattribs={"layer": "SECTION", "color": 1})
            height = SECTION_LETTER_HEIGHT * scale
            msp.add_text(sym["letter"], dxfattribs={"layer": "SECTION",
                                                    "height": height}) \
               .set_placement((tip[0] - height / 2.0, tip[1] + height * 0.4))


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


def _finish_evidence(path: Path, evidence: dict[str, Any], part_name: str, revision: str,
                     provenance: dict[str, Any] | None) -> dict[str, Any]:
    """补上溯源、写 ``.evidence.json`` sidecar（单件图与装配图共用同一条收尾）。"""
    evidence.update(provenance or {})
    evidence.update({"part": part_name, "revision": revision,
                     "generated_at": datetime.now(timezone.utc).isoformat(),
                     "hidden_line_method": HIDDEN_LINE_METHOD})
    from aipd_os.cad.evidence import sidecar_path

    sidecar = sidecar_path(path)
    sidecar.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    evidence["evidence_file"] = str(sidecar)
    return evidence


def generate_drawing(model: Any, out_path: Path | str, *,
                     part_name: str, revision: str = "A",
                     views: tuple[str, ...] = ("FRONT", "TOP", "RIGHT"),
                     scale: float = 1.0, material: str = "-",
                     sheet: str = "A3",
                     provenance: dict[str, Any] | None = None,
                     spec: dict[str, Any] | None = None,
                     sections: Sequence[str] = (),
                     details: Sequence[str] = ()) -> dict[str, Any]:
    """端到端：单件模型 -> 视图 -> DXF -> 证据字典（含哈希与实体统计）。

    装配图走 ``aipd_os.cad.assembly.generate_assembly_drawing``（它 import 本模块，
    本模块不 import 它 —— 反向边会被无环门判红）。

    ``spec`` 只用于声明公差（``{"features": [{"feature": "TOP.hole_2",
    "tolerance": {"upper": 0.05, "lower": -0.05}}], "global_tolerance": {...}}``），
    尺寸值一律来自几何测量，spec 不参与测量。

    ``details`` 是局部放大声明（``"TOP@(-30,0)/12=2"``）：圆心/半径用母视图局部坐标，
    倍数是相对母视图印出比例的放大。母视图名写错直接报错，不静默少一张图。
    """
    path = Path(out_path)
    built: list[ViewGeometry] = []
    for name in views:
        if name not in STANDARD_VIEWS:
            raise ValueError(f"未知视图 {name}；可用：{sorted(STANDARD_VIEWS)}")
        direction, up = STANDARD_VIEWS[name]
        built.append(build_view(model, name, direction, up))
    seen_axes: set[str] = set()
    for idx, raw in enumerate(sections):
        axis, offset = parse_section_spec(raw)
        suffix = "" if axis not in seen_axes else f"_{sorted(seen_axes).index(axis) + idx + 1}"
        seen_axes.add(axis)
        built.append(section_view(model, f"SECTION_{axis}{suffix}", axis, offset))
    by_name = {v.name: v for v in built}
    for idx, raw in enumerate(details):
        parent_name, center, radius, factor = parse_detail_spec(raw)
        parent = by_name.get(parent_name)
        if parent is None:
            raise ValueError(f"局部放大的母视图 {parent_name!r} 不在本图里；"
                             f"可用：{sorted(by_name)}")
        detail = detail_view(parent, f"DETAIL_{idx + 1}", center, radius, factor)
        built.append(detail)
        by_name[detail.name] = detail
    evidence = write_dxf(built, path, part_name=part_name, revision=revision,
                         scale=scale, material=material, sheet=sheet,
                         provenance=provenance, spec=spec)
    return _finish_evidence(path, evidence, part_name, revision, provenance)
