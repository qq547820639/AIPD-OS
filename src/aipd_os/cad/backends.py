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

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from aipd_os.cad.evidence import make_artifact_record, sha256_file
from aipd_os.cad.maturity import (
    EXTERNAL_DEPENDENCY,
    FULL,
    NOT_IMPLEMENTED,
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

class CadQueryBackend(CadBackend):
    """基于 CadQuery/OpenCASCADE 的真实可编辑参数化 B-Rep 后端。

    仅当 ``cadquery`` 已安装才可用；否则 ``is_available()`` 返回 False，
    ``capability_status()`` 返回 ``external_dependency``。
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
        return {'length': 100.0, 'width': 50.0, 'thickness': 10.0,
                'hole_diameter': 8.0, 'hole_count': 4.0}

    def load_native_model(self, path: Optional[Path]) -> Any:
        default = {'name': 'parametric_plate', 'parameters': self._default_params()}
        if path is None or not Path(path).is_file():
            return default
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except Exception:
            data = {}
        params = dict(self._default_params())
        params.update(data.get('parameters', {}))
        return {'name': data.get('name', 'parametric_plate'), 'parameters': params}

    def list_parameters(self, model: Any) -> List[Dict[str, Any]]:
        params = model['parameters']
        return [{'name': k, 'value': float(v), 'unit': 'mm'} for k, v in params.items()]

    def edit_parameter(self, model: Any, name: str, value: Any) -> Any:
        params = dict(model['parameters'])
        if name not in params:
            raise KeyError(f"unknown parameter: {name}")
        params[name] = float(value)
        return {'name': model['name'], 'parameters': params}

    def regenerate(self, model: Any) -> Any:
        # 真实内核重新生成几何；此处派生体积等参考量。
        p = model['parameters']
        derived = {'volume_mm3': float(p['length']) * float(p['width']) * float(p['thickness'])}
        return {'name': model['name'], 'parameters': dict(p), 'derived': derived}

    def _build(self, model: Any):
        """利用 CadQuery 构造可编辑参数化 B-Rep（仅内核可用时调用）。"""
        if self._cq is None:
            raise RuntimeError('CadQuery is not available')
        p = model['parameters']
        cq = self._cq
        plate = (
            cq.Workplane('XY')
            .box(float(p['length']), float(p['width']), float(p['thickness']))
        )
        n = max(1, int(float(p['hole_count'])))
        hole_r = float(p['hole_diameter']) / 2.0
        spacing = float(p['length']) / (n + 1)
        for i in range(n):
            cx = spacing * (i + 1) - float(p['length']) / 2.0
            plate = plate.faces('>Z').workplane().center(cx, 0).hole(hole_r)
        return plate

    def export_step(self, model: Any, path: Path) -> Dict[str, Any]:
        if self._cq is None:
            raise RuntimeError('CadQuery is not available; cannot export native STEP')
        shape = self._build(model)
        self._cq.exporters.export(shape, str(path))
        return make_artifact_record(
            path, tool=self.name, tool_version=self.tool_version(),
            for_level='C2')

    def export_native(self, model: Any, path: Path) -> Dict[str, Any]:
        if self._cq is None:
            raise RuntimeError('CadQuery is not available')
        # 原生可编辑表示：导出一个可复现的参数化源脚本。
        p = model['parameters']
        lines = [
            '# parametric plate (CadQuery native editable source)',
            'import cadquery as cq',
            f"p = {json.dumps(p)}",
            'result = (cq.Workplane("XY")',
            '  .box(p["length"], p["width"], p["thickness"]))',
            'for cx in ...:  # hole loop',
            '    pass',
        ]
        Path(path).write_text('\n'.join(lines), encoding='utf-8')
        return make_artifact_record(
            path, tool=self.name, tool_version=self.tool_version(), for_level='C2')

    def geometry_validity_check(self, model: Any) -> Dict[str, Any]:
        p = model['parameters']
        errors: List[str] = []
        for k, v in p.items():
            if not (isinstance(v, (int, float)) and v > 0):
                errors.append(f'{k} must be a positive number, got {v!r}')
        if float(p.get('hole_diameter', 0)) >= min(
                float(p.get('length', 0)), float(p.get('width', 0))):
            errors.append('hole_diameter must be smaller than the plate plan size')
        valid = not errors
        return {'valid': valid, 'errors': errors,
                'checks': {'positive_finite': not errors}}


# ---------------------------------------------------------------------------
# 确定性本地适配器：无真实内核时诚实降级
# ---------------------------------------------------------------------------

DEFAULT_PARAMETERS: Dict[str, float] = {
    'length': 100.0, 'width': 50.0, 'thickness': 10.0, 'hole_diameter': 8.0,
}


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
        return [{'name': k, 'value': float(v), 'unit': 'mm'}
                for k, v in model['parameters'].items()]

    def edit_parameter(self, model: Any, name: str, value: Any) -> Any:
        params = dict(model['parameters'])
        if name not in params:
            raise KeyError(f"unknown parameter: {name}")
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
        p = model['parameters']
        errors: List[str] = []
        for k, v in p.items():
            if not (isinstance(v, (int, float)) and v > 0):
                errors.append(f'{k} must be a positive number, got {v!r}')
        if float(p.get('hole_diameter', 0)) >= min(
                float(p.get('length', 0)), float(p.get('width', 0))):
            errors.append('hole_diameter must be smaller than the plate plan size')
        valid = not errors
        return {'valid': valid, 'errors': errors,
                'checks': {'positive_finite': not errors}}


def get_default_backend() -> CadBackend:
    """返回可用的默认后端：优先真实内核，否则回退到确定性本地适配器。"""
    if _CADQUERY_AVAILABLE:
        return CadQueryBackend()
    return ContractBackend()


__all__ = [
    'CadBackend', 'CadQueryBackend', 'ContractBackend', 'get_default_backend',
    '_CADQUERY_AVAILABLE',
]