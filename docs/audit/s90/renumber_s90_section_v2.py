#!/usr/bin/env python3
"""把新写的那一节从 §十 改成 §六（本文只有 一..五，跳号会让读者以为丢了四节），
   并修两处指涉：一处指向本文不存在的 §九，一处把"没验过"的 schema 断言改成现读的。

闸门：每个锚点必须恰好命中 1 次（整体先算完再落盘），任一不过就一个字都不写。
"""
import pathlib
import re

DOC = pathlib.Path("docs/audit/RECOGNITION_WIDENING_S90_2026-09-28.md")
LOG = pathlib.Path("CHANGELOG.md")

EDITS = [
    ("doc", "## 十、第二轮独立复核", "## 六、第二轮独立复核"),
    ("doc", "### 十之一、", "### 六之一、"),
    ("doc", "### 十之二、", "### 六之二、"),
    ("doc", "### 十之三、", "### 六之三、"),
    ("doc", "### 十之四、", "### 六之四、"),
    ("doc", "按 §十 复核件 #4", "按 §六 复核件 #4"),
    ("doc", "按 §十之一 改判原行内标注过期", "按 §六之一 改判原行内标注过期"),
    ("doc", "Unicode、三段版本号、`--旗=值`（§九 已登记）。",
     "Unicode、三段版本号、`--旗=值`——那三条已逐条登记在\n"
     "   `CHANGELOG.md` 的 v5.51 那条「未做」句里，本文不另开号。"),
    ("doc", "1. `--emit-register` 的草案与判决现在同口径（#8），但草案**不写** `example` 计数列：\n"
            "   读草案的人看不出\"这条只剩举例引用\"，要读 `--json` 才看得见。要不要开一列属排版裁决。",
            "1. `--emit-register` 的草案与判决现在同口径（#8），但册子的 schema 只有\n"
            "   `path / note / cited_by_at_emit_time` 三样，**没有一列**能表达\"这条只剩举例引用\"：\n"
            "   读草案的人看不出来，要读 `--json` 的 `entry_states` 与判决理由才看得见。\n"
            "   要不要给册子开第四列属排版裁决，本轮不动 schema。"),
    ("log", "逐条取证见 `RECOGNITION_WIDENING_S90_2026-09-28.md` §十",
            "逐条取证见 `RECOGNITION_WIDENING_S90_2026-09-28.md` §六"),
]

texts = {"doc": DOC.read_text(encoding="utf-8"), "log": LOG.read_text(encoding="utf-8")}
bad = []
for which, old, new in EDITS:
    n = texts[which].count(old)
    if n != 1:
        bad.append((which, n, old[:50]))
if bad:
    for b in bad:
        print(f"[GATE FAIL] {b[0]} 锚点命中 {b[1]} 次（要 1）：{b[2]!r}")
    print("任一不过 ⇒ 一个字都不写。")
    raise SystemExit(3)
for which, old, new in EDITS:
    texts[which] = texts[which].replace(old, new, 1)
DOC.write_text(texts["doc"], encoding="utf-8")
LOG.write_text(texts["log"], encoding="utf-8")

back = DOC.read_text(encoding="utf-8")
print("回读：'十、' 残留", back.count("十、"), "| '## 六、' 标题", back.count("## 六、"),
      "| '### 六之' 小节", back.count("### 六之"),
      "| 悬空 '（§九 已登记' ", len(re.findall(r"（§九 已登记", back)))
assert back.count("## 六、") == 1 and "十、" not in back and "（§九 已登记" not in back
assert "path / note / cited_by_at_emit_time" in back
assert "RECOGNITION_WIDENING_S90_2026-09-28.md` §六" in LOG.read_text(encoding="utf-8")
# 注意：上一版这里写的是 `"§十" not in 整份 CHANGELOG`——那是**过宽的断言**：
# 第 74/79 片那两条指向**别的**取证文档的 §九/§十 本来就该在（实测行 1081、2094）。
# 断言要钉"我改的那一处"，不是"这个符号在整本账里消失"。
print(f"OK {len(EDITS)} 处锚点各命中 1 次，两份文件已落盘并复读通过")
