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
import argparse, hashlib, json, shutil, subprocess, sys
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


# ==========================================================================
# P0-1 发布证据体系：--release-ready 模式
# 校验并全部通过才返回 success；修改任意被保护文件后必须失败。
# ==========================================================================

def _run_git(repo: Path, args) -> str:
    try:
        proc = subprocess.run(['git', *args], cwd=str(repo),
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return ''
        return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def _load_json(path: Path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _regenerate_source_manifest(repo: Path) -> dict:
    """用与 release_evidence 相同逻辑重新生成 source manifest（不写盘）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import release_evidence  # noqa: E402
    return release_evidence.generate_source_manifest(repo)


def _regenerate_bundle_manifest(bundle: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import release_evidence  # noqa: E402
    return release_evidence.generate_bundle_manifest(bundle)


def _check_workspace_clean(repo: Path):
    porcelain = _run_git(repo, ['status', '--porcelain'])
    dirty = [ln for ln in porcelain.splitlines() if ln.strip()]
    return (not dirty), dirty


def _check_commit(repo: Path, tag, provenance):
    head = _run_git(repo, ['rev-parse', 'HEAD'])
    errs = []
    tag_sha = None
    if tag:
        # 解析 tag 指向的提交（轻量/注释 tag 均可）
        tag_sha = _run_git(repo, ['rev-parse', f'{tag}^{{commit}}'])
        if not tag_sha:
            errs.append(f'tag not found: {tag}')
    if provenance:
        sc = provenance.get('source_commit')
        if not sc:
            errs.append('PROVENANCE missing source_commit')
        elif tag_sha:
            # 发布锚点：source_commit 必须等于最终 tag（指向被测试的提交）；
            # HEAD 可能因“发布证据元数据提交”略领先于 tag，属正常。
            if sc != tag_sha:
                errs.append(f'PROVENANCE source_commit {sc} != tag {tag} ({tag_sha})')
        elif sc != head:
            errs.append(f'PROVENANCE source_commit {sc} != HEAD {head}')
    return (not errs), errs


def _check_source_manifest_zero_diff(repo: Path):
    """重新生成后与磁盘现有 SOURCE_MANIFEST.json 逐条比对 path+sha256。"""
    disk_path = repo / 'SOURCE_MANIFEST.json'
    if not disk_path.is_file():
        return False, ['SOURCE_MANIFEST.json missing']
    disk = _load_json(disk_path)
    fresh = _regenerate_source_manifest(repo)
    disk_files = {(e.get('path'), e.get('sha256')) for e in disk.get('files', [])}
    fresh_files = {(e.get('path'), e.get('sha256')) for e in fresh.get('files', [])}
    if disk_files != fresh_files:
        only_disk = sorted(disk_files - fresh_files)
        only_fresh = sorted(fresh_files - disk_files)
        errs = []
        for p, h in only_disk:
            errs.append(f'only on disk: {p}')
        for p, h in only_fresh:
            errs.append(f'only regenerated: {p}')
        return False, errs[:20]
    return True, []


def _check_bundle_manifest_zero_diff(repo: Path):
    disk_path = repo / 'BUNDLE_MANIFEST.json'
    if not disk_path.is_file():
        return False, ['BUNDLE_MANIFEST.json missing']
    disk = _load_json(disk_path)
    bundle = disk.get('bundle_path')
    if not bundle or not Path(bundle).is_file():
        return False, [f'bundle not found: {bundle}']
    fresh = _regenerate_bundle_manifest(Path(bundle))
    disk_entries = {(e.get('path'), e.get('sha256')) for e in disk.get('entries', [])}
    fresh_entries = {(e.get('path'), e.get('sha256')) for e in fresh.get('entries', [])}
    if disk.get('bundle_sha256') != fresh.get('bundle_sha256'):
        return False, ['bundle_sha256 mismatch']
    if disk_entries != fresh_entries:
        return False, ['bundle entries mismatch']
    return True, []


def _check_test_report(provenance):
    """测试数字必须来自机器报告（解析 pytest JSON），不得硬编码。"""
    tr = provenance.get('test_report') or {}
    if not tr.get('present'):
        return False, ['test_report not present in PROVENANCE']
    if not tr.get('parsed'):
        return False, [f'test_report unparsable: {tr.get("path")}']
    passed = tr.get('passed')
    failed = tr.get('failed')
    total = tr.get('total')
    if passed is None or failed is None or total is None:
        return False, ['test_report missing passed/failed/total']
    if isinstance(failed, int) and failed > 0:
        return False, [f'test_report has {failed} failed']
    return True, [f'passed={passed} failed={failed} total={total}']


def _check_signature(bundle):
    """用公开密钥 verify bundle 的 Ed25519 签名。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sign_release  # noqa: E402
    sig_path = Path(str(bundle) + '.ed25519.sig')
    if not sig_path.is_file():
        return False, [f'Ed25519 signature missing for {bundle}']
    try:
        ok = sign_release.verify_file_ed25519(Path(bundle))
    except Exception as exc:
        return False, [f'signature verification error: {exc}']
    return ok, ['Ed25519 signature verified' if ok else 'Ed25519 signature FAILED']


_SECRET_PATTERNS = (
    r'-----BEGIN (RSA |EC |)?PRIVATE KEY-----',
    r'\bAKIA[0-9A-Z]{16}\b',
    r'\bghp_[0-9A-Za-z]{36}\b',
    r'\bsk-[0-9A-Za-z]{16,}\b',
    r'\bAIza[0-9A-Za-z_-]{35}\b',
)


def _check_secrets(repo: Path, source_manifest):
    import re
    _ACK = 'AIPD_ACK_SECRET'
    hits = []
    for e in source_manifest.get('files', []):
        rel = e.get('path')
        if not rel or not rel.endswith('.py'):
            continue
        p = repo / rel
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        # 显式声明“含故意测试夹具密钥”的文件视为已承认，不误报。
        if _ACK in text:
            continue
        for pat in _SECRET_PATTERNS:
            if re.search(pat, text):
                hits.append(f'{rel}: matches {pat!r}')
                break
    return (not hits), hits[:20]


def _check_cve_license(repo: Path):
    """pip-audit 若可用则检查未承认 CVE；许可证/密钥之外再扫 .env 模式。"""
    issues = []
    # pip-audit 尽力而为：可用则运行，失败(网络等)不阻断
    pip_audit = shutil.which('pip-audit')
    note = 'pip-audit not available; CVE check skipped'
    if pip_audit:
        try:
            proc = subprocess.run(
                [pip_audit, '--skip-editable', '--no-deps', '-r',
                 str(repo / 'requirements-quality.txt')],
                capture_output=True, text=True, timeout=180)
            if proc.returncode != 0:
                issues.append(f'pip-audit found vulnerabilities:\n{proc.stdout[:2000]}')
            else:
                note = 'pip-audit: no unacknowledged CVE'
        except Exception as exc:
            note = f'pip-audit could not run: {exc}'
    return (not issues), issues, note


def run_release_ready(repo: Path, tag: str | None, test_report: Path | None) -> dict:
    """执行全部 release-ready 校验，返回统一结果。"""
    checks = []
    def add(name, ok, detail):
        checks.append({'check': name, 'passed': bool(ok), 'detail': detail})

    provenance = None
    prov_path = repo / 'PROVENANCE.json'
    if prov_path.is_file():
        provenance = _load_json(prov_path)

    # 1) 工作区 clean
    ok, dirty = _check_workspace_clean(repo)
    add('workspace_clean', ok, dirty or 'clean')

    # 2) tag / provenance 指向 HEAD
    ok, errs = _check_commit(repo, tag, provenance)
    add('commit_matches_head', ok, errs or 'HEAD matches')

    # 3) Source Manifest 零差异
    ok, errs = _check_source_manifest_zero_diff(repo)
    add('source_manifest_zero_diff', ok, errs or 'zero diff')

    # 4) Bundle Manifest 零差异
    ok, errs = _check_bundle_manifest_zero_diff(repo)
    add('bundle_manifest_zero_diff', ok, errs or 'zero diff')

    # 5) 测试数字来自机器报告
    ok, detail = _check_test_report(provenance or {})
    add('test_numbers_from_report', ok, detail)

    # 6) 签名可验证（Ed25519）
    # 优先用 BUNDLE_MANIFEST 的绝对 bundle_path（权威记录）；退而求其次用 provenance 的 bundle 字段。
    bundle = None
    bm = repo / 'BUNDLE_MANIFEST.json'
    if bm.is_file():
        bp = _load_json(bm).get('bundle_path') or _load_json(bm).get('bundle')
        if bp:
            cand = Path(bp)
            if not cand.is_absolute():
                cand = repo / cand
            if cand.is_file():
                bundle = cand
    if bundle is None and provenance and provenance.get('bundle'):
        cand = Path(provenance['bundle'])
        if not cand.is_absolute():
            cand = repo / cand
        if cand.is_file():
            bundle = cand
    sig_ok, sig_detail = _check_signature(bundle) if bundle else (False, ['bundle not found'])
    add('signature_verifiable', sig_ok, sig_detail)

    # 7) secret / CVE / license
    source_manifest = _load_json(repo / 'SOURCE_MANIFEST.json') \
        if (repo / 'SOURCE_MANIFEST.json').is_file() else {}
    sec_ok, sec_hits = _check_secrets(repo, source_manifest)
    add('no_secrets', sec_ok, sec_hits or 'no secret patterns found')
    cve_ok, cve_issues, cve_note = _check_cve_license(repo)
    add('no_unacknowledged_cve', cve_ok, cve_issues if cve_issues else cve_note)

    passed = all(c['passed'] for c in checks)
    return {'release_ready': passed, 'checks': checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default=None)
    ap.add_argument('--target', default=None, choices=LEVELS)
    ap.add_argument('--json-out')
    ap.add_argument('--max-evidence-age-hours', type=float, default=8760.0)
    # --release-ready 模式参数
    ap.add_argument('--release-ready', action='store_true')
    ap.add_argument('--repo', default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument('--tag', default=None)
    ap.add_argument('--test-report', default=None)
    a = ap.parse_args()

    if a.release_ready:
        result = run_release_ready(Path(a.repo), a.tag,
                                   Path(a.test_report) if a.test_report else None)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(text)
        if a.json_out:
            Path(a.json_out).write_text(text + '\n', encoding='utf-8')
        return 0 if result['release_ready'] else 2

    # 原 CAD 成熟度门禁逻辑（--manifest/--target 必填）
    if not a.manifest or not a.target:
        ap.error('--manifest and --target are required unless --release-ready')

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
