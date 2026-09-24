"""装配图：多零件逐个投影 + 序号球标 + 明细表（capability ``cad.2d_drawings``）。

三条不可让的规矩，都能机器核：

1. **逐个投影再叠加，不合成一次投影。** 本机实测：两个 20×20×8 盒子，单盒 24 条
   raw edge、合成 compound 48 条（``TopExp_Explorer(EDGE)``），``classify_view`` 投出
   8 条 vs 16 条折线——几何上一次投得完、条数也正好翻倍，但 ``detect_circles`` 会把两件的
   孔全局混编号、``_bbox`` 变成合并包络、``_coincident`` 会把「A 的轮廓压住 B 的那条边」
   判成不存在。逐件投影让每条线**天然知道自己属于谁**，不需要事后聚类猜。
2. **球标编号只来自 manifest 的 ``balloon``。** 与 FreeCAD TechDraw 的
   ``DrawViewBalloon`` 同一语义——气泡内容是作者设的 ``Text`` 属性
   （``src/Mod/TechDraw/App/DrawViewBalloon.cpp:67`` "The text to be displayed"），
   箭头落点 ``OriginX/OriginY`` 也是作者指的（同文件 51-54 行注释），上游没有任何
   从遍历顺序发号的机制。缺号、重号、写 0、零件重名、
   STEP 不存在一律 ``ValueError``（CLI 层是 rc=2），不按遍历顺序发号——
   顺序发号等于图纸在声称一个作者从没说过的编号。
3. **挂点是量出来的。** 引线终点取该零件在该视图里已投影折线的**质心**，
   所以「这条引线指的是这个零件」是可复核的几何事实，不是排版巧合。

明细表用 ``ezdxf.addons.tablepainter.TablePainter``（本机实测：``text_cell`` +
``render(msp)`` 产出 TEXT+LINE，落在 TABLECONTENT / TABLEGRID 两层）。
**不用** DXF 原生 TABLE 实体：本仓锁定的 ezdxf 1.4.2 没有表实体的写作 API
（``Modelspace.add_table`` 不存在，``ezdxf.entities`` 里没有 ``Table`` 类）。

球标↔BOM **已经**交叉核对（``bind_bom``）：对应关系只认 manifest 里作者声明的
``bom_item``，**不按零件名字自动映射**；数量、单位、材料与工艺一律取自 BOM 行（解析器不读
manifest 的 ``quantity``/``material``/``process``），绑不上/歧义/没声明/BOM 多出行都判未收口，
绑不上留空不折算成 0、材料与工艺留空不写占位符，两格各自独立不许互相顶。
``BomLine.process`` 是**明细表那一格要的那道主工艺**，不是工序路线：本仓不建 operations
表（成熟实现把多工序建成独立对象——Dynamics 365 BC 的 BOM 行只带 Routing Link Code、
ERPNext v15 用子表 BOM Operation），所以这里不承载顺序、工时与工序成本。
**供应商（``BomLine.supplier``）刻意不进明细表**——这是裁决不是漏做：明细表随图纸版本
冻结，而供应商是商务事实（本仓契约把它归在「供应链开发清单」，BOM 侧也只叫「候选供应商」，
见 ``references/deliverable-contracts.md``），把供应商印到受控技术文件上等于让图纸携带
一个未取证就绪的采购承诺。要改这条需要先给理由，别当默认值。
爆炸视图**已经**能做，但位移**一律由作者声明**（manifest 的 ``explode``）：文献里的自动
求法（JCAD《智能装配规划中的拆卸方向计算》）要对装配约束做离散球面搜索、并为一件零件
找到一条**无碰撞路径**才定全局拆卸方向，而本仓两样前提都没有（没有约束数据，也不做实体
求交），硬算等于画一张没证过的拆卸顺序。缺声明就拒绝出图，不画摆开一半的爆炸图。
明确**未实现**（不要当成已具备）：干涉/碰撞检查（只报**包络投影重叠**面积，不是实体求交）；
装配约束/配合；爆炸位移的自动求解；多工序工艺路线（一格一个字符串，工序成本/工时无处安放）；
同一 item 在 BOM 里出现多行时判歧义而不是合并（本仓还没有合并口径，就不猜）。
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

BALLOON_RADIUS = 4.0          # 球标圆半径（视图局部坐标，随比例缩放前）
BALLOON_COLUMN_GAP = 15.0     # 球标列相对装配包络右沿的外移
BALLOON_ROW_SPACING = 12.0    # 相邻球标的纵向间距（够放一格编号）
BALLOON_TEXT_HEIGHT = 3.5
TABLE_CELL_W = 34.0
TABLE_CELL_H = 7.0
TABLE_TEXT_HEIGHT = 2.8
_ENVELOP_KEYS = ("envelope_width", "envelope_height")


def parse_assembly_manifest(path: str | Path) -> list[dict[str, Any]]:
    """读装配 manifest 并校验声明；**不合规一律抛错**，不修数据、不发号。

    ``{"parts": [{"name": "支架", "step": "parts/a.step", "balloon": 1,
                  "offset": [0, 45, 0]}]}``；``step`` 相对 manifest 所在目录解析。
    """
    file = Path(path)
    if not file.is_file():
        raise ValueError(f"装配清单不存在：{file}")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"装配清单不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("parts"), list):
        raise ValueError('装配清单顶层必须是 {"parts": [...]}，'
                         f'实得 {str(data)[:80]}')
    if not data["parts"]:
        raise ValueError("装配清单里一个零件都没有：那就不是装配图")
    out: list[dict[str, Any]] = []
    names: set[str] = set()
    numbers: set[int] = set()
    for raw in data["parts"]:
        if not isinstance(raw, dict):
            raise ValueError(f"parts 每一项都得是对象，实得 {raw!r}")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError("零件必须有非空 name（球标与明细表都靠它认人）")
        if name in names:
            raise ValueError(f"零件名重复：{name}；同名零件在一张装配图上无法区分")
        names.add(name)
        if "balloon" not in raw:
            raise ValueError(f"零件 {name} 没写 balloon 序号；"
                             "序号由作者声明，本模块不按遍历顺序代发")
        number = raw["balloon"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise ValueError(f"零件 {name} 的 balloon 必须是正整数（球标编号），实得 {number!r}")
        if number in numbers:
            raise ValueError(f"球标序号重复：{number}（两个零件不能共用一个序号）")
        numbers.add(number)
        step_raw = str(raw.get("step") or "").strip()
        if not step_raw:
            raise ValueError(f"零件 {name} 没写 step（STEP 路径）")
        step = Path(step_raw)
        if not step.is_absolute():
            step = (file.parent / step).resolve()
        if not step.is_file():
            raise ValueError(f"零件 {name} 的 STEP 文件不存在：{step}")
        offset = raw.get("offset", [0.0, 0.0, 0.0])
        if not isinstance(offset, (list, tuple)) or len(offset) != 3:
            raise ValueError(f"零件 {name} 的 offset 必须是三个数 [x,y,z]，实得 {offset!r}")
        try:
            vec = [float(v) for v in offset]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"零件 {name} 的 offset 都得是数：{offset!r}") from exc
        out.append({"name": name, "step": str(step), "balloon": int(number),
                    "offset": vec, "bom_item": _bom_item(raw, name),
                    "explode": _explode(raw, name)})
    return out


def _explode(raw: dict[str, Any], name: str) -> list[float] | None:
    """作者声明的爆炸位移；没写就是 ``None``，**不折成 [0,0,0]**。

    两者在图上同形（都在原位），含义完全不同：一个是「这一件不参与爆炸」，
    一个是「我还没说它该去哪」。位移不算本模块的活——自动求拆卸方向要有装配约束与
    无碰撞路径校验两样前提，本仓都没有（模块 docstring 与文件头写了），所以外推
    等于画一张没证过的拆卸顺序。
    """
    if "explode" not in raw:
        return None
    value = raw["explode"]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"零件 {name} 的 explode 必须是三个数 [x,y,z]（沿哪个方向移多远"
                         f"由你说），实得 {value!r}")
    try:
        vec = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"零件 {name} 的 explode 都得是数：{value!r}") from exc
    return vec


def _bom_item(raw: dict[str, Any], name: str) -> str | None:
    """作者声明的 BOM 行标识；没写就是 ``None``，**不会**拿零件名去找行。

    manifest 里的 ``quantity`` 一类字段一律不解析：数量的权威在 BOM 行上。
    """
    if "bom_item" not in raw:
        return None
    value = raw["bom_item"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"零件 {name} 的 bom_item 必须是非空字符串（要绑哪一行由你说），"
                         f"实得 {value!r}")
    return value.strip()


def _translate(shape: Any, offset: list[float]) -> Any:
    """按 manifest 的偏移摆放零件（真做刚体平移，不是把坐标手工加起来）。"""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec

    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(offset[0], offset[1], offset[2]))
    made = BRepBuilderAPI_Transform(shape, trsf, True)
    return made.Shape()


def load_assembly_parts(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐个读 STEP：读不到就点名，绝不静默少画一个零件。"""
    import cadquery as cq

    out: list[dict[str, Any]] = []
    for spec in specs:
        step = Path(spec["step"])
        entry = dict(spec)
        entry["step_sha256"] = hashlib.sha256(step.read_bytes()).hexdigest()
        try:
            imported = cq.importers.importStep(str(step))
            solids: list[Any] = imported.solids().vals()
        except Exception as exc:
            raise ValueError(f"零件 {spec['name']} 的 STEP 读不出来："
                             f"{type(exc).__name__}: {exc}") from exc
        if not solids:
            entry["shape"] = None
            entry["empty_reason"] = (f"零件 {spec['name']} 的 {step.name} 里没有任何实体"
                                     f"（球标无处可挂，明细表照列但不画几何）")
            out.append(entry)
            continue
        compound = cq.Compound.makeCompound(solids)
        entry["shape"] = _translate(compound.wrapped, spec["offset"])
        entry["solid_count"] = len(solids)
        out.append(entry)
    return out


