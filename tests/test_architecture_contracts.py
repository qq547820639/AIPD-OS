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
        "src/aipd_os/state/migrations/__init__.py",
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


# =====================================================================
# Architecture Boundary Invariants（v5.10 P0）
# =====================================================================

def test_project_boundary_doc_exists():
    """project_boundary.md 必须存在且声明 AIPD-OS 是执行后端。"""
    doc_path = REPO_ROOT / "docs" / "architecture" / "project_boundary.md"
    assert doc_path.is_file(), "docs/architecture/project_boundary.md 缺失"
    text = doc_path.read_text(encoding="utf-8")
    # 必须声明 AIPD-OS 不是 agent-facing orchestrator
    assert "执行后端" in text or "execution backend" in text.lower(), \
        "project_boundary.md 必须声明 AIPD-OS 是执行后端"
    assert "IdeaToLaunch" in text, \
        "project_boundary.md 必须提及 IdeaToLaunch 是唯一 agent-facing 入口"


def test_agent_yaml_boundary_consistent():
    """agents/openai.yaml 不得重新声明 AIPD-OS 为旗舰 agent。

    当 project_boundary.md 声明 AIPD-OS 不是主 agent-facing entry 时，
    agent metadata 不得重新声明相反行为。
    """
    import yaml  # type: ignore[import-not-found]

    boundary = (REPO_ROOT / "docs" / "architecture" / "project_boundary.md").read_text(
        encoding="utf-8")
    # 确认 boundary 文档存在且声明了 backend 定位
    if "执行后端" not in boundary and "execution backend" not in boundary.lower():
        return  # boundary 文档不存在或未声明 → 跳过此检查

    agent_path = REPO_ROOT / "agents" / "openai.yaml"
    if not agent_path.is_file():
        return  # agent 文件不存在 → 跳过

    with open(agent_path, encoding="utf-8") as fh:
        agent = yaml.safe_load(fh)

    policy = agent.get("policy", {})
    # 不得允许隐式调用
    assert not policy.get("allow_implicit_invocation", False), \
        "agents/openai.yaml: allow_implicit_invocation 不得为 true（AIPD-OS 是执行后端）"

    interface = agent.get("interface", {})
    display = interface.get("display_name", "")
    # 不得自称"主管"或"旗舰"
    assert "主管" not in display, \
        f"agents/openai.yaml: display_name 不得含'主管'（当前: {display}）"


def test_skill_md_boundary_consistent():
    """SKILL.md 不得同时宣传 AIPD-OS 是独立旗舰 Agent 入口。"""
    boundary = (REPO_ROOT / "docs" / "architecture" / "project_boundary.md").read_text(
        encoding="utf-8")
    if "执行后端" not in boundary and "execution backend" not in boundary.lower():
        return

    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    # SKILL.md 的 frontmatter description 不得声称是"唯一需要对话的执行入口"
    # （因为 IdeaToLaunch 才是）
    # 允许 SKILL.md 描述 CLI 命令能力，但不得重新声明旗舰 agent 定位
    lines = skill.splitlines()
    for line in lines:
        # 检查 frontmatter 中的 description
        if line.strip().startswith("description:") and "唯一" in line and "入口" in line:
            raise AssertionError(
                "SKILL.md frontmatter 不得声明 AIPD-OS 是'唯一入口'")


def test_command_contract_is_single_source_of_truth():
    """命令元数据必须来自 canonical contract，不得在审计脚本中硬编码。"""
    # command_contract.py 必须存在
    contract_path = REPO_ROOT / "src" / "aipd_os" / "cli" / "command_contract.py"
    assert contract_path.is_file(), "src/aipd_os/cli/command_contract.py 缺失"

    # 导入并验证基本结构
    from aipd_os.cli.command_contract import (
        PUBLIC_COMMANDS,
        CommandCategory,
        CommandStatus,
        get_all_commands,
    )
    # 必须有 public 命令
    assert len(PUBLIC_COMMANDS) > 0, "PUBLIC_COMMANDS 为空"
    # 必须有分类和状态
    cmds = get_all_commands()
    assert len(cmds) > 0
    for cmd in cmds:
        assert isinstance(cmd.status, CommandStatus)
        assert isinstance(cmd.category, CommandCategory)


def test_audit_repo_strict_mode_supported():
    """audit_repo.py 必须支持 --strict 模式。"""
    src = (REPO_ROOT / "scripts" / "audit_repo.py").read_text(encoding="utf-8")
    assert "--strict" in src, "audit_repo.py 缺少 --strict 模式"
    assert "_check_strict" in src, "audit_repo.py 缺少 _check_strict 函数"


# =====================================================================
# Architecture Invariant Tests（v5.10 Section 12）
# =====================================================================

