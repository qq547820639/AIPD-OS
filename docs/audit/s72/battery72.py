# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 72 片（收回第 71 片留下的两处各写一遍）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
SUP = ROOT / "src/aipd_os/supervisor/supervisor.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_supervisor_execution.py", "tests/test_evidence_rework.py",
         "tests/test_supervisor_fact_writeback.py"]

ARMS = [
    {"id": "K1-suite-reconstructed-in-rerun", "file": SUP,
     "note": "把三步套件在 rerun 里再抄一遍（第 71 片的原状）⇒ 结构守卫必须红",
     "old": '        out, _registry = self._run_capability(\n            wid, row["capability_floor"], inputs,',
     "new": '        from aipd_os.execution.execution_router import ExecutionRouter\n'
            '        _r2 = ExecutionRouter(None, None, None)\n'
            '        out, _registry = self._run_capability(\n            wid, row["capability_floor"], inputs,'},
    {"id": "K2-suite-construction-removed", "file": SUP,
     "note": "共用口子被拆掉 ⇒ 守卫不能只会朝一个方向红（少一处也要红）",
     "old": '            router = ExecutionRouter(\n                RunStore(str(self.path.parent / "execution_runs.db")),\n                adapter_registry, get_logger("aipd.router"))',
     "new": '            router = _LEGACY_ROUTER_FACTORY(\n                RunStore(str(self.path.parent / "execution_runs.db")),\n                adapter_registry, get_logger("aipd.router"))'},
    {"id": "K3-scope-from-constructor-again", "file": SUP,
     "note": "作用域退回用构造参数 ⇒ 跨项目重跑会把 run 记到错的项目",
     "old": '            project_id=row["project_id"] or self.project_id(),\n            tenant_id=row["tenant_id"] or self._tenant_id,',
     "new": '            project_id=self.project_id(),\n            tenant_id=self._tenant_id,'},
    {"id": "K4-second-direct-router-run", "file": SUP,
     "note": "第二处 router.run（自带一份 context）⇒ 两处 context 会各说各话",
     "old": '                out, _registry = self._run_capability(\n                    wid, capability_floor, inputs, project_id=pid,',
     "new": '                out = router.run(wid, capability_floor, inputs,\n'
            '                                 context={"work_id": wid})\n'
            '                out, _registry = self._run_capability(\n                    wid, capability_floor, inputs, project_id=pid,'},
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
    src = SUP.read_text(encoding="utf-8")
    base = sha(SUP)
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
            compile(mutated, str(SUP), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc)))
            continue
        SUP.write_text(mutated, encoding="utf-8")
        try:
            assert sha(SUP) != base
            rc, line = run_tests()
        finally:
            SUP.write_text(src, encoding="utf-8")
            assert sha(SUP) == base
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line))
    print(f"基线 supervisor.py sha={base}")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}  {d}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {k} / 其余 {len(rows) - k}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
