# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 82 片（速查语料"断续行"判据 ②b）的变异电池。

每条臂撤掉本片新增的一条牙，必须在 `tests/test_doc_command_census.py` 上开火。
跑法：`docs/audit/s82/battery82.py`（要落盘改源文件，跑完逐臂还原并校验 sha）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
DCC = ROOT / "scripts/doc_command_census.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_doc_command_census.py"]

ARMS = [
    {"id": "Z1-face-scans-but-drops-the-hit", "file": DCC,
     "note": "扫到了却不记 ⇒ 『0 处』变成假绿，只有历史原件那条用例能抓",
     "reps": [('                out.append((rel, idx + 1, lines[idx].rstrip()))',
               '                pass  # 变异：看见了但不记')]},
    {"id": "Z2-hit-never-reaches-violations", "file": DCC,
     "reps": [('    for rel, no, seg in cont:\n        judged.append(("续行", rel, no, seg))', '')],
     "note": "整段撤掉进 violations 的那一步：分母还在自报、判决却不再生效"},
    {"id": "Z3-field-renamed", "file": DCC,
     "reps": [('        judged.append(("续行", rel, no, seg))',
               '        judged.append(("续X", rel, no, seg))')],
     "note": "判决字段改名：渲染与用例都按 `续行` 认，改了就读不出是哪一档开的火"},
    {"id": "Z4-face-uses-its-own-walk", "file": DCC,
     "reps": [('    files, problems = quickref_corpus(root)\n    out: list[tuple[str, int, str]] = []\n    for rel, lines in files:\n        for idx in range(len(lines) - 1):\n', '    files = [(str((root / rel).relative_to(root)),\n              (root / rel).read_text(encoding="utf-8").splitlines())\n             for rel in QUICKREF_FILES if (root / rel).is_file()]\n    problems: list[str] = []\n    out: list[tuple[str, int, str]] = []\n    for rel, lines in files:\n        for idx in range(len(lines) - 1):\n')],
     "note": "②b 自己另写一遍遍历、只读 QUICKREF_FILES：`docs/architecture` 那一侧从此不被判，"
             "而 README 侧照绿——只有 test_broken_continuation_is_also_judged_under_quickref_dirs 抓得到"},
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header", "-rf",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    lines = out.splitlines()
    tally = [ln for ln in lines if "passed" in ln or "failed" in ln][-1:]
    fired = [ln[len("FAILED "):] for ln in lines if ln.startswith("FAILED ")]
    return proc.returncode, (tally[0][:70] if tally else ""), fired


def main() -> int:
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in ARMS}
    bases = {k: sha(k) for k in srcs}
    rows = []
    for arm in ARMS:
        tgt = arm["file"]
        src = srcs[tgt]
        mutated = src
        bad = None
        for old, new in arm["reps"]:
            if src.count(old) != 1:
                bad = f"old 命中 {src.count(old)} 次"
                break
            if new and new in src:
                bad = "new 已在树上（空改写）"
                break
            mutated = mutated.replace(old, new, 1)
        if bad:
            rows.append((arm["id"], "BAD-ANCHOR", bad, []))
            continue
        if mutated == src:
            rows.append((arm["id"], "BAD-MUTATION", "改写后与原文逐字节相同", []))
            continue
        try:
            compile(mutated, str(tgt), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc), []))
            continue
        tgt.write_text(mutated, encoding="utf-8")
        try:
            assert sha(tgt) != bases[tgt], "落地失败"
            rc, line, fired = run_tests()
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line, fired))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, v, d, fired in rows:
        print(f"[{v:11}] {rid}  {d[:70]}")
        for f in fired:
            print(f"              开火: {f}")
    killed = sum(1 for _r, v, _d, _f in rows if v == "KILLED")
    # "其余"必须分类抄：BAD-* 是电池自己的问题，不是"这条牙没人守"。
    other: dict = {}
    for _r, v, _d, _f in rows:
        if v != "KILLED":
            other[v] = other.get(v, 0) + 1
    print(f"合计 KILLED {killed} / {len(ARMS)}；其余按判决分类："
          + ("、".join(f"{k} {n}" for k, n in sorted(other.items())) or "无"))
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