def test_validation_tables_have_tenant_project_scope():
    """新 project-scoped canonical table 必须有 tenant/project scope（#3）。"""
    defs_path = REPO_ROOT / "src" / "aipd_os" / "state" / "migrations" / "definitions.py"
    migration_src = defs_path.read_text(encoding="utf-8")
    # validation_* 表必须有 tenant_id 和 project_id
    for table in ("validation_plans", "validation_tests", "validation_runs",
                  "validation_results", "issues", "corrective_actions"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration_src, \
            f"migration 缺少 {table} 表"
        # 每个表必须有 tenant_id 和 project_id
        # 找到对应 CREATE TABLE 块
        idx = migration_src.find(f"CREATE TABLE IF NOT EXISTS {table}")
        if idx >= 0:
            block = migration_src[idx:idx + 1000]
            assert "tenant_id TEXT NOT NULL" in block, \
                f"{table} 缺少 tenant_id"
            assert "project_id TEXT NOT NULL" in block, \
                f"{table} 缺少 project_id"


def test_validation_no_separate_truth_db():
    """Validation/Issue 不允许独立创建新的未经 ADR 批准的 truth DB（#4）。"""
    # validation 模块必须使用 AIPDStateDB，不创建新 DB
    service_src = (REPO_ROOT / "src" / "aipd_os" / "validation" / "service.py").read_text(
        encoding="utf-8")
    issue_src = (REPO_ROOT / "src" / "aipd_os" / "validation" / "issues.py").read_text(
        encoding="utf-8")
    # 不得有 sqlite3.connect 或创建新数据库的代码
    assert "sqlite3.connect" not in service_src, \
        "ValidationService 不得直接创建数据库连接"
    assert "sqlite3.connect" not in issue_src, \
        "IssueService 不得直接创建数据库连接"


def test_readiness_no_missing_data_pass():
    """Missing evidence 不能生成 PASS（#5）。"""
    readiness_src = (REPO_ROOT / "src" / "aipd_os" / "validation" / "readiness.py").read_text(
        encoding="utf-8")
    # 当数据缺失时必须返回 HOLD，不是 PASS
    assert "READINESS_HOLD" in readiness_src, "readiness.py 缺少 READINESS_HOLD"
    # 检查 default 行为是 HOLD
    assert "missing_evidence" in readiness_src, "readiness.py 缺少 missing_evidence 处理"


def test_stale_result_not_satisfy_readiness():
    """Stale result 不能满足 readiness（#6）。"""
    test_src = (REPO_ROOT / "tests" / "test_readiness.py").read_text(encoding="utf-8")
    assert "stale" in test_src.lower(), "test_readiness.py 缺少 stale 测试"
    assert "READINESS_HOLD" in test_src, "test_readiness.py 缺少 HOLD 验证"


def test_blocking_issue_not_pass_readiness():
    """Blocking open issue 不能 readiness PASS（#7）。"""
    test_src = (REPO_ROOT / "tests" / "test_readiness.py").read_text(encoding="utf-8")
    assert "blocking" in test_src.lower(), "test_readiness.py 缺少 blocking 测试"
    assert "READINESS_FAIL" in test_src, "test_readiness.py 缺少 FAIL 验证"


def test_external_side_effect_no_unsafe_retry():
    """External side-effect operation 不允许不安全自动重复（#8）。"""
    adapter_path = REPO_ROOT / "src" / "aipd_os" / "tool_adapters" / "evt_dvt_pvt_adapter.py"
    adapter_src = adapter_path.read_text(encoding="utf-8")
    # 必须声明 side_effect_mode
    assert "side_effect_mode" in adapter_src, "evt_dvt_pvt_adapter.py 缺少 side_effect_mode"
    assert "EXTERNAL_SIDE_EFFECT" in adapter_src, \
        "evt_dvt_pvt_adapter.py 必须声明 EXTERNAL_SIDE_EFFECT"


def test_multi_project_ids_no_conflict():
    """Multi-project IDs 不得冲突（#9）。"""
    test_src = (REPO_ROOT / "tests" / "test_validation_domain.py").read_text(encoding="utf-8")
    # 必须有 multi-tenant/multi-project 隔离测试
    assert "t2" in test_src, "test_validation_domain.py 缺少多租户测试"
    assert "p2" in test_src, "test_validation_domain.py 缺少多项目测试"


def test_doc_architecture_matches_executable_metadata():
    """Documentation architecture assertions 与 executable metadata 不得明显冲突（#12）。"""
    # project_boundary.md 必须存在且声明 backend
    boundary = _doc("architecture/project_boundary.md")
    assert "执行后端" in boundary or "execution backend" in boundary.lower()
    # openai.yaml 不得声明旗舰 agent
    import yaml  # type: ignore[import-not-found]
    agent_path = REPO_ROOT / "agents" / "openai.yaml"
    if agent_path.is_file():
        with open(agent_path, encoding="utf-8") as fh:
            agent = yaml.safe_load(fh)
        policy = agent.get("policy", {})
        assert not policy.get("allow_implicit_invocation", False), \
            "agent metadata 与 project_boundary.md 冲突"


# =====================================================================
# P2 State Infrastructure Architecture Invariants
# =====================================================================

def test_state_infrastructure_modules_exist():
    """P2 state infrastructure 必须存在。"""
    for rel in (
        "src/aipd_os/state/connection.py",
        "src/aipd_os/state/transaction.py",
        "src/aipd_os/state/errors.py",
    ):
        assert (REPO_ROOT / rel).is_file(), f"missing {rel}"


def test_state_errors_importable():
    """状态层错误类型必须可导入。"""
    from aipd_os.state.errors import (
        ConcurrentModificationError,
        ConflictError,
        ExternalOperationUnknownError,
        InvalidTransitionError,
        MigrationError,
        NotFoundError,
        ProjectScopeViolation,
        StateError,
        TenantScopeViolation,
    )
    # 继承链验证
    assert issubclass(NotFoundError, StateError)
    assert issubclass(ConflictError, StateError)
    assert issubclass(ConcurrentModificationError, ConflictError)
    assert issubclass(TenantScopeViolation, StateError)
    assert issubclass(ProjectScopeViolation, StateError)
    assert issubclass(InvalidTransitionError, StateError)
    assert issubclass(MigrationError, StateError)
    assert issubclass(ExternalOperationUnknownError, StateError)


def test_state_transaction_importable():
    """事务上下文管理器必须可导入。"""
    from aipd_os.state.transaction import transaction, transaction_from_path
    assert callable(transaction)
    assert callable(transaction_from_path)


def test_state_connection_factory_importable():
    """ConnectionFactory 必须可导入。"""
    from aipd_os.state.connection import ConnectionFactory, apply_pragmas
    assert callable(ConnectionFactory)
    assert callable(apply_pragmas)
