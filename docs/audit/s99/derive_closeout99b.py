r"""由 `docs/audit/s99/closeout99.sh`（第一代）派生第二代 `closeout99b.sh`。

为什么要第二代：第一代那一跑之后我又改了 `CHANGELOG.md`（补 92/70 那组现读），而它是被哈希的面
⇒ `source_manifest_zero_diff` 判红，而报告的自记指纹是对着旧清单算的 ⇒ 绑定前预检必然拒。
唯一正确的路是清单一重锚后**重跑一遍干净全量**，所以这一份只是换名与换下界，工序一字不减。

与第一代派生器同一套闸门：锚点先数（任一 ≠ 预期 ⇒ 一支不落，退 7）、
记号面残留归零、工序哨兵在场、落盘后 `bash -n` 与写后读回复算。
换的东西只有五类：worktree 名（`.wt-s99b`）、报告名（`report-s99b.json`）、
三个日志名的 `b` 后缀、两处提交信息、头部注释。**`PRIOR_FLOOR` 不动**（仍是已认证的
第 98 片实测 collected **2783**）：第一代（2785）作废、不当下界，而第二代测的就是
第一代那棵树的同一份内容 ⇒ collected 只会复现 2785；把下界也抬到 2785 会让
`collected > PRIOR_FLOOR` 这条防缩水的前提把一次合法的重跑读成"用例少了"。
产物目录仍是 `docs/audit/s99/`（同一轮的证件放同一个目录，代次写在文件名里）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = Path("docs/audit/s99/closeout99.sh")
DST = Path("docs/audit/s99/closeout99b.sh")

OLD_HEAD = """# 第 99 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 98 片）逐行派生（派生器 `derive_closeout99.py`，锚点命中数与工序哨兵都在它手里），
#   只换：报告名 / worktree 名（`.wt-s99`，绝对路径且落在仓库**外**）/ 产物目录名 /
#   PRIOR_FLOOR=上一代实测 collected(2783) / 绑定提交信息 / --expect-test 点三条"""

NEW_HEAD = """# 第 99 片收口链【第二代 b】：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由本片第一代 `closeout99.sh` 派生（派生器 `derive_closeout99b.py`，同一套锚点计数与工序哨兵），
#   只换：worktree 名（`.wt-s99b`，绝对路径、落在仓库**外**）/ 报告名（`report-s99b.json`）/
#   三个日志名的 b 后缀 / 两处提交信息 / 头部注释。
#   **`PRIOR_FLOOR` 沿用已认证的 2783（第 98 片实测 collected），不改**：第一代（2785）已作废、
#   不当下界；而第二代测的就是同一棵树的内容 ⇒ collected 只会复现 2785，若把下界也写成 2785，
#   前提判据 `collected > PRIOR_FLOOR` 会把一次合法的重跑读成"用例缩水"。派生器因此
#   **没有** PRIOR_FLOOR 这条替换锚（哨兵仍要求 `PRIOR_FLOOR=2783` 在场）。
#   第二代的原因记在本片 §认证读数与那份 VOID 报告：绑定之后又动了被哈希的面
#   （`CHANGELOG.md`）⇒ 清单与树不同源，绕不过（绑定前预检正是为此而立），只能重锚后重跑一遍。
#   --expect-test 仍点三条：`tests/test_forensic_scripts_root.py`（.sh 面 12 条）、
#   `tests/test_ci_surface_census.py`（行钉进自测 + 条数两格同源，15 条）、
#   `tests/test_forensic_scripts_parse.py`（本轮新增取证脚本与收口件的语法读者）。"""

OLD_BIND_MSG = """chore(s99): 绑定第 99 片的 attestation 报告

一次绑定、两个旗子同时给。本轮两处：① 取证根路径那把尺的语料面从 `*.py` 扩到 `*.py` + `*.sh`
（shell 赋值右侧是裸路径，只用引号分支时 17 个 `.sh` 里带仓库内绝对路径的 16 个一个都读不到），
名册 52 → 69 条、`s83b.sh` 的仓库根改由 `BASH_SOURCE` 推；② CI 面两条行钉判决
（`CI面行钉不穷举` / `CI面行钉指错行`）接进 `ci_surface_census --self-test`（6 → 8 条读数），
并给自测补"自报条数 == 逐条打印行数"两格同源——电池臂 Y1 第一版就是这么 SURVIVED 的。
上一代（第 98 片，collected 2783）只作下界对比。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。"""

