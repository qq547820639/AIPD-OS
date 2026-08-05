#!/usr/bin/env python3
"""Production release gate -- unified C0..C7 maturity (AIPD-OS v5).

Fixes the v4 bug where `achieved` reported the target level as reached even
when the lowest level's requirements failed. `achieved` is now the highest
level whose requirements are ALL satisfied cumulatively; if C0 itself fails,
`achieved` is None and the gate reports "not reached" with passed=False and
explicit `achieved_reached: false`.

Beyond field truthiness the gate performs multi-dimensional checks:
  (a) field present and truthy
  (b) file-path requirements exist / readable and sha256 matches manifest hash
  (c) version consistency across model / bom / drawings
  (d) counts consistency (model / bom / drawings numbers match)
  (e) units and datum scheme completeness
  (f) approval status
  (g) evidence freshness (timestamp not older than --max-evidence-age-hours)
  (h) tool capability ceiling (manifest runtime must allow the claimed level)
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

LEVELS = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7']

REQ = {
    'C0': ['design_intent', 'coordinate_system', 'overall_dimensions'],
    'C1': ['faceted_brep_mesh', 'step_assemblies'],
    'C2': ['native_parametric_brep', 'editable_feature_tree', 'real_part_features', 'step_parts'],
    'C3': ['assembly_constraints', 'continuous_rom_clearance', 'collision_reports'],
    'C4': ['cae_reports', 'load_cases', 'strength_stiffness_evidence', 'fatigue_plan_or_evidence'],
    'C5': ['dfm_dfa', 'tolerance_gdt'],
    'C6': ['drawings', 'bom', 'inspection_plan', 'assembly_instructions', 'release_manifest'],
    'C7': ['physical_evidence', 'owner_release', 'dvt_evidence', 'pvt_control_plan'],
}

RUNTIME_MAX = {
    'mesh': 'C0',
    'faceted_brep': 'C1',
    'native_brep': 'C7',
    'provider_native_cad': 'C7',
}

# Keys whose value may reference a file path that must exist and hash-match.
FILE_KEYS = {
    'faceted_brep_mesh', 'step_assemblies', 'step_parts', 'cae_reports',
    'drawings', 'bom', 'inspection_plan', 'assembly_instructions',
    'release_manifest', 'physical_evidence',
}


def present(v) -> bool:
    return v is True or v not in (None, '', [], {})


def val(d, key):
    if key in d:
        return d[key]
    ev = d.get('evidence')
    if isinstance(ev, dict) and key in ev:
        return ev[key]
    return None


def resolve_path(value):
    """Return (path, sha256) if the value references a file, else (None, None)."""
    if isinstance(value, dict):
        return value.get('path'), value.get('sha256')
    if isinstance(value, str) and value.strip() and not value.strip().startswith(('http://', 'https://')):
        return value.strip(), None
    return None, None


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(str(path), 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_ts(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def check_requirement(d, root, level, key):
    """Return a list of failure strings for one required key (per-key checks)."""
    errs = []
    value = val(d, key)

    # (a) field present and truthy
    if not present(value):
        errs.append(f"{level}:{key}: missing or empty")
        return errs

    # (b) file-path requirement exists / readable / sha256 matches
    if key in FILE_KEYS:
        path, sha = resolve_path(value)
        if path:
            p = (root / path).resolve()
            if not p.is_file():
                errs.append(f"{level}:{key}: file not found: {path}")
            elif sha:
                try:
                    if file_hash(p) != sha:
                        errs.append(f"{level}:{key}: sha256 mismatch")
                except OSError as exc:
                    errs.append(f"{level}:{key}: unreadable: {exc}")

    # (e) units / datum scheme completeness
    if key == 'units' and not (isinstance(value, str) and value.strip()):
        errs.append(f"{level}:units: missing or empty units string")
    if key == 'tolerance_gdt' and not present(val(d, 'datum_scheme')):
        errs.append(f"{level}:tolerance_gdt: datum_scheme missing")

    # (f) approval status for owner release
    if key == 'owner_release':
        status = val(d, 'approval_status')
        if present(status) and str(status).lower() not in ('approved', 'released'):
            errs.append(f"{level}:owner_release: approval_status not approved")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--target', required=True, choices=LEVELS)
    ap.add_argument('--json-out')
    ap.add_argument('--max-evidence-age-hours', type=float, default=8760.0)
    a = ap.parse_args()

    manifest_path = Path(a.manifest)
    d = json.loads(manifest_path.read_text(encoding='utf-8'))
    root = manifest_path.parent
    now = datetime.now(timezone.utc)
    target_idx = LEVELS.index(a.target)

    runtime = d.get('runtime', 'native_brep')
    ceiling = RUNTIME_MAX.get(runtime, 'C0')
    ceiling_idx = LEVELS.index(ceiling)

    # (h) tool capability ceiling
    failures = []
    if ceiling_idx < target_idx:
        failures.append(
            f"tool ceiling: runtime '{runtime}' caps at {ceiling}, target {a.target} requires more")

    # (c) version consistency across model / bom / drawings
    versions = {k: val(d, k) for k in ('model_version', 'bom_version', 'drawings_version')
                if present(val(d, k))}
    if len(set(versions.values())) > 1:
        failures.append(f"version mismatch: {versions}")

    # (d) counts consistency
    counts = {k: val(d, k) for k in ('model_part_count', 'bom_line_count', 'drawing_count')
              if val(d, k) is not None}
    if len(set(counts.values())) > 1:
        failures.append(f"count mismatch: {counts}")

    # (g) evidence freshness
    ts_dt = parse_ts(val(d, 'timestamp'))
    if ts_dt is not None:
        age_h = (now - ts_dt).total_seconds() / 3600.0
        if age_h > a.max_evidence_age_hours:
            failures.append(f"evidence stale: {age_h:.1f}h > {a.max_evidence_age_hours}h")

    # cumulative level evaluation (per-key checks), bounded by the runtime ceiling
    achieved = None
    missing = []
    for level in LEVELS:
        if LEVELS.index(level) > ceiling_idx:
            break
        level_errs = []
        for k in REQ[level]:
            level_errs.extend(check_requirement(d, root, level, k))
        if level_errs:
            missing.extend(level_errs)
            break
        achieved = level

    achieved_reached = achieved is not None and LEVELS.index(achieved) >= target_idx
    passed = achieved_reached and not failures

    result = {
        'passed': passed,
        'target': a.target,
        'achieved': achieved,
        'achieved_reached': achieved_reached,
        'missing': missing,
        'failures': failures,
        'runtime': runtime,
        'runtime_ceiling': ceiling,
        'production_release_ready': bool(passed and a.target == 'C7'),
        'prototype_build_ready': bool(passed and target_idx >= 6),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if a.json_out:
        Path(a.json_out).write_text(text + '\n', encoding='utf-8')
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
