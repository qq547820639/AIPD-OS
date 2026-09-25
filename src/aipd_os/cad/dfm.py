"""DFM/DFA 可制造性分析的**生产者**（capability ``cad.dfm_dfa``，C5 与 C6 都要的那一项）。

分工先说清楚，因为这是这片的全部要点：

* **事实来自内核实测**：壁厚、孔径与孔深、孔周留肉、内圆角半径、同轴孔系、包络与体积——
  都是 OCP 拓扑/几何量出来的，不读名字、不按「看着像」猜。整孔与圆角的区分用**角向张角是否
  满一周**（圆柱面 u 参数区间 ÷ 2π），这是拓扑判据；Ø6×10 通孔张角 1.0000、R2 圆角 0.2500，
  本机实测。**但张角满一周还不足以说是孔**：Ø20 圆棒的侧面同样满一周，所以再加一根正交判据
  ——从面上一点**径向外移** 1µm 问 `BRepClass3d_SolidClassifier`，落进材料里才是孔
  （本机实测：垫片 Ø30 外圆 + Ø8 中心孔 → 只报 1 个孔 Ø8）。
* **阈值一律带来处**：每条规则自带 `source`（URL + 访问日期 + 是厂商能力还是转述的标准表 +
  一句限定）。本仓**不发明阈值**：量不出可比对象的建议（比如厂商给的「内圆角 ≥ 腔深 1/3」
  是个比值，本仓没有一个可比的「腔深」定义）就**只报事实不判红**，条目 `limit` 为 ``None``。
  确实要把厂商给**甲特征**的数用到**乙特征**上时（孔周留肉借壁厚那条），必须走
  ``borrowed_out_of_scope`` 并写明「原述是给甲的」——挂个 URL 就自称有出处，是把外推
  冒充标准。
* **测不出来就说测不出来**：规则前提不成立（材料认不出类别、没有整孔、没有声明公差）时记
  ``blind`` 并写明原因，**绝不折算成 pass**。一次都没测出来的分析不能读成「没有 DFM 问题」。

为什么不是封装第三方库（2026-09-25 实检，详见
`docs/audit/DFM_DFA_PRODUCER_F-DFM-01_2026-09-25.md` §二）：最贴近的两个开源实现
`ncc-uk/SmartDFM`（GitHub API 列出的 26 个根条目里**没有 LICENSE 文件**，实现是 GNN 训练
+ CATIA 脚本群）与 `ishaannsaini-sudo/DFMedusa`（README 取不到，等于无法判断规则来处）
都**不可合法引入**；SmartDFM 的 `fact_base.py` + `rule_base.py` 那套「先抽事实、再判规则」
分层是对的，这里借结构不借代码。阈值来处也不是随便挑的：HLH Rapid 与 Xometry 两家厂商
**各自独立**给出金属最小壁厚 0.8mm / 0.794mm（后者是 1/32 英寸的换算）、塑料 1.5mm、
钻孔深径比 ≤4×（Xometry 补上限 10×），量级一致才敢用作 advisory/hold 的分界；
ISO 2768-1 的 f/m/c/v 表由 3ERP 页面**转述**（该页没有声称逐字转录，来源里就写转述）。

明确**未实现**（不要当成已具备）：DFA 的装配力与紧固顺序、模具侧抽芯与脱模方向、
铸造圆角与收缩率、热变形/振动的 CAE 仿真（那是 `cad.cae_*` 那几行的事）、
工序工时与加工成本（本仓不建 operations 表，见第 16 片裁决）。
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 壁厚射线的网格间距（毫米）。0.5 是实测折中：1.0 会在 0.6mm 薄板上漏测（采样点
#: 全部落在孔的投影带外时读数会变成 12mm 那个方向的最小值），0.25 让单个小件从
#: 秒级涨到十秒级而读数不变。它是**分辨率**不是阈值：换粗只会漏掉薄壁，不会凭空造出薄壁。
DEFAULT_SPACING_MM = 0.5

#: 整孔判据：圆柱面角向张角达到满圆这个比例才算孔（圆角是 1/4 周，实测 0.2500）。
FULL_REVOLUTION_RATIO = 0.999

#: 同轴判据：两条圆柱轴线之间的距离（毫米）小于这个值算同一根孔系。
COAXIAL_TOLERANCE_MM = 0.05

#: 部分回转的圆柱面至少要张到这么大（弧度）才计入圆角统计——避开缝合线退化面。
MIN_PARTIAL_ARC_RADIANS = 0.2

#: 射线探测的最大长度 = 包络对角线的这个倍数。命中数为奇数（相切/非流形）只计数不猜。
_PROBE_MARGIN = 1e-3

_TOL = "\u00b1"      # ±
_DIA = "\u00d8"      # Ø

NOT_COVERED = ["DFA 装配力与紧固顺序", "模具侧抽芯与脱模方向", "铸造圆角与收缩率",
               "热变形/振动的 CAE 仿真", "工序工时与加工成本"]


def _src(url: str, accessed: str, kind: str, note: str,
         stated_for: str | None = None) -> dict[str, str]:
    """`stated_for` 只有借数（``borrowed_out_of_scope``）那条路才填：页子把那个数
    **原本**是给哪条特征的 —— 缺这一格，借数就退化成「挂了个 URL 的自造阈值」。"""
    out = {"url": url, "accessed": accessed, "kind": kind, "note": note}
    if stated_for is not None:
        out["stated_for"] = stated_for
    return out


#: basis/kind 的人话名字（报告里出现的是这个，不是机器码）。
_KIND_LABEL = {"vendor_capability": "厂商能力页",
               "borrowed_out_of_scope": "借来的数：厂商页原述是别的特征"}


#: 规则表。`basis` 与 `source.kind` 必须一致（运行时 `_check_source_integrity` 与
#: 常驻用例都会逐条核对），三种取值见该函数的 docstring；
#: `limit` 为 ``None`` 表示这条**只报事实**——没有可引用的阈值来处时不编一个数。
RULES: list[dict[str, Any]] = [
    {
        "id": "wall_thickness_metal", "name": "金属最小壁厚", "basis": "vendor_capability",
        "measure": "facts.min_wall_thickness_mm", "op": "<", "limit": 0.8, "unit": "mm",
        "severity": "advisory",
        "source": _src(
            "https://hlhrapid.com/knowledge/design-guide-cnc-machining/", "2026-09-25",
            "vendor_capability",
            f"页内给出金属最小壁厚 0.8mm、塑料 {_TOL}1.5mm；页面无 License 声明。"
            "互证：Xometry《CNC 加工的行业标准》同主题页独立给出金属 0.794mm"
            "（= 1/32 英寸换算）、塑料 1.5mm——两家数值同量级，故取作 advisory 分界"),
    },
    {
        "id": "wall_thickness_plastic", "name": "塑料最小壁厚", "basis": "vendor_capability",
        "measure": "facts.min_wall_thickness_mm", "op": "<", "limit": 1.5, "unit": "mm",
        "severity": "advisory",
        "source": _src(
            "https://hlhrapid.com/knowledge/design-guide-cnc-machining/", "2026-09-25",
            "vendor_capability",
            f"页内给出塑料 {_TOL}1.5mm；Xometry 同主题页独立给出 1.5mm，两家一致"),
    },
    {
        "id": "hole_depth_to_diameter", "name": "钻孔深径比", "basis": "vendor_capability",
        "measure": "facts.holes[].depth_over_diameter", "op": ">", "limit": 4.0,
        "unit": "\u00d7", "severity": "advisory",
        "source": _src(
            "https://xometry.hk/en/industry-standards-in-cnc-machining/", "2026-09-25",
            "vendor_capability",
            "页内：一般推荐直径 4 倍深度，最大可到 10 倍；HLH Rapid 独立给出「深径比 >4 "
            "需二次操作」。取 4 为保守侧，>10 另列 gun_drill_required"),
    },
    {
        "id": "gun_drill_required", "name": "深孔需专用工艺", "basis": "vendor_capability",
        "measure": "facts.holes[].depth_over_diameter", "op": ">", "limit": 10.0,
        "unit": "\u00d7", "severity": "hold",
        "source": _src(
            "https://xometry.hk/en/industry-standards-in-cnc-machining/", "2026-09-25",
            "vendor_capability",
            "页内把 10 倍标为该工艺上限；超过就不是普通铣钻能定的事，需制造方确认，"
            "故判 hold（阻断就绪，不阻断出报告）"),
    },
    {
        "id": "tolerance_below_achievable", "name": "声明公差超出常规可达",
        "basis": "vendor_capability", "measure": "spec.tolerances[].abs_half_band_mm",
        "op": "<", "limit": 0.025, "unit": "mm", "severity": "hold",
        "source": _src(
            "https://xometry.hk/en/industry-standards-in-cnc-machining/", "2026-09-25",
            "vendor_capability",
            f"页内标称常规可达 0.025mm（同页通用公差 0.125mm）；参照：3ERP 转述的 "
            f"ISO 2768-1 f 级最细也只到 {_TOL}0.05（0.5–3mm 段）。比 0.025 更严的尺寸公差"
            "不是「图纸写紧一点」就能交，判 hold 待制造方确认"),
    },
    {
        "id": "inside_radius_reported", "name": "最小内圆角半径（只报事实）",
        "basis": "own_measure", "measure": "facts.inside_radius_mm", "op": "report",
        "limit": None, "unit": "mm", "severity": "info",
        "source": _src(
            "", "2026-09-25", "own_measure",
            "本仓口径、不设阈值：厂商（HLH Rapid）给的是「内圆角半径 \u2265 腔深 1/3」"
            "这个**比值**，本仓没有一个可比的「腔深」定义，硬编一个绝对毫米数就是假装标准"),
    },
    {
        "id": "same_axis_hole_count", "name": "同轴孔系数量（只报事实）",
        "basis": "own_measure", "measure": "facts.coaxial_groups[].hole_count",
        "op": "report", "limit": None, "unit": "孔", "severity": "info",
        "source": _src(
            "", "2026-09-25", "own_measure",
            "本仓口径、不设阈值：同一根轴上量出几个整孔，对应「一次装夹能钻几个孔」，"
            "不是合格与否"),
    },
    {
        "id": "hole_land_reported", "name": "孔周最小留肉（只报事实）", "basis": "own_measure",
        "measure": "facts.min_hole_land_mm", "op": "report",
        "limit": None, "unit": "mm", "severity": "info",
        "source": _src(
            "", "2026-09-25", "own_measure",
            "本仓口径：孔口圆到最近自由边（含相邻孔的口边）的精确极值距离。"
            "检索到的厂商页（HLH Rapid、Xometry）都没写孔边距；3ERP 转述的 ISO 2768 "
            "只把 edge distance 当成「由一般公差覆盖的尺寸」，不是阈值"),
    },
    {
        "id": "hole_land_metal", "name": "金属孔周留肉", "basis": "borrowed_out_of_scope",
        "measure": "facts.min_hole_land_mm", "op": "<", "limit": 0.8, "unit": "mm",
        "severity": "advisory",
        "source": _src(
            "https://hlhrapid.com/knowledge/design-guide-cnc-machining/", "2026-09-25",
            "borrowed_out_of_scope",
            "**这个数页子上是给「金属最小壁厚」的，不是给孔边距的**（本轮检索证实：HLH Rapid "
            "与 Xometry 都没有 machined 件的孔边距规则，3ERP 转述的 ISO 2768 只把 edge distance "
            "当成「由一般公差覆盖的尺寸」）。借的理由：孔口到自由边剩下的那段肉与「一堵墙」"
            "是同一类特征——钻完孔后悬着的一条窄料，会让孔口翻边、刀具让不住。"
            "判 advisory：这一步外推由制造方核，本仓不自证为标准",
            stated_for="wall_thickness_metal"),
    },
    {
        "id": "hole_land_plastic", "name": "塑料孔周留肉", "basis": "borrowed_out_of_scope",
        "measure": "facts.min_hole_land_mm", "op": "<", "limit": 1.5, "unit": "mm",
        "severity": "advisory",
        "source": _src(
            "https://hlhrapid.com/knowledge/design-guide-cnc-machining/", "2026-09-25",
            "borrowed_out_of_scope",
            "同 metal 那条：数是页子上「塑料最小壁厚 ±1.5mm」的（Xometry 同页独立给 1.5mm），"
            "外推到孔周留肉；厂商没有孔边距规则可引，故仍是 advisory 不是 hold",
            stated_for="wall_thickness_plastic"),
    },
]

#: 材料关键词。认不出来返回 ``None``（= 不知道），**不**按「非塑料即金属」兜底。
_PLASTIC_KEYS = ("abs", "pc", "pmma", "nylon", "pa6", "pa66", "pom", "pp", "pe",
                 "peek", "pvdf", "ptfe", "acetal", "塑", "尼龙")
_METAL_KEYS = ("6061", "7075", "5052", "aluminum", "aluminium", "ss", "steel",
               "stainless", "brass", "copper", "bronze", "ti-6al-4v", "titanium",
               "mg", "铝", "钢", "钛", "铜", "镁")


def rule_by_id(rule_id: str) -> dict[str, Any]:
    for rule in RULES:
        if rule["id"] == rule_id:
            return rule
    raise ValueError(f"规则表里没有 {rule_id!r}；现有：{[r['id'] for r in RULES]}")


def _check_source_integrity(rule: dict[str, Any]) -> None:
    """阈值必须有来处，且来处的说法必须自洽。

    三种 basis 各有规矩：``own_measure`` 不许挂 URL（本仓口径不自称标准）；
    ``vendor_capability`` 必须有页；``borrowed_out_of_scope`` 是「页上那个数原本是给
    别的特征的」，所以除了页，还必须指回表内那条**真被页撑着**的规则，并且**借的是同一个数、
    同一页** —— 不然一条自造的阈值挂上任意 URL 就冒充有出处了。
    """
    source = rule.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"规则 {rule.get('id')!r} 没有 source：阈值必须有来处，"
                         "本仓不发明公差/壁厚数")
    if source.get("kind") != rule.get("basis"):
        raise ValueError(f"规则 {rule.get('id')!r} 的 basis 与 source.kind 不一致")
    if rule.get("basis") == "own_measure" and source.get("url"):
        raise ValueError(f"规则 {rule.get('id')!r} 自称本仓口径却挂了 URL")
    if rule.get("basis") != "borrowed_out_of_scope":
        return
    donor_id = source.get("stated_for")
    if not donor_id:
        raise ValueError(f"规则 {rule.get('id')!r} 自称借数却没写 stated_for："
                         "页子上那个数原本是给哪个特征的，必须指名")
    donor = rule_by_id(str(donor_id))
    if donor["basis"] != "vendor_capability":
        raise ValueError(f"规则 {rule.get('id')!r} 从 {donor_id!r} 借数，"
                         "但那条自己就不是页子上的数")
    if donor.get("limit") != rule.get("limit"):
        raise ValueError(f"规则 {rule.get('id')!r} 借的是 {donor_id!r} 的数，"
                         f"limit 却写成 {rule.get('limit')!r}（那条是 {donor.get('limit')!r}）")
    if donor["source"].get("url") != source.get("url"):
        raise ValueError(f"规则 {rule.get('id')!r} 与被借的 {donor_id!r} 挂的不是同一页")


def material_is_plastic(material: str | None) -> bool | None:
    """三态分类：``True`` 塑料、``False`` 金属、``None`` **认不出来**。

    拿「不在塑料表里就按金属」兜底会得到一个假结论：复合材料/陶瓷/未登记牌号既不该按
    0.8mm 线判也不该按 1.5mm 线判，正确处置是记 blind（原因 `material_class_unknown`）。
    """
    if material is None:
        return None
    text = str(material).strip().lower()
    if not text:
        return None
    if any(key in text for key in _PLASTIC_KEYS):
        return True
    if any(key in text for key in _METAL_KEYS):
        return False
    return None


# ---------------------------------------------------------------------------
# 一、几何事实（内核测量）
# ---------------------------------------------------------------------------

def _walk_faces(shape: Any) -> list[Any]:
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out: list[Any] = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while exp.More():
        out.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return out


def _cylinder_reading(face: Any) -> dict[str, Any] | None:
    """读一个圆柱面：半径、轴向深度、角向张角（占整周的比例）、轴线与轴上一点。"""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    surf = BRepAdaptor_Surface(face)
    if surf.GetType() != GeomAbs_Cylinder:
        return None
    cyl = surf.Cylinder()
    u0, u1 = surf.FirstUParameter(), surf.LastUParameter()
    v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
    p0, p1 = surf.Value(0.0, v0), surf.Value(0.0, v1)
    axis = cyl.Axis()
    location = axis.Location()          # 轴**线**上的点，不是曲面上的点（下面分轴要用它）
    direction = axis.Direction()
    return {
        "radius_mm": float(cyl.Radius()),
        "depth_mm": math.dist((p0.X(), p0.Y(), p0.Z()), (p1.X(), p1.Y(), p1.Z())),
        "arc_fraction": abs(u1 - u0) / (2.0 * math.pi),
        "arc_radians": abs(u1 - u0),
        "axis": [float(direction.X()), float(direction.Y()), float(direction.Z())],
        "axis_point": [float(location.X()), float(location.Y()), float(location.Z())],
    }


def _envelope(shape: Any) -> list[float]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return [hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z()]


def _volume(shape: Any) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def _coaxial_groups(holes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """按**轴线**分组：方向平行且轴间距离小于容差 ⇒ 同一根孔系。

    不比较名字、不比较直径：Ø6 通孔与 Ø2.5 盲孔同轴时是同一次装夹的两个工序，
    分组判据只有几何。
    """
    groups: list[dict[str, Any]] = []
    for hole in holes:
        placed = False
        for group in groups:
            if _same_axis(group["axis"], hole["axis"], group["axis_point"],
                          hole["axis_point"]):
                group["hole_count"] += 1
                group["diameter_mm"].append(hole["diameter_mm"])
                placed = True
                break
        if not placed:
            groups.append({"axis": list(hole["axis"]),
                           "axis_point": list(hole["axis_point"]),
                           "hole_count": 1, "diameter_mm": [hole["diameter_mm"]]})
    return sorted(groups, key=lambda g: (-g["hole_count"], g["axis_point"]))


def _same_axis(a: Sequence[float], b: Sequence[float], pa: Sequence[float],
               pb: Sequence[float]) -> bool:
    cross = _cross(a, b)
    if _len(cross) > 1e-6:                       # 方向不平行就不是同一根轴
        return False
    return _len(_cross([pb[i] - pa[i] for i in range(3)], a)) < COAXIAL_TOLERANCE_MM


def _cross(u: Sequence[float], v: Sequence[float]) -> list[float]:
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0]]


def _len(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _oriented(axis: Sequence[float]) -> list[float]:
    """把轴向量规范化成**无向直线**的一个代表：绝对值最大的分量取正。

    孔的轴线方向取决于建模顺序（本机实测：顶面钻的 Ø6 轴是 +Z、底面钻的 Ø3 是 -Z），
    同轴判据不能依赖它；而分组报告要稳定可断言，所以先规范化再存进证据。
    """
    idx = max(range(3), key=lambda i: abs(axis[i]))
    sign = -1.0 if axis[idx] < 0.0 else 1.0
    return [round(axis[i] * sign, 6) for i in range(3)]


#: 判「孔还是外圆」时径向外移多少去问分类器。这里是拓扑分类（IN/OUT）不是量长度，
#: 但移太大会穿过薄壁落到另一侧的空气里。
_BORE_PROBE_MM = 1e-3


def _solid_classifiers(shape: Any) -> list[Any]:
    """逐**实体**建 `BRepClass3d_SolidClassifier`（compound 里的每个实体各一个）。"""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out = []
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SOLID)
    while exp.More():
        out.append(BRepClass3d_SolidClassifier(TopoDS.Solid_s(exp.Current())))
        exp.Next()
    return out


def _cylinder_is_bore(face: Any, classifiers: Sequence[Any],
                      offset_mm: float = _BORE_PROBE_MM) -> bool | None:
    """整周回转的圆柱面是**孔**还是**外圆**：从面上一点径向外移，落进材料里就是孔。

    「弧长满一周」这一个条件分不出来：Ø20 圆棒的侧面也满一周。按旧口径它会被当成
    一个 Ø20×深 20 的孔，于是孔数、深径比、孔周留肉全跟着错（留肉那条会拿外圆
    到内孔的距离当「孔边剩下的肉」）。所以加这根正交的判据：
    孔壁**外面**是材料（分类器给 IN），外圆**外面**是空气（给 OUT）。

    没有实体可分类（纯曲面/纯线框输入）⇒ 返回 ``None`` = **不知道**，不猜成孔也不猜成外圆。
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopAbs import TopAbs_State

    if not classifiers:
        return None
    surf = BRepAdaptor_Surface(face)
    if surf.GetType() != GeomAbs_Cylinder:
        return None
    axis = surf.Cylinder().Axis()
    dirv = gp_Vec(axis.Direction())
    point = surf.Value(0.5 * (surf.FirstUParameter() + surf.LastUParameter()),
                       0.5 * (surf.FirstVParameter() + surf.LastVParameter()))
    vec = gp_Vec(axis.Location(), point)
    axial = vec.Dot(dirv)
    perp = gp_Vec(vec.X() - axial * dirv.X(), vec.Y() - axial * dirv.Y(),
                  vec.Z() - axial * dirv.Z())
    if perp.Magnitude() < 1e-9:
        return None                       # 采到了轴上（半径退化成 0）
    perp.Normalize()
    probe = gp_Pnt(point.X() + offset_mm * perp.X(), point.Y() + offset_mm * perp.Y(),
                   point.Z() + offset_mm * perp.Z())
    states = set()
    for clf in classifiers:
        clf.Perform(probe, 1e-7)
        states.add(clf.State())
    if TopAbs_State.TopAbs_IN in states:
        return True
    if states & {TopAbs_State.TopAbs_ON, TopAbs_State.TopAbs_UNKNOWN}:
        return None                       # 落在边界上或分类器没结论：不猜
    return False


