"""WBX-1 黄金样本视觉差距评测测试。

- (a) 构造合成 batch_state + pages_dir（用 PIL 生成 2480x3508 白图）调用
  golden_gap_evaluate，断言结构/键齐全、overall 为 float。
- (b) 图像后端不可用诚实性：页面 PNG 缺失时评测如实报失败而非假装成功。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os.visual_audit.auditor import A4_PX  # noqa: E402
from aipd_os.visual_audit.golden import GoldenGapEvaluator, golden_gap_evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_MANIFEST = ROOT / "evals" / "wbx1_golden_reference_manifest.json"


def _make_defn(page_id: str = "p1") -> dict:
    return {
        "page_id": page_id,
        "role": "cover",
        "title": "产品手册封面",
        "body": ["正文内容"],
        "caption": "封面配图",
        "rendered_by_us": True,
        "page_number": 1,
    }


def _write_a4_png(path: Path) -> None:
    img = Image.new("RGB", A4_PX, (255, 255, 255))
    img.save(str(path))


def _batch_state(defns) -> dict:
    return {
        "batch_runs": [
            {
                "batch_id": "b1",
                "prior_batch": None,
                "output_pages": [{"page_id": d["page_id"], "defn": d} for d in defns],
            }
        ]
    }


def test_golden_manifest_exists():
    assert GOLDEN_MANIFEST.exists(), "缺少 WBX-1 黄金清单"
    assert "golden_reference_registered" in GOLDEN_MANIFEST.read_text(encoding="utf-8")


def test_golden_gap_evaluate_structure(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    defn = _make_defn()
    _write_a4_png(pages_dir / "p1.png")
    result = golden_gap_evaluate(_batch_state([defn]), str(pages_dir), str(GOLDEN_MANIFEST))

    # 顶层键
    assert set(result) == {"pages", "overall", "passed"}
    assert isinstance(result["overall"], float)
    assert isinstance(result["passed"], bool)
    assert len(result["pages"]) == 1

    page = result["pages"][0]
    assert page["page_id"] == "p1"
    assert isinstance(page["score"], float)
    assert isinstance(page["dims"], dict)
    # 15 个维度键齐全
    assert set(page["dims"]) == set(GoldenGapEvaluator.DIMENSIONS)
    for name, d in page["dims"].items():
        assert isinstance(d["score"], float), name
        assert 0.0 <= d["score"] <= 1.0, name
        assert "note" in d, name


def test_golden_gap_missing_render_reports_failure(tmp_path):
    """PNG 缺失时如实报失败，绝不假装成功。"""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    defn = _make_defn()
    # 不写 p1.png -> 页面渲染缺失
    result = golden_gap_evaluate(_batch_state([defn]), str(pages_dir), str(GOLDEN_MANIFEST))

    assert len(result["pages"]) == 1
    page = result["pages"][0]
    assert page["render_missing"] is True
    assert page["score"] == 0.0
    assert result["passed"] is False
    assert result["overall"] == 0.0


def test_golden_gap_missing_manifest_fails_honestly(tmp_path):
    """黄金清单缺失/损坏时诚实返回失败，不抛导致评估中断。"""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    defn = _make_defn()
    _write_a4_png(pages_dir / "p1.png")
    missing = tmp_path / "nope.json"
    result = golden_gap_evaluate(_batch_state([defn]), str(pages_dir), str(missing))
    assert result["passed"] is False
    assert result["pages"] == []
    assert "error" in result
