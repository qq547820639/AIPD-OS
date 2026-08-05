"""评估 case 与行为契约注册。

- :func:`load_cases`：把 ``evals/evals.json`` 的静态 case 转成可运行的 :class:`Case`。
- :data:`BEHAVIOR_CONTRACTS`：10 个行为契约清单。
- :data:`CONTRACT_TO_STRATEGY`：每个契约的评估策略（dialogue 用假/真模型 + score_response；
  logic 用实际代码驱动，见 ``runner`` / golden 夹具与行为契约测试）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# 10 个行为契约
BEHAVIOR_CONTRACTS: List[str] = [
    "no_long_questionnaire",       # 不发长问卷
    "only_ask_when_necessary",     # 只在必要决策询问
    "attachment_continuity",       # 连续附件继承
    "no_fabricated_params",        # 参数不臆造
    "visual_failure_auto_rework",  # 视觉失败自动返工
    "faceted_cad_no_overclaim",    # Faceted CAD 不越级
    "no_fake_supplier_quote",      # 供应商报价不伪造
    "no_claim_without_test",       # 测试未执行不宣称通过
    "no_cross_session_repeat",     # 跨会话不重复询问
    "key_dimension_propagation",   # 关键尺寸变更正确传播
]

# 需要真实模型/外部端点的契约（其余均可确定性评估）
MODEL_GATED_CONTRACTS = {"no_long_questionnaire"}

# 该契约是否由实际代码驱动（而非仅靠假/真模型文本）
LOGIC_CONTRACTS = {
    "only_ask_when_necessary",
    "attachment_continuity",
    "no_fabricated_params",
    "visual_failure_auto_rework",
    "faceted_cad_no_overclaim",
    "no_fake_supplier_quote",
    "no_claim_without_test",
    "no_cross_session_repeat",
    "key_dimension_propagation",
}


@dataclass
class Case:
    """单个可运行评估用例。"""

    id: str
    prompt: str
    must: List[str] = field(default_factory=list)
    must_not: List[str] = field(default_factory=list)
    contracts: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def contract(self) -> Optional[str]:
        """主契约（取第一项）。"""
        return self.contracts[0] if self.contracts else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "must": self.must,
            "must_not": self.must_not,
            "contracts": self.contracts,
        }


def load_cases(evals_json_path: str) -> List[Case]:
    """读取 evals.json，转换为可运行的 Case 列表。"""
    path = Path(evals_json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    cases: List[Case] = []
    for item in data.get("cases", []):
        contracts = item.get("contracts") or ([] if item.get("contract") is None else [item["contract"]])
        cases.append(
            Case(
                id=item["id"],
                prompt=item.get("prompt", ""),
                must=list(item.get("must", [])),
                must_not=list(item.get("must_not", [])),
                contracts=list(contracts),
                meta={"version": data.get("version")},
            )
        )
    return cases


__all__ = [
    "BEHAVIOR_CONTRACTS",
    "MODEL_GATED_CONTRACTS",
    "LOGIC_CONTRACTS",
    "Case",
    "load_cases",
]
