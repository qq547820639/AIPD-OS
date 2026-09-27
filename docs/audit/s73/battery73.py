"""第 73 片（分类器子句粒度 + 三轴账）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TGT = ROOT / "scripts/absence_claim_census.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_absence_claim_census.py"]

ARMS = [
    {"id": "M1-clause-split-narrowed",
     "note": "把逗号、顿号从子句切分里去掉 ⇒ 回到整句判，同句里的谈口径又把真缺失挡掉",
     "old": '    clauses = [c for c in re.split(r"[。；;，、]", body) if c.strip()]',
     "new": '    clauses = [c for c in re.split(r"[。；;]", body) if c.strip()]'},
    {"id": "M2-non-claim-list-emptied",
     "note": "清空「谈判决」排除表 ⇒ 那一轴变空，账目与下界必须发现它被改废了",
     "old": 'NON_CLAIM_PATTERNS = ("不算收口", "不写任何公差", "即判未收口", "记成盲区",\n'
            '                      "不会被伪装成", "不能用来放行", "读者不会把")',
     "new": 'NON_CLAIM_PATTERNS = ()',
     "id_check": True},
    {"id": "M3-noun-list-emptied",
     "note": "能力名词表被清空 ⇒ 判据面塌成 0，下界守卫要红",
     "old": 'CAPABILITY_NOUNS = ("执行器", "生产者", "实现", "接入", "映射", "路", "入口", "求解",',
     "new": 'CAPABILITY_NOUNS = ("__nothing__",'},
    {"id": "M4-classifier-always-narrow",
     "note": "分类器什么都判成能力缺失 ⇒ 三轴账与「未处置」两头都会炸",
     "old": '    clauses = [c for c in re.split(r"[。；;，、]", body) if c.strip()]',
     "new": '    clauses = [body] if body.strip() else []\n'
            '    if clauses:\n        return "narrow", ""'},
]


def sha():
    return hashlib.sha256(TGT.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header",
                           "-p", "no:cacheprovider",
                           "tests/test_supervisor_execution.py"],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines() if "passed" in ln or "failed" in ln][-1:]
    return proc.returncode, keep[0][:80] if keep else ""


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
            assert sha() != base
            rc, line = run_tests()
        finally:
            TGT.write_text(src, encoding="utf-8")
            assert sha() == base
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line))
    print(f"基线 sha={base}")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}  {d}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {k} / 其余 {len(rows) - k}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
