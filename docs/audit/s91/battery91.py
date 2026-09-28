#!/usr/bin/env python3
r"""第 91 片变异电池：`ci_surface_census` 的每道判决/每个解析选择，各配一支撤销臂。

| 臂 | 撤掉的东西 | 谁必须翻红 |
| --- | --- | --- |
| A0 | 不改任何字节（对照） | ——必须全绿，否则电池前提不成立 |
| A1 | 「无人守」不再判红（只计数） | 自测第一格 + `…_new_ci_command_without_entry_fires…` + 真仓库那条 |
| A2 | 「结构性免跑必须带理由」 | 自测第三格 + `test_structural_exemption_without_a_reason_is_red` |
| A3 | 「空头委托」不再判红 | 自测第一格（mypy 那一支）+ tmp 注入用例 |
| A4 | 「消费表该撤」反向臂 | 自测 + tmp 注入用例第四步步 |
| A5 | 消费方作用域判据（只 `tests/` 要真有用例）退回"所有 .py 都要有 `def test_`" | **真语料原告**：册子里 `scripts/closeout_verifier.py` 等没有用例 ⇒ 集体判「空头委托」 |
| A6 | `\` 续行不归一 | **真语料原告**：那条 `curl … \` 的键对不上 ⇒ 无人守 + 该撤各一笔 |
| A7 | block 标量不切行（整个 run 当一条命令） | **真语料原告**：分母从 32 掉到 ~17，`-m pytest` 那 10 条全部错配 |
| A8 | `consumer_alive` 不核文件是否存在（永真） | 自测的 mypy 那一格（挂的文件不在树里）|

形状说明：A1/A3/A4 撤的是**判决**（会少红），A5–A8 撤的是**解析/作用域选择**（会多红或错红）。
两类都要有臂：只有前者，读不出"判据为什么长这样"；只有后者，读不出"判据真的会放行"。
`--self-test` 的期望值在这里当第二把尺用（它对 A1–A4、A8 都敏感）。

跑法：`python docs/audit/s91/battery91.py`。开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TOOL = REPO / "scripts" / "ci_surface_census.py"
TESTS = ["tests/test_ci_surface_census.py"]

# 锚点里那两串反斜杠由 chr(92) 拼，不手写转义：本仓已经在"中文串里嵌半角引号"
# 与"多层反斜杠"上翻过两次车（第 87/90 片），宁可让程序拼。
BS = chr(92)
A6_OLD = '        if out and out[-1].endswith("' + BS + BS + '"):'

ARMS = [
    ("A0-control-no-change", "对照：原样必须全绿", None, None),
    ("A1-unwatched-not-red", "「无人守」退成只计数不判红",
     '        if ent is None:\n            buckets["unwatched"] += 1',
     '        if ent is None:\n            buckets["unwatched"] += 1\n            continue'),
    ("A2-exemption-needs-no-reason", "结构性免跑不再要求写理由",
     '            if not ent["why"]:',
     "            if False:"),
    ("A3-vacuous-consumer-not-red", "「空头委托」不再判红",
     '        if not ent["consumers"] or dead:',
     "        if False:"),
    ("A4-no-reverse-arm", "撤掉「消费表该撤」这条反向臂",
     "        if key not in seen:",
     "        if False:"),
    ("A5-scope-all-py-need-tests", "把「只 tests/ 要真有用例」退回「所有 .py 都要有 def test_」",
     '    if p.suffix == ".py" and rel.startswith("tests/"):',
     '    if p.suffix == ".py":'),
    ("A6-no-continuation-fold", "续行不再折回上一条命令（折叠点在 `_split_shell`）",
     A6_OLD,
     "        if False:"),
    ("A7-block-is-one-command", "run 块不逐行切（整块当一条）",
     "    for line in raw.splitlines():",
     '    for line in [" ".join(raw.splitlines())]:'),
    ("A8-consumer-existence-off", "`consumer_alive` 不核文件在不在（永真）",
     '    if not p.is_file():\n        return False, "文件不在树里"',
     '    if not p.is_file():\n        return True, ""'),
]


def pairs(arm):
    """把一支臂的编辑归一成 [(旧, 新), …]（一支臂可以有多处）。"""
    old, new = arm[2], arm[3]
    if old is None:
        return []
    if new is None:
        return list(old)
    return [(old, new)]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home())})
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    original = TOOL.read_bytes()
    print(f"原文件 sha={sha(original)}")
    text = original.decode("utf-8")
    stale = [(arm[0], text.count(o)) for arm in ARMS
             for o, _n in pairs(arm) if text.count(o) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if pairs(a))} 支臂、"
          f"{sum(len(pairs(a)) for a in ARMS)} 处编辑各命中 1 次")
    rc, out = run_tests()
    if rc != 0:
        print("A0 对照臂不绿，电池前提不成立：", out[-900:])
        return 5
    print("[CONTROL OK] A0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for arm in ARMS:
        edits = pairs(arm)
        if not edits:
            continue
        mutated = text
        for o, n in edits:
            mutated = mutated.replace(o, n, 1)
        TOOL.write_text(mutated, encoding="utf-8")
        if sha(TOOL.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {arm[0]} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        chk = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "py_compile", str(TOOL)],
                             capture_output=True, text=True)
        if chk.returncode != 0:
            print(f"[BAD-ANCHOR] {arm[0]} 变异体编译不过：{chk.stderr[-200:]}")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        rc, out = run_tests()
        TOOL.write_bytes(original)
        if sha(TOOL.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {arm[0]}")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        nfail = len(killed)
        if rc == 0:
            print(f"[SURVIVED] {arm[0]}（{arm[1]}）撤掉之后用例照绿 ⇒ 这一格其实没被看见")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {arm[0]}（{arm[1]}）被抓住 {nfail} 条："
                  f"{'; '.join(killed)[:520]}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if pairs(a))
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {sha(original)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
