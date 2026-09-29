r"""第 98 片变异电池：CI 行钉"按 (job, line) 记账"这四处口径，各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| V0 | 不改任何字节（对照臂）⇒ 必须全绿 |
| V1 | 行钉不再逐 job 记（只留第一个 job）⇒ `occurrences` 与 `job` 列又不同源 |
| V2 | `line_pin_defects()` 整个短路（两条判决一起摘掉） |
| V3 | 只摘第二查（不再核对行号那一行的原文含不含命令） |
| V4 | 第二查退化成只判越界（越界之外的"指到别处"看不见） |

用例简名：`live` = `test_every_ci_command_reports_a_line_and_that_line_says_that_command`；
`perjob` = `test_a_command_running_in_several_jobs_pins_every_one_of_them`；
`synth` = `test_a_pin_pointing_at_a_line_without_the_command_is_named`；
`fold` = `test_a_second_job_that_cannot_be_pinned_fires_instead_of_shrinking`。

跑法：`python -B docs/audit/s98/battery98.py`。开局先数锚点：任一命中 ≠ 1 就一支都不跑（退 7）。
语法门用 `ast.parse`（`py_compile` 会把变异体的字节码落进 `sys.pycache_prefix`，
同长度变异 + 同秒还原会遮蔽还原后的源——第 96 片实测），子进程带 `-B`，每臂复位后清缓存。
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

ARMS = [
    ("V0-control-no-change", "对照：原样必须全绿", None, None),
    ("V1-occurrence-not-per-job", "行钉不再逐 job 记账",
     '                ent["occ"].setdefault(job, [])\n'
     '                if ent["line"] == 0 and base:\n'
     '                    ent["line"] = base + off\n'
     '                if base:\n'
     '                    ent["occ"][job].append(base + off)',
     '                if not ent["occ"]:\n'
     '                    ent["occ"].setdefault(job, [])\n'
     '                if ent["line"] == 0 and base:\n'
     '                    ent["line"] = base + off\n'
     '                if base and ent["occ"].get(job) is not None:\n'
     '                    ent["occ"][job].append(base + off)'),
    ("V2-line-judge-shorted", "行钉两条判决整个短路",
     '    defects: list[dict] = []',
     '    return []\n    defects: list[dict] = []'),
    ("V3-text-check-dropped", "第二查（行号处的原文）整个摘掉",
     '        for job, lines in occ.items():',
     '        for job, lines in []:'),
    ("V4-only-out-of-range-checked", "第二查退化成只判越界",
     '                if ln < 1 or ln > len(file_lines) or c["at"] not in file_lines[ln - 1]:',
     '                if ln < 1 or ln > len(file_lines):'),
]


def pairs(arm):
    old, new = arm[2], arm[3]
    if old is None:
        return []
    if new is None:
        return list(old)
    return [(old, new)]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def _drop_cache() -> None:
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__"
                     / f"{TOOL.stem}.{sys.implementation.cache_tag}.pyc")):
        with contextlib.suppress(OSError):
            os.remove(cand)


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


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
        print("V0 对照臂不绿，电池前提不成立：", out[-1200:])
        return 5
    print("[CONTROL OK] V0 原样全绿")
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
        try:
            ast.parse(TOOL.read_text(encoding="utf-8"))
            chk_err = ""
        except SyntaxError as exc:
            chk_err = str(exc)
        if chk_err:
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
