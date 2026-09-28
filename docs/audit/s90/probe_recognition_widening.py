#!/usr/bin/env python3
"""第 90 片开工前的"先量再改"探针：把面 ⑤ 识别面的四族漏形各数一遍。

判据：加宽识别器会**直接动死链分母与登记册内容**（第 85 片立的纪律：先量分母再立条），
所以这一片的第一步不是改正则，而是把"加宽之后会多出多少条、各属哪一族、
其中多少今天已经跑不动"读出来。本脚本只读，不改任何文件。

四类形状（对应第 87 片 §九#5 与 §九#6 的两条 + 第 89 片识别漏的那一族非 ASCII）：

  A 解释器带路径前缀：`/abs/x/.venv/bin/python foo.py`、`.venv/bin/python foo.py`
    （现行 lookbehind `(?<![A-Za-z0-9_./-])` 把前面是 `/` 或 `.` 的整批挡掉了）
  B 版本号解释器：`python3.11 foo.py`
  C 解释器与路径之间夹短旗：`python -u foo.py`、`python3 -B scripts/x.py`
  D 路径含非 ASCII：`python 脚本/取数.py`

用法：`python docs/audit/s90/probe_recognition_widening.py [仓库根]`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import doc_command_census as census  # noqa: E402

FAMILIES = {
    "A-interp-with-path-prefix": re.compile(
        r"(?<![A-Za-z0-9_-])(?:[A-Za-z0-9_./\u4e00-\u9fff-]+/)"
        r"(?:\.venv/bin/)?python3?(?:\.\d+)?\s+([A-Za-z0-9_./\u4e00-\u9fff-]+\.(?:py|sh))\b"),
    "B-versioned-interp": re.compile(
        r"(?<![A-Za-z0-9_./-])python3?\.\d+\s+"
        r"([A-Za-z0-9_./\u4e00-\u9fff-]+\.(?:py|sh))\b"),
    "C-flag-between": re.compile(
        r"(?<![A-Za-z0-9_./-])(?:\.venv/bin/)?python3?(?:\.\d+)?(?:\s+-{1,2}[A-Za-z][\w-]*)+"
        r"\s+([A-Za-z0-9_./\u4e00-\u9fff-]+\.(?:py|sh))\b"),
    "D-non-ascii-path": re.compile(
        r"(?<![A-Za-z0-9_./-])(?:\.venv/bin/)?(?:python3?(?:\.\d+)?|bash|sh|zsh)\s+"
        r"([A-Za-z0-9_./\u4e00-\u9fff-]*[\u4e00-\u9fff]"
        r"[A-Za-z0-9_./\u4e00-\u9fff-]*\.(?:py|sh))\b"),
}


def current_hits(root: Path) -> set[tuple[str, int, str]]:
    files, problems = census.entry_corpus(root)
    out = set()
    for rel, lines in files:
        for no, line in enumerate(lines, 1):
            for m in census.ENTRY_LINE_RE.finditer(line):
                out.add((rel, no, m.group(1)))
    if problems:
        print("语料问题（读数按缺这一部分看待）：", problems)
    return out


def family_hits(root: Path, pat: re.Pattern) -> set[tuple[str, int, str]]:
    files, _problems = census.entry_corpus(root)
    out = set()
    for rel, lines in files:
        for no, line in enumerate(lines, 1):
            for m in pat.finditer(line):
                out.add((rel, no, m.group(1)))
    return out


def classify(root: Path, path: str) -> str:
    if path.startswith("/"):
        inside = "绝对路径（任何签出里都不可解析）"
    else:
        inside = "仓内存在" if (root / path).exists() else "仓内不存在 ⇒ 会成为新死链"
    return inside + ("，非 ASCII" if any(ord(c) > 127 for c in path) else "")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cur = current_hits(root)
    print(f"仓库 {root}")
    print(f"现行识别面命中（位置, 路径）三元组：{len(cur)}")
    total_new = set()
    for name, pat in FAMILIES.items():
        got = family_hits(root, pat)
        new = {(r, n, p) for (r, n, p) in got if (r, n, p) not in cur}
        # 只看路径面：同一处引用换个解释器写法，位置三元组会变，但路径可能已在册
        new_paths = {p for _r, _n, p in new}
        total_new |= new
        print(f"\n== {name}：新增 {len(new)} 处（{len(new_paths)} 个不同路径）")
        known = {p for p in new_paths if p in census.load_entry_register(root)[0]}
        print(f"   其中已在死链册里的路径：{len(known)}")
        for r, n, p in sorted(new)[:12]:
            print(f"   {r}:{n}  {p}   [{classify(root, p)}]")
        if len(new) > 12:
            print(f"   …另有 {len(new) - 12} 处")
    print(f"\n合计新增位置：{len(total_new)}；涉及的注册表外新死链候选："
          f"{len({p for _r, _n, p in total_new if not (root / p).exists() and not p.startswith('/')})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
