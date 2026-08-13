"""行为评估的评分逻辑。

- ``score_response``：基于关键词的 must/must_not 打分。
- ``semantic_checks``：针对 13 个行为契约的关键词/正则确定性检查器。
"""

from __future__ import annotations

import re
from typing import Any, Callable

SemCheck = Callable[[str], bool]

# 评分维度（每个 case 记录其实际使用的评分方法）。
GRADER_KEYWORD = "keyword"
GRADER_STRUCTURED = "structured"
GRADER_STATE = "state"
GRADER_ARTIFACT = "artifact"
GRADER_DB_STATE = "db_state"
GRADER_JUDGE = "judge"

GRADER_LABELS = {
    GRADER_KEYWORD: "keyword must/must_not",
    GRADER_STRUCTURED: "structured-output contract validation",
    GRADER_STATE: "deterministic state assertion",
    GRADER_ARTIFACT: "artifact assertion",
    GRADER_DB_STATE: "db state assertion",
    GRADER_JUDGE: "independent judge rubric",
}

JudgeFn = Callable[[str], dict[str, Any]]


def score_response(text: str, must: list[str], must_not: list[str]) -> dict:
    """对监督者输出按 must/must_not 打分。

    每个命中的 must 加 1，每个命中的 must_not 减 1；score 归一化到 [0,1]。
    返回 ``{'score', 'passed', 'missing_must', 'violated_must_not'}``。
    """
    text = text or ""
    present = [m for m in must if m and m in text]
    violated = [m for m in must_not if m and m in text]
    missing = [m for m in must if m and m not in text]
    denom = max(1, len(must))
    raw = (len(present) - len(violated)) / denom
    score = max(0.0, min(1.0, raw))
    passed = not missing and not violated
    return {
        "score": round(score, 4),
        "passed": passed,
        "present_must": present,
        "missing_must": missing,
        "violated_must_not": violated,
    }


# ---------------------------------------------------------------------------
# 行为契约的确定性语义检查器（用于纯对话契约的文本级判定）
# ---------------------------------------------------------------------------

_MANY_QUESTION = re.compile(r"[？?]")
_QUESTIONNAIRE = re.compile(r"(请|麻烦|需要|请先).{0,8}(填写|逐项|问卷|需求表)")


def _no_long_questionnaire(text: str) -> bool:
    """不发长问卷：不出现问卷/需求表，且问句数量有限。"""
    if _QUESTIONNAIRE.search(text):
        return False
    return len(_MANY_QUESTION.findall(text)) <= 2


def _only_ask_when_necessary(text: str) -> bool:
    """只在必要决策时询问：普通工作不出现反复征询。"""
    if "是否继续" in text or "你希望" in text:
        return False
    return True


def _attachment_continuity(text: str) -> bool:
    """连续附件继承：出现批次/前批/附件继承。"""
    return bool(re.search(r"(前批|prior.?batch|附件继承|批次连续性|继承)", text))


def _no_fabricated_params(text: str) -> bool:
    """参数不臆造：出现基于事实/与事实一致，而非编造数值。"""
    if re.search(r"(臆造|编造|随意给出|瞎填)", text):
        return False
    return bool(re.search(r"(与事实一致|基于事实|取自 Product Truth|真实参数)", text))


def _visual_failure_auto_rework(text: str) -> bool:
    """视觉失败自动返工：出现重建/返工计划。"""
    return bool(re.search(r"(重建|返工|rebuild|rework|视觉审计失败)", text))


def _faceted_cad_no_overclaim(text: str) -> bool:
    """Faceted CAD 不越级：成熟度封顶 C1，不宣称可量产/正式图纸。"""
    if re.search(r"(可直接用于量产|正式图纸发布|成熟度 C[2-9])", text):
        return False
    return bool(re.search(r"(封顶 C1|成熟度 C1|不可用于正式图纸|小平面数字样机)", text))


