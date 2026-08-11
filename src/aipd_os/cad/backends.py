"""可替换的 CAD 后端适配器契约与实现。

``CadBackend`` 是抽象接口，定义：加载原生模型、列出可编辑参数、编辑参数、
重新生成、导出 STEP、导出原生文件、几何有效性检查、工具版本、产物哈希、
成熟度上限。所有生产 CAD 后端都应实现该接口。

实现：
* ``CadQueryBackend`` —— 真实可编辑参数化 B-Rep 内核（CadQuery/OpenCASCADE）。
  仅当 ``cadquery`` 已安装时才可用；否则 ``capability_status()`` 返回
  ``external_dependency``，绝不伪装成已完整实现。
* ``ContractBackend`` —— 无真实内核时的确定性本地适配器。它管理参数化模型
  的契约（参数增删改、重新生成、几何有效性），但**只能产出小平面(faceted)
  临时产物**，成熟度上限诚实封顶为 C1，并把 C2 标记为 ``external_dependency``，
  直到配置了真实参数化内核。

诚实性约束：没有真实内核时，C2 及以上的原生 B-Rep 能力必须标记为
``external_dependency`` 或 ``not_implemented``，faceted 运行时永远无法达到
C2（上限为 C1）。
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from aipd_os.cad.evidence import make_artifact_record, sha256_file
from aipd_os.cad.maturity import (
    EXTERNAL_DEPENDENCY,
    FULL,
)

# 可选的真实内核；缺失时 CadQueryBackend 不可用。
try:  # pragma: no cover - 取决于环境是否安装 cadquery
    import cadquery as _cq  # type: ignore  # noqa: F401
    _CADQUERY_AVAILABLE = True
except Exception:  # pragma: no cover
    _cq = None  # type: ignore
    _CADQUERY_AVAILABLE = False


class CadBackend(ABC):
    """CAD 后端抽象接口。"""

    # ---- 元信息 ----
    @property
    @abstractmethod
    def name(self) -> str:
        """后端标识，如 'cadquery' / 'contract-backend'。"""

    @abstractmethod
    def tool_version(self) -> str:
        """返回工具/内核版本字符串；不可用时返回 'n/a'。"""

    @abstractmethod
    def maturity_ceiling(self) -> str:
        """返回诚实的能力成熟度上限（如 'C1' / 'C2'）。"""

    @abstractmethod
    def capability_status(self) -> str:
        """返回 'full' | 'external_dependency' | 'not_implemented'。"""

    @abstractmethod
    def is_available(self) -> bool:
        """返回后端当前是否可用（真实内核已配置）。"""

    # ---- 模型加载 / 参数 ----
    @abstractmethod
    def load_native_model(self, path: Optional[Path]) -> Any:
        """加载原生模型；无真实内核时可加载参数化契约表示。"""

    @abstractmethod
    def list_parameters(self, model: Any) -> List[Dict[str, Any]]:
        """列出可编辑参数，每项含 name / value / unit。"""

    @abstractmethod
    def edit_parameter(self, model: Any, name: str, value: Any) -> Any:
        """编辑单个参数，返回新模型（不改动原模型）。"""

    @abstractmethod
    def regenerate(self, model: Any) -> Any:
        """按当前参数重新生成派生几何，返回新模型。"""

    # ---- 导出 ----
    @abstractmethod
    def export_step(self, model: Any, path: Path) -> Dict[str, Any]:
        """导出 STEP 文件，返回产物证据记录。"""

    @abstractmethod
    def export_native(self, model: Any, path: Path) -> Dict[str, Any]:
        """导出原生格式文件，返回产物证据记录。"""

    # ---- 几何与校验 ----
    @abstractmethod
    def geometry_validity_check(self, model: Any) -> Dict[str, Any]:
        """执行几何有效性检查，返回 {valid, errors, checks}。"""

    def artifact_hash(self, path: Path) -> str:
        """产物 sha256 哈希。"""
        return sha256_file(path)

    def describe(self) -> Dict[str, Any]:
        """返回后端能力描述（诚实性契约的核心）。"""
        return {
            'backend': self.name,
            'tool_version': self.tool_version(),
            'maturity_ceiling': self.maturity_ceiling(),
            'capability_status': self.capability_status(),
            'available': self.is_available(),
        }


# ---------------------------------------------------------------------------
# 小平面临时 STEP 写入（仅用于无真实内核的临时产物，成熟度上限 C1）
# ---------------------------------------------------------------------------

def _cube_mesh(size: float) -> Dict[str, Any]:
    h = size / 2.0
    v = [
        (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
        (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
    ]
    f = [
        (0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6),
        (0, 3, 7), (0, 7, 4), (1, 2, 6), (1, 6, 5),
    ]
    return {'name': 'plate', 'vertices': v, 'faces': f}


def _write_faceted_step(mesh: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """写一个最小的小平面 STEP 文件（C1 顶）。"""
    entities: List[str] = []
    name = str(mesh['name']).replace("'", "")
    vrefs: List[int] = []
    for v in mesh['vertices']:
        vrefs.append(len(entities) + 1)
        entities.append('CARTESIAN_POINT(\'\',(' + ','.join(
            f'{float(x):.6f}' for x in v) + '))')
    frefs: List[int] = []
    for tri in mesh['faces']:
        entities.append('POLY_LOOP(\'\',(' + ','.join(
            f'#{vrefs[int(i)]}' for i in tri) + '))')
        loop = len(entities)
        entities.append(f'FACE_OUTER_BOUND(\'\',#{loop},.T.)')
        bound = len(entities)
        frefs.append(len(entities) + 1)
        entities.append(f'FACE(\'\',(#{bound}))')
    entities.append('CLOSED_SHELL(\'\',(' + ','.join(
        f'#{i}' for i in frefs) + '))')
    shell = len(entities)
    entities.append(f'FACETED_BREP(\'{name}\',#{shell})')
    solid = len(entities)
    header = [
        'ISO-10303-21;', 'HEADER;',
        'FILE_DESCRIPTION((\'AIPD faceted temporary\'),\'2;1\');',
        'FILE_SCHEMA((\'CONFIG_CONTROL_DESIGN\'));', 'ENDSEC;', 'DATA;',
    ]
    data = [f'#{i}={e};' for i, e in enumerate(entities, 1)]
    path.write_text('\n'.join(
        header + data + [f'#{solid+1}=FACETED_BREP_WRAP;', 'ENDSEC;', 'END-ISO-10303-21;', '']),
        encoding='ascii')
    return {'entities': len(entities), 'solids': 1, 'faces': len(frefs)}


# ---------------------------------------------------------------------------
# 真实内核后端：CadQuery（可选依赖，缺失时不可用）
# ---------------------------------------------------------------------------

# 黄金参数化模型（CadQuery 原生可编辑 B-Rep）的参数规格。
# 多参数 + 多特征（孔/圆角/倒角），支撑 “改参 -> 重生成 -> STEP/原生源导出
# -> 重载 -> 几何校验 -> 哈希/版本 -> 差异 -> Product Truth 写回” 的完整闭环。
GOLDEN_PARAM_SPEC: Dict[str, Dict[str, Any]] = {
    'length': {'default': 100.0, 'min': 10.0, 'unit': 'mm'},
    'width': {'default': 50.0, 'min': 10.0, 'unit': 'mm'},
    'thickness': {'default': 10.0, 'min': 2.0, 'unit': 'mm'},
    'hole_diameter': {'default': 8.0, 'min': 1.0, 'unit': 'mm'},
    'hole_count': {'default': 4, 'min': 1, 'unit': 'pcs'},
    'fillet_radius': {'default': 3.0, 'min': 0.0, 'unit': 'mm'},
    'chamfer': {'default': 2.0, 'min': 0.0, 'unit': 'mm'},
}

# 源脚本中保存模型名与参数的字面量名，供 load_native_model 用 AST 无副作用解析。
_SOURCE_PARAM_NAME = 'PARAMETERS'
_SOURCE_NAME_NAME = 'MODEL_NAME'


def validate_param(name: str, value: Any) -> str | None:
    """以 GOLDEN_PARAM_SPEC 为唯一来源校验单个参数；返回错误信息或 None。

    合法要求：参数存在于契约中、数值类型、且 ``value >= spec['min']``
    （min 可为 0.0，例如 fillet_radius/chamfer 的 0 值契约合法）。
    """
    spec = GOLDEN_PARAM_SPEC.get(name)
    if spec is None:
        return f'unknown parameter: {name}'
    if not isinstance(value, (int, float)):
        return f'{name} must be a number, got {value!r}'
    v = float(value)
    if v < float(spec['min']):
        return f'{name} must be >= {spec["min"]}, got {v!r}'
    return None


def validate_geometry_params(params: dict[str, Any]) -> list[str]:
    """以 GOLDEN_PARAM_SPEC 为唯一来源校验全部参数 + 交叉规则。

    交叉规则：``hole_diameter < min(length, width)``（孔必须在板平面内）。
    返回错误信息列表（空表示合法）。
    """
    errors: list[str] = []
    for name in GOLDEN_PARAM_SPEC:
        err = validate_param(name, params.get(name))
        if err is not None:
            errors.append(err)
    hd = params.get('hole_diameter')
    length = params.get('length')
    width = params.get('width')
    if (isinstance(hd, (int, float)) and isinstance(length, (int, float))
            and isinstance(width, (int, float))
            and float(hd) >= min(float(length), float(width))):
        errors.append('hole_diameter must be smaller than the plate plan size')
    return errors


def _default_golden_params() -> Dict[str, float]:
    return {k: float(spec['default']) for k, spec in GOLDEN_PARAM_SPEC.items()}


# STEP 头部 FILE_NAME 中的易变时间戳形如 '2026-08-06T13:37:07'。
_STEP_TIMESTAMP_RE = re.compile(r"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'")
# OpenCASCADE STEP 翻译器在 PRODUCT 名中嵌入递增的进程计数（7.7 1 / 7.7 2 ...）。
_STEP_TRANSLATOR_RE = re.compile(r"Open CASCADE STEP translator 7\.7 \d+")


def _normalize_step_timestamp(path: Path) -> None:
    """把 STEP 文件头部的易变元数据（时间戳、翻译器进程计数）替换为固定值，
    使同一模型多次导出的磁盘字节一致，产物哈希可复现。"""
    text = Path(path).read_text(encoding='ascii', errors='ignore')
    normalized = _STEP_TIMESTAMP_RE.sub("'0000-00-00T00:00:00'", text)
    normalized = _STEP_TRANSLATOR_RE.sub("Open CASCADE STEP translator 7.7 0", normalized)
    Path(path).write_text(normalized, encoding='ascii')


def _render_native_source(model_name: str, params: Dict[str, Any]) -> str:
    """把参数化黄金模型渲染为独立、可执行的 CadQuery 源脚本（.py）。

    生成的源文件可被独立执行（``python model.py``）重建同一模型，并可通过
    ``EXPORT_STEP`` 环境变量同时写出 STEP。参数以 ``PARAMETERS`` 字面量保存，
    供 :meth:`CadQueryBackend.load_native_model` 用 AST 无副作用恢复。
    """
    p = {k: float(v) for k, v in params.items()}
    src = '\n'.join([
        f'"""Golden parametric bracket `{model_name}` (CadQuery native editable source).',
        'Generated by AIPD-OS CadQueryBackend (real OpenCASCADE kernel).',
        'Edit PARAMETERS and re-run to regenerate the editable B-Rep model;',
        'set the EXPORT_STEP env var to a path to also write a STEP export.',
        'This file is independently executable and re-loadable.',
        '"""',
        'import cadquery as cq',
        '',
        f'{_SOURCE_NAME_NAME} = {model_name!r}',
        f'{_SOURCE_PARAM_NAME} = {json.dumps(p, indent=2, sort_keys=True)}',
        '',
        'def build():',
        "    p = PARAMETERS",
        "    L = float(p['length']); W = float(p['width']); T = float(p['thickness'])",
        "    HD = float(p['hole_diameter']); n = max(1, int(p['hole_count']))",
        "    FR = float(p['fillet_radius']); CH = float(p['chamfer'])",
        "    plate = cq.Workplane('XY').box(L, W, T)",
        "    if FR > 0:  # 0 半径 = 不应用圆角（契约合法）",
        "        plate = plate.edges('|Z').fillet(FR)",
        "    if CH > 0:  # 0 倒角 = 不应用倒角（契约合法）",
        "        plate = plate.faces('>Z').edges().chamfer(CH)",
        "    for i in range(n):",
        "        cx = (L / (n + 1)) * (i + 1) - L / 2",
        "        plate = plate.faces('>Z').workplane().center(cx, 0).hole(HD)",
        "    return plate",
        '',
        "if __name__ == '__main__':",
        '    import os',
        '    result = build()',
        "    print('built', result.val().isValid())",
        "    export = os.environ.get('EXPORT_STEP')",
        '    if export:',
        "        from cadquery import exporters",
        "        exporters.export(result, export, exportType='STEP')",
        '',
    ])
    return src


