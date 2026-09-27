# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 79 片（前缀级信任 + 门规则单点）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_research_fulltext_step.py", "tests/test_supervisor_execution.py"]
ARMS = [
    {"id": "W1-prefix-swapped-to-nothing", "file": ROOT / 'src/aipd_os/research/fulltext.py',
     "note": '前缀表清空 ⇒ Europe PMC 全文端点不再算开放来源（正向控制）',
     "old": '    "ebi.ac.uk": ("/europepmc/webservices/rest/",),',
     "new": '    "ebi.ac.uk": ("/__never__/",),'},  # noqa: E501
    {"id": 'W2-host-only-again', "file": ROOT / 'src/aipd_os/research/fulltext.py',
     "note": '退回第 78 片的主机级判定 ⇒ 同主机别的路径也判开放（负向控制）',
     "old": '            return any(path == p.rstrip("/") or path.startswith(p) for p in prefixes)',
     "new": '            return True'},  # noqa: E501
    {"id": 'W3-prefix-map-bypassed', "file": ROOT / 'src/aipd_os/research/fulltext.py',
     "note": '完全不查前缀表 ⇒ 与 W2 同一后果的另一条路（少一层就是两处各写一遍）',
     "old": '    for domain, prefixes in OPEN_ACCESS_PREFIXES.items():',
     "new": '    for domain, prefixes in {}.items():'},  # noqa: E501
    {"id": 'W4-gate-rule-duplicated', "file": ROOT / 'src/aipd_os/supervisor/supervisor.py',
     "note": '把门的 findings 规则抄第二份 ⇒ 单点实现用例必须红',
     "old": '    def _quality_gate(self, wid, record):',
     "new": '    _LEGACY_GATE_RULE = "missing evidence references"\n\n    def _quality_gate(self, wid, record):'},  # noqa: E501
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
