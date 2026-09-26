"""production_release_gate 单元测试：achieved 修复、多维门检查与新增 evidence_checks。"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "production_release_gate.py"
_NS = runpy.run_path(str(GATE))


def full_evidence() -> dict:
    ev = {}
    for keys in _NS["REQ"].values():
        for k in keys:
            ev[k] = True
    return ev


def run_gate(manifest: Path, target: str, max_age: float = 8760.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--manifest", str(manifest), "--target", target,
         "--max-evidence-age-hours", str(max_age)],
        capture_output=True, text=True,
    )


def write_complete_manifest(tmp_path: Path, **overrides) -> Path:
    m = {
        "runtime": "native_brep",
        "model_version": "1.0.0",
        "bom_version": "1.0.0",
        "drawings_version": "1.0.0",
        "model_part_count": 3,
        "bom_line_count": 3,
        "drawing_count": 3,
        "units": "mm",
        "datum_scheme": "DRF-A",
        "approval_status": "approved",
        # fail-closed 证据项所需数据（缺失即失败，不得空真通过）。
        # 两侧都带记录号，因为生产者就是这么写的（`ctq[].record_id` 见
        # `src/aipd_os/release_manifest.py:86`，`gdt[].ctq_record_id` 见同文件 :257/:293），
        # 门禁也按记录号核对覆盖。只写名字的夹具是**生产者不会产出的形状**，
        # 它会把"按名字求差丢条数"这类真缺陷一直藏到有人用真链数据跑门禁那天。
        "ctq": [{"record_id": "T-001", "feature": "hole_a",
                 "inspection_method": "CMM"}],
        "gdt": [{"feature": "hole_a", "ctq_record_id": "T-001"}],
        # 变更控制那一格由生产者（aipd release manifest）写好；缺它即判红，
        # 与上面 ctq/gdt 同一口径：没有证据 ≠ 证据说没问题。
        "eco": {"coverage": "complete", "artifacts": 2, "covered": 2,
                "uncovered": [], "unverified": [], "undetermined": []},
        "timestamp": "2026-08-01T00:00:00Z",
        "evidence": full_evidence(),
    }
    m.update(overrides)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def get_check(out, name: str) -> dict:
    return next(c for c in out["evidence_checks"] if c["check"] == name)


def test_c0_missing_achieved_none(tmp_path):
    """回归：C0 任一要求缺失时 achieved 必须为 None 且 passed=False。"""
    ev = full_evidence()
    del ev["design_intent"]
    p = write_complete_manifest(tmp_path, evidence=ev)
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["achieved"] is None
    assert out["passed"] is False
    assert out["achieved_reached"] is False
    assert r.returncode == 2


def test_complete_manifest_passes(tmp_path):
    """完整清单达到目标级时通过。"""
    p = write_complete_manifest(tmp_path)
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["achieved"] == "C7"
    assert out["passed"] is True
    assert r.returncode == 0
    assert "evidence_checks" in out
    assert all(c["passed"] for c in out["evidence_checks"])


def test_missing_file_requirement_fails(tmp_path):
    """文件路径要求指向不存在的文件时失败。"""
    p = write_complete_manifest(tmp_path, drawings="missing_drawings.pdf")
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert any("drawings" in x and "file not found" in x for x in out["missing"])


def test_stale_evidence_fails(tmp_path):
    """证据时间戳超过最大时效时失败。"""
    p = write_complete_manifest(tmp_path, timestamp="2020-01-01T00:00:00Z")
    r = run_gate(p, "C7", max_age=1)
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert any("stale" in f for f in out["failures"])
    assert get_check(out, "evidence_not_expired")["passed"] is False


def test_gdt_not_covering_ctq_fails(tmp_path):
    """gdt 没覆盖某条 ctq **记录**时证据门失败，理由要点名是哪条记录。"""
    p = write_complete_manifest(
        tmp_path,
        ctq=[{"record_id": "T-001", "feature": "hole_a",
              "inspection_method": "CMM"}],
        gdt=[{"feature": "slot_b", "ctq_record_id": "T-009"}],
    )
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    chk = get_check(out, "gdt_covers_ctq")
    assert chk["passed"] is False, chk
    assert "T-001" in chk["detail"], chk["detail"]
    # 一条用例一个原告：这条夹具的 ctq 写了检验方法，不该顺手把那一格也判红
    assert get_check(out, "ctq_has_inspection")["passed"] is True


def test_two_ctq_records_sharing_a_feature_label_are_not_masked(tmp_path):
    """两条记录共用一个 feature 标签时，未覆盖的那条不许被掩盖成绿。

    判据原先按名字集合求差（`ctq_feats - gdt_feats`），名字撞车就只剩一个元素 ⇒
    "其中一条没上图"读成全绿。本轮实测过：同名臂 passed=True、只把标签换成异名就红，
    其余一模一样 —— 差别只在标签，说明集合差丢了**记录条数**。
    """
    p = write_complete_manifest(
        tmp_path,
        ctq=[{"record_id": "T-001", "feature": "hole_a", "inspection_method": "CMM"},
             {"record_id": "T-002", "feature": "hole_a", "inspection_method": "CMM"}],
        gdt=[{"feature": "hole_a", "ctq_record_id": "T-001"}],
    )
    out = json.loads(run_gate(p, "C2").stdout)
    chk = get_check(out, "gdt_covers_ctq")
    assert chk["passed"] is False, chk
    assert "T-002" in chk["detail"], chk["detail"]


def test_every_record_covered_is_green_even_with_shared_labels(tmp_path):
    """不开火对照：两条同名记录**各自**都有覆盖凭据 ⇒ 绿，理由报出记录条数。"""
    p = write_complete_manifest(
        tmp_path,
        ctq=[{"record_id": "T-001", "feature": "hole_a", "inspection_method": "CMM"},
             {"record_id": "T-002", "feature": "hole_a", "inspection_method": "CMM"}],
        gdt=[{"feature": "hole_a", "ctq_record_id": "T-001"},
             {"feature": "hole_a", "ctq_record_id": "T-002"}],
    )
    out = json.loads(run_gate(p, "C2").stdout)
    chk = get_check(out, "gdt_covers_ctq")
    assert chk["passed"] is True, chk
    assert "all 2 ctq records covered" in chk["detail"], chk["detail"]


def test_ctq_entry_without_record_id_fails_closed(tmp_path):
    """缺记录号只能判"不可核"，不许退回按名字猜——按名字正是刚被推翻的那个错做法。"""
    p = write_complete_manifest(tmp_path,
                                ctq=[{"feature": "hole_a",
                                      "inspection_method": "CMM"}])
    out = json.loads(run_gate(p, "C2").stdout)
    chk = get_check(out, "gdt_covers_ctq")
    assert chk["passed"] is False and "record_id" in chk["detail"], chk


def test_ctq_missing_inspection_fails(tmp_path):
    """ctq 条目缺少 inspection_method / test_method 时证据门失败。"""
    p = write_complete_manifest(
        tmp_path, ctq=[{"record_id": "T-001", "feature": "hole_a"}])
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert get_check(out, "ctq_has_inspection")["passed"] is False


def test_drawing_model_version_mismatch_fails(tmp_path):
    """drawings_version != model_version 时证据门失败。"""
    p = write_complete_manifest(tmp_path, drawings_version="2.0.0")
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert get_check(out, "drawing_cad_same_revision")["passed"] is False


def test_consistent_c2_manifest_passes(tmp_path):
    """完全一致的 C2 清单通过，且所有 evidence_checks 通过。"""
    p = write_complete_manifest(tmp_path)
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is True
    assert out["achieved"] == "C7"
    assert r.returncode == 0
    assert all(c["passed"] for c in out["evidence_checks"])


ECO_CHECK = "change_control_closes_deliverables"


def test_change_control_complete_passes(tmp_path):
    """每条带哈希的交付物都有已复验的单覆盖 ⇒ 这一项绿，detail 给出对上了几条。"""
    p = write_complete_manifest(tmp_path)
    chk = get_check(json.loads(run_gate(p, "C6").stdout), ECO_CHECK)
    assert chk["passed"] is True and "2/2" in chk["detail"], chk


def test_change_control_section_missing_fails_closed(tmp_path):
    """没有 eco 这一格 = 从没核过变更控制，不能读成「核过且没问题」。"""
    m = json.loads(write_complete_manifest(tmp_path).read_text(encoding="utf-8"))
    del m["eco"]
    p = tmp_path / "m_eco.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    out = json.loads(run_gate(p, "C6").stdout)
    chk = get_check(out, ECO_CHECK)
    assert chk["passed"] is False and "no eco section" in chk["detail"]
    assert out["passed"] is False


def test_change_control_uncovered_and_unverified_name_the_paths(tmp_path):
    """违规那一支必须点名到路径：只说「没过」等于看不出差哪一条。"""
    p = write_complete_manifest(
        tmp_path,
        eco={"coverage": "incomplete", "artifacts": 3, "covered": 1,
             "uncovered": ["dfm.md"], "unverified": ["assy.step.evidence.json"],
             "undetermined": []})
    chk = get_check(json.loads(run_gate(p, "C6").stdout), ECO_CHECK)
    assert chk["passed"] is False
    assert "dfm.md" in chk["detail"] and "assy.step.evidence.json" in chk["detail"]


def test_change_control_with_no_orders_is_a_blind_spot_not_a_pass(tmp_path):
    """一条单都没有 ⇒ 生产者记成盲区（不阻断），但门**不**把它读成通过。

    两侧口径不同是有意的：`aipd release manifest` 的 rc 管「这份证据自己有没有
    说错话」，发布门管「你敢不敢拿这句话去放行」。不知道改没改过不该用来放行。
    """
    p = write_complete_manifest(
        tmp_path,
        eco={"coverage": "undetermined", "artifacts": 2, "covered": 0,
             "uncovered": [], "unverified": [],
             "undetermined": ["dfm.md", "dfm.md.evidence.json"]})
    out = json.loads(run_gate(p, "C6").stdout)
    chk = get_check(out, ECO_CHECK)
    assert chk["passed"] is False
    assert "无任何变更单可判 2 条" in chk["detail"] and "不知道改没改" in chk["detail"]
    assert out["passed"] is False


def test_change_control_partial_blind_does_not_read_as_complete(tmp_path):
    """有单但没全覆盖（partial）：同样不通过，且盲区条数照报。"""
    p = write_complete_manifest(
        tmp_path,
        eco={"coverage": "partial", "artifacts": 3, "covered": 2,
             "uncovered": [], "unverified": [], "undetermined": ["assy.step"]})
    chk = get_check(json.loads(run_gate(p, "C6").stdout), ECO_CHECK)
    assert chk["passed"] is False and "assy.step" in chk["detail"]


def test_change_control_unclaimed_removal_fails_with_otherwise_clean_coverage(tmp_path):
    """第 28 片：基线里有、这次没交，也没一张 VERIFIED 的 REMOVE 认领 ⇒ 拦。

    这一支单独存在是因为**它不会出现在 uncovered 里**：文件已经不交了，
    按「交付物逐条核」的思路看不见它，只有跟上一版比才看得见。
    """
    p = write_complete_manifest(
        tmp_path,
        eco={"coverage": "complete", "artifacts": 1, "covered": 1,
             "uncovered": [], "unverified": [], "undetermined": [],
             "baseline_coverage": "incomplete",
             "removed_unclaimed": ["assy.step.evidence.json"]})
    chk = get_check(json.loads(run_gate(p, "C6").stdout), ECO_CHECK)
    assert chk["passed"] is False
    assert "没人认领" in chk["detail"] and "assy.step.evidence.json" in chk["detail"]


def test_change_control_passes_on_zero_orders_when_the_baseline_says_unchanged(tmp_path):
    """零张单 + 基线证明两条都没改 ⇒ 通过，并把「不需要单」的理由写在 detail 里。"""
    p = write_complete_manifest(
        tmp_path,
        eco={"coverage": "complete", "artifacts": 2, "covered": 0,
             "uncovered": [], "unverified": [], "undetermined": [],
             "baseline_coverage": "complete",
             "unchanged_since_baseline": ["dfm.md", "dfm.md.evidence.json"]})
    chk = get_check(json.loads(run_gate(p, "C6").stdout), ECO_CHECK)
    assert chk["passed"] is True, chk
    assert "另有 2 条由上一版基线证明语义未变" in chk["detail"]


def test_missing_revision_data_fails_closed(tmp_path):
    """fail-closed：drawings_version 缺失不得空真通过。"""
    m = json.loads(write_complete_manifest(tmp_path).read_text(encoding="utf-8"))
    del m["drawings_version"]
    p = tmp_path / "m2.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    out = json.loads(run_gate(p, "C2").stdout)
    assert get_check(out, "drawing_cad_same_revision")["passed"] is False


def test_missing_timestamp_fails_closed(tmp_path):
    """fail-closed：timestamp 缺失不得空真通过。"""
    m = json.loads(write_complete_manifest(tmp_path).read_text(encoding="utf-8"))
    del m["timestamp"]
    p = tmp_path / "m2.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    out = json.loads(run_gate(p, "C2").stdout)
    assert get_check(out, "evidence_not_expired")["passed"] is False


def test_missing_ctq_data_fails_closed(tmp_path):
    """fail-closed：ctq/gdt 缺失不得空真通过。"""
    m = json.loads(write_complete_manifest(tmp_path).read_text(encoding="utf-8"))
    del m["ctq"]
    del m["gdt"]
    p = tmp_path / "m2.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    out = json.loads(run_gate(p, "C2").stdout)
    assert get_check(out, "gdt_covers_ctq")["passed"] is False
    assert get_check(out, "ctq_has_inspection")["passed"] is False


def test_cve_check_fails_closed_when_pip_audit_missing(tmp_path, monkeypatch):
    """fail-closed：pip-audit 不可用时 no_unacknowledged_cve 必须失败而非跳过
    （有依赖清单的仓库不可空真通过）。"""
    (tmp_path / "requirements-quality.txt").write_text("jsonschema>=4.0\n",
                                                       encoding="utf-8")
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    ok, issues, note = _NS["_check_cve_license"](tmp_path)
    assert ok is False
    assert issues


def test_cve_check_vacuous_pass_without_dependency_manifests(tmp_path):
    """仓库未声明任何依赖清单 → 无第三方依赖可审计，显式 vacuous 通过。"""
    ok, issues, note = _NS["_check_cve_license"](tmp_path)
    assert ok is True
    assert "vacuous" in note


def test_workspace_clean_fails_closed_outside_git(tmp_path):
    """fail-closed：非 git 仓库不得把「查不到脏文件」当干净。"""
    ok, dirty = _NS["_check_workspace_clean"](tmp_path)
    assert ok is False
    assert dirty


def _valid_cad_contract() -> dict:
    return {
        "project_id": "P-1",
        "contract_id": "C-1",
        "cad_level": "C2",
        "spec_version": "1.0.0",
        "source_facts": [],
        "required_artifacts": ["model.step"],
        "hard_constraints": [{"id": "HC-1", "description": "closed solid"}],
        "soft_objectives": [
            {"id": "SO-1", "metric": "part_count", "direction": "min",
             "target": 1, "limit": 3, "weight": 1.0}
        ],
        "release_policy": {
            "minimum_score": 0.9,
            "minimum_improvement": 0.01,
            "max_internal_iterations": 8,
        },
    }


def test_schema_valid_accepts_valid_cad_contract(tmp_path):
    """符合 cad_contract.schema.json 的契约通过 schema_valid 证据门。"""
    p = write_complete_manifest(tmp_path, cad_contract=_valid_cad_contract())
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert get_check(out, "schema_valid")["passed"] is True
    assert out["passed"] is True
    assert r.returncode == 0


def test_schema_valid_rejects_invalid_cad_contract(tmp_path):
    """违反 schema（缺少必填 project_id）的契约被 schema_valid 拒绝并导致门失败。"""
    bad = _valid_cad_contract()
    del bad["project_id"]
    p = write_complete_manifest(tmp_path, cad_contract=bad)
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert get_check(out, "schema_valid")["passed"] is False
    assert any("schema_valid" in f for f in out["failures"])
    assert out["passed"] is False
    assert r.returncode == 2


def test_secrets_scan_ack_requires_justification(tmp_path):
    """回归：AIPD_ACK_SECRET 必须带理由（伪造/fake 等），否则不豁免；
    且扫描扩展到 .json 等后缀。"""
    (tmp_path / "secret.py").write_text(
        "api_key = 'sk-1234567890123456'\n", encoding="utf-8")
    # 无理由 ACK：不豁免
    (tmp_path / "acked_bare.py").write_text(
        "AIPD_ACK_SECRET\napi_key = 'sk-abcdef1234567890'\n", encoding="utf-8")
    # 带理由 ACK：豁免
    (tmp_path / "acked_justified.py").write_text(
        "AIPD_ACK_SECRET: 本文件含故意伪造的密钥样例（fake fixture）\n"
        "api_key = 'sk-abcdef1234567890'\n", encoding="utf-8")
    # .json 也被扫描
    (tmp_path / "config.json").write_text(
        '{"key": "sk-1234567890123456"}', encoding="utf-8")
    manifest = {"files": [
        {"path": "secret.py"}, {"path": "acked_bare.py"},
        {"path": "acked_justified.py"}, {"path": "config.json"},
    ]}
    ok, hits = _NS["_check_secrets"](tmp_path, manifest)
    assert ok is False
    joined = "; ".join(hits)
    assert "secret.py" in joined
    assert "acked_bare.py" in joined
    assert "config.json" in joined
    assert "acked_justified.py" not in joined
