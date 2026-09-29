r"""函数体里 `return` 之后还挂着语句 ⇒ 判红（常驻，第 103 片）。

为什么另开一把尺：`ruff` 的默认与 `select = ["E","F","I","W","UP","B","SIM"]` 词表里
**没有"不可达代码"这一项**（B018「useless statement」不抓函数体中间的裸字符串语句），
`mypy` 在本仓配置下也不报。于是这种残段能长期活着：第 103 片就是在扩
`scripts/doc_reference_census.py` 时读到 `resolve()` 里有
`return None, 0` 之后跟着一段**旧实现的 docstring + 触磁盘的 ROOTS 循环**——
五条语句永远执行不到，而函数的现行 docstring 恰好写着"全在缓存清单上做子串匹配，
不再触磁盘"，读代码的人会被那段残句误导。本仓没人守这一格，故立常驻判据。

判据只取**函数体顶层**的 `return` 之后的语句（`if …: return` 之后还有代码是合法的，
`try/finally` 里的 return 也不在函数体顶层），所以它不误伤正常控制流。
自证形状照"探针必须先证明能开火"那条：真语料读 0 处之前，先让合成片段开火。
"""
from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("src", "scripts", "state_service", "tests")
SKIP_NAMES = {"__pycache__"}


def _py_files(root: Path) -> list[Path]:
    """按目录枚举；不用 `git ls-files`：临时副本没有 .git，用 VCS 名单会读成"一个都没有"。"""
    out: list[Path] = []
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        out += [p for p in sorted(base.rglob("*.py")) if not (set(p.parts) & SKIP_NAMES)]
    return out


def unreachable_after_return(tree: ast.AST) -> Iterator[tuple[str, int, int]]:
    """产出 (函数名, 顶层 return 的行号, 其后第一条语句的行号)。"""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]                    # docstring 不算残段
        for i, st in enumerate(body[:-1]):
            if isinstance(st, ast.Return):
                yield node.name, st.lineno, body[i + 1].lineno


def scan_tree(tree: ast.AST) -> list[tuple[str, int, int]]:
    return sorted(unreachable_after_return(tree), key=lambda x: (x[1], x[0]))


def find_in_file(path: Path) -> list[tuple[str, int, int]] | None:
    """返回该文件的残段清单；语法不过的文件返回 None（不可判，不折成"干净"）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError, OSError):
        return None
    return scan_tree(tree)


def test_probe_can_fire_on_a_synthetic_fragment() -> None:
    """正臂（先证明这把尺会开火）：`return` 后面挂着一条赋值 ⇒ 必须被点名。"""
    bad = ast.parse("def f(x):\n    return 1\n    y = x\n")
    assert scan_tree(bad) == [("f", 2, 3)], scan_tree(bad)
    # 三组"合法但形状相似"的必须沉默：嵌套 return / try-finally / 只剩 docstring
    assert scan_tree(ast.parse("def g(x):\n    if x:\n        return 1\n    return 2\n")) == []
    assert scan_tree(ast.parse(
        "def h():\n    try:\n        return 1\n    finally:\n        cleanup()\n")) == []
    assert scan_tree(ast.parse('def k():\n    """只有 docstring"""\n    return 1\n')) == []


def test_real_repo_has_no_unreachable_tail() -> None:
    """真语料读 0 处；语法不过的文件单列成"不可判"，不许从分母里静默消失。"""
    files = _py_files(ROOT)
    assert len(files) > 200, f"扫描面缩水到 {len(files)} 个文件，本条前提塌"
    undecidable = [str(p.relative_to(ROOT)) for p in files if find_in_file(p) is None]
    assert not undecidable, undecidable
    hits = [(str(p.relative_to(ROOT)), *h) for p in files for h in (find_in_file(p) or [])]
    assert not hits, f"函数体顶层 return 之后还挂着语句：{hits}"


def test_the_ruler_itself_is_in_the_scanned_face() -> None:
    """这把尺的语料里必须包含它自己扩的那把量具——否则"量具自己干净"这件事没人看过。"""
    covered = {str(p.relative_to(ROOT)) for p in _py_files(ROOT)}
    for must in ("scripts/doc_reference_census.py", "scripts/doc_command_census.py",
                 "scripts/scripts_lint_ratchet.py", "tests/test_unreachable_code.py"):
        assert must in covered, must
