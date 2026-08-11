"""P1-4 测试：CAD 能力按成熟度真实实现。

覆盖：后端适配器契约、C2 诚实性（无真实内核时为 external_dependency）、
几何有效性、产物哈希/工具版本、写回链传播、faceted 上限 C1 一致性。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aipd_os.cad.backends import (
    CadBackend,
    CadQueryBackend,
    ContractBackend,
    get_default_backend,
)
from aipd_os.cad.evidence import (
    artifact_hash,
    make_artifact_record,
    sha256_file,
    verify_artifact,
)
from aipd_os.cad.maturity import (
    EXTERNAL_DEPENDENCY,
    FULL,
    LEVELS,
    REQUIREMENTS,
    RUNTIME_MAX,
    evaluate_maturity,
    faceted_ceiling,
    honest_level_status,
)
from aipd_os.cad.writeback import propagate_cad_change


def full_evidence() -> dict:
    ev = {}
    for keys in REQUIREMENTS.values():
        for k in keys:
            ev[k] = True
    return ev


def make_manifest(runtime: str, has_real_kernel: bool = False) -> dict:
    return {"runtime": runtime, "evidence": full_evidence()}


# ---------------------------------------------------------------------------
# 1. 后端适配器契约
# ---------------------------------------------------------------------------

def test_default_backend_implements_contract():
    backend = get_default_backend()
    assert isinstance(backend, CadBackend)
    for method in (
        'load_native_model', 'list_parameters', 'edit_parameter', 'regenerate',
        'export_step', 'export_native', 'geometry_validity_check',
        'tool_version', 'maturity_ceiling', 'capability_status', 'artifact_hash',
    ):
        assert callable(getattr(backend, method)), f"missing method {method}"
    desc = backend.describe()
    assert desc['backend'] == backend.name
    assert desc['capability_status'] in ('full', 'external_dependency', 'not_implemented')


def test_contract_backend_parameter_edit_and_regenerate():
    backend = ContractBackend()
    model = backend.load_native_model(None)
    names = [p['name'] for p in backend.list_parameters(model)]
    assert 'length' in names
    edited = backend.edit_parameter(model, 'length', 200.0)
    assert edited['parameters']['length'] == 200.0
    assert model['parameters']['length'] == 100.0  # 原模型未被改动
    regen = backend.regenerate(edited)
    assert regen['derived']['volume_mm3'] == pytest.approx(200.0 * 50.0 * 10.0)


def test_contract_backend_unknown_param_rejected():
    backend = ContractBackend()
    model = backend.load_native_model(None)
    with pytest.raises(KeyError):
        backend.edit_parameter(model, 'not_a_param', 1.0)


# ---------------------------------------------------------------------------
# 2. C2 诚实性：无真实内核时 external_dependency
# ---------------------------------------------------------------------------

def test_cadquery_backend_honest_status():
    from aipd_os.cad.backends import _CADQUERY_AVAILABLE
    backend = CadQueryBackend()
    # 诚实性契约：真实内核可用 -> full；未安装 -> external_dependency，绝不伪装。
    if _CADQUERY_AVAILABLE:
        assert backend.capability_status() == FULL
        assert backend.is_available() is True
    else:
        assert backend.capability_status() == EXTERNAL_DEPENDENCY
        assert backend.is_available() is False
    assert backend.maturity_ceiling() == 'C2'  # 声明能力上限，但状态随内核虚实而变


def test_contract_backend_honest_external_dependency():
    backend = ContractBackend()
    assert backend.capability_status() == EXTERNAL_DEPENDENCY
    assert backend.maturity_ceiling() == 'C1'  # 无真实内核，几何上限 C1
    assert backend.is_available() is True    # 契约/临时适配器始终可选


def test_honest_level_status_c2_not_full_without_kernel():
    status = honest_level_status(EXTERNAL_DEPENDENCY)
    assert status['C0'] == FULL
    assert status['C1'] == FULL
    for level in ('C2', 'C3', 'C4', 'C5', 'C6', 'C7'):
        assert status[level] == EXTERNAL_DEPENDENCY


def test_honest_level_status_c2_full_only_with_real_kernel():
    status = honest_level_status(FULL)
    assert status['C2'] == FULL


# ---------------------------------------------------------------------------
# 3. 几何有效性
# ---------------------------------------------------------------------------

def test_geometry_validity_valid():
    backend = ContractBackend()
    model = backend.load_native_model(None)
    check = backend.geometry_validity_check(model)
    assert check['valid'] is True
    assert check['errors'] == []


def test_geometry_validity_invalid_negative_param():
    backend = ContractBackend()
    model = backend.load_native_model(None)
    # CS9：edit_parameter 现在与 CadQueryBackend 一致，负数在编辑期即拒绝；
    # 此处直接构造含非法参数的模型，验证 geometry_validity_check 拒绝。
    with pytest.raises(ValueError):
        backend.edit_parameter(model, "thickness", -5.0)
    bad = dict(model["parameters"])
    bad["thickness"] = -5.0
    check = backend.geometry_validity_check({"name": "bad", "parameters": bad})
    assert check["valid"] is False
    assert any("thickness" in e for e in check["errors"])


# ---------------------------------------------------------------------------
# 4. 产物哈希 / 工具版本 / 证据记录
# ---------------------------------------------------------------------------

def test_artifact_hash_and_evidence_record(tmp_path):
    backend = ContractBackend()
    model = backend.load_native_model(None)
    step = tmp_path / "model.step"
    record = backend.export_step(model, step)
    assert step.is_file()
    # sha256 与磁盘一致
    assert record['sha256'] == sha256_file(step) == artifact_hash(step)
    assert record['tool'] == backend.name
    assert record['tool_version'] == backend.tool_version()
    assert record['timestamp']
    assert 'C1' in record['maturity_evidence']
    assert verify_artifact(record) is True
    # 诚实备注：临时 faceted 产物，原生 B-Rep 需外部内核
    assert 'external' in record.get('note', '')


def test_make_artifact_record_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_artifact_record(tmp_path / "nope.step", "x", "1.0")


# ---------------------------------------------------------------------------
# 5. 写回链传播
# ---------------------------------------------------------------------------

def test_writeback_propagation():
    manifest = {
        "model": {"revision": "R1", "parameters": {"length": 100.0}},
        "spec": {"revision": "R1", "content_ref": "spec.md"},
        "bom": {"revision": "R1", "content_ref": "bom.csv"},
        "manual": {"revision": "R1", "content_ref": "manual.md"},
        "verification_plan": {"revision": "R1", "content_ref": "vp.md"},
    }
    out = propagate_cad_change(manifest, {"length": 150.0},
                               tool_version="contract-backend/1.0")
    assert out['model']['revision'] == 'R2'
    assert out['model']['parameters']['length'] == 150.0
    for key in ('spec', 'bom', 'manual', 'verification_plan'):
        assert out[key]['revision'] == 'R2'
        assert out[key]['regeneration_needed'] is True
        assert out[key]['cad_source_revision'] == 'R2'
    # 原 manifest 不被改动（深拷贝）
    assert manifest['model']['revision'] == 'R1'
    assert manifest['model']['parameters']['length'] == 100.0


def test_writeback_respects_downstream_subset():
    manifest = {
        "model": {"revision": "R1", "parameters": {}},
        "spec": {"revision": "R1"},
        "bom": {"revision": "R1"},
    }
    out = propagate_cad_change(manifest, {"length": 10.0}, downstream=["spec"])
    assert out['spec']['regeneration_needed'] is True
    assert 'bom' not in out or out['bom'].get('regeneration_needed') is None


# ---------------------------------------------------------------------------
# 6. 成熟度一致性：faceted 上限 C1，C2 需真实内核
# ---------------------------------------------------------------------------

def test_faceted_ceiling_is_C1():
    assert faceted_ceiling() == 'C1'
    assert RUNTIME_MAX['faceted_brep'] == 'C1'


def test_faceted_brep_never_reaches_C2_even_with_full_evidence():
    manifest = make_manifest('faceted_brep')
    result = evaluate_maturity(manifest, has_real_kernel=False)
    assert result['faceted_brep_capped'] is True
    assert result['reached_level'] == 'C1'
    assert LEVELS.index(result['reached_level']) <= LEVELS.index('C1')


def test_c2_only_achieved_with_real_kernel():
    # 无真实内核：即使 native_brep + 全证据，C2 也只是 external_dependency，不达到。
    no_kernel = evaluate_maturity(make_manifest('native_brep'), has_real_kernel=False)
    assert no_kernel['reached_level'] == 'C1'

    # 有真实内核：C2 可完整实现并达到。
    with_kernel = evaluate_maturity(make_manifest('native_brep'), has_real_kernel=True)
    assert with_kernel['backend_capability_status'] == FULL
    assert with_kernel['reached_level'] == 'C2'
    assert LEVELS.index(with_kernel['reached_level']) >= LEVELS.index('C2')


def test_faceted_consistency_assertion_flags_overclaim():
    from aipd_os.cad.maturity import assert_faceted_not_over_c1
    bad = {"runtime": "faceted_brep", "reached_level": "C2"}
    with pytest.raises(AssertionError):
        assert_faceted_not_over_c1(bad)
    ok = {"runtime": "faceted_brep", "reached_level": "C1"}
    assert_faceted_not_over_c1(ok)  # 不抛异常