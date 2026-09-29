r"""由 `docs/audit/s99/closeout99b.sh` 派生第 100 片的收口链 `docs/audit/s100/closeout100.sh`。

与上一片两个派生器同一套纪律：**两阶段**（先在内存里把所有替换算完并过闸门，任一锚点
命中数 ≠ 预期就一份都不落盘）、**整行锚**（前缀锚会在"已经改过"的行上仍然命中 ⇒ 重跑把清单
贴两遍，第 100 片的接面派生器就是这么被自己的复验拦下的）、**写后读回复算** + `bash -n`。

头部（`set -u` 之前的那段注释）按**结构**整段换掉而不是逐句找锚：上一片那一跑留下的
"第一代作废 / VOID 报告 / 下界沿用 2783"这些句子对本片全是错的，逐句改最容易改漏。

换的东西：worktree 名（`.wt-s100`，绝对路径、仓库外）、报告名（`report-s100.json`）、
三个日志名（`bind100/gate100/closeout100.log`）、产物目录（`docs/audit/s100/`）、
`PRIOR_FLOOR`（已认证的上一代 collected **2785**）、绑定提交信息、三条 `--expect-test`
（本片原告：`tests/test_scripts_lint_ratchet.py` 10 条新常驻、
`tests/test_ci_face_gates.py` 改过的镜像三连之一、
`tests/test_forensic_scripts_parse.py` 作为本轮新增取证脚本 `docs/audit/s100/*.py`
与 `scripts/scripts_lint_ratchet.py` 的语法读者）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = Path("docs/audit/s99/closeout99b.sh")
DST = Path("docs/audit/s100/closeout100.sh")

NEW_HEAD = """# 第 100 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片第二代 `closeout99b.sh` 派生（派生器 `derive_closeout100.py`：锚点先数、
#   任一 ≠ 预期整批不落盘、整行锚、落盘后 `bash -n` 与写后读回复算）。
#   只换：worktree 名（`.wt-s100`，绝对路径且落在仓库**外**——`git -C 仓库 worktree add 相对路径`
#   会按 `-C` 的目标解析，第 99 片实测把签出建到仓库里过一次）/ 报告名 / 三个日志名 /
#   产物目录（`docs/audit/s100/`）/ PRIOR_FLOOR=上一代实测 collected(2785) / 绑定提交信息 /
#   --expect-test 三条（原告换成 `tests/test_scripts_lint_ratchet.py`、
#   `tests/test_ci_face_gates.py`、`tests/test_forensic_scripts_parse.py`）。
#   工序顺序按第 99 片那条教训摆：**所有被哈希的面（README/CHANGELOG/.github/scripts/tests/src）
#   都在"生成清单 → 干净全量 → 绑定"这条链开始之前定稿**；链跑完之后只动 `docs/audit/`
#   （两份清单整体排除该前缀），否则等于自己开第二代。
"""

OLD_HEAD_LINE = "chore(s99b): 绑定第 99 片第二代的 attestation 报告（第一代作废）"

NEW_BIND_MSG = """chore(s100): 绑定第 100 片的 attestation 报告

一次绑定、两个旗子同时给。本轮把 `scripts/` 接进 CI 的 ruff 面：`.github/workflows/ci.yml`
那条命令逐个点名今天 0 债的 16 个文件，其余 44 个有债文件由**测量基线**管
（`docs/audit/SCRIPTS_LINT_BASELINE.json`，138 格 / 642 条命中）——不用 ruff 的
`per-file-ignores`，因为那会把同码新增命中一起吞掉，而绕开它数真债只能再复刻一份配置。
上一代（第 99 片第二代，collected 2785）作下界；本轮新增常驻 10 条 ⇒ collected 只会更多。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。"""

OLD_EXPACT = """    --expect-test tests/test_forensic_scripts_root.py \\
    --expect-test tests/test_ci_surface_census.py \\
    --expect-test tests/test_forensic_scripts_parse.py \\
"""

NEW_EXPACT = """    --expect-test tests/test_scripts_lint_ratchet.py \\
    --expect-test tests/test_ci_face_gates.py \\
    --expect-test tests/test_forensic_scripts_parse.py \\
