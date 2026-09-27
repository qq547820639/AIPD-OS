"""第 69 片变异电池：存在式登记的两个方向 + CLI 入口的四条牙。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
INSTRUMENT = ROOT / "scripts/absence_claim_census.py"
PRODUCT = ROOT / "src/aipd_os/cli/product_commands.py"
PARSER = ROOT / "src/aipd_os/cli/main.py"
PY = str(ROOT / ".venv/bin/python")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def probe(spec: str) -> tuple[str, int, str]:
    if spec == "self-test":
        cmd, label = [PY, str(INSTRUMENT), "--self-test"], "self-test"
    elif spec.startswith("file:"):
        rel = spec.split(":", 1)[1]
        cmd, label = [PY, "-m", "pytest", rel, "-q", "--no-header",
                      "-p", "no:cacheprovider"], f"pytest:{Path(rel).stem}"
    else:
        cmd, label = [PY, "-m", "pytest", "tests/test_absence_claim_census.py",
                      "-k", spec.split(":", 1)[1], "-q", "--no-header",
                      "-p", "no:cacheprovider"], spec
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                          timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines()
            if "passed" in ln or "failed" in ln or "Error" in ln][-2:]
    return label, proc.returncode, " | ".join(k[:70] for k in keep)


ARMS = [
    {"id": "E1-presence-branch-removed", "target": INSTRUMENT,
     "note": "去掉 expect=present 那一支 ⇒ 存在式登记按缺席式判，说「有入口」反而永远过期",
     "old": ('        if str(check.get("expect", "absent")) == "present":\n'
             '            return (not has, [head] + external, problems)'),
     "new": '        if False:\n            return (not has, [head] + external, problems)',
     "probes": ["self-test", "file:tests/test_absence_claim_census.py"]},
    {"id": "E2-absence-polarity-deadened", "target": INSTRUMENT,
     "note": "默认（缺席式）那一支永不判红 ⇒ 第 68 片那种登记再也证伪不了「没人调用」",
     "old": '        return (has, [head] + external, problems)',
     "new": '        return (has and False, [head] + external, problems)',
     "probes": ["self-test"]},
    {"id": "E3-cli-branch-removed", "target": PRODUCT,
     "note": "摘掉 --commit 的处理支（旗子还在但不做事）⇒ CLI 用例必须红",
     "old": '    if getattr(args, "commit", False):',
     "new": '    if False:',
     "probes": ["file:tests/test_product_gate_commit_cli.py"]},
    {"id": "E4-cli-swallows-refusal", "target": PRODUCT,
     "note": "把前置校验的抛错洗成 ok ⇒ 把「拒绝」读成「提交成功」，正是本仓最忌的静默降级",
     "old": '        receipt = gate.commit_approved(actor="owner-cli")',
     "new": ('        try:\n            receipt = gate.commit_approved(actor="owner-cli")\n'
             '        except Exception:\n'
             '            receipt = {"commit_id": "FAKE", "committed": [], "requirements": 0,\n'
             '                       "features": 0, "snapshot_id": "", "snapshot_hash": "",\n'
             '                       "decision_id": "", "gate": "committed",\n'
             '                       "authorization": "APPROVED", "idempotent_replay": False}'),
     "probes": ["file:tests/test_product_gate_commit_cli.py"]},
    {"id": "E5-flag-not-registered", "target": PARSER,
     "note": "旗子没进 argparse ⇒ 走不到那条支路，读数也不该绿",
     "old": '    pg.add_argument("--commit", action="store_true",',
     "new": '    pg.add_argument("--commit-disabled-here", action="store_true",',
     "probes": ["file:tests/test_product_gate_commit_cli.py",
                "file:tests/test_command_surface_census.py"]},
]


def main() -> int:
    rows = []
    bases = {a["target"]: sha(a["target"]) for a in ARMS}
    srcs = {t: t.read_text(encoding="utf-8") for t in bases}
    for arm in ARMS:
        tgt, old, new = arm["target"], arm["old"], arm["new"]
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
            readings = [probe(p) for p in arm["probes"]]
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        killed = any(rc != 0 for _l, rc, _t in readings)
        rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                     " ;; ".join(f"{lbl}→rc={rc} {t}" for lbl, rc, t in readings)))
    for t, h in bases.items():
        print(f"基线 {t.name} sha={h}（每臂还原后同值）")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}\n    {d[:400]}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {k} / 其余 {len(rows) - k}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
