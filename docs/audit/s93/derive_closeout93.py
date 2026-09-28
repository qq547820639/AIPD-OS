#!/usr/bin/env python3
"""由第 92 片的收口脚本逐行派生 closeout93.sh，并把残留轮次号归零。

派生完必须做的两件事（记忆里的老坑）：`grep -c "s92"` 归零、`bash -n` 过一遍。
唯一允许的残留是 `$X` 那个 `.s88-outside`——第 85 片起共用的**盘外**暂存区
（工具 stdout 必须落树外，否则 `workspace_clean` 在数学上不可能绿），故意不随轮次改名。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

SRC = pathlib.Path("docs/audit/s92/closeout92.sh")
DST = pathlib.Path("docs/audit/s93/closeout93.sh")

t = SRC.read_text(encoding="utf-8")
HEAD_START = "# 第 92 片收口链"
head_new = """# 第 93 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 92 片）的收口脚本逐行派生，只换五处：报告名 / worktree 名 / 产物目录名
#   随轮次换；PRIOR_FLOOR 取上一代实测 collected（2745）；
#   --expect-test 仍只点 `tests/test_dependency_license_gate.py` 一条
#   （第 93 片的原告全在上一片那个文件里：它给那把尺加了正文面，9 条 → 17 条，
#   本轮没有新开常驻文件，所以这一旗不改名——改了反而会把"本轮的原告"写成"别人的原告"）。
# 派生完做两件事：grep 残留 s92 归零（下面 $X 的 .s88-outside 除外）、bash -n 过一遍。
#   唯一允许的残留是 $X 那个 .s88-outside —— 第 85 片起共用的**盘外**暂存区。
"""
_i0 = t.index(HEAD_START)
_i1 = t.index("set -u")
t = head_new + t[_i1:]

REPL = [
    ("report-s92.json", "report-s93.json"),
    (".wt-s92", ".wt-s93"),
    ("docs/audit/s92/", "docs/audit/s93/"),
    ("$R/docs/audit/s92", "$R/docs/audit/s93"),
    ("closeout92", "closeout93"),
    ("bind92", "bind93"),
    ("gate92", "gate93"),
    ("chore(s92): 收下发布门读数", "chore(s93): 收下发布门读数"),
    ("chore(s92): 收尾验签读数入库", "chore(s93): 收尾验签读数入库"),
    ("PRIOR_FLOOR=2736", "PRIOR_FLOOR=2745"),
    ("=== 第 92 片收口结束", "=== 第 93 片收口结束"),
    ("""chore(s92): 绑定第 92 片的 attestation 报告""",
     """chore(s93): 绑定第 93 片的 attestation 报告"""),
    ("""一次绑定、两个旗子同时给。本轮新增依赖许可证门禁（scripts/dependency_license_gate.py）
与它的常驻牙（tests/test_dependency_license_gate.py，9 条）⇒ 这一代报告必须含那 9 条；
上一代（第 91 片，collected 2736）只作下界对比。
门禁本身今天对 casadi/LGPL 判红是有意的：台账 decision=needs-review，等属主拍板。""",
     """一次绑定、两个旗子同时给。本轮把正文面接进上一片那把尺
（scripts/dependency_license_gate.py 的 detect_body / bodies_of / body_face /
package_license），并把常驻牙从 9 条加到 17 条 ⇒ 这一代报告必须含那 17 条；
上一代（第 92 片，collected 2745）只作下界对比。
门禁今天仍对 casadi/LGPL 判红是有意的：台账 decision=needs-review，等属主拍板；
正文面在真语料上是 0 条判红（防御性加严，见取证文档 §一 与 §四）。"""),
]
for old, new in REPL:
    t = t.replace(old, new)

bad = [ln for ln in t.split("\n") if "s92" in ln and ".s88-outside" not in ln]
if bad:
    print("残留 s92 未清零 ⇒ 一个字都不写：")
    for b in bad:
        print("  ", b[:130])
    raise SystemExit(3)
n_exp = t.count("--expect-test")
if n_exp != 2:                      # 头注释里不写旗子名 ⇒ 命令行里应当恰好一次
    print("expect-test 次数不对：", n_exp)
    raise SystemExit(3)
DST.parent.mkdir(parents=True, exist_ok=True)
DST.write_text(t, encoding="utf-8")
DST.chmod(0o755)
chk = subprocess.run(["bash", "-n", str(DST)], capture_output=True, text=True)
print("written", DST, "| bash -n rc =", chk.returncode, chk.stderr[-200:])
print("PRIOR_FLOOR 行 =", [ln for ln in t.split("\n") if ln.startswith("PRIOR_FLOOR")])
print("expect-test 调用行 =", [ln.strip() for ln in t.split("\n")
                              if "--expect-test tests/" in ln])
sys.exit(chk.returncode)
