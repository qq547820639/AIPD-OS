"""Change Set 11 异常处理治理测试（P1-6）。

AST 静态扫描 ``src/aipd_os`` 与 ``scripts/*.py``：断言「except 体恰好只有
``pass``（或 ``...``）且无 ``# noqa: EMPTY_EXCEPT`` 豁免注释」的处理器数量为 0。

豁免政策：确属「必须吞」的场景（可选依赖探测、多格式解析回退、清理尽力而为、
优雅退出等）必须在 except 块内（或同一行）标注 ``# noqa: EMPTY_EXCEPT`` 并附
原因；默认不允许无注释空吞。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [
    ROOT / "src" / "aipd_os",
    ROOT / "scripts",
]


def _py_files():
    files = []
    for root in SCAN_DIRS:
        if root.name == "scripts":
            files += sorted(root.glob("*.py"))
        else:
            files += sorted(root.rglob("*.py"))
    return files


def _only_pass(node: ast.ExceptHandler) -> bool:
    body = node.body
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    # 也接受单个 Ellipsis 表达式（等价占位）
    return (len(body) == 1 and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and body[0].value.value is Ellipsis)


def _empty_except_without_exemption():
    """返回 [(path, lineno)]：空 except 且无 EMPTY_EXCEPT 豁免注释。"""
    hits = []
    for f in _py_files():
        try:
            src = f.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(src, filename=str(f))
        except SyntaxError:
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _only_pass(node):
                start = node.lineno
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                block = "\n".join(lines[start - 1:end])
                if "# noqa: EMPTY_EXCEPT" in block:
                    continue
                hits.append((str(f), node.lineno))
    return hits


def test_no_uncommented_empty_except():
    hits = _empty_except_without_exemption()
    assert hits == [], (
        "存在未豁免的空 except 处理器（必须改为 log / 收窄异常 / 或加 "
        "# noqa: EMPTY_EXCEPT + 原因）：\n" + "\n".join(f"{p}:{ln}" for p, ln in hits)
    )


def test_scan_directories_present():
    for d in SCAN_DIRS:
        assert d.is_dir(), f"扫描目录不存在：{d}"
    assert _py_files(), "未找到待扫描的 .py 文件"
