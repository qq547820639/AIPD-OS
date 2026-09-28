#!/usr/bin/env python3
"""第 90 片变异电池：识别面每一族加宽，各配一支"把这一族收回去"的撤销臂。

| 臂 | 撤掉的能力 | 谁必须翻红 |
| --- | --- | --- |
| Z0 | 不改任何字节（对照） | ——必须全绿，否则电池前提不成立 |
| Z1 | 路径字符集里的 CJK 基本区（D 族：中文命名的入口脚本重新变成看不见） | `test_non_ascii_entrypoint_is_recognised_and_judged` |
| Z2 | 点名语义退成"整行 disable"（markdownlint 那一步就好，多吃一口） | 那条用例的"同行未点名仍判"半支 + 自测 doc.md 第 8 行 |
| Z3 | 去掉"点不到 occurrence 就判失效"的反查 | 那条用例的第三格 + 自测 `entry_example_stale` |
| Z4 | `..` 不归一化（回到"当成占位免判"） | 自测里 `docs/audit/gone.py` 那一格 |
| Z5 | 解释器与路径之间不许夹短旗 | 自测的 `/tmp/zzz_flagged.py` |
| Z6 | 不认版本后缀 | 自测的 `/tmp/zzz_versioned.py` |
| Z7 | 解释器不许带目录前缀 | 自测的 `/tmp/zzz_absinterp.py` |

识别面加宽的失败模式与判决面不同：**它不产生红，它产生"没有读数"**。
一条认不出的入口既不在 `tracked` 也不在 `dead`，而是从 `corpus.entry_points` 的分母里
消失——所以每一族加宽都必须配一支收回臂，证明"这一族真的被看见了"，
否则加宽与没加宽在读数上不可区分。（对照第 89 片 Y 系列：那一批撤的是判决，会留红。）

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
ARMS = [
    ("Z0-control-no-change", "对照：原样必须全绿", None, None),
    ("Z1-cjk-charset-removed", "把 CJK 基本区从路径字符集里收回（D 族重新变隐形）",
     r'ENTRY_PATH_CHARS = r"A-Za-z0-9_\u4e00-\u9fff./\-\{\}$<>*…"',
     r'ENTRY_PATH_CHARS = r"A-Za-z0-9_./\-\{\}$<>*…"'),
    ("Z2-marker-becomes-line-wide", "点名语义退成整行 disable（同行未点名的也跟着免判）",
     "                if path in named or posixpath.normpath(path) in named:",
     "                if named:"),
    ("Z3-stale-marker-check-removed", "去掉"
     "「点了名却点不到 occurrence 就判失效」的反查",
     "    if not p9:",
     "    if False:"),
    ("Z4-dotdot-stays-muted", "`..` 不再归一化（回到被占位分支静默免判）",
     '                if ".." in path:',
     '                if False:'),
    ("Z5-no-flags-between", "解释器与路径之间不许夹短旗",
     r'ENTRY_FLAGS = r"(?:\s+-{1,2}[A-Za-z][\w-]*)*"',
     r'ENTRY_FLAGS = r""'),
    ("Z6-no-version-suffix", "不认 `python3.11` 这种带版本后缀的解释器",
     r'ENTRY_PY = r"(?:\.venv/bin/)?python3?(?:\.\d+)?"',
     r'ENTRY_PY = r"(?:\.venv/bin/)?python3?"'),
    ("Z7-no-interp-dir-prefix", "解释器不许带目录前缀（绝对路径里的 .venv 又看不见）",
     r'ENTRY_INTERP = r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_./-]+/)?(?:" + ENTRY_PY + ',
     r'ENTRY_INTERP = r"(?<![A-Za-z0-9_./-])(?:" + ENTRY_PY + '),
]


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
    stale = [(n, text.count(o)) for n, _w, o, _n2 in ARMS
             if o is not None and text.count(o) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if a[2] is not None)} 支臂各命中 1 次")
    rc, out = run_tests()
    if rc != 0:
        print("Z0 对照臂不绿，电池前提不成立：", out[-800:])
        return 5
    print("[CONTROL OK] Z0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, old, new in ARMS:
        if old is None:
            continue
        CEN.write_text(text.replace(old, new, 1), encoding="utf-8")
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
    total = len(ARMS) - 1
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(CEN.read_bytes())}（应等于 {sha(original)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
