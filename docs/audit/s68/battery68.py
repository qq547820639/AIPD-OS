# ruff: noqa: E501
"""第 68 片 external_callers 档的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TARGET = ROOT / "scripts/absence_claim_census.py"
PY = str(ROOT / ".venv/bin/python")

ARMS = [
    {"id": "D1-defining-file-not-excluded",
     "note": "外部=全部调用点 ⇒ 同文件里的兼容包装算成生产入口（commit_snapshot 被读成已接上）",
     "old": '    external = [h for h in hits if h.split(":", 1)[0] not in defining]',
     "new": '    external = list(hits)',
     "probes": ["self-test", "pytest:gate_commit"]},
    {"id": "D2-defining-set-never-filled",
     "note": "不记录定义文件 ⇒ 与 D1 同效但从另一支产生，两支都要有各自的控制",
     "old": '                    defining.add(here)',
     "new": '                    pass',
     "probes": ["self-test", "pytest:gate_commit"]},
    {"id": "D3-empty-authority-folds-into-holds",
     "note": "生产面读不到任何文件时不报前提，直接给 0 处调用点 ⇒ 把「看不见」折成「这句话对」",
     "old": '    if scanned - only_registry_files <= 0:',
     "new": '    if False:',
     "probes": ["pytest:without_production_tree"]},
    {"id": "D4-probe-can-never-fire",
     "note": "present 恒 False ⇒ 真接上 CLI 也不会翻红（正是记忆里「探针恒零」的形状）",
     "old": '        return (bool(external), [f"{symbol} 生产面外部调用点 = {len(external)} 处"] + external,\n                problems)',
     "new": '        return (False, [f"{symbol} 生产面外部调用点 = {len(external)} 处"] + external,\n                problems)',
     "probes": ["self-test", "pytest:can_fire_positive"]},
]


def sha() -> str:
    return hashlib.sha256(TARGET.read_bytes()).hexdigest()[:12]


def run_probe(probe: str):
    if probe == "self-test":
        cmd = [PY, str(TARGET), "--self-test"]
    else:
        cmd = [PY, "-m", "pytest", "tests/test_absence_claim_census.py", "-k",
               probe.split(":", 1)[1], "-q", "--no-header", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines()
            if "passed" in ln or "failed" in ln or "Error" in ln][-2:]
    return probe, proc.returncode, " | ".join(k[:80] for k in keep)


def main() -> int:
    base, src = sha(), TARGET.read_text(encoding="utf-8")
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
            compile(mutated, str(TARGET), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc)))
            continue
        TARGET.write_text(mutated, encoding="utf-8")
        try:
            assert sha() != base
            readings = [run_probe(p) for p in arm["probes"]]
        finally:
            TARGET.write_text(src, encoding="utf-8")
            assert sha() == base
        killed = any(rc != 0 for _p, rc, _t in readings)
        rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                     " ;; ".join(f"{p}→rc={rc} {t}" for p, rc, t in readings)))
    print(f"基线 sha={base}")
    for rid, v, d in rows:
        print(f"[{v:12}] {rid}\n    {d}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {k} / 其余 {len(rows) - k}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
