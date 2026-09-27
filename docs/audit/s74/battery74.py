# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 74 片（具名轴样本）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TGT = ROOT / "scripts/absence_claim_census.py"
PY_BIN = str(ROOT / ".venv/bin/python")

ARMS = [
    {"id": "Q1-validation-never-runs",
     "note": "把校验改成永远返回空表 ⇒ 真语料那条断言照样绿，只有接线控制能红",
     "old": '    if root.resolve() != Path(__file__).resolve().parent.parent:\n        return []',
     "new": '    if True:\n        return []'},
    {"id": "Q2-axis-without-sample-not-reported",
     "note": "某档没有样本时不报 ⇒ 有人删光对照也能自绿",
     "old": '            problems.append(f"axis_without_sample: 档 {axis} 没有具名样本")',
     "new": '            pass'},
    {"id": "Q3-mismatch-check-disabled",
     "note": "落错轴不再报 ⇒ 词表被改到让样本换档时没人知道",
     "old": '            if not any(got == axis for _b, got in hits):',
     "new": '            if False:'},
    {"id": "Q4-missing-sample-not-reported",
     "note": "样本找不到时静默跳过 ⇒ 样本会随登记表漂成空壳",
     "old": '                problems.append(f"sample_missing: 档 {axis} 的样本「{key[:28]}」"\n'
              '                                "在语料里找不到（登记表改了文案，样本要跟着改，不能删了事）")\n'
              '                continue',
     "new": '                continue  # 电池臂 Q4：静默跳过，不报 sample_missing'},
    {"id": "Q5-sample-string-drifted",
     "note": "把一条真语料样本改成不存在的文案 ⇒ 真语料那条测试必须红",
     "old": '    "non-claim": ("圆内没有图线即判未收口",',
     "new": '    "non-claim": ("这句被改得不存在了-电池臂",'},
]


def sha():
    return hashlib.sha256(TGT.read_bytes()).hexdigest()[:12]


def step(label):
    if label == "self-test":
        cmd = [PY_BIN, str(TGT), "--self-test"]
    else:
        cmd = [PY_BIN, "-m", "pytest", "tests/test_absence_claim_census.py",
               "-q", "--no-header", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                          timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines()
            if "passed" in ln or "failed" in ln or "Error" in ln][-1:]
    return proc.returncode, keep[0][:70] if keep else ""


def main():
    src = TGT.read_text(encoding="utf-8")
    base = sha()
    rows = []
    for arm in ARMS:
        old, new = arm["old"], arm["new"]
        if src.count(old) != 1:
            rows.append((arm["id"], "BAD-ANCHOR", f"old 命中 {src.count(old)} 次"))
            continue
        if new in src:
            rows.append((arm["id"], "BAD-ANCHOR", "new 已在树上"))
            continue
        mutated = src.replace(old, new, 1)
        try:
            compile(mutated, str(TGT), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc)))
            continue
        TGT.write_text(mutated, encoding="utf-8")
        try:
            assert sha() != base, "落地失败"
            rcs = [step("self-test")]
            rcs.append(step("pytest"))
        finally:
            TGT.write_text(src, encoding="utf-8")
            assert sha() == base, "还原失败"
        killed = any(rc != 0 for rc, _ in rcs)
        rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                     " ;; ".join(t for _rc, t in rcs)))
    print(f"基线 sha={base}")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}  {d[:110]}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {k} / 其余 {len(rows) - k}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
