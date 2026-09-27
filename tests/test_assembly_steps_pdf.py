"""装配步骤的 PDF 版式（F-ASSEMBLY-PDF，第 80 片）。

第 56 片留的话是"版式只有 Markdown，PDF/图框未做"。这一片补上，验收方式刻意
**不看文件大小**：reportlab 内置 CID 字体出的中文是**可抽取**的，
所以每条断言都用 pypdf 独立解码回来核——文件存在只证明写了字节，不证明写得对。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aipd_os.cad.assembly_steps import (  # noqa: E402
    NOT_COVERED,
    generate_assembly_steps,
)


def _manifest(tmp_path: Path, steps: list[dict]) -> Path:
    parts = [{"name": "支架", "balloon": 1, "step": "支架.step"},
             {"name": "压板", "balloon": 2, "step": "压板.step"}]
    for one in parts:
        (tmp_path / one["step"]).write_bytes(b"ISO-10303-21;HEADER;")
    file = tmp_path / "assy.json"
    file.write_text(json.dumps({"parts": parts, "assembly_steps": steps},
                               ensure_ascii=False), encoding="utf-8")
    return file


def _clean_steps() -> list[dict]:
    return [{"no": 1, "action": "支架贴合基面", "balloons": [1]},
            {"no": 2, "action": "压板压在支架上并拧至规定扭矩", "balloons": [1, 2]}]


def _text(path: Path) -> str:
    return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)


def test_pdf_carries_every_declared_step_in_chinese(tmp_path: Path) -> None:
    man = _manifest(tmp_path, _clean_steps())
    out = tmp_path / "steps.md"
    pdf = tmp_path / "steps.pdf"
    ev = generate_assembly_steps(out, manifest=str(man), part_name="ASSY-77",
                                 revision="B", pdf_path=pdf)
    assert pdf.is_file() and pdf.read_bytes()[:5] == b"%PDF-"
    text = _text(pdf)
    for probe in ("ASSY-77", "Rev B", "支架贴合基面", "压板压在支架上并拧至规定扭矩"):
        assert probe in text, probe
    assert ev["pdf"]["pages"] >= 1 and ev["pdf"]["chars"] > 0, ev["pdf"]
    assert len(ev["pdf"]["sha256"]) == 64, ev["pdf"]


def test_pdf_and_markdown_come_from_one_projection(tmp_path: Path) -> None:
    """两边内容必须同源：Markdown 里有的步骤，PDF 里一步不许少。

    这条是"两处各写一遍"的反证——第 52/53 片同一格：
    两份投影里最坏的错不是格式不同，而是**其中一份少了一行**还各自都自洽。
    """
    man = _manifest(tmp_path, _clean_steps())
    out = tmp_path / "steps.md"
    pdf = tmp_path / "steps.pdf"
    generate_assembly_steps(out, manifest=str(man), part_name="ASSY-77",
                            revision="A", pdf_path=pdf)
    md = out.read_text(encoding="utf-8")
    text = _text(pdf)
    md_steps = [ln.split("：", 1)[1].strip() for ln in md.splitlines()
                if ln.startswith("## 步骤 ")]
    # 比**整行**而不是比零件名：件名会出现在步骤动作里（"支架贴合基面"含"支架"），
    # 只比名字的话，PDF 少掉整张零件清单也照样绿——电池 X2 就是把 table 传成空表。
    md_rows = [ln.strip().strip("|").strip() for ln in md.splitlines()
               if ln.startswith("| ") and "ITEM" not in ln and "---" not in ln]
    assert md_steps, "夹具前提：Markdown 里要有步骤标题"
    lines = [ln.strip() for ln in text.splitlines()]
    # Markdown 写的是 "## 步骤 2：<action>"，PDF 排版成 "步骤 2：<action>"：
    # 比的是"每条动作一字不差地出现在某一页的某一行里"，不是整行相等。
    for action in md_steps:
        assert any(action in ln for ln in lines), (action, lines[:6])
    assert md_rows, "夹具前提：Markdown 里要有零件清单行"
    for row in md_rows:
        # Markdown 用 "| a | b |"，PDF 排成 "a | b"：去空格后必须逐行相等
        assert any(row.replace(" ", "") == ln.replace(" ", "") for ln in lines), \
            (row, lines[:8])
    assert "本文档不承载" in text and NOT_COVERED[0][:6] in text, text[:400]


def test_frame_and_page_numbers_appear_on_every_page(tmp_path: Path) -> None:
    """图框是每页都画的：第二页没页码就等于版式在长内容下悄悄失效。"""
    many = [{"no": i, "action": f"第 {i} 步动作说明，写得长一些以便跨页" * 6,
             "balloons": [1, 2]} for i in range(1, 15)]
    man = _manifest(tmp_path, many)
    out = tmp_path / "steps.md"
    pdf = tmp_path / "steps.pdf"
    ev = generate_assembly_steps(out, manifest=str(man), part_name="ASSY-LONG",
                                 revision="A", pdf_path=pdf)
    reader = PdfReader(str(pdf))
    assert len(reader.pages) >= 2, len(reader.pages)
    assert ev["pdf"]["pages"] == len(reader.pages), ev["pdf"]
    for index, page in enumerate(reader.pages, 1):
        assert f"第 {index} 页" in (page.extract_text() or ""), index


def test_pdf_key_is_explicit_none_when_not_requested(tmp_path: Path) -> None:
    """没要 PDF 时写 None，而不是省略键：读者要能区分"没要"与"要了但没生成"。"""
    man = _manifest(tmp_path, _clean_steps())
    ev = generate_assembly_steps(tmp_path / "steps.md", manifest=str(man),
                                 part_name="ASSY-77", revision="A")
    assert "pdf" in ev and ev["pdf"] is None, sorted(ev)


def test_cli_flag_lands_the_pdf_next_to_the_markdown(tmp_path: Path) -> None:
    from aipd_os.cli.main import main

    man = _manifest(tmp_path, _clean_steps())
    out = tmp_path / "steps.md"
    rc = main(["drawing", "assembly-steps", "--manifest", str(man),
               "--out", str(out), "--part", "ASSY-CLI", "--revision", "C",
               "--pdf"])
    assert rc == 0, rc
    pdf = out.with_suffix(".pdf")
    assert pdf.is_file(), sorted(p.name for p in tmp_path.iterdir())
    text = _text(pdf)
    assert "ASSY-CLI" in text and "Rev C" in text, text[:300]


def test_explicit_pdf_path_is_honoured(tmp_path: Path) -> None:
    from aipd_os.cli.main import main

    man = _manifest(tmp_path, _clean_steps())
    target = tmp_path / "sub" / "作业指导书.pdf"
    rc = main(["drawing", "assembly-steps", "--manifest", str(man),
               "--out", str(tmp_path / "steps.md"), "--part", "ASSY-CLI",
               "--pdf", str(target)])
    assert rc == 0, rc
    assert target.is_file(), target
    assert "装配步骤：ASSY-CLI" in _text(target)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
