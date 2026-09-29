r"""第 99 片变异电池：取证根路径门禁新加的 `.sh` 面（四支撤销臂 + 一支真语料必须开火臂），
外加 CI 面"行钉两条判决进自测"的条数下限臂。

| 臂 | 撤掉的东西 | 靶 |
| --- | --- | --- |
| X0 | 不改任何字节（对照臂）⇒ 必须全绿 | — |
| X1 | `literals()` 里裸路径那条分支（`if shell:` 永不成立）⇒ 只认引号 | 量具 |
| X2 | `facts()` 不再枚举 `.sh`（分母退回纯 `.py`） | 量具 |
| X3 | `closeout` 点名规则退回 `\.(py)$` ⇒ `.sh` 的收口脚本无人点名 | 量具 |
| X4 | 语料档位求和把 `.py` 记成 0（分母还在、拆错两档） | 量具 |
| X5 | 把 `docs/audit/s83/s83b.sh` 的仓库根**重新写死**（裸赋值）⇒ 真语料必须判红 | 语料 |
| Y1 | CI 量具自报的条数不再随注入增长（本片新增两格同源的牙） | CI 量具 |
| Y2 | 取证量具同一格的镜像臂（自报总数与逐条 `✓立住` 分家） | 取证量具 |

X5 是本片唯一一支"不是改尺子、而是改被尺子量的树"的臂：它证明 `.sh` 面不是整片豁免掉，
也证明第 99 片对 `s83b.sh` 的去硬编码是承重的——改回去门就红。
Y1/Y2 守的是第 99 片补的**自测条数两格同源**（两个常驻文件的 `test_instrument_self_test_*`）：
逐条 `✓立住` 是无条件打印的，`N 条…全部对上` 是工具自报的总数，两格必须相等。
**这两支臂是第一版断言 SURVIVED 之后补出来的**：`marks >= 8` 只数打印行，
把 `marks.append(text)` 改成 `pass` 时打印照旧 8 行而自报变成 0 条 ⇒ 原断言结构上看不见。
CI 面今天 8 条判决，其中两条（行钉不穷举 / 指错行）是本片新接进自测的。
**这一格的已知边界**：常驻牙看得见自测"报了几条"与"逐条打了几行"是否相等，
看不见自测内部每条断言的强度——把某条内部断言放宽（例如 `buckets["line-defect"] >= 1`
改成 `>= 0`）在常驻层上不可观察，因此不列为臂（列了也只会被判 SURVIVED 而凑数）。
判决强度由 `test_ci_surface_census.py` 与 `test_forensic_scripts_root.py`
各自那 15/12 条常驻用例守着，不在这一格里。

跑法：`python -B docs/audit/s99/battery99.py`。开局先数锚点：任一命中 ≠ 1 就一支都不跑（退 7）。
语法门用 `ast.parse`（`py_compile` 会把变异体的字节码落进 `sys.pycache_prefix`，
同长度变异 + 同秒还原会遮蔽还原后的源——第 96 片实测），只对 `.py` 靶做；
`.sh` 靶改跑 `bash -n`。子进程带 `-B`，每臂复位后清缓存并复算 sha。

**未收录的臂（等价变异，如实记录）**：`literals()` 里 `if item not in out` 那句去重。
摘掉它不改变任何判决与读数——`inside_hardcoded` 数的是"有没有原告"（布尔），
名册每文件只取首个行号，`audit()` 里 `ins = set(inside)` 本就去重，
自测那条断言用集合比 ⇒ 它在可观察输出上没有落点。按"臂存活先问变异改得了任何可观察输出吗"
判为等价变异，不塞进电池凑数。
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
CORPUS = REPO / "docs" / "audit" / "s83" / "s83b.sh"
CISC = REPO / "scripts" / "ci_surface_census.py"
FORENSIC_TESTS = ["tests/test_forensic_scripts_root.py"]
CI_TESTS = ["tests/test_ci_surface_census.py"]

# (臂名, 撤掉的东西, 靶文件, [(旧, 新), …], 跑哪些常驻牙)
ARMS: list[tuple[str, str, Path | None, list[tuple[str, str]], list[str]]] = [
    ("X0-control-no-change", "对照：原样必须全绿", None, [], FORENSIC_TESTS),
    ("X1-bare-branch-off", "裸绝对路径分支永不成立", TOOL, [
        ('    if shell:\n        for m in SHELL_ABS_RE.finditer(text):',
         '    if shell and False:\n        for m in SHELL_ABS_RE.finditer(text):'),
    ], FORENSIC_TESTS),
    ("X2-sh-not-enumerated", "分母退回纯 .py", TOOL, [
        ('             if f.suffix in (".py", ".sh") and f.is_file()]',
         '             if f.suffix in (".py",) and f.is_file()]'),
    ], FORENSIC_TESTS),
    ("X3-closeout-py-only", "点名规则不再接住 .sh", TOOL, [
        (r'    ("closeout", r"/closeout\d+[a-z]*\.(?:py|sh)$",',
         r'    ("closeout", r"/closeout\d+[a-z]*\.py$",'),
    ], FORENSIC_TESTS),
    ("X4-py-bucket-zeroed", "语料拆档把 .py 记成 0", TOOL, [
        ('    n_py = sum(1 for r in rows if not r["shell"])',
         '    n_py = 0'),
    ], FORENSIC_TESTS),
    ("X5-reparse-hardcoded", "把 s83b.sh 的仓库根重新写死（裸赋值）", CORPUS, [
        ('R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"',
         "R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS"),
    ], FORENSIC_TESTS),
    ("Y1-selftest-count-not-live", "自测的条数不再随注入增长（本片新加的条数下限的牙）",
     CISC, [("    marks.append(text)", "    pass")], CI_TESTS),
    ("Y2-selftest-count-not-live-forensic", "取证量具同一格的镜像臂",
     TOOL, [("    marks.append(text)", "    pass")], FORENSIC_TESTS),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def _drop_cache(target: Path) -> None:
    for cand in (importlib.util.cache_from_source(str(target)),
                 str(target.parent / "__pycache__"
                     / f"{target.stem}.{sys.implementation.cache_tag}.pyc")):
        with contextlib.suppress(OSError):
            os.remove(cand)


def syntax_ok(target: Path) -> str:
    """`.py` 走 ast.parse，`.sh` 走 bash -n；返回空串代表语法门过。"""
    text = target.read_text(encoding="utf-8")
    if target.suffix == ".py":
        try:
            ast.parse(text)
            return ""
        except SyntaxError as exc:
            return f"ast.parse：{exc}"
    proc = subprocess.run(["bash", "-n", str(target)], capture_output=True, text=True)
    return "" if proc.returncode == 0 else f"bash -n：{proc.stderr[:200]}"


def run_tests(tests: list[str]) -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *tests],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    originals: dict[Path, bytes] = {}
    for _n, _w, tgt, _p, _t in ARMS:
        if tgt is not None and tgt not in originals:
            _drop_cache(tgt)
            originals[tgt] = tgt.read_bytes()
    print("原文件 sha=" + "、".join(f"{t.name}:{sha(b)}" for t, b in originals.items()))

    stale: list[tuple[str, Path, int]] = []
    for name, _what, tgt, pairs, _tests in ARMS:
        if tgt is None:
            continue
        text = originals[tgt].decode("utf-8")
        for old, _new in pairs:
            if text.count(old) != 1:
                stale.append((name, tgt, text.count(old)))
    if stale:
        for n, t, h in stale:
            print(f"[BAD-ANCHOR] {n} 在 {t.name} 的锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if a[3])} 支臂、"
          f"{sum(len(a[3]) for a in ARMS)} 处编辑各命中 1 次")

    rc, out = run_tests(FORENSIC_TESTS)
    if rc != 0:
        print("X0 对照臂（取证面）不绿，电池前提不成立：", out[-1200:])
        return 5
    rc, out = run_tests(CI_TESTS)
    if rc != 0:
        print("X0 对照臂（CI 自测面）不绿，电池前提不成立：", out[-1200:])
        return 5
    print("[CONTROL OK] X0 原样全绿（取证 12 条 + CI 15 条两侧都跑）")

    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, tgt, pairs, tests in ARMS:
        if tgt is None:
            continue
        text = originals[tgt].decode("utf-8")
        for old, new in pairs:
            text = text.replace(old, new, 1)
        tgt.write_text(text, encoding="utf-8")
        if sha(tgt.read_bytes()) == sha(originals[tgt]):
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            tgt.write_bytes(originals[tgt])
            continue
        err = syntax_ok(tgt)
        if err:
            print(f"[BAD-ANCHOR] {name} 变异体语法不过：{err}")
            marks["BAD-ANCHOR"] += 1
            tgt.write_bytes(originals[tgt])
            _drop_cache(tgt)
            continue
        rc, out = run_tests(tests)
        tgt.write_bytes(originals[tgt])
        _drop_cache(tgt)
        if sha(tgt.read_bytes()) != sha(originals[tgt]):
            print(f"[!] 复位失败 {name}（{tgt.name}）")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {name}（{what}）撤掉之后用例照绿 ⇒ 这一格其实没被看见")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {name}（{what}）被抓住 {len(killed)} 条："
                  f"{'; '.join(killed)[:520]}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if a[3])
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print("收尾复算 sha=" + "、".join(f"{t.name}:{sha(t.read_bytes())}" for t in originals)
          + f"（应等于 " + "、".join(f"{t.name}:{sha(b)}" for t, b in originals.items()) + "）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