def _polyline_centroid(polys: list[list[tuple[float, float]]]) -> tuple[float, float]:
    """按**线段长度加权**的折线质心；按顶点平均会让长边少算、短边多算。"""
    sx = sy = wsum = 0.0
    for poly in polys:
        for i in range(len(poly) - 1):
            x1, y1 = poly[i]
            x2, y2 = poly[i + 1]
            if (x1, y1) == (x2, y2):
                continue
            w = math.hypot(x2 - x1, y2 - y1)
            sx += 0.5 * (x1 + x2) * w
            sy += 0.5 * (y1 + y2) * w
            wsum += w
    if wsum <= 0.0:
        pts = [p for poly in polys for p in poly]
        if not pts:
            return (0.0, 0.0)
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return (sx / wsum, sy / wsum)


def _rect_overlap(a: list[float], b: list[float]) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0.0 and dy > 0.0 else 0.0


def build_assembly_view(parts: list[dict[str, Any]], view_name: str,
                        direction: tuple[float, float, float],
                        up: tuple[float, float, float],
                        with_balloons: bool = True,
                        explode: bool = False) -> Any:
    """逐件投影 → 叠成一张装配视图，并算出球标、包络与包络投影重叠。

    ``with_balloons=False`` 用于副视图：一套编号在每个投影方向都圈一遍是重复标注，
    装配图惯例是**只在一个视图上标球标**（这里是第一个请求的方向）。
    ``explode=True`` 时按每个零件**声明**的 ``explode`` 位移把它摆开：平行投影下
    「先平移实体再投影」与「投影后在视图里平移折线」逐位等价（每件各自做 HLR，
    件与件之间不互相遮挡），所以这里走后者——省一次内核投影，且不引入新的几何假设。
    零件沿视线方向摆开时在这个视图上**看不出分离**，那是告警不是错误（图没错，
    但读者得不到信息，换一个视图看）。
    """
    from aipd_os.cad.drawings2d import ViewGeometry, _bbox, classify_view, view_basis

    per_part: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    all_polys: list[list[tuple[float, float]]] = []
    connectors: list[dict[str, Any]] = []
    issues: list[str] = []
    for part in parts:
        name = str(part["name"])
        if part.get("shape") is None:
            issues.append(str(part.get("empty_reason") or f"零件 {name} 没有几何"))
            continue
        shift = part.get("explode")
        if explode and not shift:
            raise ValueError(f"零件 {name} 没声明 explode 位移：爆炸视图里它该摆去哪无从可知")
        basis = view_basis(direction, up)
        vis, hid = classify_view(part["shape"], basis)
        assembled = [round(v, 6) for v in _polyline_centroid(vis)]
        if shift and explode:
            dx = _dot3(shift, basis["right"])
            dy = _dot3(shift, basis["up"])
            vis = [[(x + dx, y + dy) for x, y in poly] for poly in vis]
            hid = [[(x + dx, y + dy) for x, y in poly] for poly in hid]
        bbox = _bbox(vis + hid)
        centroid = [round(v, 6) for v in _polyline_centroid(vis)]
        per_part.append({"part": name, "balloon": int(part["balloon"]),
                         "bbox": [round(b, 6) for b in bbox],
                         "visible_polylines": len(vis), "hidden_polylines": len(hid),
                         "centroid": centroid, "assembled_centroid": assembled,
                         "explode": list(shift) if shift else None})
        if explode:
            # 一件一条：两头一个是装配位、一个是爆炸位，读者才知道它是从哪儿摆开的
            connectors.append({"part": name, "balloon": int(part["balloon"]),
                               "from": assembled, "to": centroid})
        for poly in vis:
            segments.append({"part": name, "kind": "visible"})
            all_polys.append(poly)
        for poly in hid:
            segments.append({"part": name, "kind": "hidden"})
            all_polys.append(poly)

    envelope = list(_bbox(all_polys))
    overlap = 0.0
    for i, one in enumerate(per_part):
        for other in per_part[i + 1:]:
            overlap += _rect_overlap(one["bbox"], other["bbox"])

    balloons: list[dict[str, Any]] = []
    column_x = envelope[2] + BALLOON_COLUMN_GAP if per_part else 0.0
    numbered = sorted(per_part, key=lambda p: p["balloon"]) if with_balloons else []
    for slot, one in enumerate(numbered):
        anchor = tuple(one["centroid"])
        y = envelope[3] - slot * BALLOON_ROW_SPACING
        dx, dy = anchor[0] - column_x, anchor[1] - y
        length = math.hypot(dx, dy)
        # 引线从**圆圈边上**起笔（离球标心 R），不是离挂点 R——写反了会得到一条
        # 从挂点附近开始的短线，位移看着对、圈与线却不挨着（用例 rim 判据抓到的就是它）
        lead = ((column_x + dx * (BALLOON_RADIUS / length) if length else column_x),
                (y + dy * (BALLOON_RADIUS / length)) if length else y)
        balloons.append({"number": one["balloon"], "part": one["part"],
                         "anchor": [round(anchor[0], 6), round(anchor[1], 6)],
                         "x": round(column_x, 6), "y": round(y, 6),
                         "leader_start": [round(lead[0], 6), round(lead[1], 6)]})

    # 两个球标指向同一个投影点 = 读图的人分不出归属。几何上没错（零件确实沿投影
    # 方向叠着），所以不升格成未收口，也不擅自换作者点的视图——只把话说明。
    anchor_warnings: list[str] = []
    by_anchor: dict[tuple[float, float], list[str]] = {}
    for one in balloons:
        by_anchor.setdefault((one["anchor"][0], one["anchor"][1]), []).append(one["part"])
    for spot, owners in sorted(by_anchor.items()):
        if len(owners) > 1:
            anchor_warnings.append(
                f"{view_name}：球标 {'、'.join(sorted(owners))} 落在视图上的同一个位置 "
                f"({spot[0]:g}, {spot[1]:g})——零件沿投影方向叠着，图上指不出各是谁；"
                f"换一个能分开零件的视图当球标视图（--views 的第一个）")

    view = ViewGeometry(name=view_name, direction=direction, up=up,
                        visible=all_polys, hidden=[],
                        bbox=(envelope[0], envelope[1], envelope[2], envelope[3]))
    view.dimensions = [
        {"kind": "envelope", "feature": f"{view_name}.{key}",
         "value": round(envelope[2] - envelope[0] if key == _ENVELOP_KEYS[0]
                        else envelope[3] - envelope[1], 3),
         "unit": "mm", "tolerance": None,
         "source": "union bbox of placed parts (projected geometry)"}
        for key in _ENVELOP_KEYS]
    if explode and connectors:
        still = [c for c in connectors
                 if math.dist(c["from"], c["to"]) < 1e-6]
        if len(still) == len(connectors):
            anchor_warnings.append(
                f"{view_name}：所有爆炸位移都与视线平行，这个视图上看不出分离"
                "（图没错，但爆炸要换一个能看出摆开的视图）")
    view.assembly = {"parts": per_part, "segments": segments, "balloons": balloons,
                     "exploded": bool(explode), "connectors": connectors,
                     # 明写「本视图是不是编号视图」：否则 balloons=[] 既可能是作者
                     # 只标一个视图的惯例，也可能是发号这一步出了问题，读证据的人分不出
                     "balloon_view": bool(with_balloons),
                     "envelope": [round(v, 6) for v in envelope],
                     "overlap_area_mm2": round(overlap, 6),
                     "warnings": anchor_warnings
                     + _overlap_messages(view_name, per_part),
                     "issues": issues}
    # 球标这一层由图纸侧在排完图线后用**同一个 place** 回调；挂函数而不是让
    # drawings2d import 本模块，是为了保持依赖单向（装配 → 图纸）。
    view.render_overlay = render_assembly
    return view


