#!/usr/bin/env python3
"""由上一片的收口脚本逐行派生 closeout92.sh，并把残留轮次号归零。

派生完必须做的两件事（记忆里的老坑）：`grep -c "s91"` 归零、`bash -n` 过一遍。
唯一允许的残留是 `$X` 那个 `.s88-outside`——第 85 片起共用的**盘外**暂存区
（工具 stdout 必须落树外，否则 `workspace_clean` 在数学上不可能绿），故意不随轮次改名。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

SRC = pathlib.Path("docs/audit/s91/closeout91.sh")
DST = pathlib.Path("docs/audit/s92/closeout92.sh")

t = SRC.read_text(encoding="utf-8")
HEAD_START = "# 第 91 片收口链"
head_new = """# 第 92 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 91 片）的收口脚本逐行派生，只换五处：报告名 / worktree 名 / 产物目录名
#   随轮次换；PRIOR_FLOOR 取上一代实测 collected（2736）；
#   --expect-test 点 `tests/test_dependency_license_gate.py` 一条
#   （第 92 片只有一个新常驻文件，且它是那把尺的牙；上一片那两条本轮没动，
#   留着不撤也没关系——但 `--expect-test` 的语义是"本轮新原告跑过了"，
#   多点一条会让 C8 从"本轮的"退化成"某轮的"，所以照实只点一条）。
# 派生完做两件事：grep 残留 s91 归零（下面 $X 的 .s88-outside 除外）、bash -n 过一遍。
#   唯一允许的残留是 $X 那个 .s88-outside —— 第 85 片起共用的**盘外**暂存区。
"""
i0, i1 = t.index(HEAD_START), t.index("set -u")
t = head_new + t[i1:]

REPL = [
    ("report-s91.json", "report-s92.json"),
    (".wt-s91", ".wt-s92"),
    ("docs/audit/s91/", "docs/audit/s92/"),
    ("$R/docs/audit/s91", "$R/docs/audit/s92"),
    ("closeout91", "closeout92"),
    ("bind91", "bind92"),
    ("gate91", "gate92"),
    ("terminal91", "terminal92"),
    ('chore(s91): 收下发布门读数', 'chore(s92): 收下发布门读数'),
    ('chore(s91): 收尾验签读数入库', 'chore(s92): 收尾验签读数入库'),
    ("PRIOR_FLOOR=2726", "PRIOR_FLOOR=2736"),
    ("--expect-test tests/test_ci_surface_census.py \\\n    "
     "--expect-test tests/test_ci_face_gates.py",
     "--expect-test tests/test_dependency_license_gate.py"),
    ("=== 第 91 片收口结束", "=== 第 92 片收口结束"),
    ("""chore(s91): 绑定第 91 片的 attestation 报告

一次绑定、两个旗子同时给。本轮新增对账尺与常驻三面（scripts/ci_surface_census.py、
tests/test_ci_surface_census.py、tests/test_ci_face_gates.py），并把 mypy 24→0 的修复
落在 src/ 与 tests/ 上 ⇒ 这一代报告必须测的是这些都在的那棵树；
上一代（第 90 片，collected 2726）只作下界对比。""",
     """chore(s92): 绑定第 92 片的 attestation 报告

一次绑定、两个旗子同时给。本轮新增依赖许可证门禁（scripts/dependency_license_gate.py）
与它的常驻牙（tests/test_dependency_license_gate.py，9 条）⇒ 这一代报告必须含那 9 条；
上一代（第 91 片，collected 2736）只作下界对比。
门禁本身今天对 casadi/LGPL 判红是有意的：台账 decision=needs-review，等属主拍板。"""),
]
for old, new in REPL:
    t = t.replace(old, new)

bad = [ln for ln in t.split("\n") if "s91" in ln and ".s88-outside" not in ln]
if bad:
    print("残留 s91 未清零 ⇒ 一个字都不写：")
    for b in bad:
        print("  ", b[:130])
    raise SystemExit(3)
if t.count("--expect-test") != 3:      # 头注释里提一次 + 命令行里一次
    print("expect-test 次数不对：", t.count("--expect-test"))
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
