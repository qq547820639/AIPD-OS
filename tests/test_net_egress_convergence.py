"""F-NET-01：src/ 网络出口必须收敛到 ``aipd_os.net.http``。

收敛只有在**能被机器重新钉住**时才算完成：本用例按 AST 扫描 ``src/``，
要求除 ``net/http.py`` 之外没有任何直连 socket 级出口（``urlopen``）或
optional extra 依赖（``requests``）——此前 8 处各写一遍 timeout/重试，
正是超时不统一、429 语义各异的根因。

判据按 AST 而非文本匹配：注释里提到 ``urlopen``（例如本模块自己的说明、
``imggen/providers.py`` 的迁移注释）不能变成假阳性，这是量具能开火的前提。
第二条用例用合成源码逐条验证探针真的会开火，避免「扫到 0 处 = 干净」的
假绿读数。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
CLIENT_PATH = SRC_ROOT / "aipd_os" / "net" / "http.py"

URLOPEN_NAMES = {"urlopen"}
REQUESTS_ROOT = "requests"


def _dotted(node: ast.AST) -> str:
    """把 a.b.c 形式的表达式还原成点号字符串，非属性链返回空串。"""
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def egress_violations(source: str, filename: str = "<memory>") -> list[str]:
    """返回一段源码里的网络出口违规（AST 判定，纯函数便于注入反证）。"""
    tree = ast.parse(source, filename=filename)
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == REQUESTS_ROOT or alias.name.startswith(REQUESTS_ROOT + "."):
                    found.append(f"{filename}:{node.lineno}: imports optional extra "
                                 f"'{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == REQUESTS_ROOT or module.startswith(REQUESTS_ROOT + "."):
                found.append(f"{filename}:{node.lineno}: imports optional extra "
                             f"'{module}'")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        tail = name.rsplit(".", 1)[-1] if name else ""
        if tail in URLOPEN_NAMES and (
                name in URLOPEN_NAMES or name.endswith("urllib.request.urlopen")):
            found.append(f"{filename}:{node.lineno}: calls urlopen() directly "
                         f"instead of aipd_os.net.http.request()")
        elif name.startswith(REQUESTS_ROOT + ".") and tail in {"get", "post", "request", "Session"}:
            found.append(f"{filename}:{node.lineno}: uses requests.{tail}() "
                         f"instead of aipd_os.net.http.request()")
    return found


def scan_src() -> tuple[int, list[str]]:
    """返回 (实际扫到的源文件数, 违规清单)——分母随读数一起出，防止空树假绿。"""
    scanned = 0
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path == CLIENT_PATH:
            continue
        scanned += 1
        violations.extend(egress_violations(path.read_text(encoding="utf-8"), str(path)))
    return scanned, violations


def test_client_module_exists() -> None:
    assert CLIENT_PATH.is_file(), "统一出口模块必须存在，否则白名单等于放过全仓"


def test_src_has_no_direct_egress_outside_the_client() -> None:
    scanned, violations = scan_src()
    # 分母前提：扫到空目录同样返回 0 违规，那是一条假绿
    assert scanned > 150, f"扫描分母异常（{scanned} 个文件），结论不可信"
    assert violations == [], "src/ 存在未收敛的网络出口：\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "snippet,expected_marker",
    [
        ("import urllib.request\nurllib.request.urlopen('http://x')\n", "urlopen"),
        ("from urllib.request import urlopen\nurlopen('http://x')\n", "urlopen"),
        ("import requests\nrequests.get('http://x')\n", "requests"),
        ("from requests import Session\nSession()\n", "requests"),
        ("import requests\nVALUE = 1\n", "requests"),
    ],
)
def test_probe_fires_on_each_egress_shape(snippet: str, expected_marker: str) -> None:
    """注入反证：每一种绕过形态都必须被读到，否则上面的绿灯没有说服力。"""
    hits = egress_violations(snippet, "synthetic.py")
    assert hits, f"探针未开火：{snippet!r}"
    assert any(expected_marker in h for h in hits)


def test_probe_stays_quiet_on_compliant_and_mentioning_code() -> None:
    """合规调用与「注释里提到 urlopen」都不算违规——文本匹配的假阳性面。"""
    compliant = (
        "# 这里注释提到 urlopen，但只是注释\n"
        "from aipd_os.net.http import HttpError\n"
        "from aipd_os.net.http import request as http_request\n"
        "import urllib.parse\n"
        "def f(u):\n"
        "    return http_request(u, source='x'), urllib.parse.quote(u)\n"
    )
    assert egress_violations(compliant, "synthetic_ok.py") == []
