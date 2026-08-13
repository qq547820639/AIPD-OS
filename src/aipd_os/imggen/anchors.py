"""Anchor Registry / Visual Bible / 可机器比较特征。

把人物锚点、产品结构锚点、CMF（颜色/材质/表面）锚点登记为可机器比较的特征
（颜色 HEX、结构关键点、CMF token），并把 Visual Bible 转成结构化约束供批次与
锚点比对。提供可机器比较接口：特征向量 / 哈希提取，以及两个锚点集的一致度比较。

与 ``aipd_os.imggen.registry`` 的差异：registry 偏“记录/持久化结构”，本模块聚焦
**可机器比较的特征提取与一致度计算**（颜色归一为 HEX、结构关键点、CMF token）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 认知色 -> 可机器比较的 HEX（用于颜色锚点归一化，避免“工程橙/金属灰”等自然语言歧义）
COLOR_HEX_MAP = {
    "工程橙": "#FF6A00",
    "金属灰": "#8A8D91",
    "银灰": "#B0B4B8",
    "深空灰": "#3A3A3C",
    "碳黑": "#2B2B2B",
    "黑色": "#1A1A1A",
    "白色": "#FFFFFF",
    "科技蓝": "#0A66FF",
    "苏联红": "#C8102E",
    "钛金": "#C9A05C",
}


def extract_hex(text: str) -> List[str]:
    """从文本提取颜色 HEX：既识别 ``#RRGGBB`` 字面量，也把认知色映射为 HEX。"""
    found = re.findall(r"#[0-9a-fA-F]{3,8}", text or "")
    for name, hx in COLOR_HEX_MAP.items():
        if name in (text or "") and hx not in found:
            found.append(hx)
    return found


def cmf_tokens(cmf: Optional[dict]) -> List[str]:
    """把 CMF（颜色/材质/表面）转成可比较 token 列表。"""
    out: List[str] = []
    for key in ("color", "material", "finish"):
        val = (cmf or {}).get(key)
        if val:
            out.append(f"{key}={val}")
    return out


@dataclass
class AnchorFeature:
    """一个可机器比较的锚点特征。

    kind 取值：person / structure / cmf / module / camera / lighting。
    """

    kind: str
    name: str
    color_hex: List[str] = field(default_factory=list)
    key_points: List[dict] = field(default_factory=list)
    cmf_tokens: List[str] = field(default_factory=list)

    def feature_vector(self) -> Tuple:
        """确定性有序特征向量，供哈希与一致度比较。"""
        return (
            self.kind,
            self.name,
            tuple(self.color_hex),
            tuple(json.dumps(p, ensure_ascii=False, sort_keys=True) for p in self.key_points),
            tuple(self.cmf_tokens),
        )

    def digest(self) -> str:
        """特征向量哈希（可机器比较）。"""
        payload = json.dumps(self.feature_vector(), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "color_hex": list(self.color_hex),
            "key_points": list(self.key_points),
            "cmf_tokens": list(self.cmf_tokens),
        }

    @classmethod
    def from_dict(cls, d: dict) -> AnchorFeature:
        return cls(
            kind=d.get("kind", ""),
            name=d.get("name", ""),
            color_hex=list(d.get("color_hex") or []),
            key_points=list(d.get("key_points") or []),
            cmf_tokens=list(d.get("cmf_tokens") or []),
        )


def features_from_facts(facts: Optional[dict]) -> List[AnchorFeature]:
    """从 Product Truth / 内容模型派生可比较锚点特征。"""
    facts = facts or {}
    features: List[AnchorFeature] = []

    cmf = facts.get("cmf") or {}
    features.append(
        AnchorFeature(
            kind="cmf",
            name="whole_product_cmf",
            color_hex=extract_hex(cmf.get("color", "")),
            cmf_tokens=cmf_tokens(cmf),
        )
    )

    for c in (facts.get("characters") or []):
        appearance = c.get("appearance", "")
        features.append(
            AnchorFeature(
                kind="person",
                name=c.get("name", "person"),
                color_hex=extract_hex(appearance),
                cmf_tokens=cmf_tokens({"color": appearance}),
            )
        )

    for i, m in enumerate(facts.get("modules") or []):
        features.append(
            AnchorFeature(
                kind="module",
                name=m.get("name", f"module_{i}"),
                key_points=[{"module": m.get("name", ""), "desc": m.get("desc", "")}],
            )
        )

    structure = (facts.get("product") or {}).get("structure", "")
    if structure:
        features.append(
            AnchorFeature(
                kind="structure",
                name="product_structure",
                key_points=[{"structure": structure}],
            )
        )
    return features