def geometry_facts(shape: Any) -> dict[str, Any]:
    """从 TopoDS_Shape 量出 DFM 要用的几何事实；读不出面就抛，不交一份空分析。"""
    faces = _walk_faces(shape)
    if not faces:
        raise ValueError("这个形状里一个面都读不到：孔数/壁厚/圆角都无从测量，"
                         "不折算成「0 个孔、没有薄壁」")
    classifiers = _solid_classifiers(shape)
    holes: list[dict[str, Any]] = []
    partials: list[float] = []
    outer_cylinders = undecided = 0
    for face in faces:
        read = _cylinder_reading(face)
        if read is None:
            continue
        if read["arc_fraction"] >= FULL_REVOLUTION_RATIO:
            bore = _cylinder_is_bore(face, classifiers)
            if bore is False:
                outer_cylinders += 1     # 外圆不是孔：不计入孔数、深径比与留肉
                continue
            if bore is None:
                undecided += 1
            diameter = round(2.0 * read["radius_mm"], 6)
            depth = round(read["depth_mm"], 6)
            holes.append({"diameter_mm": diameter, "depth_mm": depth,
                          "depth_over_diameter": round(depth / diameter, 6) if diameter else None,
                          "axis": _oriented(read["axis"]),
                          "axis_point": [round(v, 6) for v in read["axis_point"]]})
        elif read["arc_radians"] >= MIN_PARTIAL_ARC_RADIANS:
            partials.append(read["radius_mm"])
    env = [round(v, 6) for v in _envelope(shape)]
    return {
        "holes": sorted(holes, key=lambda h: (-h["depth_over_diameter"], h["diameter_mm"])),
        "partial_cylinder_count": len(partials),
        "inside_radius_mm": round(min(partials), 6) if partials else None,
        "coaxial_groups": _coaxial_groups(holes),
        "outer_cylinder_count": outer_cylinders,
        "bore_undecided_cylinder_count": undecided,
        "envelope_mm": env,
        "volume_mm3": round(_volume(shape), 6),
        "face_count": len(faces),
    }


