r"""第 94 片变异电池：CI 对账尺**行号面 + 软门面**的每个口径选择，各配一支撤销臂。

harness 与 `docs/audit/s93/battery93.py` 同构（逐字沿用）：对照臂、锚点预数、
落字节证明、变异体 ast.parse 语法门、每臂复位后 sha 复核、末尾合计行。
只换三样：被变异文件、臂表、pytest 靶（`tests/test_ci_surface_census.py`）。

| 臂 | 撤掉的第 94 片决定 |
| --- | --- |
| W0 | 不改任何字节（对照臂）⇒ 必须全绿，否则电池前提不成立 |
| W1 | 行号退回恒 0：`"line": (base + off) if base else 0` → `"line": 0` |
| W2 | `_run_marks` 的块标量按 `start_mark.line + 2` 定锚（退回"指示行 + 一行"的猜法）|
| W3 | `\` 续行的偏移取末行而不是起始行 |
| W4 | `first_line` 跳过注释行去找第一条命令（锚点整体后移）|
| W5 | 空行与注释不占偏移（见下）|
| W6 | 「软门」整档不开火（`if c["swallow"] or c["soft"]` → `if False`）|
| W7 | 只看命令级 swallow、忽略步骤级 `continue-on-error` |
| W8 | `_SWALLOW_RE` 漏掉 `--exit-zero` 那一支 |
| W9 | `_SWALLOW_RE` 整条换掉：只剩 `set +e` / `--warn-only` / `--ignore-errors` |
| W10 | 定不到行号时静默记 0（删掉 `run_mark_unmatched` 那条前提诊断）|
| W11 | 桶计数不数软门（`soft-declared` 加 0）|
| W12 | `--emit-register` 不写 `line_text_at_emit_time`（写成空串）|
| W13 | 两档判红都不指位：软门与「无人守」的 `line` 各写回 0（一处锚点命中 2 次 ⇒ 必须两处一起撤）|

W5 的具体做法（照臂表字面执行，不另改）：只把
`for idx, line in enumerate(raw.splitlines()):` 的分母换成
`[l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]`，
于是 `idx` 从"标量里的第几行"变成"第几条非空非注释行"——空行与注释行不再占偏移，
而行号仍是 `base + idx`（`first_line` 那一头仍连注释一起数）。

W13 的锚点按臂表原文 `"line": c["line"],` 在本文件里命中 **2** 次
（`scripts/ci_surface_census.py:261` 软门那笔、`:274` 「CI面无人守」那笔），
harness 的预数门会直接退 7、一支都不跑。这里不改判决也不改替换文本，
只把锚点按臂表点名的位置扩一行上下文（`"field": "CI面被声明为可失败"…` 那一整行），
改动仍精确落在 :261 一处，`:274` 不碰。

用例简名（`self` 那条是 spawn `--self-test` 的常驻用例，其余是行号面/软门面的常驻牙）：
`line` = `test_every_ci_command_reports_a_line_and_that_line_says_that_command`
`fold` = `test_folded_continuation_and_comment_block_report_the_start_line`
`soft` = `test_a_gate_declared_soft_fires_while_a_hard_gate_does_not`
`zero` = `test_soft_face_reads_zero_on_the_real_repo_and_the_zero_is_a_real_zero`
`diag` = `test_a_step_whose_line_cannot_be_located_is_a_named_diagnostic_not_a_silent_zero`
`emit` = `test_emit_register_writes_line_pins_and_keeps_hand_filled_fields`

实测翻红（冒号后是被抓住的用例数与简名。靶文件是两个版本，都写清出处）：

跑序 1｜靶 = 11 条用例（`tests/test_ci_surface_census.py` sha256[:12] `357d08d731e5`，
即 `a3c930e` 那一版）⇒ **12 杀 / 1 活 / 0 注入无效**，退 4：
W1:4 self line fold soft · W2:2 self line · W3:3 self line fold · W4:2 self fold ·
W5:2 self fold · W6:2 self soft · W7:2 self soft · W8:2 self soft · W9:2 self soft ·
W10:1 diag · W11:2 self soft · **W12:0 存活** · W13:1 soft

跑序 2｜同一把臂表重跑时读到 `scripts/ci_surface_census.py` 的 sha 是 `cc5e379135b6`
（不是 `c1a313c1d2bd`）、W1 锚点命中 0 次 ⇒ 锚点预数门退 7、一支未跑、一个字节没写。
那一刻并行会话正在改同一个文件；这格正是预数门存在的理由。

跑序 3｜靶 = 12 条用例（sha256[:12] `f7902d0adac7`，即第 94b 片 `eebea06` 补进
`emit` 那条之后的版本）⇒ **13 杀 / 0 活 / 0 注入无效**，退 0：
W1:5 self line fold soft emit · W2:3 self line emit · W3:3 self line fold ·
W4:2 self fold · W5:2 self fold · W6:2 self soft · W7:2 self soft ·
W8:3 self soft emit · W9:3 self soft emit · W10:1 diag · W11:2 self soft ·
**W12:1 emit（这一格由并行会话补的读者抓住，本轮未加也没改任何用例）** · W13:1 soft

W12 在跑序 1 存量的暴露面（用 /tmp 里的两份拷贝对同一棵合成树量，未碰仓库）：
它的 `audit()` 输出（violations / buckets / problems / commands / render / 退码）
与原版**逐字节相同**（`diff` rc=0，两份 2601 字节），唯一可观测差异是
`--emit-register` 写出的草案里 `line_text_at_emit_time` 从该行原文变成空串
（4/4 条目，其余键全等）。全仓 grep 该字段名只有两个落点：写入侧
`scripts/ci_surface_census.py:513` 与散文
`docs/audit/CI_SURFACE_LINES_F-CI-SURFACE_2026-09-29.md:83`；
当时在册的 `docs/audit/CI_SURFACE_REGISTER.json` 里该字段出现 0 次，也没有任何常驻用例
跑 `--emit-register` ⇒ 判"缺覆盖"（emit 这条出口没有读者），不判"等价变异"。

`zero` 那一格对两个版本的全部臂都没翻红，不是漏跑：它断的是"真仓库上桶计数 0
与原文正则扫描 0 同为零"，而 W6~W11 撤的都是开火侧——真仓库两边同时是 0，
读数同形。软门面的极性牙全部落在 `self`（合成树 `--self-test`）与 `soft` 这两条上。

跑法：`python docs/audit/s94/battery94.py`（stdout 落在仓库树外，见本轮交付说明）。
开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TOOL = REPO / "scripts" / "ci_surface_census.py"
TESTS = ["tests/test_ci_surface_census.py"]

# 跨行锚点与含正则元字符的锚点一律用 raw 字面量逐字抄源码，不靠转义复原。
W4_OLD = ('        for ln in value.splitlines():\n'
          '            if ln.strip():\n'
          '                return ln.strip()\n')
W4_NEW = ('        for ln in value.splitlines():\n'
          '            t0 = ln.strip()\n'
          '            if t0 and not t0.startswith("#"):\n'
          '                return t0\n')
W5_OLD = 'for idx, line in enumerate(raw.splitlines()):'
W5_NEW = ("for idx, line in enumerate([l for l in raw.splitlines()"
          " if l.strip() and not l.strip().startswith('#')]):")
# 第 1 处删 `--exit-zero\b|` 整个分支；第 2 处把行尾的 `|` 补回下一支开头，
# 两支合起来才等于"正则里没有 --exit-zero"这一档撤销（少任一处都留半截竖线）。
W8_EDITS = [(r'\bset\s+\+e\b|--exit-zero\b|', r'\bset\s+\+e\b|'),
            (r'                         r"--warn-only\b',
             r'                         r"|--warn-only\b')]
W9_OLD = (r'_SWALLOW_RE = re.compile(r"(\|\|\s*(?:true|:)\s*$|\bset\s+\+e\b|--exit-zero\b|"' + '\n'
          + r'                         r"--warn-only\b|--ignore-errors\b)")' + '\n')
W9_NEW = '_SWALLOW_RE = re.compile(r"(\\bset\\s+\\+e\\b|--warn-only\\b|--ignore-errors\\b)")\n'
W10_OLD = ('        problems_extra.append(f"run_mark_unmatched: 有 {unmatched}'
           ' 个 run 步骤定不到行号"\n'
           '                              "（块标量形状变了或解析面跟不上）'
           '⇒ 那些命令的 `line` 记 0")\n')
W10_NEW = "        pass\n"
# 臂表原文给的锚点 `"line": c["line"],` 在本文件里命中 **2** 次
# （`scripts/ci_surface_census.py:261` 软门那笔、`:274` 「CI面无人守」那笔），
# 按 harness 的"任一锚点命中 ≠ 1 就一支都不跑"会直接退 7。这里不改判决、不改替换文本，
# 只把锚点按臂表点名的位置（`CI面被声明为可失败` 那个 violation dict）扩一行上下文，
# 使字节改动仍精确落在 :261 那一处；`:274` 那笔不碰。

ARMS = [
    ("W0-control-no-change", "对照：原样必须全绿", None, None),
    ("W1-line-always-zero", "行号退回恒 0",
     '"line": (base + off) if base else 0,',
     '"line": 0,'),
    ("W2-block-scalar-start-plus-2", "块标量按 start+2 定锚",
     'out.setdefault((str(cur_job[0]), i), j + 1)',
     'out.setdefault((str(cur_job[0]), i), v.start_mark.line + 2)'),
    ("W3-continuation-offset-last-line", "续行偏移取末行",
     'out[-1] = (_norm(prev[:-1] + " " + s), off, at)',
     'out[-1] = (_norm(prev[:-1] + " " + s), idx, at)'),
    ("W4-anchor-skips-comment-lines", "锚点跳过注释行", W4_OLD, W4_NEW),
    ("W5-blank-and-comment-dont-count", "空行与注释不占偏移", W5_OLD, W5_NEW),
    ("W6-soft-tier-never-fires", "软门判据整档不开火",
     'if c["swallow"] or c["soft"]:',
     'if False:'),
    ("W7-ignore-continue-on-error", "只看命令级、忽略 continue-on-error",
     'if c["swallow"] or c["soft"]:',
     'if c["swallow"]:'),
    ("W8-regex-drops-exit-zero", "正则漏掉 --exit-zero", W8_EDITS, None),
    ("W9-regex-drops-true-and-exitzero", "正则只剩 set +e / --warn-only / --ignore-errors",
     W9_OLD, W9_NEW),
    ("W10-unmatched-silent-zero", "定不到行号时静默记 0", W10_OLD, W10_NEW),
    ("W11-bucket-doesnt-count-soft", "桶计数不数软门",
     'buckets["soft-declared"] += 1',
     'buckets["soft-declared"] += 0'),
    ("W12-emit-loses-line-text", "emit 不带原文字段",
     '"line_text_at_emit_time": c["at"],',
     '"line_text_at_emit_time": "",'),
    # 臂表原文 `"line": c["line"],` 在靶文件里命中 **2** 次（:261 软门、:274 无人守）。
    # 上一版把锚点收窄到其中一处 ⇒ 另一处的指位其实没被任何臂撤过；两处一起撤才是
    # 这一档的完整撤销臂（`pairs()` 支持一支多编辑，见 W10 那一支的写法）。
    ("W13-violations-lose-line-both-sites", "两档判红都不指位（软门与无人守的 line 各写回 0）",
     [('"field": "CI面被声明为可失败", "doc": WORKFLOW_REL, "line": c["line"],',
       '"field": "CI面被声明为可失败", "doc": WORKFLOW_REL, "line": 0,'),
      ('"field": "CI面无人守", "doc": WORKFLOW_REL, "line": c["line"],',
       '"field": "CI面无人守", "doc": WORKFLOW_REL, "line": 0,')], None),
]


def pairs(arm):
    """一支臂的编辑归一成 [(旧, 新), …]（`new is None` 时 `old` 本身就是成对清单）。"""
    old, new = arm[2], arm[3]
    if old is None:
        return []
    if new is None:
        return list(old)
    return [(old, new)]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home()),
                               "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def _drop_cache() -> None:
    """删掉靶文件在 pycache_prefix / __pycache__ 里的两份缓存（防陈旧字节码遮蔽还原后的源）。"""
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__" / (TOOL.stem + f".{sys.implementation.cache_tag}.pyc"))):
        with contextlib.suppress(OSError):
            os.remove(cand)


def main() -> int:
    _drop_cache()
    original = TOOL.read_bytes()
    print(f"原文件 sha={sha(original)}")
    text = original.decode("utf-8")
    stale = [(arm[0], text.count(o)) for arm in ARMS
             for o, _n in pairs(arm) if text.count(o) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if pairs(a))} 支臂、"
          f"{sum(len(pairs(a)) for a in ARMS)} 处编辑各命中 1 次")
    rc, out = run_tests()
    if rc != 0:
        print("W0 对照臂不绿，电池前提不成立：", out[-900:])
        return 5
    print("[CONTROL OK] W0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for arm in ARMS:
        edits = pairs(arm)
        if not edits:
            continue
        mutated = text
        for o, n in edits:
            mutated = mutated.replace(o, n, 1)
        TOOL.write_text(mutated, encoding="utf-8")
        if sha(TOOL.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {arm[0]} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        # 语法门用进程内 ast.parse：外部字节码编译会往 `sys.pycache_prefix` 落缓存，
        # 而缓存有效性只看 (源 mtime 整秒, 字节数) ⇒ 同长度变异＋同秒还原会遮蔽还原后的源。
        try:
            ast.parse(TOOL.read_text(encoding="utf-8"))
            chk_rc, chk_err = 0, ""
        except SyntaxError as exc:
            chk_rc, chk_err = 1, str(exc)
        if chk_rc != 0:
            print(f"[BAD-ANCHOR] {arm[0]} 变异体语法不过：{chk_err[:200]}")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        rc, out = run_tests()
        TOOL.write_bytes(original)
        _drop_cache()
        if sha(TOOL.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {arm[0]}")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {arm[0]}（{arm[1]}）撤掉之后用例照绿 ⇒ 这一格其实没被看见")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {arm[0]}（{arm[1]}）被抓住 {len(killed)} 条："
                  f"{'; '.join(killed)[:520]}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if pairs(a))
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {sha(original)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