@dataclass
class VisualBible:
    """Visual Bible：把视觉圣经转成结构化约束，供批次与锚点比对。"""

    structure: str = ""
    characters: List[dict] = field(default_factory=list)
    modules: List[dict] = field(default_factory=list)
    cmf: Dict[str, str] = field(default_factory=dict)
    camera: Dict[str, str] = field(default_factory=dict)
    lighting: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_truth(cls, facts: Optional[dict]) -> VisualBible:
        facts = facts or {}
        return cls(
            structure=(facts.get("product") or {}).get("structure", ""),
            characters=list(facts.get("characters") or []),
            modules=list(facts.get("modules") or []),
            cmf=dict(facts.get("cmf") or {}),
            camera=dict(facts.get("camera") or {}),
            lighting=dict(facts.get("lighting") or {}),
        )

    def to_constraints(self) -> dict:
        """输出结构化约束：颜色 HEX、CMF token、结构关键点、人物外观等。"""
        return {
            "cmf": {
                "color_hex": extract_hex(self.cmf.get("color", "")),
                "tokens": cmf_tokens(self.cmf),
            },
            "characters": [
                {
                    "name": c.get("name", ""),
                    "appearance": c.get("appearance", ""),
                    "color_hex": extract_hex(c.get("appearance", "")),
                }
                for c in self.characters
            ],
            "structure": self.structure,
            "modules": [m.get("name", "") for m in self.modules],
            "camera": self.camera,
            "lighting": self.lighting,
        }

    def fingerprint(self) -> dict:
        con = self.to_constraints()
        digest = hashlib.sha256(
            json.dumps(con, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {"constraints": con, "digest": digest}

    def to_dict(self) -> dict:
        return self.to_constraints()


@dataclass
class AnchorRegistry:
    """锚点注册表：登记可机器比较的锚点特征 + 可选 Visual Bible。"""

    features: List[AnchorFeature] = field(default_factory=list)
    visual_bible: Optional[VisualBible] = None

    @classmethod
    def build(cls, facts: Optional[dict]) -> AnchorRegistry:
        return cls(features=features_from_facts(facts), visual_bible=VisualBible.from_truth(facts))

    def register(self, feature: AnchorFeature) -> None:
        self.features = [
            f for f in self.features if (f.kind, f.name) != (feature.kind, feature.name)
        ]
        self.features.append(feature)

    def fingerprint(self) -> Dict[str, Dict[str, str]]:
        """按 kind -> {name: digest} 输出可机器比较指纹。"""
        out: Dict[str, Dict[str, str]] = {}
        for f in self.features:
            out.setdefault(f.kind, {})[f.name] = f.digest()
        return out

    def compare(self, other: AnchorRegistry) -> dict:
        """比较两个注册表的一致度，返回按 kind 的一致度与总体 score。"""
        a = self.fingerprint()
        b = other.fingerprint()
        kinds = set(a) | set(b)
        per_kind: Dict[str, dict] = {}
        total_match = total = 0
        for k in sorted(kinds):
            da, db = a.get(k, {}), b.get(k, {})
            names = set(da) | set(db)
            match = sum(1 for n in names if da.get(n) == db.get(n))
            per_kind[k] = {
                "consistent": match,
                "total": len(names),
                "score": round((match / len(names)) if names else 1.0, 4),
            }
            total_match += match
            total += len(names)
        overall = round((total_match / total) if total else 1.0, 4)
        return {
            "overall_score": overall,
            "consistent": total_match,
            "total": total,
            "per_kind": per_kind,
        }

    def compare_page(self, page_features: List[AnchorFeature]) -> dict:
        """比较页面锚点特征与注册表一致度（可机器比较）。"""
        reg = {(f.kind, f.name): f.digest() for f in self.features}
        items = []
        for f in page_features:
            key = (f.kind, f.name)
            if key in reg:
                consistent = reg[key] == f.digest()
                items.append(
                    {
                        "kind": f.kind,
                        "name": f.name,
                        "consistent": consistent,
                        "expected": reg[key][:12],
                        "actual": f.digest()[:12],
                    }
                )
            else:
                items.append(
                    {
                        "kind": f.kind,
                        "name": f.name,
                        "consistent": False,
                        "expected": None,
                        "actual": f.digest()[:12],
                        "reason": "not in registry",
                    }
                )
        consistent = sum(1 for it in items if it["consistent"])
        score = round((consistent / len(items)) if items else 1.0, 4)
        return {"score": score, "consistent": consistent, "total": len(items), "items": items}

    def to_dict(self) -> dict:
        return {
            "features": [f.to_dict() for f in self.features],
            "visual_bible": self.visual_bible.to_dict() if self.visual_bible else None,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> AnchorRegistry:
        d = d or {}
        features = [AnchorFeature.from_dict(x) for x in (d.get("features") or [])]
        vb = None
        con = d.get("visual_bible")
        if con:
            vb = VisualBible(
                structure=con.get("structure", ""),
                characters=con.get("characters", []),
                modules=con.get("modules", []),
                cmf=con.get("cmf", {}),
                camera=con.get("camera", {}),
                lighting=con.get("lighting", {}),
            )
        return cls(features=features, visual_bible=vb)


__all__ = [
    "AnchorFeature",
    "AnchorRegistry",
    "VisualBible",
    "extract_hex",
    "cmf_tokens",
    "features_from_facts",
]
