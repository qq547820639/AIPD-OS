#!/usr/bin/env python3
"""由第 93 片的收口脚本逐行派生 closeout94.sh，并把残留轮次号归零。

派生完必须做的两件事：`grep -c "s93"` 归零（$X 那个 .s88-outside 除外）、`bash -n` 过一遍。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

SRC = pathlib.Path("docs/audit/s93/closeout93.sh")
DST = pathlib.Path("docs/audit/s94/closeout94.sh")

t = SRC.read_text(encoding="utf-8")
head_new = """# 第 94 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 93 片）的收口脚本逐行派生，只换四处：报告名 / worktree 名 / 产物目录名
#   随轮次换；PRIOR_FLOOR 取上一代实测 collected（2754）；
#   --expect-test 换点 `tests/test_ci_surface_census.py`（第 94 片的原告全在那一个文件里：
#   行号那格与软门那格各两条，6 条 → 10 条；上一片点的许可证文件本轮没动，不沿留——
#   沿留会让 C8 的语义从"本轮的原告跑过了"退化成"某轮的原告跑过了"）。
# 派生完做两件事：grep 残留 s93 归零（下面 $X 的 .s88-outside 除外）、bash -n 过一遍。
#   唯一允许的残留是 $X 那个 .s88-outside —— 第 85 片起共用的**盘外**暂存区。
set -u
"""
i1 = t.index("set -u")
t = head_new + t[i1 + len("set -u\n"):]

REPL = [
    ("report-s93.json", "report-s94.json"),
    (".wt-s93", ".wt-s94"),
    ("docs/audit/s93/", "docs/audit/s94/"),
    ("$R/docs/audit/s93", "$R/docs/audit/s94"),
    ("closeout93", "closeout94"),
    ("bind93", "bind94"),
    ("gate93", "gate94"),
    ("chore(s93): 收下发布门读数", "chore(s94): 收下发布门读数"),
    ("chore(s93): 收尾验签读数入库", "chore(s94): 收尾验签读数入库"),
    ("PRIOR_FLOOR=2745", "PRIOR_FLOOR=2754"),
    ("--expect-test tests/test_dependency_license_gate.py",
     "--expect-test tests/test_ci_surface_census.py"),
    ("=== 第 93 片收口结束", "=== 第 94 片收口结束"),
    ("chore(s93): 绑定第 93 片的 attestation 报告", "chore(s94): 绑定第 94 片的 attestation 报告"),
    ("""一次绑定、两个旗子同时给。本轮把正文面接进上一片那把尺
（scripts/dependency_license_gate.py 的 detect_body / bodies_of / body_face /
package_license），并把常驻牙从 9 条加到 17 条 ⇒ 这一代报告必须含那 17 条；
上一代（第 92 片，collected 2745）只作下界对比。
门禁今天仍对 casadi/LGPL 判红是有意的：台账 decision=needs-review，等属主拍板；
正文面在真语料上是 0 条判红（防御性加严，见取证文档 §一 与 §四）。""",
     """一次绑定、两个旗子同时给。本轮把 CI 对账尺的 `line` 从恒 0 换成 `ci.yml:NNN`
（scripts/ci_surface_census.py 的 _run_marks / _split_shell 三元组），并新增一档
`CI面被声明为可失败`，常驻牙 6 条 → 10 条 ⇒ 这一代报告必须含那 10 条；
上一代（第 93 片，collected 2754）只作下界对比。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），
它不影响发布门：发布门那 8 项不消费这把尺的退码，红由常驻用例钉成"它还没被拍板"。"""),
]
# 替换锚点的下限是 1 次，不是恰好 1 次：`report-s93.json` 这类路径本来就在脚本里出现 5 次
# （预检 / MIN_TESTS / SKIP 面对账 / 两份 cp），要求"恰好 1 次"会把合法的多处引用
# 当成锚点不唯一而拒绝派生。真正的把关在事后两条：残留 s93 归零 + bash -n 过。
for old, new in REPL:
    if t.count(old) < 1:
        print(f"锚点命中 0 次：{old[:44]!r} ⇒ 整体不落盘")
        raise SystemExit(3)
    t = t.replace(old, new)

bad = [ln for ln in t.split("\n") if "s93" in ln and ".s88-outside" not in ln]
if bad:
    print("残留 s93 未清零 ⇒ 一个字都不写：")
    for b in bad:
        print("  ", b[:130])
    raise SystemExit(3)
n_exp = t.count("--expect-test")
calls = [ln.strip() for ln in t.split("\n") if "--expect-test tests/" in ln]
if n_exp < 2 or calls != ["--expect-test tests/test_ci_surface_census.py \\"]:
    print("expect-test 形状不对：", n_exp, calls)
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
