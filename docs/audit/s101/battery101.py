r"""第 101 片变异电池：`build_forensic_root_register.py` 那道行首注释门的六处口径，各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| A0 | 不改任何字节（对照臂）⇒ 自测与常驻用例都必须绿 |
| X1 | 注释门整个关掉（`match("")` 永不命中）⇒ 说明行重新变成原告 |
| X2 | 门写宽成 `'#' in src`（整行带注释就丢）⇒ 「代码 + 尾注释」那条真原告被一起丢掉 |
| X3 | 挡掉的条数不再累加 ⇒ 收窄变成**静默**的盲 |
| X4 | `corpus` 里那格聚合写成常量 0 ⇒ 自报读数与现实脱钩 |
| X5 | 那行自报不再印这个数字 ⇒ 人读面上这道门不存在 |
| X6 | 行读数 `comment_skipped` 写成常量 0 ⇒ 分档全丢，聚合也就无从核对 |

**为什么每支臂都要"判决理由"对得上**：靶文件自己就在它的语料里（`docs/audit/**` 的 `.py`/`.sh`），
某支臂如果把识别面改坏，红的可能是「名册该撤 / 根路径未点名」这类**别的判决**，
而不是本片的注释门——那不等于这一格被看见了。所以本电池除了 rc≠0，还要求：
自测那一跑的 stdout **不含**`行首注释不算原告`这条标记（说明它就是死在這一臂上），
或 pytest 的 FAILED 行点名 `test_a_line_leading_comment`；两条都不满足就记 WRONG-REASON，
不当 KILLED 也不当 SURVIVED，退 4 逼人回去读日志。

跑法：`python -B docs/audit/s101/battery101.py`。锚点先数：任一命中 ≠ 1 就一支都不跑（退 7）。
语法门用 `ast.parse`（`py_compile` 会把变异体字节码落进 `sys.pycache_prefix`，
同长度变异 + 同秒还原会遮蔽还原后的源——第 96 片实测），子进程一律带 `-B`。
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
TOOL = REPO / "docs" / "audit" / "s96" / "build_forensic_root_register.py"
TESTS = ["tests/test_forensic_scripts_root.py", "tests/test_forensic_scripts_parse.py"]
MARK = "行首注释不算原告"

ARMS = [
    ("A0-control-no-change", "对照：原样必须全绿", None, None),
    ("X1-gate-never-matches", "注释门整个关掉 ⇒ 说明行又变原告",
     '        if COMMENT_LINE_RE.match(src):',
     '        if COMMENT_LINE_RE.match(""):'),
    ("X2-gate-too-wide", "门写成整行判 ⇒ 连着尾注释的真原告一起丢",
     '        if COMMENT_LINE_RE.match(src):',
     '        if "#" in src:'),
    ("X3-counter-not-fed", "挡掉的条数不再累加 ⇒ 收窄变成静默的盲",
     '            skipped += 1',
     '            skipped = skipped'),
    ("X4-aggregate-hardcoded", "corpus 那格聚合写成常量 0 ⇒ 自报与现实脱钩",
     '"comment_skipped": sum(r["comment_skipped"] for r in rows)',
     '"comment_skipped": 0'),
    ("X5-render-drops-reading", "自报行不再印这个数字 ⇒ 人读面上这道门不存在",
     '、行首注释挡掉 {c[\'comment_skipped\']} 条），',
     '），'),
    ("X6-row-reading-hardcoded", "行读数写成常量 0 ⇒ 分档无从核对聚合",
     '            "comment_skipped": skipped,',
     '            "comment_skipped": 0,'),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def _drop_cache() -> None:
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__"
                     / f"{TOOL.stem}.{sys.implementation.cache_tag}.pyc")):
        with contextlib.suppress(OSError):
            os.remove(cand)


def _env() -> dict[str, str]:
    return {"PATH": f"{REPO / '.venv/bin'}:/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
            "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"}


def run_selftest() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", str(TOOL), "--self-test"],
                          cwd=REPO, capture_output=True, text=True, env=_env(), timeout=600)
    return proc.returncode, proc.stdout + proc.stderr


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True, env=_env(), timeout=900)
    return proc.returncode, proc.stdout + proc.stderr


def observables() -> tuple[bool, bool, str]:
    """(是否全绿, 红点是否落在本片的注释门上, 摘要)。

    第二格为什么要单独判：靶文件就在它自己的语料里，某支臂完全可能把**别的判决**弄红
    （「名册该撤」「根路径未点名」），那种红不证明这一格被看见了。
    """
    st_rc, st_out = run_selftest()
    t_rc, t_out = run_tests()
    failed = [ln.split(" - ")[0].replace("FAILED ", "")
              for ln in t_out.splitlines() if ln.startswith("FAILED ")]
    green = st_rc == 0 and t_rc == 0
    right_reason = (MARK not in st_out) or any("test_a_line_leading_comment" in f for f in failed)
    return green, right_reason, \
        f"自测 rc={st_rc}（标记在不在={MARK in st_out}）/ 用例 rc={t_rc} 红 {len(failed)} 条：" \
        f"{'; '.join(failed)[:300]}"


def main() -> int:
    _drop_cache()
    original = TOOL.read_bytes()
    text = original.decode("utf-8")
    print(f"原文件 sha={sha(original)}")
    stale = [(arm[0], text.count(arm[2])) for arm in ARMS if arm[2] is not None
             and text.count(arm[2]) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if a[2])} 支臂各命中 1 次")
    green, _why, summ = observables()
    if not green:
        print(f"A0 对照臂不绿，电池前提不成立：{summ}")
        return 5
    # 理由门前置断言：本片那条标记必须出现在**未变异**的自测输出里，
    # 否则「标记不在输出中 ⇒ 红点落在本臂上」恒成立，WRONG-REASON 这一档就是空的。
    if MARK not in run_selftest()[1]:
        print(f"前提不成立：自测输出里没有 {MARK!r} 这条标记 ⇒ 理由门恒真，一支臂都不跑")
        return 5
    print(f"[CONTROL OK] A0 原样全绿，且理由门的标记在场上：{summ}")

    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0, "WRONG-REASON": 0}
    for name, what, old, new in ARMS:
        if old is None:
            continue
        TOOL.write_text(text.replace(old, new, 1), encoding="utf-8")
        if sha(TOOL.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        try:
            ast.parse(TOOL.read_text(encoding="utf-8"))
            err = ""
        except SyntaxError as exc:
            err = str(exc)
        if err:
            print(f"[BAD-ANCHOR] {name} 变异体语法不过：{err[:200]}")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        caught, why, summ = observables()
        TOOL.write_bytes(original)
        _drop_cache()
        if sha(TOOL.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {name}")
            return 6
        if caught:
            print(f"[SURVIVED] {name}（{what}）撤掉之后自测与用例照绿 ⇒ 这一格其实没被看见")
            marks["SURVIVED"] += 1
        elif not why:
            print(f"[WRONG-REASON] {name}（{what}）确实红了，但红点不在本片的注释门上：{summ}")
            marks["WRONG-REASON"] += 1
        else:
            print(f"[KILLED]   {name}（{what}）被抓住：{summ}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if a[2])
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {sha(original)}）")
    return 0 if all(marks[k] == 0 for k in ("SURVIVED", "BAD-ANCHOR", "WRONG-REASON")) else 4


if __name__ == "__main__":
    sys.exit(main())