NEW_BIND_MSG = """chore(s99b): 绑定第 99 片第二代的 attestation 报告（第一代作废）

一次绑定、两个旗子同时给。判定内容与第一代完全相同（`.sh` 面进分母 + 两条行钉判决进 CI 自测
+ 自测条数两格同源），换的只有清单：第一代那一跑之后又改了被哈希的 `CHANGELOG.md`
（补 92 个脚本 / 名册 70 条那组现读），`source_manifest_zero_diff` 判红、逐条对磁盘复算确认
漂移只有那 1 条（692 条仍一致）⇒ 重锚清单后重跑一遍干净签出。第一代报告按惯例留档
`docs/audit/s99/report-s99-VOID-tree-51023121-fp-21085171c58e.json`。
上一代（第 98 片，collected 2783）仍是下界——第一代（2785）已作废，不拿来当自己的界，
否则同一份内容重跑一遍就会被 `collected > 下界` 读成用例缩水。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。"""

# (旧, 新, 预期命中次数)：先长后短，头部与绑定信息整块换掉之后再动散点
GLOBAL: list[tuple[str, str, int]] = [
    (OLD_HEAD, NEW_HEAD, 1),
    (OLD_BIND_MSG, NEW_BIND_MSG, 1),
    ("chore(s99): 收下发布门读数（取证件先入库，再谈验签）",
     "chore(s99b): 收下发布门读数（第二代，清树后复跑）", 1),
    ("chore(s99): 收尾验签读数入库", "chore(s99b): 收尾验签读数入库（第二代）", 1),
    ("WT=" + str(REPO.parent / ".wt-s99"), "WT=" + str(REPO.parent / ".wt-s99b"), 1),
    ("report-s99.json", "report-s99b.json", 5),
    ("bind99.log", "bind99b.log", 4),
    ("gate99.log", "gate99b.log", 3),
    ("closeout99.log", "closeout99b.log", 4),
    ("第 99 片收口结束", "第 99 片第二代收口结束", 1),
]

SENTINELS = ["GATE_RC=$?", "CV_RC=$?", "FINAL_COMMIT_RC=$?", "MIN_TESTS=",
             "SKIP 面逐条相同", "PRECHECK FAILED", "bind99b.log", "gate99b.log",
             "closeout99b.log", ".wt-s99b", "report-s99b.json", "docs/audit/s99",
             "--expect-test tests/test_forensic_scripts_root.py",
             "--expect-test tests/test_ci_surface_census.py",
             "--expect-test tests/test_forensic_scripts_parse.py",
             "PRIOR_FLOOR=2783"]

# 不许残留的第一代记号（b 后缀名不会与这些逐字相同）；PRIOR_FLOOR 是**故意不动**的那一格，
# 所以它不在这里——它由 SENTINELS 要求仍以 2783 在场（作废的那一代不当下界）。
FORBIDDEN = ["report-s99.json", "bind99.log", "gate99.log", "closeout99.log",
             "chore(s99)"]


def build(text: str) -> tuple[str, list[str]]:
    notes = []
    for old, new, want in GLOBAL:
        got = text.count(old)
        if got != want:
            notes.append(f"锚点 {old[:34]!r} 命中 {got} 次（要 {want}）⇒ 这一处不动")
            continue
        if want == 0:
            continue
        text = text.replace(old, new)
        notes.append(f"ok {got}x {old[:34]!r}")
    return text, notes


def gate(text: str) -> list[str]:
    bad = [f"第一代记号残留 {f!r} 共 {text.count(f)} 处" for f in FORBIDDEN if f in text]
    for s in SENTINELS:
        if s not in text:
            bad.append(f"工序哨兵缺席：{s!r}")
    if text.count(".wt-s99b") != 2:
        bad.append(f"worktree 名应有 2 处（注释 + WT= 行），实得 {text.count('.wt-s99b')}")
    return bad


def main() -> int:
    if not SRC.is_file():
        print(f"读不到 {SRC}")
        return 7
    text, notes = build(SRC.read_text(encoding="utf-8"))
    for n in notes:
        print("  " + n)
    bad = gate(text)
    if bad:
        print("闸门不过 ⇒ 一份都不落盘：")
        for b in bad:
            print("  ✗ " + b)
        return 7
    DST.write_text(text, encoding="utf-8")
    chk = subprocess.run(["bash", "-n", str(DST)], capture_output=True, text=True)
    print(f"bash -n rc={chk.returncode} {chk.stderr[:200]}")
    if chk.returncode != 0:
        return 6
    bad2 = gate(DST.read_text(encoding="utf-8"))
    if bad2:
        print("写后读回复算不过：")
        for b in bad2:
            print("  ✗ " + b)
        return 6
    print(f"已写 {DST}：{len(text.splitlines())} 行；哨兵 {len(SENTINELS)} 条在场；"
          f"第一代记号归零")
    return 0


if __name__ == "__main__":
    sys.exit(main())
