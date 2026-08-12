"""Status Semantics Contract（v5.8.2 Commit 2，Docs-as-Code 的一部分）。

锁定三个正交维度（epistemic_status / claim_assessment / definition_status），
防止文档或代码把：
- ``S`` 解释为 Supported、
- ``C`` 解释为 Contradicted、
- ``E`` 解释为 Evaluated、
- ``R`` 解释为 Rejected

重新写回（提示词 §6：正式定义必须保持三个正交维度）。

本测试读取 *当前仓库文本*（db.py 注释 + STATUS_SEMANTICS.md），保证文档与
代码事实绑定，避免文档长期反向误导。
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 正式 epistemic 语义（v5.8.2 锁定；与 db.FACT_STATUSES 一致）
CANONICAL_EPISTEMIC_STATUSES = frozenset({"V", "S", "C", "E", "A", "P", "T", "R", "U"})

# 正式语义描述（每项必须出现在 db.py 的 FACT_STATUSES 注释中）
CANONICAL_EPISTEMIC_MEANINGS = {
    "V": "Verified",
    "S": "Simulation",
    "C": "Calculation",
    "E": "External evidence",
    "A": "Assumption",
    "P": "Pending",
    "T": "Testable",
    "U": "Unknown",
    "R": "Retired",
}

# ClaimAssessment 状态（独立维度；见 idea/claim_assessment.py）
CLAIM_ASSESSMENT_STATUSES = frozenset({
    "SUPPORTED", "PARTIALLY_SUPPORTED", "MIXED", "CONTRADICTED",
    "INSUFFICIENT", "NOT_SEARCHED", "NOT_APPLICABLE",
})

# Definition Status（独立维度；为未来 Requirement/NPI 使用）
DEFINITION_STATUSES = frozenset({
    "CONFIRMED", "DERIVED", "RECOMMENDED", "ESTIMATED",
    "TBD", "CONFLICT", "OBSOLETE",
})


def _db_py_text() -> str:
    return (REPO_ROOT / "src" / "aipd_os" / "state" / "db.py").read_text(
        encoding="utf-8")


def _status_doc_text() -> str:
    return (REPO_ROOT / "docs" / "architecture" / "STATUS_SEMANTICS.md").read_text(
        encoding="utf-8")


# ---------------------------------------------------------------- epistemic
def test_epistemic_status_set_is_canonical():
    from aipd_os.state.db import FACT_STATUSES
    assert FACT_STATUSES == CANONICAL_EPISTEMIC_STATUSES


def test_epistemic_meanings_are_documented_in_db_code():
    """db.py 注释必须携带正式语义（防代码层回退）。"""
    text = _db_py_text()
    for value, meaning in CANONICAL_EPISTEMIC_MEANINGS.items():
        assert f"{value}=" in text, f"db.py missing meaning anchor for {value}"
        assert meaning in text, f"db.py missing meaning {meaning!r} for {value}"


def test_epistemic_doc_uses_simulation_not_supported():
    """文档 epistemic 表禁止写 S=Supported / C=Contradicted / E=Evaluated。"""
    doc = _status_doc_text()
    assert "| S | Simulation" in doc, \
        "STATUS_SEMANTICS.md must document S as Simulation (was Supported)"
    assert "| C | Calculation" in doc, \
        "STATUS_SEMANTICS.md must document C as Calculation (was Contradicted)"
    assert "| E | External evidence" in doc, \
        "STATUS_SEMANTICS.md must document E as External evidence (was Evaluated)"
    assert "| R | Retired" in doc, \
        "STATUS_SEMANTICS.md must document R as Retired (was Rejected)"
    # 旧错误映射彻底消失（任何行都不允许出现）
    for bad in ("| S | Supported", "| C | Contradicted", "| E | Evaluated",
                "| R | Rejected"):
        assert bad not in doc, f"forbidden mapping {bad!r} found in STATUS_SEMANTICS.md"


def test_epistemic_statuses_are_single_letters_only():
    """epistemic_status 是单字母枚举；ClaimAssessment 是多词枚举，互不混淆。"""
    assert all(len(s) == 1 for s in CANONICAL_EPISTEMIC_STATUSES)
    assert all(len(s) > 1 for s in CLAIM_ASSESSMENT_STATUSES)


# ---------------------------------------------------------------- assessment
def test_claim_assessment_statuses_are_independent():
    """ClaimAssessment 语义独立于 epistemic status（不映射为 S/C/E 等单字母）。"""
    from aipd_os.idea.claim_assessment import ASSESSMENT_STATUSES
    assert ASSESSMENT_STATUSES == CLAIM_ASSESSMENT_STATUSES
    # 与 epistemic 无交集
    assert not (ASSESSMENT_STATUSES & CANONICAL_EPISTEMIC_STATUSES)


def test_claim_assessment_has_no_single_letter_values():
    from aipd_os.idea.claim_assessment import ASSESSMENT_STATUSES
    assert all(len(s) > 1 for s in ASSESSMENT_STATUSES)


# ---------------------------------------------------------------- definition
def test_definition_statuses_are_independent():
    """Definition Status 是第三个正交维度（为 Requirement/NPI 使用）。"""
    # 与 epistemic / assessment 均无交集
    assert not (DEFINITION_STATUSES & CANONICAL_EPISTEMIC_STATUSES)
    assert not (DEFINITION_STATUSES & CLAIM_ASSESSMENT_STATUSES)


def test_status_doc_declares_three_orthogonal_dimensions():
    doc = _status_doc_text()
    assert "三个维度正交" in doc or "正交" in doc
    assert "definition_status" in doc
    assert "epistemic_status" in doc
    assert "lifecycle_status" in doc
    # 禁止映射表仍存在（反例防回归）
    assert "RECOMMENDED = A" in doc or "RECOMMENDED = A" in doc.replace("~~", "")


def test_definition_statuses_documented():
    doc = _status_doc_text()
    for value in DEFINITION_STATUSES:
        assert value in doc, f"definition status {value} missing from doc"


# ------------------------------------------------------------- independence
def test_three_dimensions_are_pairwise_disjoint():
    """三维度集合两两无交集（semantic independence contract）。"""
    assert not (CANONICAL_EPISTEMIC_STATUSES & DEFINITION_STATUSES)
    assert not (CANONICAL_EPISTEMIC_STATUSES & CLAIM_ASSESSMENT_STATUSES)
    assert not (DEFINITION_STATUSES & CLAIM_ASSESSMENT_STATUSES)
