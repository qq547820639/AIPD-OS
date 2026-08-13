"""Docs-as-Code Gate（v5.8.2 Commit 9，提示词 §24）。

防止文档长期反向误导 coding agent。锁定：
- canonical status semantics（三维正交，见 test_status_semantics_contract.py）；
- current package paths（runtime/maturity/lineage 等真实位置）；
- required capability names（idea.structure / research.academic_search /
  evidence.assess_relation / idea_truth.refresh / idea.decompose）；
- Idea maturity names（I0/I1/I2/I3 + IdeaMaturityPolicy）；
- lineage canonical implementation（state.lineage.LineageService 是 canonical，
  ProductTruth.LineageGraph 是 facade）；
- audit provenance 字段（audit_repo / capability_matrix 带 generator_version +
  command + source_commit）；
- Python support contract（requires-python 与 CI 验证矩阵一致）；
- CAD byte_reproducibility_profile 文档。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parent.parent

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - Python 3.9/3.10
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]


def _pyproject() -> dict:
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        return cast(dict[str, Any], tomllib.load(fh))


def _doc(path: str) -> str:
    return (REPO_ROOT / "docs" / path).read_text(encoding="utf-8")


# ----------------------------------------------------------- status semantics
def test_status_semantics_canonical_importable():
    """status semantics contract 存在且可导入（独立文件防回退）。"""
    from tests.test_status_semantics_contract import (  # noqa: F401
        CANONICAL_EPISTEMIC_STATUSES,
        CLAIM_ASSESSMENT_STATUSES,
        DEFINITION_STATUSES,
    )
    assert len(CANONICAL_EPISTEMIC_STATUSES) == 9


def test_status_semantics_doc_orthogonal():
    doc = _doc("architecture/STATUS_SEMANTICS.md")
    assert "Simulation" in doc and "Calculation" in doc and "External evidence" in doc
    assert "Supported（有支持证据）" not in doc
    assert "Contradicted（有反驳证据）" not in doc


# -------------------------------------------------------------- package paths
def test_current_package_paths_exist():
    """关键模块路径（代码事实，防文档与重构漂移）。"""
    for rel in (
        "src/aipd_os/runtime.py",                     # RuntimeContext (v5.8.2)
        "src/aipd_os/idea/maturity.py",               # IdeaMaturityPolicy
        "src/aipd_os/idea/claim_assessment.py",       # ClaimAssessment
        "src/aipd_os/state/lineage.py",               # canonical LineageService
        "src/aipd_os/product_truth/lineage.py",       # facade
        "src/aipd_os/research/providers/researchstudio.py",
        "src/aipd_os/supervisor/idea_capabilities.py",
        "src/aipd_os/state/migrations.py",
    ):
        assert (REPO_ROOT / rel).is_file(), f"missing {rel}"


def test_runtime_is_single_bootstrap_contract():
    """build_runtime 存在且装配 ResearchStudio（production wiring 事实）。"""
    import aipd_os.runtime as rt
    assert callable(rt.build_runtime)
    assert callable(rt.get_runtime)
    assert hasattr(rt.RuntimeContext, "with_adapters")
    assert hasattr(rt.RuntimeContext, "probe")
    # external provider 注册函数存在（Commit 4 契约）
    from aipd_os.research.providers.researchstudio import register_researchstudio
    assert callable(register_researchstudio)


# ------------------------------------------------------------ capability names
def test_required_capability_names():
    from aipd_os.supervisor.idea_capabilities import (
        CLAIM_RESEARCH_CAPABILITY,
        EVIDENCE_ASSESS_RELATION_CAPABILITY,
        IDEA_STRUCTURE_CAPABILITY,
        IDEA_TRUTH_REFRESH_CAPABILITY,
    )
    assert IDEA_STRUCTURE_CAPABILITY == "idea.structure"
    assert CLAIM_RESEARCH_CAPABILITY == "claim.research"
    assert EVIDENCE_ASSESS_RELATION_CAPABILITY == "evidence.assess_relation"
    assert IDEA_TRUTH_REFRESH_CAPABILITY == "idea_truth.refresh"
    from aipd_os.idea.decomposer import IDEA_DECOMPOSE_CAPABILITY
    assert IDEA_DECOMPOSE_CAPABILITY == "idea.decompose"
    from aipd_os.research.providers.researchstudio import (
        ResearchStudioPaperSearchProvider,
    )
    assert ResearchStudioPaperSearchProvider.capability_id == \
        "research.academic_search"


# --------------------------------------------------------------- maturity names
def test_idea_maturity_names_and_policy():
    from aipd_os.idea.maturity import IdeaMaturity, IdeaMaturityPolicy
    assert [m.value for m in IdeaMaturity] == ["I0", "I1", "I2", "I3"]
    p = IdeaMaturityPolicy()
    assert p.policy_id == "idea_maturity_policy_v1"
    assert p.required_claim_types == {"problem", "user", "mechanism", "technology"}
    # 文档提及 key claim coverage（防文档回退到「I2=one evidence」）
    doc = _doc("architecture/idea_evidence_architecture.md")
    assert "required key claim types" in doc


def test_idea_decomposer_same_idea_documented():
    """文档必须描述 decompose_existing（同一 canonical Idea），不是 create new。"""
    doc = _doc("architecture/idea_evidence_architecture.md")
    assert "decompose_existing" in doc
    assert "同一 canonical Idea" in doc or "同一 idea_id" in doc


# -------------------------------------------------------------- lineage canon
def test_lineage_canonical_implementation():
    """canonical LineageService 在 state.lineage；ProductTruth 是 facade。"""
    from aipd_os.state.lineage import LineageService
    assert hasattr(LineageService, "retire_edge")  # v5.8.2 Commit 5
    import inspect

    from aipd_os import product_truth
    src = inspect.getsource(product_truth.lineage.LineageGraph.__init__)
    assert "canonical_db" in src  # facade 契约


def test_lineage_relation_types_contract():
    from aipd_os.state.lineage import LINEAGE_RELATION_TYPES
    for t in ("derived_from", "supported_by", "contradicted_by", "translated_to",
              "satisfies", "validated_by", "supersedes", "implements", "affects"):
        assert t in LINEAGE_RELATION_TYPES


# -------------------------------------------------------------- audit provenance
def test_audit_reports_head_bound_with_generator_metadata():
    """机器报告必须带 source_commit/package_version/generated_at/
    generator_version/command（提示词 §25）。"""
    src = (REPO_ROOT / "scripts" / "audit_repo.py").read_text(encoding="utf-8")
    for field in ("generator_version", '"command"', "source_commit",
                  "package_version", "generated_at"):
        assert field in src, f"audit_repo.py missing {field}"
    cm = (REPO_ROOT / "scripts" / "capability_matrix.py").read_text(encoding="utf-8")
    assert "generator_version" in cm


# --------------------------------------------------------------- python contract
def test_python_support_contract_matches_ci():
    """requires-python 必须与 CI 验证矩阵一致（不宣称未验证支持）。"""
    proj = _pyproject()
    req = proj["project"]["requires-python"]
    assert req == ">=3.9,<3.13", f"requires-python={req} not pinned to CI matrix"
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert '"3.9"' in ci and '"3.12"' in ci


# ------------------------------------------------------------------- CAD doc
def test_cad_identity_contract_documented():
    """CAD artifact identity contract 文档化（byte vs semantic hash）。"""
    doc = _doc("architecture/truth_architecture.md")
    cad_tests = (REPO_ROOT / "tests" / "test_cad_contract_unify.py").read_text(
        encoding="utf-8")
    assert "semantic_geometry_hash" in cad_tests
    assert "sha256" in cad_tests
    # 任意一处文档/测试注释必须区分两种 hash 的用途
    assert ("语义 hash" in doc or "semantic" in doc
            or "几何身份" in doc or "byte_reproducibility" in doc
            or "byte_reproducibility" in cad_tests)
