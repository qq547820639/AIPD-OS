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


class _FakeVisionProvider:
    """测试替身：available()=True，audit() 返回固定「通过」结果。"""

    def available(self) -> bool:
        return True

    def audit(self, image_path: str, question: str, context: dict | None = None) -> dict:
        return {"passed": True, "score": 1.0, "conclusion": "ok", "dimensions": {}}


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


def test_vision_dims_not_faked_with_backend_string(tmp_path):
    """P1-1 修复：仅传 vision_backend 字符串（无真实 provider）不得假通过。"""
    png = tmp_path / "p1.png"
    _write_png(png)

    auditor = VisualAuditor(vision_backend="mock")  # 字符串标识，非真实 provider
    result = auditor.audit_page(_make_defn(), str(png))

    dims = result["dimensions"]
    for name in VISION_DIMS:
        assert name in dims, f"审计器应输出 {name} 维度"
        assert dims[name]["passed"] is False, name
        assert dims[name]["requiring_vision"] is True, name

    assert result["vision_pending"] == list(VISION_DIMS)


def test_vision_dims_pass_with_real_provider(tmp_path):
    """注入真实可用 provider 时，按真实审核结果判定 passed/requiring_vision。"""
    png = tmp_path / "p1.png"
    _write_png(png)

    auditor = VisualAuditor(vision_provider=_FakeVisionProvider())
    result = auditor.audit_page(_make_defn(), str(png))

    dims = result["dimensions"]
    for name in VISION_DIMS:
        assert name in dims, f"审计器应输出 {name} 维度"
        assert dims[name]["passed"] is True, name
        assert dims[name]["requiring_vision"] is False, name

    assert result["vision_pending"] == []


def test_vision_provider_rejects_non_bool_passed(tmp_path):
    """回归：provider 返回字符串 "false"/"no" 等非布尔 passed 不得被 truthy 化。

    修复前 ``bool("false")`` 为 True → 视觉审核假通过；现在非布尔一律不通过。
    """
    from aipd_os.visual_audit.providers import VisionAuditProvider

    class _StringFalseProvider:
        def available(self) -> bool:
            return True

        def audit(self, image_path: str, question: str,
                  context: dict | None = None) -> dict:
            return {"passed": "false", "score": 1.0, "conclusion": "not ok",
                    "dimensions": {}}

    png = tmp_path / "p1.png"
    _write_png(png)
    auditor = VisualAuditor(vision_provider=_StringFalseProvider())
    result = auditor.audit_page(_make_defn(), str(png))
    dims = result["dimensions"]
    for name in VISION_DIMS:
        assert dims[name]["passed"] is False, name

    # provider 层自身也必须做布尔强校验
    class _FakeResponse:
        status = 200

    provider = VisionAuditProvider(url="http://unused.invalid", api_key="k")
    # 直接断言解析逻辑：passed 非布尔 → False + parse_error 标记
    import json as _json
    import urllib.request

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self) -> bytes:
            return _json.dumps({
                "choices": [{"message": {"content":
                    _json.dumps({"passed": "false", "score": 0.9})}}],
                "usage": {}}).encode()

    import unittest.mock as _mock
    with _mock.patch.object(urllib.request, "urlopen", return_value=_Resp()):
        out = provider.audit(str(png), "q")
    assert out["passed"] is False
    assert out["parse_error"] is True
    assert out["score"] == 0.9
