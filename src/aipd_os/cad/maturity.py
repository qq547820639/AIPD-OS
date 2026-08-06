"""CAD 成熟度一致性逻辑（生产实现，供后端与测试复用）。

统一 C0..C7 成熟度体系，与 ``scripts/cad_maturity_gate.py`` 语义一致。
本模块额外提供**诚实性约束**：

1. Faceted（网格/面片级）运行时永远无法达到 C2 及以上 —— 其成熟度上限为 C1。
   任何把面片级几何与 C2 及以上成熟度关联的表述都被视为过度声称。
2. C2 只有在真实的可编辑参数化 B-Rep 内核（例如 CadQuery/OpenCASCADE）
   实际存在并被使用时才可声明为 ``full``。缺少真实内核时 C2 只能标记为
   ``external_dependency``，绝不伪装成已完整实现。
3. C3..C7 分别依赖装配约束、CAE、DFM/DFA/GD&T、图纸/BOM/检验与实物证据；
   没有真实证据时一律标记为 ``external_dependency`` 或 ``not_implemented``。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 统一的成熟度层级（与 scripts/cad_maturity_gate.py 保持一致）。
LEVELS: List[str] = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7']

# 每级达到所需满足的需求键（累积阶梯：达到某级需满足该级及以下全部需求）。
REQUIREMENTS: Dict[str, List[str]] = {
    'C0': ['design_intent', 'coordinate_system', 'overall_dimensions'],
    'C1': ['faceted_brep_mesh', 'step_assemblies'],
    'C2': ['native_parametric_brep', 'editable_feature_tree', 'real_part_features', 'step_parts'],
    'C3': ['assembly_constraints', 'continuous_rom_clearance', 'collision_reports'],
    'C4': ['cae_reports', 'load_cases', 'strength_stiffness_evidence', 'fatigue_plan_or_evidence'],
    'C5': ['dfm_dfa', 'tolerance_gdt'],
    'C6': ['drawings', 'bom', 'inspection_plan', 'assembly_instructions', 'release_manifest'],
    'C7': ['physical_evidence', 'owner_release', 'dvt_evidence', 'pvt_control_plan'],
}

# 每种运行时几何类型能达到的成熟度上限。
RUNTIME_MAX: Dict[str, str] = {
    'mesh': 'C0',
    'faceted_brep': 'C1',  # 面片级几何，上限必须为 C1
    'native_brep': 'C7',
    'provider_native_cad': 'C7',
}

# 能力状态的取值（诚实性契约）。
FULL = 'full'
EXTERNAL_DEPENDENCY = 'external_dependency'
NOT_IMPLEMENTED = 'not_implemented'
CAPABILITY_STATUSES = (FULL, EXTERNAL_DEPENDENCY, NOT_IMPLEMENTED)


def level_index(level: str) -> int:
    """返回层级的序号；非法层级抛出 ValueError。"""
    return LEVELS.index(level)


def present(v: Any) -> bool:
    return v is True or v not in (None, '', [], {})


def val(d: Dict[str, Any], key: str) -> Any:
    """从 manifest 顶层字段或 evidence 子对象解析需求值。"""
    if key in d:
        return d[key]
    ev = d.get('evidence')
    if isinstance(ev, dict) and key in ev:
        return ev[key]
    return None


def faceted_ceiling() -> str:
    """Faceted（网格/面片级）几何的成熟度硬上限。"""
    return 'C1'


def honest_level_status(capability_status: str) -> Dict[str, str]:
    """给定后端能力状态，返回每个层级的诚实状态映射。

    只有具备真实参数化内核（capability_status == FULL）时，C2 才可能为
    ``full``；否则 C2 及以上一律为 ``external_dependency`` 或
    ``not_implemented``，绝不伪装成已完整实现。
    """
    if capability_status == FULL:
        # 真实可编辑参数化内核在运行：C0..C2 可完整实现。
        # C3.. 仍依赖外部装配/CAE/制造/图纸工具与实物证据。
        return {
            'C0': FULL, 'C1': FULL, 'C2': FULL,
            'C3': EXTERNAL_DEPENDENCY, 'C4': EXTERNAL_DEPENDENCY,
            'C5': EXTERNAL_DEPENDENCY, 'C6': EXTERNAL_DEPENDENCY,
            'C7': EXTERNAL_DEPENDENCY,
        }
    if capability_status == NOT_IMPLEMENTED:
        return {level: NOT_IMPLEMENTED for level in LEVELS}
    # EXTERNAL_DEPENDENCY（或未知）：C0/C1 可由本地生成，C2 及以上需要外部真实内核。
    return {
        'C0': FULL, 'C1': FULL,
        'C2': EXTERNAL_DEPENDENCY, 'C3': EXTERNAL_DEPENDENCY,
        'C4': EXTERNAL_DEPENDENCY, 'C5': EXTERNAL_DEPENDENCY,
        'C6': EXTERNAL_DEPENDENCY, 'C7': EXTERNAL_DEPENDENCY,
    }


def assert_faceted_not_over_c1(manifest: Dict[str, Any]) -> None:
    """一致性断言：faceted 运行时给出的成熟度结果不得超过 C1。

    若违反（例如把面片级几何报告为达到 C2 及以上），直接抛 AssertionError。
    """
    runtime = manifest.get('runtime', 'mesh')
    if runtime != 'faceted_brep':
        return
    reached = manifest.get('reached_level')
    if reached is not None and level_index(str(reached)) > level_index('C1'):
        raise AssertionError(
            f"faceted_brep runtime reported reached_level={reached!r}, "
            "which exceeds the honest ceiling C1 (faceted cannot reach C2 or above)."
        )


def evaluate_maturity(
    manifest: Dict[str, Any],
    has_real_kernel: bool = False,
    capability_status: Optional[str] = None,
) -> Dict[str, Any]:
    """评估 manifest 的成熟度，并施加诚实性约束。

    :param manifest: CAD 工程清单，含 ``runtime`` 与各需求键/evidence。
    :param has_real_kernel: 是否已接入真实可编辑参数化内核（CadQuery 等）。
    :param capability_status: 后端能力状态；缺省时按
        ``FULL 若 has_real_kernel else EXTERNAL_DEPENDENCY`` 推导。
    :return: 含 ``runtime``、``runtime_ceiling``、``reached_level``、
        ``level_status``、``faceted_brep_capped`` 等字段的 dict。
    """
    status = capability_status or (FULL if has_real_kernel else EXTERNAL_DEPENDENCY)
    runtime = manifest.get('runtime', 'mesh')
    ceiling = RUNTIME_MAX.get(runtime, 'C0')
    ceiling_idx = level_index(ceiling)

    level_status = honest_level_status(status)

    # Faceted 运行时几何上限始终为 C1。
    faceted_brep_capped = runtime == 'faceted_brep'
    geometry_ceiling_idx = level_index('C1') if faceted_brep_capped else ceiling_idx

    # 逐级评估（累积阶梯），受运行时上限与诚实性状态双重约束。
    reached = None
    cumulative: List[str] = []
    level_checks: Dict[str, Any] = {}
    for level in LEVELS:
        lvl_idx = level_index(level)
        if lvl_idx > ceiling_idx:
            break
        cumulative += REQUIREMENTS[level]
        checks = {k: bool(present(val(manifest, k))) for k in cumulative}
        # 诚实性门槛：
        #   * 几何上限（faceted 不超过 C1）；
        #   * 该级能力状态必须为 full（C2 需真实内核）。
        allowed = lvl_idx <= geometry_ceiling_idx and level_status[level] == FULL
        passed = all(checks.values()) and allowed
        level_checks[level] = {'passed': passed, 'checks': checks, 'allowed': allowed}
        if passed:
            reached = level
        else:
            break

    return {
        'runtime': runtime,
        'runtime_ceiling': ceiling,
        'faceted_brep_capped': faceted_brep_capped,
        'backend_capability_status': status,
        'reached_level': reached,
        'level_status': level_status,
        'level_checks': level_checks,
    }


def summarize_levels(level_status: Dict[str, str]) -> Dict[str, List[str]]:
    """把层级状态按状态值分组，方便报告 'full' / 'external_dependency' 清单。"""
    grouped: Dict[str, List[str]] = {s: [] for s in CAPABILITY_STATUSES}
    for level, status in level_status.items():
        grouped.setdefault(status, []).append(level)
    return grouped


__all__ = [
    'LEVELS', 'REQUIREMENTS', 'RUNTIME_MAX',
    'FULL', 'EXTERNAL_DEPENDENCY', 'NOT_IMPLEMENTED', 'CAPABILITY_STATUSES',
    'level_index', 'present', 'val', 'faceted_ceiling',
    'honest_level_status', 'assert_faceted_not_over_c1',
    'evaluate_maturity', 'summarize_levels',
]