"""AIPD-OS v5.3 回归护栏：手工视觉审计员诚实性。

当未配置视觉后端时，人物/CMF 一致性等需要视觉模型的维度
必须 passed=False 且 requiring_vision=True，绝不假通过。

注：当前审计器只实现 character_consistency 与 cmf_consistency 两个
需要视觉的维度（无 product_structure_consistency），因此只对已实现
的两个维度进行断言，并额外断言整体结果对这些维度标记 requiring_vision。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os.visual_audit.auditor import VisualAuditor  # noqa: E402

VISION_DIMS = ("character_consistency", "cmf_consistency")


def _make_defn() -> dict:
    return {
        "page_id": "p1",
        "role": "cover",
        "title": "封面",
        "body": ["正文"],
        "page_number": 1,
        "rendered_by_us": True,
    }


def _write_png(path: Path) -> None:
    img = Image.new("RGB", (1500, 2100), (255, 255, 255))
    img.save(str(path))


def test_vision_dims_not_faked_without_backend(tmp_path):
    """无视觉后端时，一致性维度必须 requiring_vision 且 passed=False。"""
    png = tmp_path / "p1.png"
    _write_png(png)

    auditor = VisualAuditor()  # 默认无视觉后端
    result = auditor.audit_page(_make_defn(), str(png))

    dims = result["dimensions"]

    # 每个已实现的一致性维度：passed=False 且 requiring_vision=True
    for name in VISION_DIMS:
        assert name in dims, f"审计器应输出 {name} 维度"
        assert dims[name]["requiring_vision"] is True, name
        assert dims[name]["passed"] is False, name
        assert "not faked" in dims[name]["note"], name
        assert "real vision backend" in dims[name]["note"], name

    # 结果把这些维度标记为 vision_pending，并未声称通过
    assert result["vision_pending"] == list(VISION_DIMS)
    for name in VISION_DIMS:
        assert name in result["vision_pending"]


def test_vision_dims_pass_with_backend(tmp_path):
    """提供视觉后端时，同一维度应 passed=True 且 requiring_vision=False。"""
    png = tmp_path / "p1.png"
    _write_png(png)

    auditor = VisualAuditor(vision_backend="mock")
    result = auditor.audit_page(_make_defn(), str(png))

    dims = result["dimensions"]
    for name in VISION_DIMS:
        assert name in dims, f"审计器应输出 {name} 维度"
        assert dims[name]["passed"] is True, name
        assert dims[name]["requiring_vision"] is False, name

    assert result["vision_pending"] == []
