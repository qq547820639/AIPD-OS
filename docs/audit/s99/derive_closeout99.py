r"""由 `docs/audit/s98/closeout98.sh` 逐行派生第 99 片的收口链，只在锚点处改。

两阶段：先在内存里把所有替换算完并过闸门，任一锚点命中数不等于预期就一份都不落盘。
闸门（都是这一族真踩过的坑）：
① `s98` 这个**记号面**（basename/路径/日志名）必须归零；汉字面「第 98 片」允许且只许
   出现在指代上一代的那两处（头部注释 + 绑定提交信息），数量由脚本现算；
② 工序哨兵必须在场（`GATE_RC=$?` / `CV_RC=$?` / `FINAL_COMMIT_RC=$?` / `MIN_TESTS=` /
   「SKIP 面逐条相同」/「PRECHECK FAILED」/ 本轮三个日志名）——第 96 片那轮派生脚本只写了
   head 就过了 `bash -n`，丢掉的是门与验签两段；
③ 本轮该出现的名字（`.wt-s99`、`report-s99.json`、`docs/audit/s99/`、三条 expect-test、
   `PRIOR_FLOOR=2783`）必须各就各位；
④ 落盘后 `bash -n` 过一遍并读回磁盘复算 ①②③（写后读回，不由内存值说话）。

跑法：`python -B docs/audit/s99/derive_closeout99.py`（在仓库根）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 路径一律由 `__file__` 推：**不在这份派生器里写仓库内绝对字面量**。
# 写了它就得进名册领一条豁免（第 96 片那把尺判的就是这一格），而它其实属于"按 `__file__` 推根"
# 那一档；上一轮的 `derive_closeout98.py` 也是这么待的。
REPO = Path(__file__).resolve().parents[3]
WT_BASE = str(REPO.parent / ".wt-s99")
SRC = Path("docs/audit/s98/closeout98.sh")
DST = Path("docs/audit/s99/closeout99.sh")

OLD_HEAD = """# 第 98 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 97 片）逐行派生，只换：报告名 / worktree 名 / 产物目录名 /
#   PRIOR_FLOOR=上一代实测 collected(2780) / 绑定提交信息 / --expect-test 点两条
#   （第 98 片的原告在两个文件里：`tests/test_ci_surface_census.py` 那 15 条
#    与 `tests/test_forensic_scripts_parse.py`——后者是本轮新增取证脚本
#    `docs/audit/s98/battery98.py` 的唯一读者，它语法塌只有这一条看得见。）
# 派生完做两件事：grep 残留 s94 归零（$X 的 .s88-outside 除外）、bash -n 过一遍。"""

NEW_HEAD = """# 第 99 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 98 片）逐行派生（派生器 `derive_closeout99.py`，锚点命中数与工序哨兵都在它手里），
#   只换：报告名 / worktree 名（`.wt-s99`，绝对路径且落在仓库**外**）/ 产物目录名 /
#   PRIOR_FLOOR=上一代实测 collected(2783) / 绑定提交信息 / --expect-test 点三条
#   （第 99 片的原告：`tests/test_forensic_scripts_root.py` 那 12 条（新尺的 .sh 面）、
#    `tests/test_ci_surface_census.py` 那 15 条（行钉两条判决进自测 + 条数两格同源）、
#    `tests/test_forensic_scripts_parse.py`（本轮新增取证脚本 `docs/audit/s99/battery99.py`
#    与改过的 `docs/audit/s96/build_forensic_root_register.py` 的唯一语法读者）。"""

OLD_BIND_MSG = """chore(s98): 绑定第 98 片的 attestation 报告

一次绑定、两个旗子同时给。本轮动的是 CI 对账尺的**行钉维度**：`ci_commands()` 按命令文本去重，
所以 `line` 一直是「排序后第一个跑这条命令的 job」那一行，而 `job` 列是一串名字——现读 3 条
跨 job 命令共 23 处执行点只钉住 3 个。现在逐 (job, 行) 记账（`occurrences`/`lines_total`，
定不到行号的 job 也以空列表露头），并加两条判决 `CI面行钉不穷举` / `CI面行钉指错行`；
第二查做成纯函数 `line_pin_defects(cmds, file_lines)`，否则正常解析下天然自洽、够不到那一档。
上一代（第 97 片，collected 2780）只作下界对比。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。"""

