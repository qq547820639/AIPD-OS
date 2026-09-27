"""第 75 片（只报面拆 live / record）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TGT = ROOT / "scripts/doc_command_census.py"
PY_BIN = str(ROOT / ".venv/bin/python")

ARMS = [
    {"id": "S1-nothing-is-record",
     "note": "全部算 live ⇒ 记录性引述与测试里的故意幻影名重回可行动清单（不变量红）",
     "old": '    if norm in RECORD_FILES:\n        return True',
     "new": '    if False:\n        return True'},
    {"id": "S2-everything-is-record",
     "note": "全部算 record ⇒ live 清单恒空，不变量退化成「什么都别说」",
     "old": '    if norm in RECORD_FILES:\n        return True',
     "new": '    if True:\n        return True'},
    {"id": "S3-record-bucket-becomes-invisible",
     "note": "拆桶顺手把 record 清单清空 ⇒ 可见性下降，「拆桶不是藏语料」这条承诺落空",
     "old": '        "report_record_unmatched": [{"doc": d, "line": n, "written": w}\n'
            '                                    for d, n, w in record_bad],',
     "new": '        "report_record_unmatched": [],'},
    {"id": "S4-tests-leave-the-record-bucket",
     "note": "把 tests 从记录名单里摘掉 ⇒ 测试夹具名混进 live，可行动清单又开始说谎",
     "old": 'RECORD_DIR_PREFIXES = ("docs/audit", "tests", ".trae")',
     "new": 'RECORD_DIR_PREFIXES = ("docs/audit", ".trae")'},
]


def sha():
    return hashlib.sha256(TGT.read_bytes()).hexdigest()[:12]


def step(label):
    if label == "self-test":
        cmd = [PY_BIN, str(TGT), "--self-test"]
    else:
        cmd = [PY_BIN, "-m", "pytest", "tests/test_doc_command_census.py",
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
            rcs = [step("self-test"), step("pytest")]
        finally:
            TGT.write_text(src, encoding="utf-8")
            assert sha() == base, "还原失败"
        killed = any(rc != 0 for rc, _ in rcs)
        rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                     " ;; ".join(txt for _rc, txt in rcs)))
    print(f"基线 sha={base}")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}  {d[:110]}")
    killed = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {killed} / 其余 {len(rows) - killed}")
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