def _parse_source_model(source: str) -> Dict[str, Any]:
    """用 AST 从原生源脚本中恢复 {name, parameters}，不执行任何副作用代码。"""
    tree = ast.parse(source)
    name = 'golden_bracket'
    params: Dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Name):
                continue
            if tgt.id == _SOURCE_PARAM_NAME and isinstance(node.value, ast.Dict):
                params = ast.literal_eval(node.value)
            elif tgt.id == _SOURCE_NAME_NAME:
                try:
                    name = ast.literal_eval(node.value)
                except Exception:  # pragma: no cover - 防御
                    name = 'golden_bracket'
    return {'name': name, 'parameters': params}


class CadQueryBackend(CadBackend):
    """基于 CadQuery/OpenCASCADE 的真实可编辑参数化 B-Rep 后端。

    仅当 ``cadquery`` 已安装才可用；否则 ``is_available()`` 返回 False，
    ``capability_status()`` 返回 ``external_dependency``。

    可用时提供真实闭环：参数化黄金模型（多参数 + 孔/圆角/倒角特征）-> 改参 ->
    重生成 -> STEP 导出 -> 可编辑原生源导出 -> 重载 -> 几何校验 -> 产物哈希与
    工具版本 -> 修改前后差异 -> Product Truth 写回。
    """

    name = 'cadquery'

    def __init__(self) -> None:
        self._cq = _cq

    def tool_version(self) -> str:
        return getattr(self._cq, '__version__', 'n/a') if self._cq is not None else 'n/a'

    def maturity_ceiling(self) -> str:
        return 'C2'

    def capability_status(self) -> str:
        return FULL if self._cq is not None else EXTERNAL_DEPENDENCY

    def is_available(self) -> bool:
        return self._cq is not None

    def _default_params(self) -> Dict[str, float]:
        return _default_golden_params()

    def _make_model(self, name: str, params: Dict[str, Any],
                    source_path: Optional[Path] = None) -> Dict[str, Any]:
        return {'name': name, 'parameters': dict(params),
                'source_path': str(source_path) if source_path else None}

    def load_native_model(self, path: Optional[Path]) -> Any:
        """加载并恢复可编辑原生表示。

        - ``.py`` 原生源文件：用 AST 无副作用解析出模型名与参数，恢复特征/参数。
        - ``.json`` 契约文件：读取 parameters（兼容旧路径）。
        - 缺失/非法：返回默认黄金模型。
        """
        default = self._make_model('golden_bracket', self._default_params())
        p = Path(path) if path is not None else None
        if p is None or not p.is_file():
            return default
        text = p.read_text(encoding='utf-8', errors='ignore')
        if p.suffix.lower() == '.py':
            parsed = _parse_source_model(text)
            if parsed['parameters']:
                params = dict(self._default_params())
                params.update(parsed['parameters'])
                return self._make_model(parsed['name'], params, source_path=p)
            # 非本工具生成的 .py：回退为默认（诚实，不伪造已恢复）。
            return default
        try:
            data = json.loads(text)
        except Exception:
            data = {}
        params = dict(self._default_params())
        params.update(data.get('parameters', {}))
        return self._make_model(data.get('name', 'golden_bracket'), params)

    def list_parameters(self, model: Any) -> List[Dict[str, Any]]:
        params = model['parameters']
        return [{'name': k, 'value': float(v), 'unit': spec['unit']}
                for k, v in params.items()
                for spec in [GOLDEN_PARAM_SPEC.get(k, {'unit': 'mm'})]]

    def edit_parameter(self, model: Any, name: str, value: Any) -> Any:
        params = dict(model['parameters'])
        if name not in GOLDEN_PARAM_SPEC:
            raise KeyError(f"unknown parameter: {name}")
        err = validate_param(name, value)
        if err is not None:
            raise ValueError(err)
        params[name] = float(value)
        return self._make_model(model['name'], params,
                                source_path=model.get('source_path'))

    def _build(self, model: Any):
        """利用 CadQuery 构造可编辑参数化 B-Rep（仅内核可用时调用）。"""
        if self._cq is None:
            raise RuntimeError('CadQuery is not available')
        p = model['parameters']
        cq = self._cq
        L = float(p['length']); W = float(p['width']); T = float(p['thickness'])
        HD = float(p['hole_diameter']); n = max(1, int(p['hole_count']))
        FR = float(p['fillet_radius']); CH = float(p['chamfer'])
        plate = cq.Workplane('XY').box(L, W, T)
        # 0 半径/0 倒角 = 不应用该特征（契约 min=0.0 合法；内核不接受 0 值操作）。
        if FR > 0:
            plate = plate.edges('|Z').fillet(FR)
        if CH > 0:
            plate = plate.faces('>Z').edges().chamfer(CH)
        for i in range(n):
            cx = (L / (n + 1)) * (i + 1) - L / 2
            plate = plate.faces('>Z').workplane().center(cx, 0).hole(HD)
        return plate

    def _measure(self, shape: Any) -> Dict[str, Any]:
        """对真实几何做测量：体积、包围盒、实体数、面数、有效性。"""
        solid = shape.val()
        bb = solid.BoundingBox()
        return {
            'volume_mm3': float(solid.Volume()),
            'bbox': {'x': round(float(bb.xlen), 6),
                     'y': round(float(bb.ylen), 6),
                     'z': round(float(bb.zlen), 6)},
            'solid_count': len(shape.solids().vals()),
            'face_count': len(shape.faces().vals()),
            'is_valid': bool(solid.isValid()),
        }

    def _semantic_geometry_hash(self, shape: Any) -> str:
        """对几何语义的规范化 JSON 做 sha256（P0-14）。

        语义 = volume_mm3 / bbox / solid_count / face_count（``is_valid`` 不纳入，
        因为它是构建过程状态而非几何身份）。规范化：sort_keys + 紧凑分隔符。

        .. note::

           ``semantic_geometry_hash`` ≠ 字节级 ``sha256``。前者标识「几何身份」
           （同参同形），后者标识「磁盘字节」。发布/血缘证据必须声明使用哪个
           hash，二者不可互换。
        """
        m = self._measure(shape)
        semantic = {k: m[k] for k in ('volume_mm3', 'bbox', 'solid_count', 'face_count')}
        canonical = json.dumps(semantic, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def regenerate(self, model: Any) -> Any:
        """按当前参数真实重生成几何，并在模型上派生测量结果。"""
        if self._cq is None:
            raise RuntimeError('CadQuery is not available')
        shape = self._build(model)
        out = dict(model)
        out['parameters'] = dict(model['parameters'])
        out['derived'] = self._measure(shape)
        return out

    def export_step(self, model: Any, path: Path) -> Dict[str, Any]:
        if self._cq is None:
            raise RuntimeError('CadQuery is not available; cannot export native STEP')
        shape = self._build(model)
        self._cq.exporters.export(shape, str(path), exportType='STEP')
        # 归一化 STEP 头部的易变时间戳，使同一模型多次导出的磁盘字节一致，
        # 从而“未修改时哈希稳定、修改后哈希变化”的产物证据可复现。
        _normalize_step_timestamp(Path(path))
        rec = make_artifact_record(
            path, tool=self.name, tool_version=self.tool_version(),
            for_level='C2',
            semantic_hash=self._semantic_geometry_hash(shape))
        rec['extra'] = self._measure(shape)
        return rec

    def export_native(self, model: Any, path: Path) -> Dict[str, Any]:
        if self._cq is None:
            raise RuntimeError('CadQuery is not available')
        src = _render_native_source(model['name'], model['parameters'])
        Path(path).write_text(src, encoding='utf-8')
        return make_artifact_record(
            path, tool=self.name, tool_version=self.tool_version(), for_level='C2')

    def geometry_validity_check(self, model: Any) -> Dict[str, Any]:
        """几何有效性检查：GOLDEN_PARAM_SPEC 单源校验 + 真实内核 isValid。"""
        p = model['parameters']
        errors = validate_geometry_params(p)
        checks: Dict[str, Any] = {'parameter_constraints': not errors}

        if self._cq is not None and not errors:
            try:
                shape = self._build(model)
                m = self._measure(shape)
                checks['kernel_build'] = m['is_valid']
                checks['measurement'] = m
                if not m['is_valid'] or m['volume_mm3'] <= 0:
                    errors.append('kernel built an invalid or empty solid')
            except Exception as exc:  # pragma: no cover - 防御
                checks['kernel_build'] = False
                errors.append(f'kernel build failed: {exc}')

        valid = not errors
        return {'valid': valid, 'errors': errors, 'checks': checks}


# ---------------------------------------------------------------------------
# 确定性本地适配器：无真实内核时诚实降级
# ---------------------------------------------------------------------------

# 契约后端的默认参数：与 GOLDEN_PARAM_SPEC 对齐（全部键，取 spec default），
# 保证与 CadQueryBackend 的校验行为一致（P0-15 单源）。
DEFAULT_PARAMETERS: dict[str, float] = _default_golden_params()


class ContractBackend(CadBackend):
    """无真实参数化内核时的确定性本地适配器。

    它实现了参数化模型的**契约**（加载/增删改参数/重新生成/几何校验/导出），
    但只能产出小平面(faceted)临时 STEP 产物，成熟度上限诚实封顶为 C1，
    并把 C2 标记为 ``external_dependency``，直到配置了真实参数化内核。
    它绝不声称已完整实现原生 B-Rep（C2）。
    """

    name = 'contract-backend'

    def tool_version(self) -> str:
        return '1.0'

    def maturity_ceiling(self) -> str:
        # 无真实内核：能产出的真实几何仅为小平面级，上限为 C1。
        return 'C1'

    def capability_status(self) -> str:
        # C2 需要外部真实参数化内核，诚实标记为外部依赖。
        return EXTERNAL_DEPENDENCY

    def is_available(self) -> bool:
        # 契约/临时适配器始终可选（用于数字样机与测试），但能力上限为 C1。
        return True

    def load_native_model(self, path: Optional[Path]) -> Any:
        default = {'name': 'contract_plate', 'parameters': dict(DEFAULT_PARAMETERS)}
        if path is None or not Path(path).is_file():
            return default
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except Exception:
            data = {}
        params = dict(DEFAULT_PARAMETERS)
        params.update(data.get('parameters', {}))
        return {'name': data.get('name', 'contract_plate'), 'parameters': params}

    def list_parameters(self, model: Any) -> List[Dict[str, Any]]:
        return [{'name': k, 'value': float(v),
                 'unit': GOLDEN_PARAM_SPEC.get(k, {}).get('unit', 'mm')}
                for k, v in model['parameters'].items()]

    def edit_parameter(self, model: Any, name: str, value: Any) -> Any:
        params = dict(model['parameters'])
        if name not in params:
            raise KeyError(f"unknown parameter: {name}")
        err = validate_param(name, value)
        if err is not None:
            raise ValueError(err)
        params[name] = float(value)
        return {'name': model['name'], 'parameters': params}

    def regenerate(self, model: Any) -> Any:
        p = model['parameters']
        derived = {
            'volume_mm3': float(p['length']) * float(p['width']) * float(p['thickness']),
            'maturity_ceiling': self.maturity_ceiling(),
        }
        return {'name': model['name'], 'parameters': dict(p), 'derived': derived}

    def export_step(self, model: Any, path: Path) -> Dict[str, Any]:
        # 无真实内核：只能写小平面临时 STEP，明确标注上限 C1。
        size = sum(float(model['parameters'].get(k, 0)) for k in ('length', 'width', 'thickness'))
        _write_faceted_step(_cube_mesh(max(size, 10.0) / 10.0), Path(path))
        return make_artifact_record(
            Path(path), tool=self.name, tool_version=self.tool_version(),
            for_level='C1',
            note='temporary faceted artifact; native parametric B-Rep cannot '
                 'reach C2 without a real kernel (external_dependency)')

    def export_native(self, model: Any, path: Path) -> Dict[str, Any]:
        # 无真实内核时的"原生"表示：参数化契约清单，而非真实原生 CAD 文件。
        Path(path).write_text(
            json.dumps({'name': model['name'], 'parameters': model['parameters']},
                       ensure_ascii=False, indent=2),
            encoding='utf-8')
        return make_artifact_record(
            Path(path), tool=self.name, tool_version=self.tool_version(),
            for_level='C1',
            note='contract/NATIVE placeholder only; not a real native CAD file')

    def geometry_validity_check(self, model: Any) -> Dict[str, Any]:
        """几何有效性检查：与 CadQueryBackend 共用 GOLDEN_PARAM_SPEC 单源校验。"""
        p = model['parameters']
        errors = validate_geometry_params(p)
        valid = not errors
        return {'valid': valid, 'errors': errors,
                'checks': {'parameter_constraints': not errors}}


def get_default_backend() -> CadBackend:
    """返回可用的默认后端：优先真实内核，否则回退到确定性本地适配器。"""
    if _CADQUERY_AVAILABLE:
        return CadQueryBackend()
    return ContractBackend()


__all__ = [
    'CadBackend', 'CadQueryBackend', 'ContractBackend', 'get_default_backend',
    'GOLDEN_PARAM_SPEC', 'validate_param', 'validate_geometry_params',
    'DEFAULT_PARAMETERS', '_default_golden_params', '_render_native_source',
    '_parse_source_model', '_CADQUERY_AVAILABLE',
]
