"""WBX-1 黄金样本视觉差距评测（页面级）。

实现 :class:`GoldenGapEvaluator.evaluate`：对 batch 输出的每页复用
:class:`VisualAuditor.audit_page` 的既有语义维度（结构/角色/叙事/中文真文字等），
并叠加黄金专属检查（模块一致性、场景工厂写实度、文案来源、参数来源、拼版、
旧图复用、低清放大、伪文字、参数臆造）。

黄金清单（``evals/wbx1_golden_reference_manifest.json``）目前只登记了每页 PNG 的
sha256 与尺寸等元数据。凡评估维度需要但清单缺失的字段（模块集合、理论/文案全文、
事实参数），统一标记为 ``golden_missing`` 并以中性 0.5 分计，同时在 note 中说明，
绝不假装通过。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from aipd_os.visual_audit.auditor import (
    A4_PX,
    PLACEHOLDER_MARKERS,
    VisualAuditor,
    _intrinsic_size,
    _sha256,
    _text_of,
)

# 工厂写实场景关键词（可被 golden 的 factory_scene_keywords 覆盖）
DEFAULT_FACTORY_KEYWORDS = [
    "工厂", "车间", "产线", "装配", "工位", "焊接", "搬运", "生产现场",
    "factory", "workshop", "assembly",
]

# 拼版（plate-making）标记
_PLATE_RE = re.compile(r"(拼版|plate.?making|多页合并|排到同一图)", re.IGNORECASE)

# 需要 golden 提供字段、缺失时按 golden_missing 处理的维度
GOLDEN_DEP_FIELDS = {
    "module_consistency": "modules",
    "caption_from_theory": "copy_text",
    "params_from_fact_sheet": "params",
    "no_fabricated_params": "params",
}

DIMENSIONS: List[str] = [
    "structural_consistency",
    "character_consistency",
    "module_consistency",
    "cmf_consistency",
    "scene_factory_realism",
    "page_role_completeness",
    "narrative_continuity",
    "caption_from_theory",
    "params_from_fact_sheet",
    "chinese_real_text",
    "no_plate_making",
    "no_old_image_reuse",
    "no_lowres_upscale",
    "no_fake_text",
    "no_fabricated_params",
]


def _dim(score: float, passed: Optional[bool], note: str = "", **extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"score": round(float(score), 4), "passed": passed, "note": note}
    d.update(extra)
    return d


def _golden_missing(field: str) -> Dict[str, Any]:
    return _dim(
        0.5,
        None,
        note=f"golden_missing: 黄金清单缺少 '{field}' 字段，维度按中性 0.5 计，无法判真伪",
    )


def _bool_score(ok: bool) -> float:
    return 1.0 if ok else 0.0


class GoldenGapEvaluator:
    """页面级黄金样本差距评测器。"""

    DIMENSIONS = DIMENSIONS

    def __init__(self, vision_backend: Optional[str] = None) -> None:
        self.auditor = VisualAuditor(vision_backend=vision_backend)

    # -- 内部辅助 -----------------------------------------------------------

    @staticmethod
    def _prior_hashes(golden: dict) -> set:
        hashes = set()
        for item in (golden or {}).get("items", []) or []:
            h = item.get("sha256")
            if h:
                hashes.add(h)
        return hashes

    @staticmethod
    def _golden_facts(golden: dict) -> Optional[dict]:
        """从 golden 提取事实参数（兼容 facts / params 两种形态）。"""
        if not golden:
            return None
        if golden.get("facts") is not None:
            return golden["facts"]
        if golden.get("params") is not None:
            return {"params": golden["params"]}
        return None

    def _vision_dim(self, d: dict) -> Dict[str, Any]:
        """人物/CMF 等需要真实视觉模型的维度：无后端时诚实标记未验证。"""
        if d.get("requiring_vision") and not self.auditor._vision():
            return _dim(
                0.5,
                None,
                note="requires a real vision backend; not faked (golden_gap 未验证)",
                requiring_vision=True,
            )
        ok = bool(d.get("passed", False))
        return _dim(_bool_score(ok), ok, note=d.get("note") or "")

    @staticmethod
    def _params_mismatches(defn: dict, golden_facts: dict) -> List[str]:
        mism = []
        facts_params = (golden_facts or {}).get("params", {}) if golden_facts else {}
        for row in defn.get("param_table", []) or []:
            key = row.get("param")
            if key in facts_params and row.get("value") != facts_params[key]:
                mism.append(key)
        return mism

    # -- 主入口 -------------------------------------------------------------

    def evaluate(self, batch_state: dict, pages_dir: str, golden: dict) -> dict:
        """对整批页面做黄金差距评测，返回 ``{'pages', 'overall', 'passed'}``。"""
        defns: Dict[str, dict] = {}
        for br in batch_state.get("batch_runs", []):
            for op in br.get("output_pages", []) or []:
                if op.get("page_id"):
                    defns[op["page_id"]] = op.get("defn") or {}

        pages_dir = Path(pages_dir)
        prior = self._prior_hashes(golden)
        golden_facts = self._golden_facts(golden)
        module_set = (golden or {}).get("modules")
        copy_text = (golden or {}).get("copy_text")
        if not copy_text:
            copy_text = (golden or {}).get("theory")
        factory_kw = (golden or {}).get("factory_scene_keywords") or DEFAULT_FACTORY_KEYWORDS

        pages: List[Dict[str, Any]] = []
        for pid, defn in defns.items():
            png = pages_dir / f"{pid}.png"
            if not png.exists():
                dims = {d: _dim(0.0, False, note="render_missing: PNG 未找到") for d in self.DIMENSIONS}
                pages.append(
                    {"page_id": pid, "score": 0.0, "dims": dims, "render_missing": True}
                )
                continue
            page_score, dims = self._evaluate_page(
                defn, str(png), prior, golden_facts, module_set, copy_text, factory_kw
            )
            pages.append({"page_id": pid, "score": page_score, "dims": dims, "render_missing": False})

        overall = 0.0
        if pages:
            overall = sum(p["score"] for p in pages) / len(pages)
        passed = bool(pages) and overall >= 0.5 and not any(p.get("render_missing") for p in pages)
        return {"pages": pages, "overall": round(overall, 4), "passed": passed}

    def _evaluate_page(
        self,
        defn: dict,
        png: str,
        prior: set,
        golden_facts: Optional[dict],
        module_set: Any,
        copy_text: Any,
        factory_kw: List[str],
    ) -> tuple:
        aud = self.auditor.audit_page(
            defn, png, facts={"params": (golden_facts or {}).get("params", {})} if golden_facts else None
        )
        ad = aud["dimensions"]
        role = defn.get("role")
        text = _text_of(defn)
        dims: Dict[str, Dict[str, Any]] = {}

        # 1) 结构一致性（复用 audit_page）
        d = ad.get("structural_consistency", {})
        ok = bool(d.get("passed", False))
        dims["structural_consistency"] = _dim(_bool_score(ok), ok, note=d.get("reason") or "")

        # 2) 人物一致性（需视觉模型）
        dims["character_consistency"] = self._vision_dim(ad.get("character_consistency", {}))

        # 3) 模块一致性：role=module 页须命中黄金模块集合
        if role == "module":
            if not module_set:
                dims["module_consistency"] = _golden_missing("modules")
            else:
                mod = defn.get("module") or defn.get("title")
                ok = mod in module_set
                dims["module_consistency"] = _dim(
                    _bool_score(ok), ok, module=mod,
                    note="" if ok else "page 模块(module)不在黄金模块集合内",
                )
        else:
            dims["module_consistency"] = _dim(1.0, True, note="非 module 页 (n/a)")

        # 4) CMF 一致性（需视觉模型）
        dims["cmf_consistency"] = self._vision_dim(ad.get("cmf_consistency", {}))

        # 5) 场景工厂写实度：role=user_scene 页须引用工厂写实场景关键词
        if role == "user_scene":
            ok = any(k in text for k in factory_kw)
            dims["scene_factory_realism"] = _dim(
                _bool_score(ok), ok,
                note="" if ok else "user_scene 未引用工厂写实场景关键词",
            )
        else:
            dims["scene_factory_realism"] = _dim(1.0, True, note="非 user_scene 页 (n/a)")

        # 6) 角色完整性（复用 audit_page）
        d = ad.get("page_role_completeness", {})
        ok = bool(d.get("passed", False))
        dims["page_role_completeness"] = _dim(
            _bool_score(ok), ok, note=f"缺失必需字段 {d.get('missing')}" if d.get("missing") else ""
        )

        # 7) 叙事连续性（复用 audit_page）
        d = ad.get("narrative_continuity", {})
        ok = bool(d.get("passed", False))
        dims["narrative_continuity"] = _dim(_bool_score(ok), ok, page_number=defn.get("page_number"))

        # 8) 文案来源：caption 须出现在黄金理论/文案全文
        caption = str(defn.get("caption", "")).strip()
        if not copy_text:
            dims["caption_from_theory"] = _golden_missing("copy_text")
        elif not caption:
            dims["caption_from_theory"] = _dim(0.0, False, note="page 无 caption")
        else:
            ok = caption in copy_text
            dims["caption_from_theory"] = _dim(
                _bool_score(ok), ok, note="" if ok else "caption 未出现在黄金理论/文案文本中"
            )

        # 9) 参数来源：param_table 值须命中黄金事实参数
        if golden_facts is None:
            dims["params_from_fact_sheet"] = _golden_missing("params")
        else:
            mism = self._params_mismatches(defn, golden_facts)
            ok = not mism
            dims["params_from_fact_sheet"] = _dim(_bool_score(ok), ok, mismatches=mism)

        # 10) 中文真文字（复用 audit_page chinese_renders）
        d = ad.get("chinese_renders", {})
        ok = bool(d.get("passed", False))
        dims["chinese_real_text"] = _dim(
            _bool_score(ok), ok,
            rendered_by_us=d.get("rendered_by_us"),
            placeholder=d.get("placeholder_detected"),
        )

        # 11) 拼版（无拼版标记）
        plate = _PLATE_RE.search(text)
        ok = plate is None
        dims["no_plate_making"] = _dim(_bool_score(ok), ok, note="检测到拼版/多页合并标记" if plate else "")

        # 12) 旧图复用：页面哈希不得命中黄金旧图哈希
        cur = _sha256(png)
        ok = cur not in prior
        dims["no_old_image_reuse"] = _dim(_bool_score(ok), ok, note="" if ok else "页面哈希命中黄金旧图(复用)")

        # 13) 低清放大：内部分辨率须接近 A4 (2480x3508)
        size = _intrinsic_size(png)
        ok = size is not None and abs(size[0] - A4_PX[0]) <= 5 and abs(size[1] - A4_PX[1]) <= 5
        dims["no_lowres_upscale"] = _dim(
            _bool_score(ok), ok, intrinsic=list(size) if size else None,
            note="" if ok else f"内部分辨率 {size} 非 A4@{A4_PX}",
        )

        # 14) 伪文字：无占位标记
        fake = any(m in text for m in PLACEHOLDER_MARKERS)
        ok = not fake
        dims["no_fake_text"] = _dim(_bool_score(ok), ok, note="检测到占位/伪文字标记" if fake else "")

        # 15) 参数不臆造：param_table 与黄金事实一致
        if golden_facts is None:
            dims["no_fabricated_params"] = _golden_missing("params")
        else:
            mism = self._params_mismatches(defn, golden_facts)
            ok = not mism
            dims["no_fabricated_params"] = _dim(_bool_score(ok), ok, mismatches=mism)

        page_score = sum(d["score"] for d in dims.values()) / len(dims)
        return page_score, dims


def golden_gap_evaluate(batch_state: dict, pages_dir: str, golden_path: str) -> dict:
    """便捷函数：从黄金清单路径加载并执行页面级差距评测。"""
    try:
        golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 清单缺失/损坏时诚实返回失败
        return {
            "pages": [],
            "overall": 0.0,
            "passed": False,
            "error": f"golden manifest 读取失败: {exc}",
        }
    return GoldenGapEvaluator().evaluate(batch_state, pages_dir, golden)


__all__ = ["GoldenGapEvaluator", "golden_gap_evaluate", "DIMENSIONS"]
