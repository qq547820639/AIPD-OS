# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 80 片（装配步骤 PDF 版式）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
PDF = ROOT / "src/aipd_os/cad/assembly_steps_pdf.py"
GEN = ROOT / "src/aipd_os/cad/assembly_steps.py"
CLI = ROOT / "src/aipd_os/cli/commands_drawing.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_assembly_steps_pdf.py"]

ARMS = [
    {"id": "X1-frame-only-on-page-one", "file": PDF,
     "note": "长文档第二页没图框没页码 ⇒ 版式在真实长度下悄悄失效",
     "old": '        y = _frame(c, (pages := pages + 1), part_name, revision)',
     "new": '        y = h - MARGIN - LINE_H\n        pages += 1'},
    {"id": "X2-pdf-drops-the-shared-projection", "file": GEN,
     "note": "PDF 不用生成器算好的表 ⇒ 两份投影可以各少一行还都自洽",
     "old": '            columns=columns, table=table,',
     "new": '            columns=columns, table=[],'},
    {"id": "X3-pdf-key-omitted-not-none", "file": GEN,
     "note": "没要 PDF 就省键 ⇒ 读者分不出「没要」与「要了但没生成」",
     "old": '        "pdf": pdf,',
     "new": '        **({"pdf": pdf} if pdf else {}),'},
    {"id": "X4-cjk-drawn-with-a-latin-font", "file": PDF,
     "note": "正文改用 Helvetica ⇒ 中文不出字：「文件生成了」与「文件里有内容」是两件事",
     "old": '            c.setFont(FONT, size)',
     "new": '            c.setFont("Helvetica", size)'},
    {"id": "X5-explicit-pdf-path-ignored", "file": CLI,
     "note": "给 --pdf PATH 却永远落在同名 .pdf ⇒ 旗子的取值被静默忽略",
     "old": '        pdf_path = (out.with_suffix(".pdf") if pdf_arg == "@AUTO@" else Path(pdf_arg))',
     "new": '        pdf_path = out.with_suffix(".pdf")'},
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