def _face_normal_thickness(shape: Any, spacing_mm: float,
                           max_samples_per_face: int = 12) -> dict[str, Any]:
    """沿**面法向**量局部壁厚：从面上每一点向两侧走，取第一段「确实在材料里、
    出射点确实在材料外」的距离。

    为什么要有这一法：三轴射线与面的夹角未知，量到的永远是**弦**而不是**垂直厚度**，
    而弦可以比垂直厚度**长**（斜穿）也可以比它**短**（在棱角附近擦过）。
    本机实测：3mm 厚、绕 Y 转 45° 的板，三轴法给 1.00mm（不是「只会测厚不测薄」）。
    所以这一法不是「更保守」，是**方向正确**：CATIA 的壁厚分析同样有沿法向的 Ray 模式
    （其文档明说 Ray 在尖边处误差可超容差，故默认用球），本仓的处理是
    ①只采参数域**中间 60%**（躲开棱边与角点）、②法向退化（极点/奇异）直接跳过、
    ③用 `BRepClass3d_SolidClassifier` 逐条验「中点在材料内、出射点在材料外」才计数。

    逐**实体**分类而不是对整个 shape 分类：壁厚是一个实体本身的属性，
    两个互不相连的实体不应互相把对方的内部当成「材料内」。
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Vec
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    eps = 1e-4
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox, False)
    cmin, cmax = bbox.CornerMin(), bbox.CornerMax()
    diag = _len([cmax.X() - cmin.X(), cmax.Y() - cmin.Y(), cmax.Z() - cmin.Z()]) + 1.0

    best: float | None = None
    probed = usable = skipped = faces_seen = 0
    exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_SOLID)
    while exp.More():
        solid = TopoDS.Solid_s(exp.Current())
        exp.Next()
        inter = IntCurvesFace_ShapeIntersector()
        inter.Load(solid, 1e-7)
        clf = BRepClass3d_SolidClassifier(solid)
        fexp = TopExp_Explorer(solid, TopAbs_ShapeEnum.TopAbs_FACE)
        while fexp.More():
            face = TopoDS.Face_s(fexp.Current())
            fexp.Next()
            faces_seen += 1
            adaptor = BRepAdaptor_Surface(face)
            u0, u1 = adaptor.FirstUParameter(), adaptor.LastUParameter()
            v0, v1 = adaptor.FirstVParameter(), adaptor.LastVParameter()
            prop = BRepGProp_Face(face)
            nu = max(2, min(max_samples_per_face, int(abs(u1 - u0) / spacing_mm) + 1))
            nv = max(2, min(max_samples_per_face, int(abs(v1 - v0) / spacing_mm) + 1))
            for i in range(nu):
                for j in range(nv):
                    # 只采参数域中间 60%：面边界与角点附近法向本身就不可靠
                    u = u0 + (u1 - u0) * (0.2 + 0.6 * (i / max(nu - 1, 1)))
                    v = v0 + (v1 - v0) * (0.2 + 0.6 * (j / max(nv - 1, 1)))
                    point, normal = gp_Pnt(), gp_Vec()
                    prop.Normal(u, v, point, normal)
                    if normal.Magnitude() < 1e-9:
                        skipped += 1       # 极点/奇异：法向没定义，不猜
                        continue
                    normal.Normalize()
                    probed += 1
                    for sign in (1.0, -1.0):
                        dirv = gp_Vec(normal.X() * sign, normal.Y() * sign,
                                      normal.Z() * sign)
                        inter.Perform(gp_Lin(point, gp_Dir(dirv)), eps, diag)
                        n = inter.NbPnt()
                        if n < 1:
                            continue
                        run = min(inter.WParameter(k + 1) for k in range(n))
                        # Perform 的参数域就从 eps 起，不必再挡一次「零长命中」
                        mid = gp_Pnt(point.X() + dirv.X() * run / 2.0,
                                     point.Y() + dirv.Y() * run / 2.0,
                                     point.Z() + dirv.Z() * run / 2.0)
                        beyond = gp_Pnt(point.X() + dirv.X() * (run + 1e-3),
                                        point.Y() + dirv.Y() * (run + 1e-3),
                                        point.Z() + dirv.Z() * (run + 1e-3))
                        clf.Perform(mid, 1e-7)
                        if clf.State() != TopAbs_State.TopAbs_IN:
                            continue       # 中点不在材料里：这一段不是壁厚
                        clf.Perform(beyond, 1e-7)
                        if clf.State() != TopAbs_State.TopAbs_OUT:
                            continue       # 出射点还在材料里：第一段命中不是边界
                        usable += 1
                        if best is None or run < best:
                            best = run
    return {"min_mm": round(best, 6) if best is not None else None,
            "faces_probed": faces_seen, "samples": probed,
            "samples_usable": usable, "samples_degenerate_normal": skipped,
            "sample_cap_per_face": max_samples_per_face,
            "sample_domain": "参数域中间 60%（躲棱边与角点）"}


def measure_hole_lands(shape: Any) -> dict[str, Any]:
    """孔口到**最近自由边**的最小留肉宽度（含相邻孔之间那一段）。

    量法：**孔**（不是外圆，判据见 `_cylinder_is_bore`）的圆柱面取出它的孔口圆边，
    对每一条找到「法向平行于孔轴且包含该圆圆心」的那个平面面片（就是孔开口的那一面），
    再取这个面片上**除孔自己那圈周边之外**的所有边，
    用 OCCT 的精确极值距离量「孔口圆 ↔ 那条边」的最小距离。
    相邻孔的口圆也是「别的边」，所以两孔之间的留肉天然落在同一个数里；
    同心/共面的台阶孔会各自量到自己那一层开口，取最小。

    为什么不报「中心到边」而是报留肉：中心距把孔径混进去了，读的人还得自己减半径；
    留肉就是**剩下的肉有多厚**，和壁厚那条判据说的是同一件事。中心距仍一并给出。
    一个孔的**每一个口**都各给一条读数（``rim_readings``），交出去的那条取其中最薄的一个——
    读数成对给出，别把「只量了遍历碰到的第一个口」这件事藏成一个数。

    量不出来给 ``land_mm=None`` + 原因（找不到开口面 / 那个面片除了孔边没有别的边 /
    口边根本不是圆），不折成 0，也不折成「很大」。
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    def sub(holder, kind, cast):
        exp = TopExp_Explorer(holder, kind)
        out = []
        while exp.More():
            out.append(cast(exp.Current()))
            exp.Next()
        return out

    def circle_edges(face):
        out = []
        for edge in sub(face, TopAbs_ShapeEnum.TopAbs_EDGE, TopoDS.Edge_s):
            curve = BRepAdaptor_Curve(edge)
            if curve.GetType() != GeomAbs_Circle:
                continue
            circ = curve.Circle()
            centre, axis = circ.Location(), circ.Axis().Direction()
            out.append({"edge": edge, "radius": float(circ.Radius()),
                        "centre": (centre.X(), centre.Y(), centre.Z()),
                        "axis": (axis.X(), axis.Y(), axis.Z())})
        return out

    def plane_of(face):
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Plane:
            return None
        pl = surf.Plane()
        normal, loc = pl.Axis().Direction(), pl.Location()
        return ((normal.X(), normal.Y(), normal.Z()), (loc.X(), loc.Y(), loc.Z()))

    def parallel(a, b):
        return all(abs(abs(a[i]) - abs(b[i])) < 1e-6 for i in range(3))

    faces = _walk_faces(shape)
    classifiers = _solid_classifiers(shape)
    planar = [(face, plane_of(face)) for face in faces]
    planar = [(face, info) for face, info in planar if info]
    rows: list[dict[str, Any]] = []
    for face in faces:
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Cylinder:
            continue
        arc = abs(surf.LastUParameter() - surf.FirstUParameter())
        if arc < 2.0 * math.pi * FULL_REVOLUTION_RATIO:
            continue                                   # 不是整周回转（圆角/槽壁）
        if _cylinder_is_bore(face, classifiers) is False:
            continue                                   # 整周但是外圆：没有「孔口」可言
        cyl = surf.Cylinder()
        radius = float(cyl.Radius())
        axis3 = cyl.Axis().Direction()
        axis = (axis3.X(), axis3.Y(), axis3.Z())
        reasons: list[str] = []
        rims = [one for one in circle_edges(face)
                if abs(one["radius"] - radius) < 1e-6 and parallel(one["axis"], axis)]
        if not rims:
            # 孔口开在曲面上：那条口边不是圆（是两条曲面的交线），量不到「孔口圆」
            reasons.append("rim_circle_not_found")
        per_rim: list[dict[str, Any]] = []
        for rim in rims:
            host = None
            for candidate, (normal, point) in planar:
                if not parallel(normal, axis):
                    continue
                if abs(sum(normal[i] * (rim["centre"][i] - point[i]) for i in range(3))) > 1e-6:
                    continue                           # 平面不含这个孔口（台阶孔的另一层）
                host = candidate
                break
            if host is None:
                reasons.append("rim_plane_not_found")
                per_rim.append({"land_mm": None, "centerline_to_edge_mm": None})
                continue
            others = []
            for edge in sub(host, TopAbs_ShapeEnum.TopAbs_EDGE, TopoDS.Edge_s):
                if any(abs(one["radius"] - radius) < 1e-6
                       and all(abs(one["centre"][i] - rim["centre"][i]) < 1e-6 for i in range(3))
                       and one["edge"].IsSame(edge) for one in circle_edges(host)):
                    continue                           # 孔自己的周边不是「边」
                others.append(edge)
            if not others:
                reasons.append("rim_isolated")
                per_rim.append({"land_mm": None, "centerline_to_edge_mm": None})
                continue
            dists = []
            for edge in others:
                probe = BRepExtrema_DistShapeShape(rim["edge"], edge)
                if probe.IsDone():
                    dists.append(float(probe.Value()))
            if not dists:
                reasons.append("distance_unresolved")
                per_rim.append({"land_mm": None, "centerline_to_edge_mm": None})
                continue
            land = min(dists)
            per_rim.append({"land_mm": round(land, 6),
                            "centerline_to_edge_mm": round(land + radius, 6)})
        thin = [one for one in per_rim if one["land_mm"] is not None]
        picked = min(thin, key=lambda one: one["land_mm"]) if thin else None
        rows.append({"diameter_mm": round(2.0 * radius, 6),
                     "land_mm": picked["land_mm"] if picked else None,
                     "centerline_to_edge_mm": (picked["centerline_to_edge_mm"]
                                               if picked else None),
                     "rim_count": len(rims),
                     "rim_readings": per_rim,
                     "why": sorted(set(reasons))})
    measured = [row["land_mm"] for row in rows if row["land_mm"] is not None]
    return {"holes": rows,
            "min_land_mm": round(min(measured), 6) if measured else None,
            "measurable_count": len(measured),
            "hole_count": len(rows),
            "method": "rim-to-free-edge 精确极值距离（BRepExtrema），相邻孔的口边同算一边"}


