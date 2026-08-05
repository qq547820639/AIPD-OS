#!/usr/bin/env python3
"""CAD maturity gate -- unified C0..C7 maturity system (AIPD-OS v5).

Replaces the legacy pre-v5 CAD ladder (0..5). A single C0..C7 ladder is used across
the whole repo (cad_maturity_gate, production_release_gate, capability_gate).

Semantics:
  C0  Mesh / spatial skeleton
  C1  Faceted BREP (mesh assemblies)
  C2  Native parametric B-Rep
  C3  Assembly constraints + continuous motion validation
  C4  CAE / load / strength / fatigue / failure evidence
  C5  DFM/DFA, tolerance, GD&T, full manufacturing definition
  C6  Full production drawings, BOM, inspection, approval
  C7  Substantive suppliers, DVT/PVT, quality closed-loop
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

LEVELS = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7']

# Requirement keys per level. A level is reached only when every requirement
# for it AND all lower levels are satisfied (cumulative ladder).
REQUIREMENTS = {
    'C0': ['design_intent', 'coordinate_system', 'overall_dimensions'],
    'C1': ['faceted_brep_mesh', 'step_assemblies'],
    'C2': ['native_parametric_brep', 'editable_feature_tree', 'real_part_features', 'step_parts'],
    'C3': ['assembly_constraints', 'continuous_rom_clearance', 'collision_reports'],
    'C4': ['cae_reports', 'load_cases', 'strength_stiffness_evidence', 'fatigue_plan_or_evidence'],
    'C5': ['dfm_dfa', 'tolerance_gdt'],
    'C6': ['drawings', 'bom', 'inspection_plan', 'assembly_instructions', 'release_manifest'],
    'C7': ['physical_evidence', 'owner_release', 'dvt_evidence', 'pvt_control_plan'],
}

# The maximum maturity a runtime can ever reach, regardless of evidence.
RUNTIME_MAX = {
    'mesh': 'C0',
    'faceted_brep': 'C1',
    'native_brep': 'C7',
    'provider_native_cad': 'C7',
}


def idx(level: str) -> int:
    return LEVELS.index(level)


def val(d: dict, key: str):
    """Resolve a requirement value from top-level fields or nested evidence."""
    if key in d:
        return d[key]
    ev = d.get('evidence')
    if isinstance(ev, dict) and key in ev:
        return ev[key]
    return None


def present(v) -> bool:
    return v is True or v not in (None, '', [], {})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--json-out')
    ap.add_argument('--target', default='C3', choices=LEVELS)
    a = ap.parse_args()

    m = json.loads(Path(a.manifest).read_text(encoding='utf-8'))
    runtime = m.get('runtime', 'mesh')
    evidence = m.get('evidence', {})
    runtime_ceiling = RUNTIME_MAX.get(runtime, 'C0')
    ceiling_idx = idx(runtime_ceiling)

    reached = None
    level_checks = {}
    cumulative = []
    for level in LEVELS:
        cumulative += REQUIREMENTS[level]
        checks = {k: bool(present(val(m, k))) for k in cumulative}
        runtime_allowed = idx(level) <= ceiling_idx
        passed = all(checks.values()) and runtime_allowed
        level_checks[level] = {
            'passed': passed,
            'checks': checks,
            'runtime_allowed': runtime_allowed,
        }
        if passed:
            reached = level
        else:
            break

    target_idx = idx(a.target)
    target_passed = reached is not None and idx(reached) >= target_idx

    # A faceted BREP runtime can never climb above C1 no matter what evidence.
    faceted_brep_capped = runtime == 'faceted_brep'

    result = {
        'runtime': runtime,
        'runtime_ceiling': runtime_ceiling,
        'faceted_brep_capped': faceted_brep_capped,
        'reached_level': reached,
        'target_level': a.target,
        'target_passed': target_passed,
        'level_checks': level_checks,
        'claims': {
            'wearable_human_ready': bool(
                evidence.get('human_fit_validation')
                and evidence.get('risk_controls_validated')
                and reached is not None
                and idx(reached) >= idx('C4')),
            'prototype_build_ready': bool(target_passed and reached is not None and idx(reached) >= idx('C4')),
            'production_release_ready': bool(reached is not None and idx(reached) >= idx('C7')),
        },
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if a.json_out:
        Path(a.json_out).write_text(text + '\n', encoding='utf-8')
    return 0 if target_passed else 4


if __name__ == '__main__':
    raise SystemExit(main())
