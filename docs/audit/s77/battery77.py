# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 77 片（取到字节 vs 抽出正文）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
FT = ROOT / "scripts/research/fetch_fulltexts.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_research_fulltext_step.py"]

ARMS = [
    {"id": "U1-whitespace-counts-as-text", "file": FT,
     "note": "去掉 strip 判空 ⇒ 只抽出空白的 PDF 会被标 extracted_pdf，而库里判 restricted（两个字段互相打脸）",
     "old": '    if not text.strip():\n        return "", "pdf_without_text"',
     "new": '    if False:\n        return "", "pdf_without_text"'},
    {"id": "U2-pdf-never-extracted", "file": FT,
     "note": "PDF 一律不抽 ⇒ 装了 pypdf 也说「缺抽取器」，能力名字又变虚",
     "old": '        if kind == KIND_PDF:\n            text, outcome = pdf_to_text(raw)',
     "new": '        if kind == KIND_PDF:\n            text, outcome = "", "needs_pdf_extractor"'},
    {"id": "U3-landing-page-becomes-fulltext", "file": FT,
     "note": "全文长度下界归零 ⇒ 一页摘要被报成拿到正文",
     "old": 'MIN_FULL_TEXT_CHARS = 2000',
     "new": 'MIN_FULL_TEXT_CHARS = 1'},
    {"id": "U4-pdf-magic-not-sniffed", "file": FT,
     "note": "不认 %PDF 头 ⇒ PDF 走 undecodable 分支，「开放但不开放」两种说法混在一起",
     "old": '    if raw[:5] == b"%PDF-":\n        return KIND_PDF',
     "new": '    if False:\n        return KIND_PDF'},
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines() if "passed" in ln or "failed" in ln][-1:]
    return proc.returncode, keep[0][:80] if keep else ""


def main():
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in ARMS}
    bases = {k: sha(k) for k in srcs}
    rows = []
    for arm in ARMS:
        tgt, old, new = arm["file"], arm["old"], arm["new"]
        src = srcs[tgt]
        if src.count(old) != 1:
            rows.append((arm["id"], "BAD-ANCHOR", f"old 命中 {src.count(old)} 次"))
            continue
        if new in src:
            rows.append((arm["id"], "BAD-ANCHOR", "new 已在树上"))
            continue
        mutated = src.replace(old, new, 1)
        try:
            compile(mutated, str(tgt), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc)))
            continue
        tgt.write_text(mutated, encoding="utf-8")
        try:
            assert sha(tgt) != bases[tgt], "落地失败"
            rc, line = run_tests()
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}  {d[:110]}")
    killed = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {killed} / 其余 {len(rows) - killed}")
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