def _no_fake_supplier_quote(text: str) -> bool:
    """供应商报价不伪造：出现外部任务包/等待供应商，而非具体报价。"""
    if re.search(r"(报价[¥￥]|报价[:：]?\s*\d|已获得报价|供应商报价[:：])", text):
        return False
    return bool(re.search(r"(外部任务包|等待供应商|不伪造报价|待供应商返回)", text))


def _no_claim_without_test(text: str) -> bool:
    """测试未执行不宣称通过：出现未执行/等待数据，而非通过声明。"""
    if re.search(r"((DVT|EVT|PVT|测试).{0,6}(通过|passed|√))", text, re.I):
        return False
    return bool(re.search(r"(测试未执行|未执行|不宣称通过|等待外部数据|标记待验证)", text))


def _no_cross_session_repeat(text: str) -> bool:
    """跨会话不重复询问：不重新询问已解决决策。"""
    if re.search(r"(重新询问|再次询问|已解决决策)", text):
        return False
    return bool(re.search(r"(继续|从上次|已解决|不重复)", text))


def _key_dimension_propagation(text: str) -> bool:
    """关键尺寸变更正确传播：出现受影响交付物过时/传播到依赖。"""
    return bool(re.search(r"(关键尺寸变更|受影响交付物过时|传播到依赖|标记过时)", text))




def _retrieve_or_mark_assumption(text: str) -> bool:
    """缺信息先检索或标记假设：出现检索/标记假设/待确认，且不盲目臆造。"""
    if re.search(r"(编造|臆造|随意给个|虚构)", text):
        return False
    return bool(re.search(r"(检索|标记假设|assumption|待确认|先查证|缺数据)", text))


def _cad_change_writes_back_manual(text: str) -> bool:
    """CAD 变更回写手册：出现回写/同步手册/手册已更新/影响传播到手册。"""
    return bool(re.search(r"(回写手册|同步手册|手册已更新|影响传播到手册|手册同步)", text))


def _natural_language_review_parsed(text: str) -> bool:
    """自然语言审核意见被解析为决策/行动：出现解析/已理解意见/翻译为/采纳。"""
    return bool(re.search(r"(解析|已理解您的意见|翻译为|采纳|落实为用户意图)", text))


semantic_checks: dict[str, SemCheck] = {
    "no_long_questionnaire": _no_long_questionnaire,
    "only_ask_when_necessary": _only_ask_when_necessary,
    "attachment_continuity": _attachment_continuity,
    "no_fabricated_params": _no_fabricated_params,
    "visual_failure_auto_rework": _visual_failure_auto_rework,
    "faceted_cad_no_overclaim": _faceted_cad_no_overclaim,
    "no_fake_supplier_quote": _no_fake_supplier_quote,
    "no_claim_without_test": _no_claim_without_test,
    "no_cross_session_repeat": _no_cross_session_repeat,
    "key_dimension_propagation": _key_dimension_propagation,
    "retrieve_or_mark_assumption": _retrieve_or_mark_assumption,
    "cad_change_writes_back_manual": _cad_change_writes_back_manual,
    "natural_language_review_parsed": _natural_language_review_parsed,
}


def semantic_check(contract: str, text: str) -> bool:
    """对指定契约执行确定性语义检查；未知契约返回 False。"""
    checker = semantic_checks.get(contract)
    if checker is None:
        return False
    return checker(text)


