#!/usr/bin/env python3
"""由 docs/audit/s90/closeout90.sh 逐行派生 closeout91.sh，并把残留 s90 归零。

派生完必须做的两件事（记忆里的老坑）：`grep -c "s90"` 归零、`bash -n` 过一遍。
唯一允许的残留是 `$X` 那个 `.s88-outside`——第 85 片起共用的**盘外**暂存区，
工具 stdout 必须落树外，否则 `workspace_clean` 在数学上不可能绿。
"""
import pathlib
import subprocess
import sys

SRC = pathlib.Path("docs/audit/s90/closeout90.sh")
DST = pathlib.Path("docs/audit/s91/closeout91.sh")

t = SRC.read_text(encoding="utf-8")
HEAD_OLD_START = "# 第 90 片收口链："
HEAD_OLD_END = "set -u"
head_new = """# 第 91 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 90 片）的收口脚本逐行派生，只换六处：报告名与 worktree/产物目录换轮次 /
#   产物目录与报告同名换轮次 / PRIOR_FLOOR 取上一代实测 collected（2726）/
#   --expect-test 点**两条**新原告（`--expect-test` 是 append，本轮两个新文件都有新用例：
#   test_ci_surface_census.py 是那把尺的牙、test_ci_face_gates.py 是把 CI 三面接进常驻的地方，
#   少点一条就等于"本轮新增的原告有一类没人核对它跑没跑"）/
#   绑定提交信息的正文按本轮实际改动重写。
# 派生完做两件事：grep 残留 s90 归零（下面 $X 的 .s88-outside 除外）、bash -n 过一遍。
#   唯一允许的残留是 $X 那个 .s88-outside —— 第 85 片起共用的**盘外**暂存区。
"""
i0 = t.index(HEAD_OLD_START)
i1 = t.index(HEAD_OLD_END)
t = head_new + t[i1:]

REPL = [
    ("report-s90.json", "report-s91.json"),
    (".wt-s90", ".wt-s91"),
    ("docs/audit/s90/", "docs/audit/s91/"),
    ("closeout90", "closeout91"),
    ("bind90", "bind91"),
    ("gate90", "gate91"),
    ("terminal90", "terminal91"),
    ("$R/docs/audit/s90", "$R/docs/audit/s91"),
    ('chore(s90): 收下发布门读数', 'chore(s91): 收下发布门读数'),
    ('chore(s90): 收尾验签读数入库', 'chore(s91): 收尾验签读数入库'),
    ("PRIOR_FLOOR=2718", "PRIOR_FLOOR=2726"),
    ("PRIOR_FLOOR 2718（上一代实测 collected）", "PRIOR_FLOOR 2726（上一代实测 collected）"),
    ("--expect-test tests/test_doc_command_census.py",
     "--expect-test tests/test_ci_surface_census.py \\\n    "
     "--expect-test tests/test_ci_face_gates.py"),
    ("=== 第 90 片收口结束", "=== 第 91 片收口结束"),
    ("""chore(s90): 绑定第 90 片的 attestation 报告

一次绑定、两个旗子同时给。识别面加宽与点名式举例标记都动了 scripts/ 与 tests/，
所以这一代报告必须是加宽之后那一版；上一代（第 89 片，collected 2718）只作下界对比。""",
     """chore(s91): 绑定第 91 片的 attestation 报告

一次绑定、两个旗子同时给。本轮新增对账尺与常驻三面（scripts/ci_surface_census.py、
tests/test_ci_surface_census.py、tests/test_ci_face_gates.py），并把 mypy 24→0 的修复
落在 src/ 与 tests/ 上 ⇒ 这一代报告必须测的是这些都在的那棵树；
上一代（第 90 片，collected 2726）只作下界对比。"""),
]
for old, new in REPL:
    t = t.replace(old, new)

bad = [ln for ln in t.split("\n") if "s90" in ln and ".s88-outside" not in ln]
if bad:
    print("残留 s90 未清零：")
    for b in bad:
        print("  ", b[:120])
    sys.exit(3)
DST.write_text(t, encoding="utf-8")
DST.chmod(0o755)
chk = subprocess.run(["bash", "-n", str(DST)], capture_output=True, text=True)
print("written", DST, "| bash -n rc =", chk.returncode, chk.stderr[-200:])
print("expect-test 次数 =", t.count("--expect-test"))
print("PRIOR_FLOOR 行 =", [ln for ln in t.split("\n") if ln.startswith("PRIOR_FLOOR")])
sys.exit(chk.returncode)
