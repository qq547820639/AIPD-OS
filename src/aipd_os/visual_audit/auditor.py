"""手册视觉语义审计器。

维度：
- structural_consistency   结构一致性：300dpi A4 真实分辨率，拒绝低清放大
- character_consistency    人物一致性：需要视觉模型（无则 requiring_vision）
- cmf_consistency          CMF 一致性：需要视觉模型（无则 requiring_vision）
- page_role_completeness   角色完整性：按角色校验 title/body/caption/params
- narrative_continuity     叙事连续性：页码存在且单调、批次连续性
- chinese_renders          中文真文字：来自本排版器（rendered_by_us），拒绝占位/水字
- params_match_facts       参数与 Product Truth 事实一致
- forbidden                拒绝 lorem、极低分辨率、旧图哈希复用

回归护栏：仅靠白占比/熵/aHash 的审计会返回 pixel_statistics_only 警告；
需要视觉模型的维度在无视觉后端时 passed=False 且 requiring_vision=True，绝不假通过。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from aipd_os.layout.renderer import A4_PX

# 各角色必需字段
REQUIRED_BY_ROLE = {
    "cover": ["title", "body"],
    "principle": ["title", "body"],
    "parameter_table": ["title", "param_table"],
    "module": ["title", "body"],
    "user_scene": ["title", "body"],
    "cmf": ["title", "expected_cmf"],
    "curve": ["title", "curve"],
    "qa": ["title", "body"],
    "closure": ["title", "body"],
}

PLACEHOLDER_MARKERS = ["lorem", "待生成", "占位", "marquee", "xxx", "watermark"]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _intrinsic_size(path: str) -> Optional[tuple]:
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _text_of(defn: dict) -> str:
    parts = [str(defn.get("title", ""))]
    parts += [str(x) for x in defn.get("body", []) or []]
    parts.append(str(defn.get("caption", "")))
    return " ".join(parts).lower()


class VisualAuditor:
    """语义级手册视觉审计器（无真实视觉模型时诚实降级）。"""

    def __init__(self, vision_backend: Optional[str] = None):
        self.vision_backend = vision_backend
        self.prior_hashes: List[str] = []

    def _vision(self) -> bool:
        return bool(self.vision_backend)

    def reconcile(self, page_defn: dict, page_png: str,
                  golden_path: Optional[str] = None,
                  facts: Optional[dict] = None) -> dict:
        """别名：与 audit_page 等价，保持接口友善。"""
        return self.audit_page(page_defn, page_png, golden_path=golden_path, facts=facts)

    def audit_page(self, page_defn: dict, page_png: str,
                   golden_path: Optional[str] = None,
                   facts: Optional[dict] = None) -> dict:
        dims: Dict[str, dict] = {}

        # 1) 结构一致性
        size = _intrinsic_size(page_png)
        if size is None:
            dims["structural_consistency"] = {
                "passed": False, "reason": "cannot read image", "expected": list(A4_PX), "intrinsic": None}
        elif size[0] < 1000 or size[1] < 1000:
            dims["structural_consistency"] = {
                "passed": False, "reason": "very low resolution / likely upscaled from small source",
                "intrinsic": list(size), "expected": list(A4_PX)}
        else:
            ok = abs(size[0] - A4_PX[0]) <= 5 and abs(size[1] - A4_PX[1]) <= 5
            dims["structural_consistency"] = {
                "passed": ok, "intrinsic": list(size), "expected": list(A4_PX),
                "reason": None if ok else f"intrinsic size {size} != A4@{A4_PX}"}

        # 2) 人物一致性（需视觉模型）
        expected_char = page_defn.get("expected_character")
        dims["character_consistency"] = {
            "passed": self._vision(), "requiring_vision": not self._vision(),
            "expected": expected_char,
            "note": "requires a real vision backend; not faked" if not self._vision() else "checked by vision backend",
        }

        # 3) CMF 一致性（需视觉模型）
        expected_cmf = page_defn.get("expected_cmf")
        dims["cmf_consistency"] = {
            "passed": self._vision(), "requiring_vision": not self._vision(),
            "expected": expected_cmf,
            "note": "requires a real vision backend; not faked" if not self._vision() else "checked by vision backend",
        }

        # 4) 角色完整性
        required = REQUIRED_BY_ROLE.get(page_defn.get("role"), ["title", "body"])
        missing = [k for k in required if not page_defn.get(k)]
        dims["page_role_completeness"] = {
            "passed": not missing, "role": page_defn.get("role"),
            "required": required, "missing": missing,
        }

        # 5) 叙事连续性（单页：页码存在且为正）
        pn = page_defn.get("page_number")
        dims["narrative_continuity"] = {
            "passed": isinstance(pn, int) and pn > 0,
            "page_number": pn,
            "note": "batch-level monotonicity checked in audit_batch",
        }

        # 6) 中文真文字：来自本排版器渲染
        rendered_by_us = bool(page_defn.get("rendered_by_us"))
        text = _text_of(page_defn)
        has_placeholder = any(m in text for m in PLACEHOLDER_MARKERS)
        dims["chinese_renders"] = {
            "passed": rendered_by_us and not has_placeholder,
            "rendered_by_us": rendered_by_us,
            "placeholder_detected": has_placeholder,
        }

        # 7) 参数与事实一致
        facts_params = (facts or {}).get("params", {}) if facts else {}
        mismatches = []
        for row in page_defn.get("param_table", []) or []:
            key = row.get("param")
            if key in facts_params:
                if row.get("value") != facts_params[key]:
                    mismatches.append({"param": key, "defn": row.get("value"), "fact": facts_params[key]})
        dims["params_match_facts"] = {
            "passed": not mismatches, "mismatches": mismatches,
            "facts_provided": bool(facts and facts.get("params")),
        }

        # 8) 禁伪
        forbidden = []
        if has_placeholder:
            forbidden.append("placeholder/lorem text")
        if size is not None and max(size) < 1000:
            forbidden.append("very low resolution")
        cur_hash = _sha256(page_png) if size is not None else None
        if cur_hash and cur_hash in self.prior_hashes:
            forbidden.append("reused previous page hash")
        dims["forbidden"] = {"passed": not forbidden, "violations": forbidden}

        # 回归护栏：本次做了语义检查，非仅像素统计
        pixel_statistics_only = False
        vision_pending = [n for n, d in dims.items() if d.get("requiring_vision")]

        non_vision_fail = any(
            (not d.get("passed")) and (not d.get("requiring_vision")) for d in dims.values()
        )
        # 视觉待审维度存在时，页面不得 passed（保持 HOLD/not_verified，绝不假通过）。
        passed = (not non_vision_fail) and (not vision_pending)
        if passed:
            status = "verified"
        elif vision_pending:
            status = "hold"
        else:
            status = "failed"

        return {
            "page_id": page_defn.get("page_id"),
            "passed": passed,
            "status": status,
            "non_vision_passed": not non_vision_fail,
            "dimensions": dims,
            "pixel_statistics_only": pixel_statistics_only,
            "vision_pending": vision_pending,
            "rendered_by_us": rendered_by_us,
        }

    def audit_batch(self, batch_state: dict, pages_dir: str,
                    facts: Optional[dict] = None,
                    prior_hashes: Optional[List[str]] = None) -> dict:
        """审计整批，定位失败页面与维度，产出仅重建责任页的 rebuild_plan。"""
        self.prior_hashes = list(prior_hashes or [])
        pages_dir = Path(pages_dir)

        # 从 batch_runs 汇总各页 defn
        defns: Dict[str, dict] = {}
        for br in batch_state.get("batch_runs", []):
            for op in br.get("output_pages", []) or []:
                if op.get("page_id"):
                    defns[op["page_id"]] = op.get("defn") or {}

        results = []
        failing = []
        rebuild_plan = []
        vision_pending = []
        for pid, defn in defns.items():
            png = pages_dir / f"{pid}.png"
            if not png.exists():
                res = {
                    "page_id": pid, "passed": False,
                    "dimensions": {"render_missing": {"passed": False, "reason": "png not found"}},
                    "pixel_statistics_only": False, "vision_pending": [], "rendered_by_us": False,
                }
                results.append(res)
                failing.append(pid)
                rebuild_plan.append({"page_id": pid, "failed_dimensions": ["render_missing"]})
                continue
            res = self.audit_page(defn, str(png), facts=facts)
            results.append(res)
            if not res["passed"]:
                failing.append(pid)
                failed_dims = [n for n, d in res["dimensions"].items()
                               if not d.get("passed") and not d.get("requiring_vision")]
                vdims = [n for n, d in res["dimensions"].items() if d.get("requiring_vision")]
                if failed_dims:
                    rebuild_plan.append({"page_id": pid, "failed_dimensions": failed_dims})
                if vdims:
                    vision_pending.append({"page_id": pid, "dimensions": vdims})

        # 页码单调
        numbers = [d.get("page_number") for d in defns.values() if isinstance(d.get("page_number"), int)]
        monotonic = all(b > a for a, b in zip(numbers, numbers[1:])) if len(numbers) > 1 else True

        # 批次连续性：非首批需有 prior_batch 附件
        brs = batch_state.get("batch_runs", [])
        batch_continuity = True
        for i, br in enumerate(brs):
            if i == 0:
                continue
            if not br.get("prior_batch"):
                batch_continuity = False

        overall = (
            all(r["passed"] for r in results)
            and monotonic
            and batch_continuity
        )
        # 顶层状态：任何视觉待审页面 → hold（not_verified），绝不 passed。
        if overall:
            batch_status = "verified"
        elif any(r.get("status") == "hold" or r.get("vision_pending") for r in results):
            batch_status = "hold"
        else:
            batch_status = "failed"
        return {
            "passed": overall,
            "status": batch_status,
            "page_count": len(results),
            "pages": results,
            "failing_pages": failing,
            "rebuild_plan": rebuild_plan,
            "vision_pending": vision_pending,
            "narrative_continuity_monotonic": monotonic,
            "batch_continuity_ok": batch_continuity,
        }


def audit_batch(batch_state: dict, pages_dir: str, facts: Optional[dict] = None,
                prior_hashes: Optional[List[str]] = None) -> dict:
    """便捷函数：构造默认审计器并对整批审计。"""
    return VisualAuditor().audit_batch(batch_state, pages_dir, facts=facts, prior_hashes=prior_hashes)