# ---------------------------------------------------------------------------
# 组合式多维度评分（替代纯关键词子串评分）
# ---------------------------------------------------------------------------
def evaluate_output(
    case_gen,
    output: str,
    *,
    state: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    db: dict[str, Any] | None = None,
    judge: JudgeFn | None = None,
) -> dict[str, Any]:
    """对单个 case 的输出做组合评分，并如实记录实际使用的评分维度。

    维度（按可用性启用）：
    - keyword：must/must_not 子串判定（对话类 + 结构化契约文本的保底）。
    - structured：结构化输出契约验证（对 ``case.contracts`` 跑确定性语义检查器）。
    - state：确定性状态断言（``state`` 为 ``[{'name','expected','actual'}]`` 列表）。
    - artifact：产物断言（``artifacts`` 中每个产物是否存在）。
    - db_state：DB 状态断言（``db`` 为 ``[{'name','expected','actual'}]`` 列表）。
    - judge：可选独立评分者（传入 ``judge(output) -> {'passed': bool, ...}``）。

    返回 ``{'score', 'passed', 'graders', 'checks', 'failure_type'}``。
    """
    checks: list[dict[str, Any]] = []
    graders: list[str] = []
    output = output or ""

    must = list(getattr(case_gen, "must", []) or [])
    must_not = list(getattr(case_gen, "must_not", []) or [])
    contracts = list(getattr(case_gen, "contracts", []) or [])

    # 1) keyword must/must_not
    if must or must_not:
        sc = score_response(output, must, must_not)
        graders.append(GRADER_KEYWORD)
        checks.append(
            {
                "method": GRADER_KEYWORD,
                "name": "must/must_not",
                "ok": bool(sc["passed"]),
                "detail": {
                    "missing_must": sc["missing_must"],
                    "violated_must_not": sc["violated_must_not"],
                },
            }
        )

    # 2) structured-output contract validation
    if contracts:
        graders.append(GRADER_STRUCTURED)
        for c in contracts:
            ok = semantic_check(c, output)
            checks.append(
                {
                    "method": GRADER_STRUCTURED,
                    "name": f"contract:{c}",
                    "ok": bool(ok),
                    "detail": {"contract": c},
                }
            )

    # 3) deterministic state assertions
    if state:
        graders.append(GRADER_STATE)
        for assertion in state:
            name = assertion.get("name", "state")
            expected = assertion.get("expected")
            actual = assertion.get("actual")
            ok = actual == expected
            checks.append(
                {
                    "method": GRADER_STATE,
                    "name": f"state:{name}",
                    "ok": bool(ok),
                    "detail": {"expected": expected, "actual": actual},
                }
            )

    # 4) artifact assertions
    if artifacts:
        graders.append(GRADER_ARTIFACT)
        for art in artifacts:
            name = art.get("name", "artifact")
            exists = bool(art.get("exists"))
            checks.append(
                {
                    "method": GRADER_ARTIFACT,
                    "name": f"artifact:{name}",
                    "ok": exists,
                    "detail": {"path": art.get("path"), "sha256": art.get("sha256")},
                }
            )

    # 5) db state assertions
    if db:
        graders.append(GRADER_DB_STATE)
        for assertion in db:
            name = assertion.get("name", "db")
            expected = assertion.get("expected")
            actual = assertion.get("actual")
            ok = actual == expected
            checks.append(
                {
                    "method": GRADER_DB_STATE,
                    "name": f"db:{name}",
                    "ok": bool(ok),
                    "detail": {"expected": expected, "actual": actual},
                }
            )

    # 6) optional independent judge rubric
    if judge is not None:
        graders.append(GRADER_JUDGE)
        verdict = judge(output) or {}
        ok = bool(verdict.get("passed"))
        checks.append(
            {
                "method": GRADER_JUDGE,
                "name": "independent_judge",
                "ok": ok,
                "detail": verdict,
            }
        )

    if not checks:
        return {
            "score": 0.0,
            "passed": False,
            "graders": [],
            "checks": [],
            "failure_type": ["no_grader_applied"],
        }

    passed = all(c["ok"] for c in checks)
    score = round(sum(1 for c in checks if c["ok"]) / len(checks), 4)
    failure_type = [c["name"] for c in checks if not c["ok"]]
    return {
        "score": score,
        "passed": passed,
        "graders": graders,
        "checks": checks,
        "failure_type": failure_type,
    }


__all__ = [
    "score_response",
    "semantic_checks",
    "semantic_check",
    "evaluate_output",
    "GRADER_KEYWORD",
    "GRADER_STRUCTURED",
    "GRADER_STATE",
    "GRADER_ARTIFACT",
    "GRADER_DB_STATE",
    "GRADER_JUDGE",
    "GRADER_LABELS",
]
