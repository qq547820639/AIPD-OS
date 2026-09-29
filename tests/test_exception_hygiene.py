"""异常处理治理门禁（Change Set 11 P1-6；第 106 片改版）。

断言代码面上「无记号的刻意吞异常」数量为 0，两种吞法都算：

1. except 体恰好只有 ``pass``（或 ``...``）；
2. ``contextlib.suppress(...)``／``suppress(...)`` 块——SIM105 建议的改写
   不会让吞法消失，只会让旧判据看不见它，所以从第 106 片起纳入同一道门。

豁免记号：``# aipd: empty-except - 原因``，写在 with/except 行上、紧随其后的
下一行或紧贴其上的注释行；隔了两行以上的原因注释不算豁免（防止一条注释盖住
嵌套的多个吞点）。

旧记号 ``# noqa: EMPTY_EXCEPT`` 必须全部收回：它不是 ruff 的规则码，只会制造
``Invalid # noqa directive`` 警告；代码面再出现一次即判红（收回臂）。

面：``src/aipd_os``、``scripts``（含子目录——第 106 片收编 research 盲区）、
``state_service``。解析不了的文件单列第三态判红，不许静默 ``continue``。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MARKER = "# aipd: empty-except"
OLD_MARKER = "# noqa: EMPTY_EXCEPT"
SCAN_DIRS = [
    ROOT / "src" / "aipd_os",
    ROOT / "scripts",
    ROOT / "state_service",
]
# 反缩水底线：现读面 310 个文件、吞点分母 23（13 个 only-pass + 10 个 suppress）。
# 拆掉吞点让分母掉下去同样要过人手——不许靠"少一个 plaintiff"变绿。
FACE_FLOOR = 300
SWALLOW_FLOOR = 23


def _py_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
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


def _is_suppress(node: ast.With | ast.AsyncWith) -> bool:
    for item in node.items:
        expr = item.context_expr
        func = expr.func if isinstance(expr, ast.Call) else expr
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "suppress":
            return True
    return False


def _parse(files: list[Path]):
    """返回 ([(path, tree, lines)], [解析不了的 path])。第三态单独报，不静默跳过。"""
    parsed, unparseable = [], []
    for f in files:
        try:
            src = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unparseable.append(Path(f"{f} (读不了: {type(exc).__name__})"))
            continue
        try:
            tree = ast.parse(src, filename=str(f))
        except (SyntaxError, ValueError) as exc:
            unparseable.append(Path(f"{f} (解析不了: {exc})"))
            continue
        parsed.append((f, tree, src.splitlines()))
    return parsed, unparseable


def _marker_in_window(lines: list[str], lineno: int) -> bool:
    """记号必须落在声明行、其上一行或紧随其后的下一行。"""
    window = lines[max(lineno - 2, 0):lineno + 1]
    return any(MARKER in line for line in window)


def _swallow_sites(parsed):
    """(分母, 无记号原告)：kind ∈ {except-pass, suppress}。"""
    total, unmarked = 0, []
    for f, tree, lines in parsed:
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _only_pass(node):
                kind = "except-pass"
            elif isinstance(node, (ast.With, ast.AsyncWith)) and _is_suppress(node):
                kind = "suppress"
            else:
                continue
            total += 1
            if not _marker_in_window(lines, node.lineno):
                unmarked.append((f, node.lineno, kind))
    return total, unmarked


def _old_marker_lines(parsed):
    hits = []
    for f, _tree, lines in parsed:
        for i, line in enumerate(lines, start=1):
            if OLD_MARKER in line:
                hits.append((f, i))
    return hits


def audit(files: list[Path] | None = None) -> dict:
    """一次读数，三个字段各答各的面：无记号吞点 / 旧记号残留 / 解析不了。"""
    files = _py_files() if files is None else files
    parsed, unparseable = _parse(files)
    swallow_total, unmarked = _swallow_sites(parsed)
    return {"face": len(files), "swallow_total": swallow_total,
            "unmarked": unmarked,
            "old_marker": _old_marker_lines(parsed),
            "unparseable": unparseable}


def _fmt(hits) -> str:
    return "\n".join(f"{p}:{ln}{'' if kind is None else f' ({kind})'}"
                     for p, ln, *kind in hits)


def test_scan_directories_present():
    for d in SCAN_DIRS:
        assert d.is_dir(), f"扫描目录不存在：{d}"
    files = _py_files()
    assert len(files) >= FACE_FLOOR, (
        f"扫描面塌了：只有 {len(files)} 个 .py（下限 {FACE_FLOOR}）——"
        "先查目录改名，不是 celebrate")


def test_no_unmarked_swallow():
    rep = audit()
    assert rep["swallow_total"] >= SWALLOW_FLOOR, (
        f"吞点分母掉到 {rep['swallow_total']}（下限 {SWALLOW_FLOOR}）："
        "拆吞点要过人手，不许靠分母缩水变绿")
    assert rep["unmarked"] == [], (
        "存在未豁免的刻意吞异常（except 体只有 pass，或 suppress 块）。"
        f"必须改为 log / 收窄异常 / 或在声明行加 {MARKER} - 原因：\n"
        + _fmt(rep["unmarked"]))


def test_old_marker_fully_retracted():
    rep = audit()
    assert rep["old_marker"] == [], (
        f"旧记号 {OLD_MARKER} 不是 ruff 规则码，只制造 Invalid noqa 警告；"
        f"改为 {MARKER} - 原因：\n" + _fmt(rep["old_marker"]))


def test_unparseable_face_is_empty():
    rep = audit()
    assert rep["unparseable"] == [], (
        "扫描面里有解析不了的文件——它们今天对这道门是隐形的（第三态）：\n"
        + "\n".join(str(p) for p in rep["unparseable"]))


# ---------- 必开火控制：每支判据各配一支能红的夹具，配一支带记号不开火的反证 ----------

def _tmp_tree(tmp_path: Path, body: str) -> list[Path]:
    f = tmp_path / "fixture.py"
    f.write_text("import contextlib\n\n" + body, encoding="utf-8")
    return [f]


def test_control_unmarked_except_pass_fires(tmp_path):
    rep = audit(_tmp_tree(tmp_path, "try:\n    int('x')\nexcept ValueError:\n    pass\n"))
    assert [(p.name, k) for p, _ln, k in rep["unmarked"]] == [("fixture.py", "except-pass")]


def test_control_unmarked_suppress_fires(tmp_path):
    rep = audit(_tmp_tree(
        tmp_path, "with contextlib.suppress(ValueError):\n    int('x')\n"))
    assert [(p.name, k) for p, _ln, k in rep["unmarked"]] == [("fixture.py", "suppress")]


def test_control_bare_suppress_import_shape_also_fires(tmp_path):
    f = tmp_path / "fixture.py"
    f.write_text("from contextlib import suppress\n\nwith suppress(ValueError):\n"
                 "    int('x')\n", encoding="utf-8")
    rep = audit([f])
    assert [(p.name, k) for p, _ln, k in rep["unmarked"]] == [("fixture.py", "suppress")]


def test_control_marked_swallow_does_not_fire(tmp_path):
    rep = audit(_tmp_tree(
        tmp_path,
        "try:\n    int('x')\nexcept ValueError:  "
        f"# {MARKER.lstrip('# ')}\n    pass\n"))
    assert rep["unmarked"] == []


def test_control_marker_on_next_line_counts(tmp_path):
    rep = audit(_tmp_tree(
        tmp_path,
        "try:\n    int('x')\nexcept ValueError:\n"
        f"    # {MARKER.lstrip('# ')} - 原因\n    pass\n"))
    assert rep["unmarked"] == []


def test_control_marker_two_lines_away_does_not_exempt(tmp_path):
    rep = audit(_tmp_tree(
        tmp_path,
        f"# {MARKER.lstrip('# ')} - 隔了一行的原因不算数\n"
        "try:\n    int('x')\nexcept ValueError:\n    pass\n"))
    assert [(p.name, k) for p, _ln, k in rep["unmarked"]] == [("fixture.py", "except-pass")]


def test_control_old_marker_fires_retraction_arm(tmp_path):
    rep = audit(_tmp_tree(
        tmp_path,
        "try:\n    int('x')\nexcept ValueError:  "
        f"# {OLD_MARKER} - 旧写法\n    pass\n"))
    assert [(p.name, ln) for p, ln in rep["old_marker"]] == [("fixture.py", 5)]


def test_control_unparseable_file_is_reported_not_skipped(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def oops(:\n", encoding="utf-8")
    rep = audit([f])
    assert len(rep["unparseable"]) == 1 and "broken.py" in str(rep["unparseable"][0])
    assert rep["unmarked"] == [], "解析失败不得伪装成「面上没有吞点」"


@pytest.mark.parametrize("body", [
    "for _ in range(1):\n"
    f"    with contextlib.suppress(ValueError):  # {MARKER.lstrip('# ')} - 原因\n"
    "        int('x')\n",
    "if True:\n    try:\n        int('x')\n    except ValueError:\n"
    f"        pass  # {MARKER.lstrip('# ')} - 行内原因\n",
])
def test_control_nested_and_inline_shapes(tmp_path, body):
    rep = audit(_tmp_tree(tmp_path, body))
    assert rep["unmarked"] == []
