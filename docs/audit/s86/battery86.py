# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 86 片（锚点必填 + 40 位 SHA 形状校验）的变异电池。

每条臂撤掉本片新增的一根牙，必须在
``tests/test_release_evidence_preflight.py`` 上**增量开火**。
基线已全绿（第 84 片那条在途红随收口自己消了），但记分仍按增量开火——
同一把尺只换一种形状时，判据不该跟着换。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
EV = ROOT / "scripts/release_evidence.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_release_evidence_preflight.py"]

ARMS = [
    {"id": "X1-anchor-may-default-again", "file": EV,
     "reps": [('    if not a.source_commit:\n', '    if False:\n')],
     "note": "放掉必填：第 52/62 片那两次「多跑一整个全量」的成因重新无人守——"
             "漂掉的锚点不当场报错，只在下一轮绑定读成「清单被改过」"},
    {"id": "X2-shape-check-dropped", "file": EV,
     "reps": [('    if not re.fullmatch(r"[0-9a-f]{40}", a.source_commit):\n',
               '    if False:\n')],
     "note": "放掉形状校验：截断或含空格的锚点被逐字相等比较读成永远不等，"
             "读者看到的是「判据坏了」而不是「锚点写错了」"},
    {"id": "X3-shape-check-loosened-to-prefix", "file": EV,
     "reps": [('if not re.fullmatch(r"[0-9a-f]{40}", a.source_commit):',
               'if not re.match(r"[0-9a-f]{7}", a.source_commit):')],
     "note": "把「恰好 40 位」退化成的「至少 7 位」：git 短 SHA 正是 7 位，"
             "于是 a660405 这种截断值重新通过——这一臂证明必填与全形两半都在工作"},
    {"id": "X4-hex-class-widened-to-uppercase", "file": EV,
     "reps": [('if not re.fullmatch(r"[0-9a-f]{40}", a.source_commit):',
               'if not re.fullmatch(r"[0-9a-fA-F]{40}", a.source_commit):')],
     "note": "第 88 片把字符类收到小写（`git rev-parse` 只印小写，两个读者按逐字相等判）。"
             "这一臂把它放宽回去：大写锚点能过写入侧、却在门与验签那里永远判不红在报警——"
             "报错点离原因两环。由 `test_refuses_a_malformed_source_commit` 的大写那档抓住"},
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header", "-rf",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=1200)
    out = proc.stdout + proc.stderr
    lines = out.splitlines()
    tally = [ln for ln in lines if "passed" in ln or "failed" in ln or "error" in ln][-1:]
    fired = {ln[len("FAILED "):] for ln in lines if ln.startswith("FAILED ")}
    return proc.returncode, (tally[0][:70] if tally else ""), fired


RC0, BASE_TALLY, BASE_FIRED = run_tests()
print(f"基线 rc={RC0} {BASE_TALLY}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = argv[0] if argv and not argv[0].startswith("--") else None
    arms = [a for a in ARMS if not only or only in a["id"]]
    if only and not arms:
        print(f"没匹配到 {only!r}；现有臂：" + ", ".join(a["id"] for a in ARMS))
        return 2
    if only:
        print(f"子集复算：只跑 {len(arms)}/{len(ARMS)} 臂，合计行分母按实跑臂数算")
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in arms}
    bases = {k: sha(k) for k in srcs}
    rows = []
    for arm in arms:
        tgt = arm["file"]
        src = srcs[tgt]
        mutated = src
        bad = None
        for old, new in arm["reps"]:
            if src.count(old) != 1:
                bad = f"old 命中 {src.count(old)} 次"
                break
            if old in new and new in src:
                bad = "插入体已在树上（重复注入）"
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
            _rc, line, fired = run_tests()
            new = sorted(fired - BASE_FIRED)
            verdict = "SURVIVED" if not new else ("CRASH-KILL" if "error" in line.lower() else "KILLED")
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], verdict, line, new))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, v, d, fired in rows:
        print(f"[{v:11}] {rid}  {d[:70]}")
        for f in fired:
            print(f"              增量开火: {f}")
    good = sum(1 for _r, v, _d, _f in rows if v in ("KILLED", "CRASH-KILL"))
    other: dict = {}
    for _r, v, _d, _f in rows:
        if v not in ("KILLED", "CRASH-KILL"):
            other[v] = other.get(v, 0) + 1
    print(f"合计 KILLED+CRASH-KILL {good} / {len(arms)}；其余按判决分类："
          + ("、".join(f"{k} {n}" for k, n in sorted(other.items())) or "无"))
    return 0 if good == len(arms) else 1


if __name__ == "__main__":
    sys.exit(main())
