#!/usr/bin/env python3
"""修 Z10 的第二处编辑：上一版把 `\\.` 分支写成了 `\\.`＋`…` 连在一起（漏了 `|`），
   那是一个**永不开火的分支** ⇒ 变异体与原件在可观察输出上等价 ⇒ 臂"存活"是假信号。

这次由程序生成目标行，并**先用它自己编译一遍那条正则**：
`../outside/x.py` 必须命中、`a/b.py` 必须不命中。不开火的臂不进电池。
"""
import pathlib
import re

BS = chr(92)
P = pathlib.Path("docs/audit/s90/battery90.py")
lines = P.read_text(encoding="utf-8").split("\n")
old80 = lines[79]
assert old80.strip().startswith("(r'ENTRY_PLACEHOLDER_RE"), old80
lit = old80.strip()[1:-1]                       # 第 80 行那串字面量（去掉 `(` 与 `,`）
assert lit.startswith("r'") and lit.endswith(")'"), lit
new_lit = lit.replace("$|NN|\u2026", "$|NN|" + BS + "." + BS + "." + "|" + "\u2026")
want = "|" + BS + "." + BS + "." + "|" + "\u2026"
assert new_lit != lit and want in new_lit, new_lit
line = "       " + new_lit + ")),"
inner = re.search(r"re\.compile\(r\"(.*?)\"\)", new_lit).group(1)
pat = re.compile(inner)
assert pat.search("../outside/x.py"), inner
assert not pat.search("scripts/live.py"), inner
assert pat.search("docs/audit/s11..s12.py"), inner      # 区间模板仍要接住
lines[80] = line
P.write_text("\n".join(lines), encoding="utf-8")
print("生成物内层正则:", inner)
print("REWRITTEN:", repr(lines[80]))