"""

# (旧, 新, 预期命中次数) —— 顺序要紧：先换头部与绑定信息正文（两处都会吃掉若干锚点的次数）
GLOBAL: list[tuple[str, str, int]] = [
    ("PRELUDE", NEW_HEAD, 1),
    ("BINDMSG", NEW_BIND_MSG, 1),
    ("chore(s99b): 收下发布门读数（第二代，清树后复跑）",
     "chore(s100): 收下发布门读数（取证件先入库，再谈验签）", 1),
    ("chore(s99b): 收尾验签读数入库（第二代）", "chore(s100): 收尾验签读数入库", 1),
    ("WT=" + str(REPO.parent / ".wt-s99b") + "\n",
     "WT=" + str(REPO.parent / ".wt-s100") + "\n", 1),
    ("PRIOR_FLOOR=2783\n", "PRIOR_FLOOR=2785\n", 1),
    ("report-s99b.json", "report-s100.json", 5),
    ("bind99b.log", "bind100.log", 4),
    ("gate99b.log", "gate100.log", 3),
    ("closeout99b.log", "closeout100.log", 4),
    ("docs/audit/s99", "docs/audit/s100", 12),
    (OLD_EXPACT, NEW_EXPACT, 1),
    ("第 99 片第二代收口结束", "第 100 片收口结束", 1),
]

SENTINELS = ["GATE_RC=$?", "CV_RC=$?", "FINAL_COMMIT_RC=$?", "MIN_TESTS=",
             "SKIP 面逐条相同", "PRECHECK FAILED", "bind100.log", "gate100.log",
             "closeout100.log", ".wt-s100", "report-s100.json", "docs/audit/s100",
             "PRIOR_FLOOR=2785",
             "--expect-test tests/test_scripts_lint_ratchet.py",
             "--expect-test tests/test_ci_face_gates.py",
             "--expect-test tests/test_forensic_scripts_parse.py"]

# 上一片的记号面（路径/日志名/报告名）一律归零；汉字面只许留"下界来自第 99 片第二代"那一句
# 上一片的**操作性记号**一律归零（这些留着就是真 bug：会去读上一代的报告、写进上一代的目录）。
# 故意留下的只有两类：头部那句"派生自 `closeout99b.sh`"是出处（provenance，不是操作数），
# 以及三处「第 99 片」——worktree 相对路径那个坑、"链前定稿"那条工序教训（都在头部），
# 与绑定信息里指下界来处的那一句。
FORBIDDEN = ["docs/audit/s99", ".wt-s99b", "report-s99b", "bind99b", "gate99b",
             "closeout99b.log", "PRIOR_FLOOR=2783", "chore(s99b)"]
ALLOWED_99 = 3


def swap_prelude(text: str) -> tuple[str, list[str]]:
    """把 `set -u` 之前整段注释换成新头部；旧头部不做逐句锚，只验它确实是上一片那段。"""
    if "set -u\n" not in text:
        return text, ["结构锚 `set -u` 不在场 ⇒ 这份源脚本不是收口链"]
    prelude, rest = text.split("set -u\n", 1)
    notes = []
    if not prelude.startswith("# 第 99 片收口链"):
        notes.append(f"头部不是预期的上一片形状：{prelude[:40]!r}")
    return NEW_HEAD + "set -u\n" + rest, notes


def swap_bind_msg(text: str) -> tuple[str, list[str]]:
    """绑定提交信息同样按**结构**换（`<<'MSG'` 到 `MSG` 之间）。

    不逐句锚是因为旧正文里有七行、每行都可能被拆着写漏一句；而漏掉的句子会把上一片的
    判定内容与"第一代作废"那套账带进本片的证件里。
    """
    marker = "git commit -q -F - <<'MSG'\n"
    if text.count(marker) != 1:
        return text, [f"绑定提交的结构锚 `<<'MSG'` 命中 {text.count(marker)} 次（要 1）"]
    head, rest = text.split(marker, 1)
    if "\nMSG\n" not in rest:
        return text, ["找不到 `MSG` 结束符"]
    _body, tail = rest.split("\nMSG\n", 1)
    if not _body.startswith(OLD_HEAD_LINE):
        return text, [f"绑定提交正文不是预期形状：{_body[:40]!r}"]
    return head + marker + NEW_BIND_MSG + "\nMSG\n" + tail, []


def build(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    text, bad = swap_prelude(text)
    notes += bad
    text, bad = swap_bind_msg(text)
    notes += bad
    for old, new, want in GLOBAL:
        if old in ("PRELUDE", "BINDMSG"):
            continue
        got = text.count(old)
        if got != want:
            notes.append(f"锚点 {old[:36]!r} 命中 {got} 次（要 {want}）⇒ 这一处不动")
            continue
        text = text.replace(old, new)
        notes.append(f"ok {got}x {old[:32]!r}")
    return text, notes


def gate(text: str) -> list[str]:
    bad = [f"上一片记号残留 {f!r} 共 {text.count(f)} 处" for f in FORBIDDEN if f in text]
    n99 = text.count("第 99 片")
    if n99 != ALLOWED_99:
        where = [i + 1 for i, l in enumerate(text.splitlines()) if "第 99 片" in l]
        bad.append(f"汉字面「第 99 片」应恰好 {ALLOWED_99} 处（出处与下界各一），实得 {n99}，"
                   f"行号 {where}")
    bad += [f"工序哨兵缺席：{s!r}" for s in SENTINELS if s not in text]
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
          f"上一片记号归零")
    return 0


if __name__ == "__main__":
    sys.exit(main())
