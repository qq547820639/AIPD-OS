"""锚点注册表与 Visual Bible 结构。

记录产品结构、人物、模块、CMF、相机与光线的一致性约束，并从 Product Truth / 内容模型
构建后持久化到批次状态，供后续批次与视觉审计交叉校验（无视觉后端时不假通过）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 锚点页角色：封面、原理、参数表、模块主图（产品身份/安装结构语言）
ANCHOR_PAGE_ROLES = ["cover", "principle", "parameter_table", "module_main"]


@dataclass
class VisualBible:
    """Visual Bible：锁定人物、产品结构、模块、CMF、相机、光线的一致性基准。"""

    structure: str = ""
    characters: List[dict] = field(default_factory=list)
    modules: List[dict] = field(default_factory=list)
    cmf: Dict[str, str] = field(default_factory=dict)
    camera: Dict[str, str] = field(default_factory=dict)
    lighting: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_truth(cls, facts: dict) -> "VisualBible":
        facts = facts or {}
        return cls(
            structure=(facts.get("product") or {}).get("structure", ""),
            characters=list(facts.get("characters") or []),
            modules=list(facts.get("modules") or []),
            cmf=dict(facts.get("cmf") or {}),
            camera=dict(facts.get("camera") or {}),
            lighting=dict(facts.get("lighting") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "structure": self.structure,
            "characters": self.characters,
            "modules": self.modules,
            "cmf": self.cmf,
            "camera": self.camera,
            "lighting": self.lighting,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "VisualBible":
        d = d or {}
        return cls(
            structure=d.get("structure", ""),
            characters=list(d.get("characters") or []),
            modules=list(d.get("modules") or []),
            cmf=dict(d.get("cmf") or {}),
            camera=dict(d.get("camera") or {}),
            lighting=dict(d.get("lighting") or {}),
        )

    def consistency_constraints(self) -> dict:
        """输出跨页一致性约束（无视觉后端时供审计引用，不假通过）。"""
        return {
            "structure": self.structure,
            "characters": [c.get("appearance", "") for c in self.characters],
            "modules": [m.get("name", "") for m in self.modules],
            "cmf": self.cmf,
            "camera": self.camera,
            "lighting": self.lighting,
        }


@dataclass
class AnchorRegistry:
    """锚点注册表：记录产品结构、锚点页、人物、模块、CMF、相机、光线约束。"""

    anchors: List[dict] = field(default_factory=list)  # [{page_id, role}]
    product_structure: Dict[str, str] = field(default_factory=dict)
    characters: List[dict] = field(default_factory=list)
    modules: List[dict] = field(default_factory=list)
    cmf: Dict[str, str] = field(default_factory=dict)
    camera: Dict[str, str] = field(default_factory=dict)
    lighting: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, plan: list, facts: dict) -> "AnchorRegistry":
        facts = facts or {}
        anchors = [
            {"page_id": e.get("page_id"), "role": e.get("role")}
            for e in (plan or [])
            if e.get("role") in ANCHOR_PAGE_ROLES
        ]
        product = facts.get("product") or {}
        return cls(
            anchors=anchors,
            product_structure={"name": product.get("name", ""), "structure": product.get("structure", "")},
            characters=list(facts.get("characters") or []),
            modules=list(facts.get("modules") or []),
            cmf=dict(facts.get("cmf") or {}),
            camera=dict(facts.get("camera") or {}),
            lighting=dict(facts.get("lighting") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "anchors": self.anchors,
            "product_structure": self.product_structure,
            "characters": self.characters,
            "modules": self.modules,
            "cmf": self.cmf,
            "camera": self.camera,
            "lighting": self.lighting,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "AnchorRegistry":
        d = d or {}
        return cls(
            anchors=list(d.get("anchors") or []),
            product_structure=dict(d.get("product_structure") or {}),
            characters=list(d.get("characters") or []),
            modules=list(d.get("modules") or []),
            cmf=dict(d.get("cmf") or {}),
            camera=dict(d.get("camera") or {}),
            lighting=dict(d.get("lighting") or {}),
        )


__all__ = ["VisualBible", "AnchorRegistry", "ANCHOR_PAGE_ROLES"]