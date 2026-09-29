#!/usr/bin/env python3
"""Z10 存活的原因：把那一支臂单独落地一次，直接打印读数，不靠电池的黑盒判决。

电池说 SURVIVED ⇒ 要么"这一族真的没被任何用例看见"，要么"变异根本没到达判决点"。
两者在读数上不同：前者会给出 placeholder，后者会给出与原件一样的 dead。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "docs/audit/s90"))
spec = importlib.util.spec_from_file_location("b90", REPO / "docs/audit/s90/battery90.py")
b90 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b90)

CEN = REPO / "scripts" / "doc_command_census.py"
arm = [a for a in b90.ARMS if a[0].startswith("Z10")][0]
edits = b90.pairs(arm)
original = CEN.read_bytes()
text = original.decode("utf-8")
mut = text
for o, n in edits:
    assert mut.count(o) == 1, (arm[0], mut.count(o))
    mut = mut.replace(o, n, 1)
try:
    CEN.write_text(mut, encoding="utf-8")
    print("变异已落地，字节差 =", len(mut) - len(text))
    for i, (o, n) in enumerate(edits):
        print(f"  编辑{i}: 命中且替换（新文本长度 {len(n)}）")
    rc, out = b90.run_tests()
    print("pytest rc =", rc)
    tail = [ln for ln in out.splitlines()
            if ln.startswith(("FAILED", "ERROR", "passed", "failed", "E  "))]
    print("\n".join(tail[:20]))
finally:
    CEN.write_bytes(original)
    assert CEN.read_bytes() == original, "复位失败"
print("已复位 sha =", b90.sha(CEN.read_bytes()))
