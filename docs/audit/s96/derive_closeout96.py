#!/usr/bin/env python3
r"""由第 95 片的收口脚本派生第 96 片那一支（根路径一律由 `__file__` 推，不写死绝对路径）。

换的五类锚（每一处都由脚本现数命中次数，任一为 0 就整支不写）：
① `s95`→`s96`（报告名 / worktree 名 / 产物目录名 / 日志名一起走）；
② `PRIOR_FLOOR`（上一代实测 collected：2760 → 2761）；
③ 头部派生说明里那句"由上一片（第 94 片）…"与原告清单；
④ `--expect-test` 那第二行（第 96 片的原告在两个文件里：新建的
   `tests/test_forensic_scripts_root.py` 与补了 C5 读数标签那一极的
   `tests/test_closeout_verifier.py`；只点一条就会让"另一半没跑到"读成通过）；
⑤ 绑定提交的正文。

派生完必做三件：残留 `s95` 归零、尾巴那几个哨兵仍在（防再次只写半支）、`bash -n` 过一遍。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "docs/audit/s95/closeout95.sh"
DST = ROOT / "docs/audit/s96/closeout96.sh"

SUBS = [
    ("s95", "s96"),
    ("# 由上一片（第 94 片）逐行派生，只换：报告名 / worktree 名 / 产物目录名 /",
     "# 由上一片（第 95 片）逐行派生，只换：报告名 / worktree 名 / 产物目录名 /"),
    ("PRIOR_FLOOR=上一代实测 collected(2760)", "PRIOR_FLOOR=上一代实测 collected(2761)"),
    ("PRIOR_FLOOR=2760", "PRIOR_FLOOR=2761"),
    ("#   （第 95 片的原告在两个文件里：`tests/test_closeout_verifier.py` 的 C5 三极\n"
     "#    与 `tests/test_report_manifest_fingerprint.py` 的真跑那极；只点一条就会让\n"
     "#    \"另一半修复没跑到\"读成通过）。",
     "#   （第 96 片的原告在两个文件里：`tests/test_forensic_scripts_root.py` 那 9 条\n"
     "#    与 `tests/test_closeout_verifier.py` 补的 C5 读数标签那一极；只点一条就会让\n"
     "#    \"另一半没跑到\"读成通过）。"),
    ("    --expect-test tests/test_report_manifest_fingerprint.py \\\n",
     "    --expect-test tests/test_forensic_scripts_root.py \\\n"),
    ("一次绑定、两个旗子同时给。本轮动的是认证链自己：`tests/conftest.py` 无条件实测 HEAD 并落\n"
     "`source_commit_measured`，`scripts/closeout_verifier.py` 的 C5 祖先关系改按**那一跑实测的\n"
     "HEAD** 判（此前按验签时刻的工作树 HEAD，而那时 HEAD 已被收口链后续的\"门读数/验签读数\"两个\n"
     "提交推前 ⇒ 旧判据恒真）。⇒ 这一代报告必须带着 `source_commit_measured`，C5 才走强一档那条；\n"
     "上一代（第 94 片，collected 2760）只作下界对比。",
     "一次绑定、两个旗子同时给。本轮动的是两处读数面：`scripts/closeout_verifier.py` 的 C5 说明串\n"
     "不再被 `[:8]` 截半（标签与\"弱一档\"那句都要出现，常驻用例直读那个字符串），以及\n"
     "`docs/audit/s96/build_forensic_root_register.py` 这把新尺——取证脚本把仓库内绝对路径写死时\n"
     "必须被唯一一条写明理由的豁免接住，否则判红（名册是生成物，重新生成洗不出更宽的豁免）。\n"
     "上一代（第 95 片，collected 2761）只作下界对比。"),
]

# 只写半支是这类派生脚本最贵的一种错：尾巴（发布门 / 验签 / 三个提交）没了，
# `bash -n` 照样过，直到跑起来才发现少了一半工序。这几个哨兵必须逐字还在。
SENTINELS = ["GATE_RC=$?", "CV_RC=$?", "FINAL_COMMIT_RC=$?", "MIN_TESTS=", "SKIP 面逐条相同"]


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    for old, new in SUBS:
        n = text.count(old)
        assert n >= 1, f"锚点读不到 ⇒ 一支都不写：{old[:60]!r} 命中 {n}"
        text = text.replace(old, new)
    assert "s95" not in text, "还有 s95 残留（替换只覆盖了带前导斜杠的写法）"
    for s in SENTINELS:
        assert s in text, f"派生件丢了工序哨兵：{s}"
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(text, encoding="utf-8")
    chk = subprocess.run(["bash", "-n", str(DST)], capture_output=True, text=True)
    print(f"写出 {DST.relative_to(ROOT)}：{text.count(chr(10))} 行、"
          f"{len(SUBS)} 处替换各命中 ≥1、bash -n rc={chk.returncode} {chk.stderr[:200]}")
    return 0 if chk.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
