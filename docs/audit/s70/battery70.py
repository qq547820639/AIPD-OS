"""第 70 片新分支的变异电池（映射解析、连边、边数记账）。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
FL = ROOT / "src/aipd_os/supervisor/fact_lineage.py"
PY = str(ROOT / ".venv/bin/python")
TARGET_TESTS = ["tests/test_supervisor_fact_lineage.py",
                "tests/test_supervisor_fact_writeback.py"]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests(files):
    proc = subprocess.run([PY, "-m", "pytest", *files, "-q", "--no-header",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines() if "passed" in ln or "failed" in ln][-1:]
    return proc.returncode, keep[0][:90] if keep else ""


ARMS = [
    {"id": "G1-explicit-refs-ignored", "file": FL,
     "note": "不读 inputs 里的 truth_refs ⇒ 显式声明的上游静默失效",
     "old": '    for key in UPSTREAM_KEYS:\n        raw = inputs.get(key)',
     "new": '    for key in ():\n        raw = inputs.get(key)'},
    {"id": "G2-unknown-refs-swallowed", "file": FL,
     "note": "查不到的号不报出来 ⇒「声明过上游」假绿",
     "old": '                    unknown.append(rid)',
     "new": '                    pass'},
    {"id": "G3-no-edges-written", "file": FL,
     "note": "只解析不连边 ⇒ 传播永远走不到证据",
     "old": '            graph.add_edge(up, evidence_id, RELATION, conn=conn)',
     "new": '            pass'},
    {"id": "G4-edges-count-attempts", "file": FL,
     "note": "edges 退回「调用了几次」⇒ 重放被说成又连上了",
     "old": '    summary["edges"] = _count_rows() - before',
     "new": '    summary["edges"] = summary.get("attempted", 0) - 0'},
    {"id": "G5-receipt-column-misread", "file": FL,
     "note": "按 receipt 形状读 ledger 行（第 70 片真犯过的错）⇒ idea 解析永远 0",
     "old": '        raw = receipt.get("committed_truth_refs_json")',
     "new": '        raw = receipt.get("committed_truth_refs_json_DOES_NOT_EXIST")'},
]


def main():
    rows = []
    srcs = {t["file"]: t["file"].read_text(encoding="utf-8") for t in ARMS}
    bases = {k: sha(k) for k in srcs}
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
            assert sha(tgt) != bases[tgt]
            rc, line = run_tests(TARGET_TESTS)
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt]
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, verdict, detail in rows:
        print(f"[{verdict:11}] {rid}  {detail}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {k} / 其余 {len(rows) - k}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
