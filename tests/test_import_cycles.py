"""Change Set 10 依赖方向 / 无环测试（P1-5）。

用 AST 静态扫描 src/aipd_os 下所有 .py 的 import 语句构建模块依赖图，
断言：
1. 内部模块依赖图**无环**（忽略 stdlib / 第三方 / 条件导入失败）；
2. src 不得**静态** import scripts（动态 importlib 加载是已知收敛点，
   不在此门禁内强制）。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "aipd_os"


def _iter_py_files():
    return sorted(SRC.rglob("*.py"))


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT / "src").with_suffix("")
    return ".".join(rel.parts)


def _resolve_relative(mod: str, level: int, module: str, is_package: bool) -> str:
    """把相对 import 解析为内部模块名（近似 Python 语义，供无环门禁使用）。"""
    parts = mod.split(".")
    pkg_parts = parts if is_package else parts[:-1]
    drop = level - 1
    base_parts = pkg_parts[: len(pkg_parts) - drop] if drop > 0 else pkg_parts
    base = ".".join(base_parts)
    if module:
        return base + "." + module if base else module
    return base


def _internal_import_graph():
    """返回 {module: set(internal aipd_os 目标)}。"""
    graph: dict[str, set] = {}
    for f in _iter_py_files():
        mod = _module_name(f)
        is_package = f.name == "__init__.py"
        graph.setdefault(mod, set())
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    if target == "aipd_os" or target.startswith("aipd_os."):
                        graph[mod].add(target)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = _resolve_relative(mod, node.level, node.module or "",
                                             is_package)
                    if node.module:
                        if base == "aipd_os" or base.startswith("aipd_os."):
                            graph[mod].add(base)
                    else:
                        # from . import x：x 是当前包内符号/子模块
                        for alias in node.names:
                            if alias.name == "*":
                                continue
                            target = f"{base}.{alias.name}"
                            if target == "aipd_os" or target.startswith("aipd_os."):
                                graph[mod].add(target)
                else:
                    target = node.module or ""
                    if target == "aipd_os" or target.startswith("aipd_os."):
                        graph[mod].add(target)
    # 只保留图中真实存在的内部模块节点；条件导入的缺失模块不纳入门禁。
    known = set(graph.keys())
    return {m: {t for t in targets if t in known} for m, targets in graph.items()}


def test_no_import_cycles():
    graph = _internal_import_graph()
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {}

    def visit(node: str, stack: list) -> None:
        color[node] = GRAY
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                raise AssertionError(
                    f"import cycle detected: {' -> '.join(stack + [nxt])}")
            if c == WHITE:
                visit(nxt, stack)
        color[node] = BLACK
        stack.pop()

    for node in sorted(graph):
        if color.get(node, WHITE) == WHITE:
            visit(node, [])


def test_no_src_static_import_of_scripts():
    """src 不得静态 import scripts（scripts → src 单向）。"""
    for f in _iter_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root != "scripts", (
                        f"{f}: src 静态 import scripts ({alias.name})")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root != "scripts", (
                    f"{f}: src 静态 import scripts ({node.module})")
