r"""第 103 片变异电池：`scripts/doc_reference_census.py` 新加的六处口径，各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| A0 | 不改任何字节（对照臂）⇒ 自测与常驻用例都必须绿 |
| X1 | 现状面"裸行钉判红"这一支（谓词改成永不成立）⇒ 现状面退回"行号合法就算对" |
| X2 | `symbol-missing` 从 `defect_kinds` 里摘掉 ⇒ 符号锚指向不存在的符号也不再算缺陷 |
| X3 | 漂移档 Σ 闭合判据少加一档（`unhinted` 不算进去）⇒ "有引用在这一档上消失"没人管 |
| X4 | 符号锚的类限定（`AIPDStateDB.add_audit` 这种）失效 ⇒ 只要同名就算指对 |
| X5 | `_live_keys` 归一时丢掉行号 ⇒ 现状面那条"写成集合"的断言重新变成橡皮章 |
| X6 | 把 `bare-line-pin` 这个**档名**改掉 ⇒ 下游（自测期望值、`render` 的类序、常驻用例）认不出这条判决 |

**为什么每支都写成"谓词永不成立 / 阈值抬到不可达"而不是 `if False and …`**：靶文件
`scripts/doc_reference_census.py` **自己在 CI 的 ruff 面上**（第 100 片接进去的），
常量条件会被判成 SIM223、给 `SCRIPTS_LINT_BASELINE` 凭空添一格"未登记"，
那种"臂被抓住"是夹具变了不是判据变了（第 100 片实测过 4 支 BAD-ANCHOR）。
所以本电池照抄那一道门：每支臂落笔前后各数一次靶文件的 ruff 命中，不等就记 BAD-ANCHOR。

**理由门**（第 101 片那档）：红必须红在本片新增的这几格上——自测输出里必须缺
`现状面缺陷判得出` 或 `Σ` 那两行之一，或 pytest 的 FAILED 点名 `test_doc_reference_census` /
`test_unreachable_code`；否则记 WRONG-REASON，不当 KILLED。

跑法：`python -B docs/audit/s103/battery103.py`。锚点先数：任一命中 ≠ 1 就一支都不跑（退 7）。
语法门用 `ast.parse`（`py_compile` 会把变异体字节码落进 `sys.pycache_prefix`，
同长度变异 + 同秒还原会遮蔽还原后的源——第 96 片实测），子进程一律带 `-B`。
"""
from __future__ import annotations

import ast
import collections
import contextlib
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TOOL = REPO / "scripts" / "doc_reference_census.py"
REL = "scripts/doc_reference_census.py"
TESTS = ["tests/test_doc_reference_census.py", "tests/test_unreachable_code.py"]
REASON_MARKS = ("现状面缺陷判得出", "Σ 分类 == 分母", "Σ 漂移")

ARMS = [
    ("A0-control-no-change", "对照：原样必须全绿", None, None),
    ("X1-live-bare-pin-never-fires", "现状面退回「行号不越界就算对」",
     '    elif _is_live(doc):',
     '    elif _is_live(doc + "\\u0000"):'),
    ("X2-symbol-missing-not-a-defect", "锚到不存在的符号不再算缺陷",
     '    defect_kinds = ("missing", "line_beyond_eof", "bare-line-pin", "symbol-missing")',
     '    defect_kinds = ("missing", "line_beyond_eof", "bare-line-pin")'),
    ("X3-drift-closure-never-fires", "漂移档 Σ 不再对分母（少加一档）",
     '    total = drift["ok"] + drift["suspect"] + drift["unhinted"]',
     '    total = drift["ok"] + drift["suspect"]'),
    ("X4-class-qualifier-ignored", "类限定写死取不到 ⇒ 符号锚退化成裸名",
     '                              if isinstance(c, ast.ClassDef) and c.name == parts[-2]',
     '                              if isinstance(c, ast.ClassDef) and c.name == parts[-2].upper()'),
    ("X5-live-keys-drop-the-line", "归一键丢掉行号 ⇒ 那条集合断言重新成橡皮章",
     '    return {f"{d}|{t}|{ln}" for d, t, ln in rep["live_defects"]}',
     '    return {f"{d}|{t}" for d, t, ln in rep["live_defects"]}'),
    ("X6-verdict-tag-renamed", "档名改掉 ⇒ 下游认不出这条判决",
     '        r.klass, r.detail = "bare-line-pin", (',
     '        r.klass, r.detail = "bare-line", ('),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def _drop_cache() -> None:
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__" / f"{TOOL.stem}.{sys.implementation.cache_tag}.pyc")):
        with contextlib.suppress(OSError):
            os.remove(cand)


def _env() -> dict[str, str]:
    return {"PATH": f"{REPO / '.venv/bin'}:/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
            "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"}


def target_debt() -> collections.Counter:
    """靶文件当前的 ruff 命中表——债中性别靠肉眼，靠它（第 100 片那条门原样搬过来）。"""
    proc = subprocess.run([str(REPO / ".venv/bin/ruff"), "check", "--no-cache",
                           "--output-format", "concise", REL],
                          cwd=REPO, capture_output=True, text=True)
    return collections.Counter(ln.split(":")[3].strip().split()[0]
                               for ln in proc.stdout.splitlines() if ln.startswith(REL))


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
    """(是否全绿, 红点是否落在本片的格上, 摘要)。"""
    st_rc, st_out = run_selftest()
    t_rc, t_out = run_tests()
    failed = [ln.split(" - ")[0].replace("FAILED ", "")
              for ln in t_out.splitlines() if ln.startswith("FAILED ")]
    green = st_rc == 0 and t_rc == 0
    missing_marks = [m for m in REASON_MARKS if m not in st_out]
    right = bool(missing_marks) or any("test_doc_reference_census" in f or
                                       "test_unreachable_code" in f for f in failed)
    return green, right, (f"自测 rc={st_rc}（缺的标记 {missing_marks}）/ 用例 rc={t_rc} "
                          f"红 {len(failed)} 条：{'; '.join(failed)[:300]}")


def main() -> int:
    _drop_cache()
    original = TOOL.read_bytes()
    text = original.decode("utf-8")
    print(f"原文件 sha={sha(original)} 靶文件债={dict(target_debt()) or '无'}")
    stale = [(arm[0], text.count(arm[2])) for arm in ARMS if arm[2] is not None
             and text.count(arm[2]) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if a[2])} 支臂各命中 1 次")
    base_debt = target_debt()
    green, _r, summ = observables()
    if not green:
        print(f"A0 对照臂不绿，电池前提不成立：{summ}")
        return 5
    print(f"[CONTROL OK] A0 原样全绿：{summ}")

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
        debt = target_debt()
        if debt != base_debt:
            print(f"[BAD-ANCHOR] {name} 不债中性：靶文件命中从 {dict(base_debt)} 变成 {dict(debt)}"
                  f" ⇒ 抓住它的是夹具变了，不是判据变了")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            _drop_cache()
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
            print(f"[WRONG-REASON] {name}（{what}）确实红了，但红点不在本片的格上：{summ}")
            marks["WRONG-REASON"] += 1
        else:
            print(f"[KILLED]   {name}（{what}）被抓住：{summ}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if a[2])
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {sha(original)}）"
          f"；靶文件债={dict(target_debt()) or '无'}")
    return 0 if all(marks[k] == 0 for k in ("SURVIVED", "BAD-ANCHOR", "WRONG-REASON")) else 4


if __name__ == "__main__":
    sys.exit(main())
