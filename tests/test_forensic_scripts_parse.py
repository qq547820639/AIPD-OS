"""取证脚本自己也要能被解析：`docs/audit/**` 下的 .py/.sh 过去没有任何常驻读者。

第 89 片的现场：改完变异电池忘了 `python -m py_compile` 就交给下一轮，而它当时是
**语法死**的（中文串里嵌了半角引号）。全套件照样绿——因为 `docs/audit/` 既不 import
也不 collect，`tests/test_exception_hygiene.py` 那类扫描只覆盖 `src/` 与 `scripts/`，
并且它对 `SyntaxError` 是 `continue`（那把尺问的是空 except，不是能不能解析）。
一份跑不起来的取证脚本比没有更贵：登记册里它会以"已配电池"的身份被引用。

三条分工：`test_forensic_python/shell_scripts_still_parse` 判现状；
`test_the_parse_checks_themselves_can_fire` 证这两把尺会开火（并给合规侧一个不开火对照）；
`test_the_forensic_corpus_is_really_walked_recursively` 证语料不是被路径改动静默清空的。
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORENSIC_DIR = ROOT / "docs" / "audit"


def forensic_files(suffix: str) -> list[Path]:
    return sorted(FORENSIC_DIR.rglob(f"*{suffix}"))


def py_syntax_errors(files: list[Path]) -> list[str]:
    bad = []
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            bad.append(f"{p}: 读不出 {exc}")
            continue
        try:
            ast.parse(src, filename=str(p))
        except SyntaxError as exc:
            bad.append(f"{p}: {exc.msg} @ 第 {exc.lineno} 行")
    return bad


def sh_syntax_errors(files: list[Path]) -> list[str]:
    bad = []
    for p in files:
        proc = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()
            bad.append(f"{p}: {tail[-1] if tail else 'bash -n 非零退出'}")
    return bad


def test_the_forensic_corpus_is_really_walked_recursively() -> None:
    pys = forensic_files(".py")
    assert len(pys) >= 20, f"取证脚本少于 20 个，多半是路径或后缀变了：{pys}"
    assert any(p.parent != FORENSIC_DIR for p in pys), \
        "一个子目录都没进到 ⇒ rglob 的锚点或目录结构对不上"


def test_forensic_python_scripts_still_parse() -> None:
    assert py_syntax_errors(forensic_files(".py")) == []


def test_forensic_shell_scripts_still_parse() -> None:
    probe = subprocess.run(["bash", "--version"], capture_output=True, text=True)
    assert probe.returncode == 0, "机制前提：本机没有 bash，这条判据无从执行"
    assert sh_syntax_errors(forensic_files(".sh")) == []


def test_the_parse_checks_themselves_can_fire(tmp_path: Path) -> None:
    """不开火的尺子等于没有尺子：两支都必须能抓到注入的坏文件，合规侧不许误报。"""
    broken_py = tmp_path / "broken.py"
    broken_py.write_text("def f(:\n    return 1\n", encoding="utf-8")
    got = py_syntax_errors([broken_py])
    assert len(got) == 1 and "broken.py" in got[0], got

    good_py = tmp_path / "good.py"
    good_py.write_text("def f():\n    return 1\n", encoding="utf-8")
    assert py_syntax_errors([good_py]) == []

    broken_sh = tmp_path / "broken.sh"
    broken_sh.write_text("if [ 1 -eq 1 ]; then\n", encoding="utf-8")
    got_sh = sh_syntax_errors([broken_sh])
    assert len(got_sh) == 1 and "broken.sh" in got_sh[0], got_sh

    good_sh = tmp_path / "good.sh"
    good_sh.write_text("set -u\ntrue\n", encoding="utf-8")
    assert sh_syntax_errors([good_sh]) == []

    unreadable = tmp_path / "not_here.py"
    got_missing = py_syntax_errors([unreadable])
    assert len(got_missing) == 1 and "读不出" in got_missing[0], got_missing