def _dot3(vec: Sequence[float], axis: tuple[float, float, float]) -> float:
    """三维向量在视图基轴上的分量（= 平移量投到这个视图的 2D 位移）。"""
    return float(vec[0]) * axis[0] + float(vec[1]) * axis[1] + float(vec[2]) * axis[2]


def _bom_text(line: Any, name: str) -> str | None:
    """取 BOM 行上的一个自由文本事实（材料 / 工艺）：空白串按「没填」处理。

    两个字段与数量**同一个权威、同一个绑定结果**——``bom_item`` 没声明、找不到、或有歧义，
    这里就是 ``None``，明细表那一格留空。不写 ``"-"`` 也不写「未指定」：占位符会被读成
    「图上确实有这么一个值」，而 C6（``references/production-cad-deliverables.md``）要的是
    能落到每一行的材料**与工艺**事实。两条各填各的格子，**不许互相顶**：
    拿工艺凑材料（或反过来）会把真正缺的那一半盖住。
    """
    value = getattr(line, name) or ""
    return value.strip() or None


def bind_bom(parts: list[dict[str, Any]],
             lines: Sequence[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """按作者声明的 ``bom_item`` 把球标绑到 BOM 行上；数量与单位一律**取自 BOM**。

    对应关系是声明出来的，不是匹配出来的：没写 ``bom_item`` 的零件不会因为名字恰好
    等于某个 item 就算对上（与 ``drawing spec`` 不按名字自动映射同一条纪律——名字相似
    不等于同一个东西）。标识归一用 ``bom.models.norm_item``（strip+lower 全等），
    与 ``supply_chain/impact`` 同一处定义，两边不会各自漂。

    两头都要闭合：球标有号而 BOM 找不到 ⇒ 未收口；BOM 有行而图上没号 ⇒ 也是未收口。
    绑不上就留空（``None``），**不折算成 0**——图纸上 0 与「没核到」差一个量级。
    第 15 片起 ``material``、第 16 片起 ``process`` 走同一条绑定：值只来自绑上的那一行
    ``BomLine.material`` / ``BomLine.process``，绑不上或那行没填都是 ``None``，两格各自独立
    不互相顶。``supplier`` 一律不取（明细表与采购清单的边界，理由写在模块 docstring）。
    """
    from aipd_os.bom.models import norm_item

    by_item: dict[str, list[Any]] = {}
    for line in lines:
        by_item.setdefault(norm_item(line.item), []).append(line)

    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    used: set[str] = set()
    for part in sorted(parts, key=lambda p: p["balloon"]):
        declared = part.get("bom_item")
        row: dict[str, Any] = {"item": int(part["balloon"]), "part": str(part["name"]),
                               "bom_item": declared, "bom_line_id": None,
                               "qty": None, "unit": None, "material": None,
                               "process": None}
        if declared is None:
            issues.append(f"零件 {part['name']}（球标 {row['item']}）未声明 bom_item："
                          "明细表这一行不印数量，也不拿零件名字去 BOM 里猜一行")
        else:
            matches = by_item.get(norm_item(declared), [])
            if not matches:
                issues.append(f"球标 {row['item']}（{part['name']}）声明的 BOM 行 "
                              f"{declared!r} 在 BOM 里找不到：数量留空，"
                              "不拿 0 或别的行冒充")
            elif len(matches) > 1:
                ids = ", ".join(sorted(str(m.line_id) for m in matches))
                issues.append(f"球标 {row['item']} 声明的 {declared!r} 在 BOM 里有 "
                              f"{len(matches)} 行（{ids}）：歧义，随便取一行就是猜数量")
            else:
                line = matches[0]
                row.update({"bom_line_id": line.line_id,
                            "qty": float(line.quantity), "unit": line.unit,
                            "material": _bom_text(line, "material"),
                            "process": _bom_text(line, "process")})
                used.add(line.line_id)
        rows.append(row)

    for group in by_item.values():
        for line in group:
            if line.line_id not in used:
                issues.append(f"BOM 行 {line.item!r}（{line.line_id}，数量 "
                              f"{line.quantity:g} {line.unit}）在图上没有球标指它："
                              "这张装配图漏了零件")
    return rows, issues


def parts_list_rows(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """明细表行：**只印 manifest 声明的东西**。数量/材料由 BOM 提供，未绑定就不印。"""
    return [{"item": int(p["balloon"]), "part": str(p["name"])}
            for p in sorted(parts, key=lambda q: q["balloon"])]


def _overlap_messages(view_name: str, parts: list[dict[str, Any]]) -> list[str]:
    """包络两两投影重叠的告警文案。

    措辞刻意说「包络投影重叠」而不是「干涉」：这里没有做实体求交，
    说干涉就是越过判据下结论。它也不是未收口——图纸能交付，只是叠着的地方看不出前后。
    在 ``build_assembly_view`` 里就算好、随视图带着走，是为了让 ``drawings2d``
    不必 import 本模块（那条反向边会被 ``tests/test_import_cycles.py`` 判成环）。
    """
    out: list[str] = []
    for i, one in enumerate(parts):
        for other in parts[i + 1:]:
            area = _rect_overlap(one["bbox"], other["bbox"])
            if area > 0.0:
                out.append(f"{view_name}：零件 {one['part']} 与 {other['part']} 的"
                           f"包络投影重叠 {area:.3f}mm²（不是干涉判定：本轮不做实体求交，"
                           f"只说明图上这两处叠在一起、看不出前后）")
    return out


def draw_parts_list(msp: Any, rows: list[dict[str, Any]], sheet_wh: tuple[float, float],
                    bom: dict[str, Any] | None) -> dict[str, Any]:
    """用 ezdxf 自带的 TablePainter 把明细表画到图纸上；返回可核验的表体信息。

    位置固定在**图框内左下角**（离框 ``MARGIN + 10``），因为标题栏占右下角、视图行
    从上往下排；表体向下长的方向是实测出来的（见下）。
    ``bom`` 是「这张表的权威接到哪张 BOM」的声明：给了就多印 QTY/UNIT/MATERIAL/PROCESS
    四列，不给就维持 ITEM/PART 两列。这四列**在不在**只看权威接没接上，不看那一格有没有
    值——「全部行都没材料」恰恰是最需要看得见的一格，用「有值才长列」的写法它会整列消失。
    """
    from ezdxf.addons.tablepainter import TablePainter

    from aipd_os.cad.drawings2d import MARGIN

    columns = ["ITEM", "PART"]
    if bom is not None:
        columns += ["QTY", "UNIT", "MATERIAL", "PROCESS"]
    painter = TablePainter((0.0, 0.0), nrows=len(rows) + 1, ncols=len(columns),
                           cell_width=TABLE_CELL_W, cell_height=TABLE_CELL_H)
    for col, title in enumerate(columns):
        painter.text_cell(0, col, title)
    for i, row in enumerate(rows, start=1):
        painter.text_cell(i, 0, str(row["item"]))
        painter.text_cell(i, 1, str(row["part"]))
        if "QTY" in columns:
            # 绑不上就留空：图纸上「没核到」与「数量为 0」差一个量级，不能都写成 0
            painter.text_cell(i, 2, "" if row.get("qty") is None
                              else f"{row['qty']:g}")
            painter.text_cell(i, 3, row.get("unit") or "")
            # 材料与工艺同一留空规矩：没有就空着，不写 "-"（占位符会被读成一个值）
            painter.text_cell(i, 4, row.get("material") or "")
            painter.text_cell(i, 5, row.get("process") or "")
    width, height = painter.table_width, painter.table_height
    insert = (MARGIN + 10.0, MARGIN + 10.0 + height)
    painter.render(msp, insert)
    # 实测画法：insert 是**左上角**，表体向下长（x: insert→insert+width，
    # y: insert-height→insert），bbox 按这个方向写才不会把表说成在图纸别处。
    return {"columns": columns, "rows": rows,
            "rendered_by": "ezdxf.addons.tablepainter",
            "insert": [round(insert[0], 6), round(insert[1], 6)],
            "bbox": [round(insert[0], 6), round(insert[1] - height, 6),
                     round(insert[0] + width, 6), round(insert[1], 6)],
            "bom_bound": bom is not None}


def render_assembly(msp: Any, view: Any, scale: float, place: Any = None) -> None:
    """把一个装配视图的球标画到图纸上：圆圈 + 编号 + 引线（挂在实测质心上）。

    ``view.assembly`` 里的坐标都是**视图局部坐标**，与 ``ViewGeometry`` 同一套；
    ``place`` 由 ``_draw_view`` 传入，所以球标与图线走**同一个**变换——
    自己再算一遍偏移就会出现「图线在视图里、球标飞到图纸原点」这种错。
    ``place=None`` 用于单元测试：直接按视图局部坐标画，坐标可与证据逐位对上。
    """
    data = getattr(view, "assembly", None) or {}
    if place is None:
        def place(poly):
            return list(poly)
    attribs = {"layer": "BALLOON", "color": 4}

    for one in data.get("connectors") or []:
        start = place([(float(one["from"][0]), float(one["from"][1]))])[0]
        end = place([(float(one["to"][0]), float(one["to"][1]))])[0]
        msp.add_line(start, end, dxfattribs={"layer": "EXPLODE", "color": 8,
                                             "linetype": "DASHED"})

    for one in data.get("balloons") or []:
        centre = place([(float(one["x"]), float(one["y"]))])[0]
        anchor = place([(float(one["anchor"][0]), float(one["anchor"][1]))])[0]
        start = place([(float(one["leader_start"][0]),
                        float(one["leader_start"][1]))])[0]
        msp.add_line(start, anchor, dxfattribs=attribs)
        msp.add_circle(centre, BALLOON_RADIUS * scale, dxfattribs=attribs)
        msp.add_text(str(one["number"]),
                     dxfattribs={"layer": "BALLOON", "color": 4,
                                 "height": BALLOON_TEXT_HEIGHT * scale}) \
           .set_placement((centre[0] - BALLOON_TEXT_HEIGHT * scale * 0.35,
                           centre[1] - BALLOON_TEXT_HEIGHT * scale * 0.35))


def generate_assembly_drawing(out_path: Path | str, *, manifest: str, part_name: str,
                              revision: str = "A",
                              views: tuple[str, ...] = ("FRONT", "TOP"),
                              scale: float = 1.0, material: str = "-",
                              sheet: str = "A3",
                              provenance: dict[str, Any] | None = None,
                              bom_lines: Sequence[Any] | None = None,
                              explode: bool = False) -> dict[str, Any]:
    """端到端出装配图：清单 -> 逐件投影 -> DXF -> 证据字典。

    放在装配这一侧、由它 import 图纸模块，而不是在 ``generate_drawing`` 里加分支：
    反向依赖会被无环门判红（``tests/test_import_cycles.py``）。
    派生视图（剖视、局部放大）在这里**明确拒绝**，而不是默默产出错的图——
    装配视图的折线按零件归属，裁剪/切割会把归属打散，球标就成了指错零件的假标注。

    ``bom_lines`` 给就交叉核对并给明细表加 QTY/UNIT 两列；不给就维持第 12 片的形状
    （只有 ITEM/PART，一个数量都不印）。
    """
    from aipd_os.cad.drawings2d import STANDARD_VIEWS, _finish_evidence, write_dxf

    for name in views:
        if name not in STANDARD_VIEWS:
            raise ValueError(f"未知视图 {name}；可用：{sorted(STANDARD_VIEWS)}")
    path = Path(out_path)
    parts = load_assembly_parts(parse_assembly_manifest(manifest))
    if explode:
        missing = sorted(str(p["name"]) for p in parts if not p.get("explode"))
        if missing:
            raise ValueError(
                "爆炸视图要求每个零件都声明 explode 位移；缺的是：" + "、".join(missing)
                + "。摆开一半的爆炸图会让读者把「没动」当成「就该在那儿」——"
                  "那是图纸在替作者说一个他没说的装配顺序")

    rows = parts_list_rows(parts)
    binding_issues: list[str] = []
    bom_evidence: dict[str, Any] | None = None
    if bom_lines is not None:
        rows, binding_issues = bind_bom(parts, list(bom_lines))
        bom_ids = sorted({str(line.bom_id) for line in bom_lines})
        bom_evidence = {"bom_id": bom_ids[0] if len(bom_ids) == 1 else None,
                        "bom_ids": bom_ids, "lines": len(bom_lines)}

    def layout(msp: Any, sheet_wh: tuple[float, float]) -> dict[str, Any]:
        """图纸侧的唯一装配入口：画明细表，并把装配证据交回去。"""
        return {"parts_list": draw_parts_list(msp, rows, sheet_wh, bom_evidence)}

    built = [build_assembly_view(parts, f"ASSY_{name}", *STANDARD_VIEWS[name],
                                 with_balloons=(idx == 0), explode=explode)
             for idx, name in enumerate(views)]
    evidence = write_dxf(built, path, part_name=part_name, revision=revision,
                         scale=scale, material=material, sheet=sheet,
                         provenance=provenance, layout_hook=layout,
                         extra_evidence={"assembly": {
                             "parts": [{k: v for k, v in p.items() if k != "shape"}
                                       for p in parts]},
                             "bom": bom_evidence})
    # 绑定问题与投影问题记在同一个笼子里：都是「这张图还不能交」，
    # 但来源不同，所以文案各自点名（找不到行 / 歧义 / 没声明 / 图上漏了零件）
    evidence["assembly_issues"] = sorted(set(evidence["assembly_issues"])
                                         | set(binding_issues))
    return _finish_evidence(path, evidence, part_name, revision, provenance)
