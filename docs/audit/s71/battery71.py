# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 71 片（执行证据返工）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
ER = ROOT / "src/aipd_os/supervisor/evidence_rework.py"
CT = ROOT / "src/aipd_os/cli/commands_truth.py"
PY = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_evidence_rework.py", "tests/test_dxf_rework.py",
          "tests/test_cost_rework.py"]

ARMS = [
    {"id": "H1-trust-carried-over", "file": ER,
     "note": "信任沿用旧值、不看这次的门 ⇒ 门没过的重跑仍自称 high",
     "old": '    trust = "high" if str(fresh.get("gate") or "") == "pass" else "low"',
     "new": '    trust = "high" if True else "low"'},
    {"id": "H2-side-effect-guard-dropped", "file": ER,
     "note": "不查 side_effect_mode ⇒ 对外副作用被自动重放（第二封报价邮件那一类）",
     "old": '    if mode not in REWORKABLE_MODES:',
     "new": '    if mode in ("__never__",):'},
    {"id": "H3-same-run-guard-dropped", "file": ER,
     "note": "同一次 run 也算收口 ⇒「重跑」退化成空操作",
     "old": '    if new_run == old_run:',
     "new": '    if new_run == "__never__":'},
    {"id": "H4-status-guard-dropped", "file": ER,
     "note": "blocked_external 也当成功 ⇒ 把没收口写成收口",
     "old": '    if str(fresh.get("status") or "") not in ("succeeded", "fallback"):',
     "new": '    if str(fresh.get("status") or "") in ("__never__",):'},
    {"id": "H5-content-projection-duplicated", "file": ER,
     "note": "执行器自己写一份正文规则（不走共享投影）⇒ 生产者与返工两边各说各话",
     "old": '    content = evidence_content(str(meta.get("capability")), new_run, output_hash)',
     "new": '    content = "reworked " + str(meta.get("capability")) + ": " + new_run'},
    {"id": "H6-kind-condition-inverted", "file": ER,
     "note": "把类别判据反过来 ⇒ 证据这一类认不出证据、反倒去认别的 record_type",
     "old": '    return SUPPORTED_RECORD_TYPE if rec.record_type == SUPPORTED_RECORD_TYPE else None',
     "new": '    return SUPPORTED_RECORD_TYPE if rec.record_type != SUPPORTED_RECORD_TYPE else None'},
    {"id": "H7-cli-list-not-extended", "file": CT,
     "note": "CLI 的 supported 少了这一类 ⇒ 命令面与登记说的五类不一致",
     "old": '    supported = [SUPPORTED_ARTIFACT, DXF_ARTIFACT, BOM_ARTIFACT, COST_ARTIFACT,\n                 EVIDENCE_ARTIFACT]',
     "new": '    supported = [SUPPORTED_ARTIFACT, DXF_ARTIFACT, BOM_ARTIFACT, COST_ARTIFACT]'},
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "--no-header",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines() if "passed" in ln or "failed" in ln][-1:]
    return proc.returncode, keep[0][:80] if keep else ""


def main() -> int:
    rows = []
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in ARMS}
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
            assert sha(tgt) != bases[tgt], "落地失败"
            rc, line = run_tests()
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, verdict, detail in rows:
        print(f"[{verdict:11}] {rid}  {detail}")
    killed = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {killed} / 其余 {len(rows) - killed}")
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
