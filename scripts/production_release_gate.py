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

Additional evidence-gate checks are reported additively in `evidence_checks`
(a list of {check, level, passed, detail}) and any failed evidence check also
fails the overall gate. Existing (a)..(h) logic is preserved unchanged.
"""
from __future__ import annotations
import argparse, hashlib, json
import jsonschema
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


def _find_cad_contract(d, root):
    """Locate the CAD contract object to schema-validate, or None if absent.

    Handles the `cad_contract` field being (a) an inline dict (the contract
    object itself), (b) a ``{"path": ...}`` file reference, or (c) a plain
    string file path. A missing/unreadable referenced file yields ``{}`` so the
    schema check fails rather than silently passing.
    """
    value = val(d, 'cad_contract')
    if value is None:
        return None
    if isinstance(value, dict):
        path, _ = resolve_path(value)
        if path is None:
            return value  # inline contract object
    else:
        path, _ = resolve_path(value)
        if path is None:
            return None  # not a dict or file reference
    p = (root / path).resolve()
    if not p.is_file():
        return {}
    try:
        loaded = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def run_evidence_checks(d, root, runtime, ceiling, ceiling_idx, target, target_idx,
                        now, max_age_hours):
    """Build the additive `evidence_checks` list. Each entry: {check, level, passed, detail}."""
    checks = []

    def add(check, level, passed, detail):
        checks.append({'check': check, 'level': level, 'passed': bool(passed), 'detail': detail})

    # file_openable: for FILE_KEYS file paths, attempt to open.
    unopenable = []
    for k in sorted(FILE_KEYS):
        value = val(d, k)
        path, _ = resolve_path(value)
        if not path:
            continue
        p = (root / path).resolve()
        if not p.is_file():
            unopenable.append(f"{k}: not found: {path}")
        else:
            try:
                with open(str(p), 'rb') as fh:
                    fh.read(1)
            except OSError as exc:
                unopenable.append(f"{k}: unreadable: {exc}")
    add('file_openable', 'C1', not unopenable,
        '; '.join(unopenable) if unopenable else 'all referenced files openable')

    # schema_valid: validate the CAD contract against assets/schemas/cad_contract.schema.json.
    schema_issues = []
    schema_path = Path(__file__).resolve().parent.parent / "assets" / "schemas" / "cad_contract.schema.json"
    try:
        with open(str(schema_path), encoding='utf-8') as fh:
            schema = json.load(fh)
    except Exception as exc:
        schema_issues.append(f"cannot load CAD schema: {exc}")
        schema = None
    if schema is not None:
        contract = _find_cad_contract(d, root)
        if contract is not None:
            try:
                jsonschema.validate(contract, schema)
            except jsonschema.ValidationError as exc:
                schema_issues.append(f"cad_contract schema violation: {exc.message}")
            except jsonschema.SchemaError as exc:
                schema_issues.append(f"CAD schema invalid: {exc}")
    add('schema_valid', 'C6', not schema_issues,
        '; '.join(schema_issues) if schema_issues else 'cad_contract validates against cad_contract.schema.json')

    # drawing_cad_same_revision: drawings_version must equal model_version.
    dv = val(d, 'drawings_version')
    mv = val(d, 'model_version')
    if dv is not None and mv is not None:
        same = dv == mv
        add('drawing_cad_same_revision', 'C6', same,
            f"drawings_version={dv!r} model_version={mv!r}")
    else:
        add('drawing_cad_same_revision', 'C6', True,
            'drawings_version/model_version not both present')

    # bom_matches_model: bom_line_count must equal model_part_count.
    b = val(d, 'bom_line_count')
    mp = val(d, 'model_part_count')
    if b is not None and mp is not None:
        same = b == mp
        add('bom_matches_model', 'C6', same, f"bom_line_count={b} model_part_count={mp}")
    else:
        add('bom_matches_model', 'C6', True, 'bom_line_count/model_part_count not both present')

    # units_datum_tolerance_complete: units present; datum_scheme when tolerance_gdt
    # present; each drawing entry needs tolerance or a global tolerance_gdt.
    unit_issues = []
    units = val(d, 'units')
    if not (isinstance(units, str) and units.strip()):
        unit_issues.append('units missing')
    tol_gdt = val(d, 'tolerance_gdt')
    datum = val(d, 'datum_scheme')
    if present(tol_gdt) and not present(datum):
        unit_issues.append('datum_scheme missing while tolerance_gdt present')
    drawings = d.get('drawings')
    if isinstance(drawings, list) and not present(tol_gdt):
        if drawings and not all(
                isinstance(entry, dict) and present(entry.get('tolerance'))
                for entry in drawings):
            unit_issues.append('drawing entries lack tolerance and no global tolerance_gdt')
    add('units_datum_tolerance_complete', 'C5', not unit_issues,
        '; '.join(unit_issues) if unit_issues else 'units/datum/tolerance complete')

    # gdt_covers_ctq: every ctq feature must appear in gdt features.
    ctq = d.get('ctq')
    gdt = d.get('gdt')
    if isinstance(ctq, list) and ctq and isinstance(gdt, list):
        ctq_feats = {str(c.get('feature')) for c in ctq if isinstance(c, dict)}
        gdt_feats = {str(g.get('feature')) for g in gdt if isinstance(g, dict)}
        uncovered = sorted(ctq_feats - gdt_feats)
        add('gdt_covers_ctq', 'C5', not uncovered,
            f"ctq features not covered by gdt: {uncovered}" if uncovered
            else 'all ctq features covered by gdt')
    else:
        add('gdt_covers_ctq', 'C5', True, 'ctq/gdt not both lists present')

    # ctq_has_inspection: every ctq item must have inspection_method or test_method.
    if isinstance(ctq, list) and ctq:
        missing_ins = [
            str(c.get('feature')) for c in ctq
            if isinstance(c, dict)
            and not present(c.get('inspection_method'))
            and not present(c.get('test_method'))
        ]
        add('ctq_has_inspection', 'C6', not missing_ins,
            f"ctq items lacking inspection: {missing_ins}" if missing_ins
            else 'all ctq items have inspection')
    else:
        add('ctq_has_inspection', 'C6', True, 'no ctq present')

    # tool_capability_supports_level: runtime ceiling must allow the claimed level.
    cap_ok = ceiling_idx >= target_idx
    add('tool_capability_supports_level', 'C0', cap_ok,
        f"runtime '{runtime}' ceiling {ceiling} vs target {target}")

    # owner_approval_real: owner_release present and approval_status approved/released.
    owner = val(d, 'owner_release')
    status = val(d, 'approval_status')
    ok = present(owner) and str(status).lower() in ('approved', 'released')
    add('owner_approval_real', 'C7', ok,
        f"owner_release={present(owner)} approval_status={status!r}")

    # evidence_not_expired: timestamp freshness.
    ts = parse_ts(val(d, 'timestamp'))
    if ts is not None:
        age_h = (now - ts).total_seconds() / 3600.0
        add('evidence_not_expired', 'C7', age_h <= max_age_hours,
            f"evidence age {age_h:.1f}h <= {max_age_hours}h")
    else:
        add('evidence_not_expired', 'C7', True, 'no timestamp to check')

    return checks


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

    # additive evidence-gate checks; failed ones also fail the overall gate
    evidence_checks = run_evidence_checks(
        d, root, runtime, ceiling, ceiling_idx, a.target, target_idx, now,
        a.max_evidence_age_hours)
    for c in evidence_checks:
        if not c['passed']:
            failures.append(f"{c['level']}:{c['check']}: {c['detail']}")

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
        'evidence_checks': evidence_checks,
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