def measure_min_wall_thickness(shape: Any,
                               spacing_mm: float = DEFAULT_SPACING_MM) -> dict[str, Any]:
    """两条法各量一遍，取**最薄**那条交出去：三轴网格射线 + 沿面法向。

    三轴那条：沿 X/Y/Z 各铺一张网格，从包络外发射线，与实体所有面求交，把命中参数
    排序后两两配对（进→出）；奇数命中（相切/非流形）只计数不改判。
    这是**采样**，且量到的永远是**斜弦**——本机实测 3mm 斜板被它读成 1.00mm，
    所以「斜置只测厚不测薄」这句旧话是错的，误差两个方向都有。
    沿面法向那条补的是**方向**，但它每面最多采 12×12 个点，比三轴网格稀，
    所以它可能**漏掉**三轴抓到的薄特征（金样品 bracket 上：三轴 2.00、法向 2.24；
    这条读数还**随每面上限变**：上限降到 6×6 同一个件读成 3.73，故 `sample_cap_per_face`
    与两个数一起交出去）。

    两个数都留在读数里（`axis_min_mm` / `normal_min_mm`），`min_mm` 取两者较小：
    判阈值宁可多问一次制造方，也不把墙说厚。谁和谁不一致，报告里看得见。
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    corner_min, corner_max = box.CornerMin(), box.CornerMax()
    origin = [corner_min.X(), corner_min.Y(), corner_min.Z()]
    size = [corner_max.X() - corner_min.X(), corner_max.Y() - corner_min.Y(),
            corner_max.Z() - corner_min.Z()]
    diag = _len(size) + 1.0

    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)
    axes = ((0, (1.0, 0.0, 0.0)), (1, (0.0, 1.0, 0.0)), (2, (0.0, 0.0, 1.0)))
    best: float | None = None
    rays = odd = hits = 0
    for fixed_axis, direction in axes:
        free = [i for i in range(3) if i != fixed_axis]
        n0 = max(1, int(size[free[0]] / spacing_mm) + 1)
        n1 = max(1, int(size[free[1]] / spacing_mm) + 1)
        for i in range(n0):
            for j in range(n1):
                point = list(origin)
                point[free[0]] += (size[free[0]] * i) / max(n0 - 1, 1)
                point[free[1]] += (size[free[1]] * j) / max(n1 - 1, 1)
                point[fixed_axis] -= 1.0            # 从包络外面起笔
                inter.Perform(gp_Lin(gp_Pnt(*point), gp_Dir(*direction)),
                              -_PROBE_MARGIN, diag + _PROBE_MARGIN)
                n = inter.NbPnt()
                if not n:
                    continue
                rays += 1
                hits += n
                if n % 2:
                    odd += 1
                params = sorted(inter.WParameter(k + 1) for k in range(n))
                for pair in range(0, len(params) - 1, 2):
                    run = params[pair + 1] - params[pair]
                    if run > 1e-6 and (best is None or run < best):
                        best = run
    axis_min = round(best, 6) if best is not None else None
    normal = _face_normal_thickness(shape, spacing_mm)
    candidates = [v for v in (axis_min, normal["min_mm"]) if v is not None]
    return {"min_mm": min(candidates) if candidates else None,
            "axis_min_mm": axis_min, "normal_min_mm": normal["min_mm"],
            "normal_measurement": normal,
            "spacing_mm": spacing_mm, "rays_with_hits": rays,
            "hits": hits, "odd_hit_rays": odd,
            "method": "grid_ray_pairwise（三轴网格射线，进→出配对）"
                      " + face_normal_ray（沿面法向，分类器验材料段）",
            "caveat": "两法各量各的，min_mm 取两者较小：三轴法量的是斜弦（实测 3mm 斜板读成 "
                      "1.00mm，误差两个方向都有）；法向法方向正确但采样比网格稀，"
                      "会漏掉三轴抓到的薄特征。两个数都在读数里，不一致就看得见。"
                      "奇数命中的射线（相切/非流形）只计数不猜；"
                      "法向退化（极点/奇异）与参数域边缘的样本不采。"}


_SEVERITY_LABEL = {"hold": "需制造方确认", "advisory": "建议", "info": "事实"}
_VERDICT_LABEL = {"hold": "阻断", "flag": "告警", "pass": "合格", "info": "只报事实"}


def _markdown(part_name: str, revision: str, report: dict[str, Any]) -> str:
    facts = report["facts"]
    wall = facts["wall_measurement"]
    # 量不出来的写「没量出来」，不写 0（0 会被读成「薄到快没了」而不是「不知道」）
    axis_txt = (f"{wall['axis_min_mm']:g}" if wall["axis_min_mm"] is not None else "没量出来")
    normal_txt = (f"{wall['normal_min_mm']:g}"
                  if wall["normal_min_mm"] is not None else "没量出来")
    lines = [f"# DFM/DFA 分析：{part_name}（Rev {revision}）", "",
             "判据的阈值都带来源（见每条后面的「来处」）；**测不出来的记盲区，不折算成合格**。",
             "", "## 实测几何", "",
             f"- 包络：{facts['envelope_mm'][0]:g} × {facts['envelope_mm'][1]:g} × "
             f"{facts['envelope_mm'][2]:g} mm，体积 {facts['volume_mm3']:g} mm³，"
             f"面 {facts['face_count']} 个",
             f"- 最小壁厚（取两法较小者；三轴网格射线间距 {wall['spacing_mm']:g}mm、"
             f"有命中的射线 {wall['rays_with_hits']} 条、奇数命中 {wall['odd_hit_rays']} 条；"
             f"沿面法向探 {wall['normal_measurement']['samples']} 点、"
             f"可用 {wall['normal_measurement']['samples_usable']} 段、"
             f"每面最多 {wall['normal_measurement']['sample_cap_per_face']}"
             f"×{wall['normal_measurement']['sample_cap_per_face']} 点、"
             f"法向退化跳过 {wall['normal_measurement']['samples_degenerate_normal']} 点。"
             f"三轴 {axis_txt} mm、法向 {normal_txt} mm）："
             + (f"{wall['min_mm']:g} mm" if wall["min_mm"] is not None else "没量出来"),
             f"- {wall['caveat']}",
             "- 孔周最小留肉（孔口圆到最近自由边，相邻孔口边同算一边）："
             + (f"{facts['min_hole_land_mm']:g} mm，量到 "
                f"{facts['hole_land_measurement']['measurable_count']}/"
                f"{facts['hole_land_measurement']['hole_count']} 个整孔"
                if facts["min_hole_land_mm"] is not None else
                f"没量出来（{facts['hole_land_measurement']['hole_count']} 个整孔"
                f"一个都找不到可量的边）"),
             f"- 整孔 {len(facts['holes'])} 个；部分回转圆柱面 "
             f"{facts['partial_cylinder_count']} 个；整周外圆（不计入孔）"
             f"{facts['outer_cylinder_count']} 个；材料 {report['material'] or '未给'}"
             f"（分类：{report['material_class']}）"
             + (f"。**有 {facts['bore_undecided_cylinder_count']} 个整周圆柱面分不出是孔还是外圆**"
                f"（这个形状里读不出实体，只能按最坏情况仍计成孔）"
                if facts["bore_undecided_cylinder_count"] else ""), ""]
    if facts["holes"]:
        lines += ["| 孔 | 直径 mm | 深度 mm | 深径比 |", "|---|---|---|---|"]
        for hole in facts["holes"]:
            lines.append(f"| {_DIA}{hole['diameter_mm']:g} | {hole['diameter_mm']:g} "
                         f"| {hole['depth_mm']:g} | {hole['depth_over_diameter']:g} |")
        lines.append("")
    lines += ["## 逐条判定", ""]
    if not report["findings"]:
        lines.append("- 一条都没判成——下面的规则全在盲区里，这份分析不能读成「没有 DFM 问题」。")
    for item in report["findings"]:
        limit = f"{item['limit']:g}{item['unit']}" if item["limit"] is not None else "不设阈值"
        lines.append(f"- **{item['name']}**：{_VERDICT_LABEL[item['verdict']]}｜"
                     f"实测 {item['value']:g}{item['unit']} vs 阈值 {limit}"
                     f"（{item['measured']}）｜{_SEVERITY_LABEL[item['severity']]}")
        lines.append(f"  - 来处：{item['source']['note']}")
        if item["source"]["url"]:
            extra = ""
            if item["source"].get("stated_for"):
                donor = rule_by_id(item["source"]["stated_for"])
                extra = f"，页内原述是给「{donor['name']}」的"
            lines.append(f"    （{item['source']['url']}，访问 {item['source']['accessed']}，"
                         f"{_KIND_LABEL.get(item['source']['kind'], item['source']['kind'])}"
                         f"{extra}）")
    if report["blind"]:
        lines += ["", "## 盲区（没判的条目与原因）", ""]
        for item in report["blind"]:
            lines.append(f"- {item['name']}（{item['rule']}）：{item['reason']}")
    lines += ["", "## 本次没看的东西", ""] + [f"- {one}" for one in report["not_covered"]]
    lines.append("")
    return "\n".join(lines)


def _as_shape(model: Any) -> Any:
    """把调用方给的东西剥成 TopoDS_Shape：Workplane -> Shape -> wrapped 一层层剥。

    CLI 交来的是 ``cq.importers.importStep()`` 的 **Workplane**，测试里交来的是
    ``.val().wrapped``；两种都得能用，而剥到底还不是形状时**报错**而不是把 Workplane
    塞给 OCP（那会得到一句 incompatible constructor 的库内部话，读者看不出是谁的锅）。
    """
    for _ in range(4):
        if hasattr(model, "wrapped"):
            return model.wrapped
        if hasattr(model, "val"):
            model = model.val()
            continue
        break
    name = type(model).__name__
    if not name.startswith("TopoDS"):
        raise ValueError(f"读不出实体形状（拿到的是 {name}）：没有几何就没有壁厚/孔深可量")
    return model


def generate_dfm_report(out_path: Path | str, *, model: Any, part_name: str,
                        revision: str = "A", material: str | None = None,
                        spec: dict[str, Any] | None = None,
                        spacing_mm: float = DEFAULT_SPACING_MM,
                        provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    """端到端出 DFM/DFA 分析报告：模型 -> 实测事实 -> 判定 -> Markdown + 证据侧车。"""
    path = Path(out_path)
    report = analyze(_as_shape(model), material=material, spec=spec,
                     spacing_mm=spacing_mm)
    text = _markdown(part_name, revision, report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    evidence = {"document": "dfm_report", "part": part_name, "revision": revision,
                "document_path": str(path),
                "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "rulebook": report["rulebook"],
                "material": report["material"],
                "material_class": report["material_class"],
                "facts": report["facts"],
                "findings": report["findings"],
                "blind": report["blind"],
                "counts": {"hold": report["hold_count"], "advisory": report["advisory_count"],
                           "measured": report["measured_rule_count"],
                           "blind": len(report["blind"])},
                "not_covered": report["not_covered"]}
    evidence.update(provenance or {})
    from aipd_os.cad.evidence import sidecar_path

    sidecar = sidecar_path(path)
    sidecar.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    evidence["evidence_file"] = str(sidecar)
    return evidence


# ---------------------------------------------------------------------------
# 二、规则判定
# ---------------------------------------------------------------------------

def _declared_bands(spec: dict[str, Any] | None) -> list[tuple[str, float]]:
    """从图纸 spec 里取每条声明公差的**半带宽绝对值**（不猜、不合名）。"""
    out: list[tuple[str, float]] = []
    for feature in (spec or {}).get("features") or []:
        tolerance = feature.get("tolerance") or {}
        upper, lower = tolerance.get("upper"), tolerance.get("lower")
        if upper is None and lower is None:
            continue
        band = max(abs(float(upper or 0.0)), abs(float(lower or 0.0)))
        out.append((str(feature.get("feature") or "未命名特征"), band))
    return out


def analyze(shape: Any, *, material: str | None = None,
            spec: dict[str, Any] | None = None,
            rules: Sequence[dict[str, Any]] | None = None,
            spacing_mm: float = DEFAULT_SPACING_MM) -> dict[str, Any]:
    """量事实 → 逐条判规则 → 把判不了的分原因记成盲区。

    返回的三块各有各的含义：``findings`` 是**真判过**的结论，``blind`` 是**没判**的条目
    （带原因），``facts`` 是测量原值。三者不重叠：一条规则要么有结论、要么在盲区里。
    """
    active = list(rules) if rules is not None else list(RULES)
    for rule in active:
        _check_source_integrity(rule)

    facts = geometry_facts(shape)
    wall = measure_min_wall_thickness(shape, spacing_mm)
    facts["min_wall_thickness_mm"] = wall["min_mm"]
    facts["wall_measurement"] = wall
    lands = measure_hole_lands(shape)
    facts["min_hole_land_mm"] = lands["min_land_mm"]
    facts["hole_land_measurement"] = lands

    plastic = material_is_plastic(material)
    findings: list[dict[str, Any]] = []
    blind: list[dict[str, Any]] = []
    for rule in active:
        outcome = _judge(rule, facts, plastic, spec)
        if isinstance(outcome, dict) and outcome.get("blind"):
            blind.append({"rule": rule["id"], "reason": outcome["reason"],
                          "name": rule["name"]})
        else:
            findings.append(outcome)
    holds = [f for f in findings if f["verdict"] == "hold"]
    advisories = [f for f in findings if f["verdict"] == "flag"]
    return {
        "facts": facts,
        "findings": findings,
        "blind": blind,
        "hold_count": len(holds),
        "advisory_count": len(advisories),
        "measured_rule_count": len(findings),
        "material": material,
        "material_class": {True: "plastic", False: "metal", None: "unknown"}[plastic],
        "not_covered": list(NOT_COVERED),
        "rulebook": {"version": "2026-09-25", "rule_count": len(active)},
    }


def _judge(rule: dict[str, Any], facts: dict[str, Any], plastic: bool | None,
           spec: dict[str, Any] | None) -> dict[str, Any]:
    """把一条规则套到实测事实上。前提不成立 ⇒ 返回 blind，**不返回 pass**。"""
    base = {"rule": rule["id"], "name": rule["name"], "limit": rule.get("limit"),
            "op": rule["op"], "unit": rule["unit"], "severity": rule["severity"],
            "basis": rule["basis"], "source": rule["source"]}
    if rule["id"] in ("wall_thickness_metal", "wall_thickness_plastic"):
        if plastic is None:
            return {"blind": True, "reason": "material_class_unknown"}
        if facts["min_wall_thickness_mm"] is None:
            return {"blind": True, "reason": "no_probeable_planar_face"}
        wanted = rule["id"] == "wall_thickness_plastic"
        if wanted != plastic:
            return {"blind": True, "reason": "material_is_the_other_class"}
        value = facts["min_wall_thickness_mm"]
        return _verdict(base, value, f"网格射线测得最薄 {value:g}mm",
                        facts["wall_measurement"]["spacing_mm"])
    if rule["id"] in ("hole_depth_to_diameter", "gun_drill_required"):
        if not facts["holes"]:
            return {"blind": True, "reason": "no_full_cylindrical_hole"}
        ratios = [(h, h["depth_over_diameter"]) for h in facts["holes"]
                  if h["depth_over_diameter"] is not None]
        if not ratios:
            # 有整孔但比值量不出（直径为 0 的退化面）：也是盲区，不当「不深」
            return {"blind": True, "reason": "hole_depth_unmeasurable"}
        hole, value = max(ratios, key=lambda c: c[1])
        return _verdict(base, value,
                        f"hole {_DIA}{hole['diameter_mm']:g} \u00d7 深 {hole['depth_mm']:g}")
    if rule["id"] == "inside_radius_reported":
        if facts["inside_radius_mm"] is None:
            return {"blind": True, "reason": "no_partial_cylindrical_face"}
        out = _verdict(base, facts["inside_radius_mm"],
                       f"量出 {facts['partial_cylinder_count']} 个部分回转圆柱面，"
                       f"最小半径 {facts['inside_radius_mm']:g}mm")
        out["verdict"] = "info"
        return out
    if rule["id"] in ("hole_land_reported", "hole_land_metal", "hole_land_plastic"):
        lands = facts["hole_land_measurement"]
        if not lands["holes"]:
            return {"blind": True, "reason": "no_full_cylindrical_hole"}
        if lands["min_land_mm"] is None:
            # 有整孔但一圈都量不到边（孔开在曲面上 / 那个面片除了孔边没有别的边）：
            # 这是量不出来，不是「留肉很足」
            return {"blind": True, "reason": "hole_land_unmeasurable"}
        if rule["id"] == "hole_land_reported":
            out = _verdict(base, lands["min_land_mm"],
                           f"{lands['measurable_count']}/{lands['hole_count']} 个整孔量到留肉，"
                           f"最小 {lands['min_land_mm']:g}mm")
            out["verdict"] = "info"
            return out
        if plastic is None:
            return {"blind": True, "reason": "material_class_unknown"}
        wanted = rule["id"] == "hole_land_plastic"
        if wanted != plastic:
            return {"blind": True, "reason": "material_is_the_other_class"}
        return _verdict(base, lands["min_land_mm"],
                        f"孔口到最近自由边留肉 {lands['min_land_mm']:g}mm")
    if rule["id"] == "same_axis_hole_count":
        if not facts["coaxial_groups"]:
            return {"blind": True, "reason": "no_full_cylindrical_hole"}
        biggest = max(facts["coaxial_groups"], key=lambda g: g["hole_count"])
        out = _verdict(base, biggest["hole_count"],
                       "、".join(f"{_DIA}{d:g}" for d in biggest["diameter_mm"]))
        out["verdict"] = "info"
        return out
    if rule["id"] == "tolerance_below_achievable":
        bands = _declared_bands(spec)
        if not bands:
            return {"blind": True, "reason": "no_declared_tolerance"}
        feature, value = min(bands, key=lambda b: b[1])   # 最严的那条声明
        return _verdict(base, value, feature)
    return {"blind": True, "reason": "rule_not_implemented"}


def _verdict(base: dict[str, Any], value: float, measured: str,
             extra: float | None = None) -> dict[str, Any]:
    out = dict(base)
    out.update({"measured": measured, "value": round(float(value), 6)})
    if extra is not None:
        out["sampling_spacing_mm"] = extra
    if base["op"] == "report" or base["limit"] is None:
        out["verdict"] = "info"
    else:
        violated = value > base["limit"] if base["op"] == ">" else value < base["limit"]
        out["verdict"] = "hold" if (violated and base["severity"] == "hold") else (
            "flag" if violated else "pass")
    return out
