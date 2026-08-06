"""面向产品所有者的自然语言意图引擎（P2-1）。

在既有 ``instructions`` 关键词解析之上，提供更强的确定性自然语言操作：
  - 同义词识别（批准/同意/没问题、成本/预算/价格 等）；
  - 上下文指代 / 代词解析（"它"/"这个方案"/"上次讨论的" 解析到最近决策或制品）；
  - 多条件指令（"成本降低 20% 并且 外观更工业化" 合并为多个约束）；
  - 纠错（"撤回/撤销/回滚/重新做"）；
  - 无法确定时只问**一个**最关键问题（返回单一澄清问题，而非一堆）。

纯关键词 + 正则，确定性输出，不依赖任何 LLM / 外部服务。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..state.db import AIPDStateDB

# --------------------------------------------------------------------------
# 同义词 / 触发词表
# --------------------------------------------------------------------------
# 批准类同义词
_APPROVE_WORDS = (
    "批准", "同意", "没问题", "可以", "好的", "通过", "就这样", "执行吧",
    "就按这个", "approve", "agreed", "go ahead", "ok",
)
_APPROVE_RE = re.compile("|".join(map(re.escape, _APPROVE_WORDS)), re.IGNORECASE)

# 成本类同义词
_COST_WORDS = ("成本", "价钱", "价格", "价位", "售价", "预算", "费用")
_COST_RE = re.compile(
    rf"(?:{'|'.join(_COST_WORDS)})[^0-9]*(\d+(?:\.\d+)?)\s*%")
_BARE_COST_RE = re.compile("|".join(map(re.escape, _COST_WORDS)))

# 工业化 / 避免医疗风
_INDUSTRIAL_RE = re.compile(r"工业化|更工业|工业风|硬朗风|专业感|科技感")
_MEDICAL_RE = re.compile(r"不要医疗|避免医疗|去医疗化|不要医疗风|别搞医疗|医疗风")

# 模块化 / 暂不进入实体制造
_KEEP_MODULAR_RE = re.compile(r"保留模块化|保持模块化|模块化设计")
_HALT_PHYSICAL_RE = re.compile(
    r"暂不进入实体制造|不进入实体制造|暂缓实体制造|暂不进入量产|先不做实体|暂不量产")

# 选择某个方案
_CHOOSE_RE = re.compile(
    r"(?:选|选择|选方案|选择方案|用方案|采用方案|采取方案|就选)\s*([A-Za-z])"
    r"|方案\s*([A-Za-z])")

# 纠错 / 撤回
_REVERT_WORDS = ("撤回", "撤销", "取消上次", "回滚", "纠正", "重新做", "改回", "退了重来", "重置刚才")
_REVERT_RE = re.compile("|".join(map(re.escape, _REVERT_WORDS)))

# 代词 / 上下文指代
_PRONOUN_RE = re.compile(r"它|这个方案|那个方案|这个|那个|上次讨论的|刚才说的|上一步")

# 多条件连接词
_CONJ_RE = re.compile(r"并且|同时|还要|以及|而且|并且同时|and|and also|，同时|且同时", re.IGNORECASE)

# 制品引用
_ARTIFACT_RE = re.compile(r"@([\w\-\./\\]+)")

# 里程碑/阶段代号 → 中文（仅用于内部 details，不暴露给顶层正文）
_MILESTONE_CN = {
    "G0": "概念验证", "G1": "需求冻结", "G2": "方案定稿", "G3": "详细设计",
    "G4": "样机试制", "G5": "工程验证", "G6": "设计验证", "G7": "生产验证",
    "G8": "量产准备", "G9": "正式发布",
}


@dataclass
class Intent:
    """结构化意图。

    ``constraints`` 保存多条件指令的每一项（kind + params），
    ``ambiguous`` / ``clarifying_question`` 用于"无法确定只问一个问题"。
    """
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    target: Optional[str] = None
    propagated_impact: List[str] = field(default_factory=list)
    ambiguous: bool = False
    clarifying_question: Optional[str] = None
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    correction: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """可 JSON 序列化的意图表示。"""
        return {
            "kind": self.kind,
            "target": self.target,
            "params": dict(self.params),
            "ambiguous": self.ambiguous,
            "clarifying_question": self.clarifying_question,
            "constraints": list(self.constraints),
            "correction": self.correction,
            "propagated_impact": list(self.propagated_impact),
        }


def build_clarifying_question(kind: str) -> str:
    """返回单一最关键澄清问题（绝不返回多个）。"""
    if kind == "cost_reduction":
        return "成本要降低多少？例如：成本降低 20%。"
    if kind in ("approve", "choose"):
        return "您希望批准哪个方案？请直接说“批准”或“选 A/B”。"
    if kind == "style_constraint":
        return "您希望采用哪种外观风格？例如：工业化 / 避免医疗风。"
    return "您的指令不够明确，能否用一句话说明想要的效果？"


def _options_of(decision: Optional[Dict[str, Any]]) -> List[str]:
    """复用既有 instructions 的选项规整逻辑，把 options 规整为字符串列表。"""
    if not decision:
        return []
    raw = decision.get("options") or decision.get("options_json")
    if isinstance(raw, str):
        try:
            import json
            parsed = json.loads(raw)
        except Exception:  # noqa: BLE001
            parsed = None
        if isinstance(parsed, list):
            return [str(o) for o in parsed if str(o).strip()]
        if isinstance(parsed, str):
            raw = parsed
        elif parsed is not None:
            return []
        return [o.strip() for o in re.split(r"[/、,，|]", raw) if o.strip()]
    if isinstance(raw, list):
        return [str(o) for o in raw if str(o).strip()]
    return []


def _next_open_decision(db: AIPDStateDB, project_id: str,
                        tenant_id: str) -> Optional[Dict[str, Any]]:
    open_ds = db.list_open_decisions(tenant_id, project_id)
    return open_ds[0] if open_ds else None


def _resolve_context_target(text: str, context: Optional[Dict[str, Any]]) -> Optional[str]:
    """若文本含代词且上下文提供最近决策/制品，则把 target 解析到它。"""
    resolved: Optional[str] = None
    if not context:
        return None
    if _PRONOUN_RE.search(text):
        resolved = context.get("last_decision_id") or context.get("last_artifact_id")
    return resolved


def _record_constraint_for(kind: str, params: Dict[str, Any]) -> str:
    """为每一项约束生成人类可读的影响描述。"""
    if kind == "cost_reduction":
        pct = params.get("percentage", 0)
        return f"将成本目标降低 {pct:.0f}%"
    if kind == "style_constraint":
        style = params.get("style")
        avoid = params.get("avoid")
        if style:
            return {"industrial": "外观更工业化"}.get(style, f"采用{style}风格")
        return "避免" + (avoid or "医疗风") + "外观"
    if kind == "keep_modularity":
        return "保留模块化设计"
    if kind == "halt_physical_manufacturing":
        return "暂不进入实体制造"
    if kind == "approve":
        return "批准推荐方案"
    if kind == "choose":
        return f"选择方案：{params.get('choice') or '指定选项'}"
    return "调整当前方案"


def _parse_single(text: str, ambiguous_cost: Dict[str, bool]) -> Optional[Intent]:
    """解析单条指令为一个 Intent；无法确定时返回 ambiguous 的 Intent。"""
    artifact = _ARTIFACT_RE.search(text)
    artifact_target = artifact.group(1) if artifact else None

    # 1) 批准类同义词
    if _APPROVE_RE.search(text):
        return Intent(kind="approve", target=artifact_target,
                      params={"approve": True},
                      propagated_impact=["批准并推进当前待审方案"])

    # 2) 选择方案
    m = _CHOOSE_RE.search(text)
    if m:
        letter = (m.group(1) or m.group(2) or "").upper()
        return Intent(kind="choose", target=artifact_target,
                      params={"option_letter": letter},
                      propagated_impact=[f"选择方案 {letter}"])

    # 3) 成本降低（带百分比）
    cm = _COST_RE.search(text)
    if cm:
        pct = float(cm.group(1))
        return Intent(kind="cost_reduction", target=artifact_target,
                      params={"metric": "cost", "percentage": pct},
                      propagated_impact=[f"将成本目标降低 {pct:.0f}%"])

    # 4) 提到成本但没给百分比 → 无法确定，只问一个关键问题
    if _BARE_COST_RE.search(text):
        ambiguous_cost["cost"] = True
        return Intent(
            kind="cost_reduction", target=artifact_target,
            params={"metric": "cost"}, ambiguous=True,
            clarifying_question=build_clarifying_question("cost_reduction"),
            propagated_impact=["调整成本目标（未给出具体幅度）"])

    # 5) 工业化
    if _INDUSTRIAL_RE.search(text):
        return Intent(kind="style_constraint", target=artifact_target,
                      params={"style": "industrial", "avoid": None},
                      propagated_impact=["外观更工业化"])

    # 6) 避免医疗风
    if _MEDICAL_RE.search(text):
        return Intent(kind="style_constraint", target=artifact_target,
                      params={"style": None, "avoid": "medical"},
                      propagated_impact=["避免医疗风外观"])

    # 7) 保留模块化
    if _KEEP_MODULAR_RE.search(text):
        return Intent(kind="keep_modularity", target=artifact_target,
                      params={"constraint": "modularity"},
                      propagated_impact=["保留模块化设计"])

    # 8) 暂不进入实体制造
    if _HALT_PHYSICAL_RE.search(text):
        return Intent(kind="halt_physical_manufacturing", target=artifact_target,
                      params={"halt": "physical_manufacturing"},
                      propagated_impact=["暂不进入实体制造"])

    # 9) 纠错 / 撤回
    if _REVERT_RE.search(text):
        return Intent(kind="revert", target=artifact_target,
                      params={"revert": True}, correction=True,
                      propagated_impact=["回滚最近一次可撤销操作"])

    # 10) 引用具体制品
    if artifact_target:
        return Intent(kind="update_artifact", target=artifact_target,
                      params={"target": artifact_target},
                      propagated_impact=[f"更新制品 @{artifact_target}"])

    return None


def parse_intent(text: str, db: Optional[AIPDStateDB] = None,
                 project_id: Optional[str] = None,
                 tenant_id: str = "default",
                 context: Optional[Dict[str, Any]] = None) -> Intent:
    """把一句自然语言解析为结构化 :class:`Intent`。

    - 支持多条件（``并且/同时/还要``）合并为 ``constraints``；
    - 支持上下文指代（``context.last_decision_id`` 等）；
    - 无法确定时返回 ``ambiguous=True`` 的意图并给出**一个**澄清问题；
    - 可选传入 db/project_id 以解析"选 A"到具体选项文本。
    """
    text = (text or "").strip()
    if not text:
        return Intent(kind="unknown", params={"raw": ""}, ambiguous=True,
                      clarifying_question=build_clarifying_question("unknown"))

    # 纠错优先（"撤回上次操作"等）
    if _REVERT_RE.search(text):
        target = _resolve_context_target(text, context)
        return Intent(kind="revert", target=target, params={"revert": True},
                      correction=True,
                      propagated_impact=["回滚最近一次可撤销操作"])

    # 多条件拆分
    segments = [s.strip() for s in _CONJ_RE.split(text) if s.strip()]
    if len(segments) > 1:
        ambiguous_cost: Dict[str, bool] = {}
        parsed_segments = []
        for seg in segments:
            one = _parse_single(seg, ambiguous_cost)
            if one is not None:
                parsed_segments.append(one)
        if parsed_segments:
            primary = parsed_segments[0]
            primary.constraints = [
                {"kind": p.kind, "params": dict(p.params)} for p in parsed_segments
            ]
            # 若任一子条件无法确定，则整体需要澄清（只问那一个关键问题）
            if any(ambiguous_cost.values()):
                primary.ambiguous = True
                primary.clarifying_question = build_clarifying_question("cost_reduction")
            impact = []
            for p in parsed_segments:
                impact.extend(p.propagated_impact)
            primary.propagated_impact = impact
            return primary

    # 单条
    ambiguous_cost = {}
    single = _parse_single(text, ambiguous_cost)
    if single is not None:
        # 上下文指代解析 target
        if single.kind in ("approve", "choose") and single.target is None:
            single.target = _resolve_context_target(text, context)
        # 解析"选 A"到具体选项文本
        if single.kind == "choose" and db and project_id:
            dec = _next_open_decision(db, project_id, tenant_id)
            options = _options_of(dec)
            letter = single.params.get("option_letter", "")
            idx = ord(letter) - ord("A") if letter else -1
            if 0 <= idx < len(options):
                single.params["choice"] = options[idx]
                single.params["option_index"] = idx
                single.propagated_impact = [f"选择方案：{options[idx]}"]
            else:
                single.params["choice"] = None
        # 批准类：解析到具体待审决策并给出影响
        if single.kind == "approve" and db and project_id:
            dec = _next_open_decision(db, project_id, tenant_id)
            if dec:
                single.target = single.target or dec["decision_id"]
                single.params["decision_id"] = dec["decision_id"]
                single.params["topic"] = dec.get("topic")
                rec = dec.get("recommendation") or "推荐方案"
                single.propagated_impact = [
                    f"批准决策「{dec.get('topic')}」并采用推荐方案：{rec}"]
        return single

    # 未识别
    return Intent(kind="unknown", params={"raw": text},
                  propagated_impact=["更新当前方案"])


__all__ = ["Intent", "parse_intent", "build_clarifying_question"]