NEW_BIND_MSG = """chore(s99): 绑定第 99 片的 attestation 报告

一次绑定、两个旗子同时给。本轮两处：① 取证根路径那把尺的语料面从 `*.py` 扩到 `*.py` + `*.sh`
（shell 赋值右侧是裸路径，只用引号分支时 17 个 `.sh` 里带仓库内绝对路径的 16 个一个都读不到），
名册 52 → 69 条、`s83b.sh` 的仓库根改由 `BASH_SOURCE` 推；② CI 面两条行钉判决
（`CI面行钉不穷举` / `CI面行钉指错行`）接进 `ci_surface_census --self-test`（6 → 8 条读数），
并给自测补"自报条数 == 逐条打印行数"两格同源——电池臂 Y1 第一版就是这么 SURVIVED 的。
上一代（第 98 片，collected 2783）只作下界对比。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。"""

OLD_EXPACT = """    --expect-test tests/test_ci_surface_census.py \\
    --expect-test tests/test_forensic_scripts_parse.py \\
"""

NEW_EXPACT = """    --expect-test tests/test_forensic_scripts_root.py \\
    --expect-test tests/test_ci_surface_census.py \\
    --expect-test tests/test_forensic_scripts_parse.py \\
"""

# (旧, 新, 预期命中次数)
GLOBAL: list[tuple[str, str, int]] = [
    (OLD_HEAD, NEW_HEAD, 1),
    (OLD_BIND_MSG, NEW_BIND_MSG, 1),
    (OLD_EXPACT, NEW_EXPACT, 1),
    ("chore(s98): 收下发布门读数（取证件先入库，再谈验签）",
     "chore(s99): 收下发布门读数（取证件先入库，再谈验签）", 1),
    ("chore(s98): 收尾验签读数入库", "chore(s99): 收尾验签读数入库", 1),
    ("WT=" + str(REPO.parent / ".wt-s98b"), "WT=" + WT_BASE, 1),
    ("PRIOR_FLOOR=2780", "PRIOR_FLOOR=2783", 1),
    ("report-s98.json", "report-s99.json", 5),
    ("docs/audit/s98", "docs/audit/s99", None),          # 次数由现算给出，只要求 >0 且残留归零
    ("bind98.log", "bind99.log", 4),
    ("gate98.log", "gate99.log", 3),
    ("closeout98.log", "closeout99.log", 4),
    ("第 98 片收口结束", "第 99 片收口结束", 1),
]

SENTINELS = ["GATE_RC=$?", "CV_RC=$?", "FINAL_COMMIT_RC=$?", "MIN_TESTS=",
             "SKIP 面逐条相同", "PRECHECK FAILED", "bind99.log", "gate99.log",
             "closeout99.log", ".wt-s99", "report-s99.json", "docs/audit/s99",
             "--expect-test tests/test_forensic_scripts_root.py",
             "PRIOR_FLOOR=2783"]


def build(text: str) -> tuple[str, list[str]]:
    notes = []
    for old, new, want in GLOBAL:
        got = text.count(old)
        if want is None:
            if got < 1:
                notes.append(f"锚点没命中：{old[:40]!r}")
                continue
        elif got != want:
            notes.append(f"锚点 {old[:40]!r} 命中 {got} 次（要 {want}）")
            continue
        text = text.replace(old, new)
        notes.append(f"ok {got}x {old[:34]!r}")
    return text, notes


def gate(text: str) -> list[str]:
    bad = []
    # 记号面（路径/日志名/报告名/worktree 名）一律不许残留 98；汉字面只许指代上一代那两处：
    # 头部注释「由上一片（第 98 片）逐行派生」与绑定提交信息「上一代（第 98 片，collected 2783）」。
    if "s98" in text:
        lines = [i + 1 for i, ln in enumerate(text.splitlines()) if "s98" in ln]
        bad.append(f"记号面残留 s98 共 {text.count('s98')} 处，行号 {lines}")
    n98 = text.count("第 98 片")
    if n98 != 2:
        bad.append(f"汉字面「第 98 片」应有 2 处（都指代上一代），实得 {n98}")
    if text.count("98") != 2:
        lines = [i + 1 for i, ln in enumerate(text.splitlines()) if "98" in ln]
        bad.append(f"全文 `98` 出现 {text.count('98')} 次（只许那两处），行号 {lines}")
    for s in SENTINELS:
        if s not in text:
            bad.append(f"工序哨兵缺席：{s!r}")
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
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(text, encoding="utf-8")

    chk = subprocess.run(["bash", "-n", str(DST)], capture_output=True, text=True)
    back = DST.read_text(encoding="utf-8")
    print(f"bash -n rc={chk.returncode} {chk.stderr[:200]}")
    if chk.returncode != 0:
        return 6
    bad2 = gate(back)
    if bad2:
        print("写后读回复算不过：")
        for b in bad2:
            print("  ✗ " + b)
        return 6
    print(f"已写 {DST}：{len(back.splitlines())} 行；"
          f"哨兵 {len(SENTINELS)} 条全部在场；记号面 s98 归零")
    return 0


if __name__ == "__main__":
    sys.exit(main())
