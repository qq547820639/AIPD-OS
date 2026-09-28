#!/usr/bin/env python3
r"""第 90 片变异电池：识别面/判决面每一处改动，各配一支"把这一处收回去"的撤销臂。

| 臂 | 撤掉的能力 | 谁必须翻红 |
| --- | --- | --- |
| Z0 | 不改任何字节（对照） | ——必须全绿，否则电池前提不成立 |
| Z1 | 路径字符集里的 CJK 基本区（D 族：中文命名的入口脚本重新变成看不见） | `test_non_ascii_entrypoint_is_recognised_and_judged` |
| Z2 | 点名语义退成"整行 disable"（markdownlint 那一步就好，多吃一口） | 那条用例的"同行未点名仍判"半支 + 自测 doc.md 第 8 行 |
| Z3 | 去掉"点不到 occurrence 就判失效"的反查 | 那条用例的第三格 + 自测 `entry_example_stale` |
| Z5 | 解释器与路径之间不许夹短旗 | 自测的 `/tmp/zzz_flagged.py` |
| Z6 | 不认版本后缀 | 自测的 `/tmp/zzz_versioned.py` |
| Z7 | 解释器不许带目录前缀 | 绝对路径那一条 + 自测的 `/tmp/zzz_absinterp.py` |
| Z8 | 结尾退回 `\b`（路径后紧跟汉字 ⇒ 一行都不产生） | `test_cjk_adjacent_path_is_recognised_and_pyx_is_not` |
| Z9 | 不做无条件归一化（`./x` 保持原样） | `test_dot_prefixed_form_folds_onto_the_tracked_name` |
| Z10 | 逃出仓库根的 `../` 回到"被占位分支免判"（两处同时撤，见下） | `test_path_escaping_the_repo_root_is_dead_not_placeholder` |
| Z11 | 标记不许点名带 `>` 的名字（`[^>]*?` 让整条标记作废） | `test_two_markers_on_one_line_and_one_naming_an_angle_bracket_path` |
| Z12 | 一行只认第一个标记（`search` 代替 `finditer`） | 同上一条用例的另一格 + 自测 `doc.md:16` |
| Z13 | "只剩举例引用"不再算撤登记的理由 | `test_register_entry_left_only_as_an_example_is_reversible` |
| Z14 | 前提问题不去重（同一个"读不出"记两笔） | `test_unreadable_corpus_records_the_premise_once` |

识别面加宽的失败模式与判决面不同：**它不产生红，它产生"没有读数"**。
一条认不出的入口既不在 `tracked` 也不在 `dead`，而是从 `corpus.entry_points` 的分母里
消失——所以每一族加宽都必须配一支收回臂，证明"这一族真的被看见了"，
否则加宽与没加宽在读数上不可区分。（对照第 89 片 Y 系列：那一批撤的是判决，会留红。）

**Z4 在本轮被撤掉**：它撤的是 `if ".." in path:` 那一支归一化，而复核件 #2/#3 之后
归一化已经**前移成无条件**（`path = posixpath.normpath(raw)`），那一行字面已不存在。
同一件事现在由 Z9 撤，覆盖面更大 ⇒ 留着 Z4 只会得到一个 BAD-ANCHOR。
Z10 是本轮第一支"两处一起撤"的臂：只删判决分支会落回占位分支吗？不会——判决分支在
占位分支**之前**，所以只撤它反而读成 dead（假存活）。要还原缺陷必须把当年免判它的那条
`\.\.` 一起放回去，两支编辑缺一支就测不到那一格。

跑法：`python docs/audit/s90/battery90.py`。开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
CEN = REPO / "scripts" / "doc_command_census.py"
TESTS = ["tests/test_doc_command_census.py"]

# 注意：这里的字符串一律写 raw —— 目标行本身含字面量 `\u4e00`，
# 非 raw 串会先把转义解成"中"字，锚点就永远命中 0（第 87 片记过的引号族）。
# 第 4 项 `new` 可以是 None（表示 `old` 本身就是 ((旧, 新), …) 的成对清单）。
ARMS = [
    ("Z0-control-no-change", "对照：原样必须全绿", None, None),
    ("Z1-cjk-charset-removed", "把 CJK 基本区从路径字符集里收回（D 族重新变隐形）",
     r'ENTRY_PATH_CHARS = r"A-Za-z0-9_\u4e00-\u9fff./\-\{\}$<>*…"',
     r'ENTRY_PATH_CHARS = r"A-Za-z0-9_./\-\{\}$<>*…"'),
    ("Z2-marker-becomes-line-wide", "点名语义退成整行 disable（同行未点名的也跟着免判）",
     "                if path in named or raw in named:",
     "                if named:"),
    ("Z3-stale-marker-check-removed", "去掉"
     "「点了名却点不到 occurrence 就判失效」的反查",
     "    if not p9:",
     "    if False:"),
    ("Z5-no-flags-between", "解释器与路径之间不许夹短旗",
     r'ENTRY_FLAGS = r"(?:\s+-{1,2}[A-Za-z][\w-]*)*"',
     r'ENTRY_FLAGS = r""'),
    ("Z6-no-version-suffix", "不认 `python3.11` 这种带版本后缀的解释器",
     r'ENTRY_PY = r"(?:\.venv/bin/)?python3?(?:\.\d+)?"',
     r'ENTRY_PY = r"(?:\.venv/bin/)?python3?"'),
    ("Z7-no-interp-dir-prefix", "解释器不许带目录前缀（绝对路径里的 .venv 又看不见）",
     r'ENTRY_INTERP = r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_./-]+/)?(?:" + ENTRY_PY + ',
     r'ENTRY_INTERP = r"(?<![A-Za-z0-9_./-])(?:" + ENTRY_PY + '),
    ("Z8-word-boundary-tail", "结尾退回 `\\b`：路径后紧跟汉字时一行都不产生",
     r'r"\s+([" + ENTRY_PATH_CHARS + r"]+\.(?:py|sh))(?![A-Za-z0-9_])")',
     r'r"\s+([" + ENTRY_PATH_CHARS + r"]+\.(?:py|sh))\b")'),
    ("Z9-no-unconditional-fold", "不做无条件归一化（`./x` 保持带前缀的原样）",
     "                path = posixpath.normpath(raw)",
     '                path = raw if ".." not in raw else posixpath.normpath(raw)'),
    ("Z10-escaping-root-muted-again", "逃出仓库根的 `../` 回到"
     "「被占位分支静默免判」（判决分支＋当年那条 `\\.\\.` 两处一起撤）",
     (("                if path == \"..\" or path.startswith(\"../\"):",
       "                if False:"),
      (r'ENTRY_PLACEHOLDER_RE = re.compile(r"(?:X\.(?:py|sh)$|NN|…|[<>{}*]|\$\{|s\d+\.\.s)")',
       r'ENTRY_PLACEHOLDER_RE = re.compile(r"(?:X\.(?:py|sh)$|NN|\.\.|…|[<>{}*]|\$\{|s\d+\.\.s)")')),
     None),
    ("Z11-marker-cannot-name-angle-bracket", "标记的取名退回 `[^>]*?`"
     "（被点名的名字里带 `>` ⇒ 整条标记两头不沾）",
     r'ENTRY_EXAMPLE_RE = re.compile(r"<!--\s*aipd-census:example(?P<paths>.*?)-->")',
     r'ENTRY_EXAMPLE_RE = re.compile(r"<!--\s*aipd-census:example(?P<paths>[^>]*?)-->")'),
    ("Z12-only-first-marker-on-line", "一行只认第一个标记（`search` 代替 `finditer`）",
     '    return {tok for m in ENTRY_EXAMPLE_RE.finditer(line)\n'
     '            for tok in m.group("paths").split() if tok}',
     '    mm = ENTRY_EXAMPLE_RE.search(line)\n'
     '    return {tok for tok in mm.group("paths").split() if tok} if mm else set()'),
    ("Z13-example-still-counts-as-cited", "「只剩举例引用」不再算该撤的理由",
     '        cited = [s for s in states if s != "example"]',
     "        cited = list(states)"),
    ("Z14-premises-not-deduplicated", "前提问题不去重：两条各读一遍语料的路把同一格记两笔",
     "    problems += [p for p in p9 if p not in problems]",
     "    problems += p9"),
]


def pairs(arm):
    """把一支臂的编辑归一成 [(旧, 新), …]（一支臂可以有两处）。"""
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
    original = CEN.read_bytes()
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
        print("Z0 对照臂不绿，电池前提不成立：", out[-800:])
        return 5
    print("[CONTROL OK] Z0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, old, new in ARMS:
        edits = pairs((name, what, old, new))
        if not edits:
            continue
        mutated = text
        for o, n2 in edits:
            mutated = mutated.replace(o, n2, 1)
        CEN.write_text(mutated, encoding="utf-8")
        if sha(CEN.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            CEN.write_bytes(original)
            continue
        chk = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "py_compile",
                              str(CEN)], capture_output=True, text=True)
        if chk.returncode != 0:
            print(f"[BAD-ANCHOR] {name} 变异体编译不过：{chk.stderr[-160:]}")
            marks["BAD-ANCHOR"] += 1
            CEN.write_bytes(original)
            continue
        rc, out = run_tests()
        CEN.write_bytes(original)
        if sha(CEN.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {name}")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {name}（{what}）收回这一族，用例照绿 ⇒ 这一族其实没被看见")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {name}（{what}）被抓住："
                  f"{'; '.join(killed) or '(无 FAILED 行，见日志)'[:600]}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if pairs(a))
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(CEN.read_bytes())}（应等于 {sha(original)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
