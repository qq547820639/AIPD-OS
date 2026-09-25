"""接口清单与契约证据（**不叫 ICD**）：把本机声明的每条接口逐条列出，并写明它凭什么算被验过。

为什么这一格以前是零实现：真正的接口控制文档要含「责任与变更授权」与「接口职责」两节，
那两段内容只能由**对侧**给（NASA SE Handbook 附录 L 的 §1.3 / §3.1.2，2026-09-25 实读该页，
它自己把自己叫 IRD 不叫 ICD）。本仓单方生成一份叫「ICD」的文件，等于替别人签字。
所以这里只做可自查的那一半：**接口清单 + 每条的定义件 + 每条的验证证据 + 明确写出证不到什么**。

三条形状规矩，都是这片反复在防的假绿：

1. **分母一律重算，不抄表**。CLI 命令面取自 `command_contract.PUBLIC_COMMANDS`，
   MCP 工具取自 `state_service/mcp_server.py` 的 `def mcp_*`，schema 清单取 `assets/schemas/`
   目录实际文件，schema 的消费者取自全仓文本反查那个文件名。手抄一份数字，
   改名那天就悄悄漏项。
2. **「被引用」不等于「被验证」**。每条的 `verified_by` 必须是**真存在、真收集得到 test 的文件**
   （AST 解析，不靠人记得测试还在不在）；解析不到就进 `unverified`，不折算成已验证。
3. **声明了却没人消费 = 一条发现，不是一条通过**。schema 文件在盘上但全仓没人按它校验，
   记进 `declared_but_unconsumed`，整份文档的 verdict 因此只能 `incomplete`。
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTRACT_KIND = "aipd.interface_contract.v1"

#: 反查消费者时要扫的目录（不含 releases/ 与 build/：那是产物，不是接口的一方）。
SCAN_DIRS = ("src", "scripts", "tests", "state_service")

#: 本仓自己声明的文件格式契约：定义件与「拼法/名字」的唯一出处。
FILE_FORMAT_CONTRACTS: list[dict[str, Any]] = [
    {"id": "file_format:evidence_sidecar",
     "defines": ["src/aipd_os/cad/evidence.py"],
     "note": "侧车名 = 产物全名 + .evidence.json，拼法只允许存在 sidecar_path() 一处"},
    {"id": "file_format:delivery_baseline",
     "defines": ["src/aipd_os/delivery_baseline.py"],
     "note": "上一版交付物清单 kind=aipd.delivery_baseline.v1，易变字段按整名白名单"},
    {"id": "file_format:source_manifest",
     "defines": ["scripts/release_evidence.py"],
     "note": "SOURCE_MANIFEST.json：逐文件 path+sha256 + source_commit"},
    {"id": "file_format:provenance",
     "defines": ["scripts/release_evidence.py"],
     "note": "PROVENANCE.json：test_report 数字只从机器报告读，不硬编码"},
    {"id": "file_format:release_manifest",
     "defines": ["scripts/regenerate_release_manifest.py"],
     "note": "RELEASE_MANIFEST.json：与 SOURCE_MANIFEST 同口径的被哈希面"},
]

#: 每 kind 的「证到什么 / 证不到什么」。这两句必须是**这一 kind 的一般事实**，
#: 不许写成「已验证」了事——OpenAPI 自己就写明描述接口不等于断言服务端实现。
PROVES = {
    "cli_command": ("命令在 registry / SKILL.md / README 三处登记一致且可 dispatch",
                    "命令的行为对不对——那由各家族自己的用例管"),
    "mcp_tool": ("工具函数存在、走同一套 principal 认证",
                 "MCP 客户端真按这个签名调用（对侧不在此仓）"),
    "json_schema": ("schema 文件在盘、可解析、哈希与清单一致",
                    "有实例真按它被校验；对侧是否实现同一契约"),
    "file_format": ("该格式的读写代码与常量在同一处定义",
                    "外部工具能读这个格式"),
    "http_surface": ("服务端路由方法存在（do_GET/do_POST）与认证入口在位",
                     "对端客户端的期望一致"),
    "egress_consumer": ("本仓经由唯一出网点 aipd_os.net.http 访问外部端点",
                        "远端仍然提供该端点或同样的返回形状"),
}


@dataclass
class Section:
    """一类接口的行集合，加上这一类怎么被重算出来的。"""

    kind: str
    rows: list[dict[str, Any]] = field(default_factory=list)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(kind: str, name: str, defines: list[str], verified_by: list[str], *,
         direction: str = "provides", counterpart: str = "", **extra: Any) -> dict[str, Any]:
    proves, not_proves = PROVES[kind]
    row: dict[str, Any] = {
        "id": f"{kind}:{name}",
        "kind": kind,
        "name": name,
        "direction": direction,
        "counterpart": counterpart or "-",
        "defines": defines,
        "verified_by": verified_by,
        "proves": proves,
        "does_not_prove": not_proves,
    }
    row.update(extra)
    return row


def cli_rows(repo: Path) -> list[dict[str, Any]]:
    """命令面：分母来自 command_contract，不另数一遍。"""
    import sys

    sys.path.insert(0, str(repo / "src"))
    from aipd_os.cli.command_contract import PUBLIC_COMMANDS, get_command_entry

    out = []
    for name in sorted(PUBLIC_COMMANDS):
        entry = get_command_entry(name)
        out.append(_row("cli_command", name,
                        ["src/aipd_os/cli/command_contract.py", "src/aipd_os/cli/main.py"],
                        ["tests/test_command_coverage.py"],
                        requires_args=sorted(entry.requires_args),
                        category=entry.category.value, introduced_in=entry.introduced_in,
                        description=entry.description)
                    if entry is not None else
                    _row("cli_command", name,
                         ["src/aipd_os/cli/command_contract.py", "src/aipd_os/cli/main.py"],
                         ["tests/test_command_coverage.py"],
                         entry_missing=True))
    return out


def mcp_rows(repo: Path) -> list[dict[str, Any]]:
    """MCP 工具：AST 取 `def mcp_*`，认证入口要求真在同一个文件里。"""
    server = repo / "state_service" / "mcp_server.py"
    tree = ast.parse(server.read_text(encoding="utf-8"))
    tools = [n.name[len("mcp_"):] for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("mcp_")]
    guarded = any(isinstance(n, ast.FunctionDef) and n.name == "require_mcp_principal"
                  for n in ast.walk(tree))
    return [_row("mcp_tool", name, ["state_service/mcp_server.py"],
                 ["tests/test_mcp_authorization.py"],
                 auth_guarded=guarded)
            for name in sorted(tools)]


def schema_rows(repo: Path) -> list[dict[str, Any]]:
    """schema：文件清单取目录实际内容；消费者按**精确文件名**全仓反查。"""
    rows = []
    for path in sorted((repo / "assets" / "schemas").glob("*.json")):
        consumers = scan_consumers(repo, path.name)
        rows.append(_row("json_schema", path.name,
                         [f"assets/schemas/{path.name}"],
                         [c for c in consumers if c.startswith("tests/")],
                         consumers=consumers,
                         parses=_schema_parses(path)))
    return rows


def _schema_parses(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return True


def scan_consumers(repo: Path, needle: str) -> list[str]:
    """哪些文件里提到了这个精确名字（字面量反查，不猜）。"""
    hits: list[str] = []
    for base in SCAN_DIRS:
        root = repo / base
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if needle in text:
                hits.append(str(path.relative_to(repo)))
    return hits


def http_rows(repo: Path) -> list[dict[str, Any]]:
    """HTTP 提供面：按 do_GET / do_POST 实际在不在判，不靠 README 的自述。"""
    rows = []
    for rel, name in (("src/aipd_os/web/server.py", "owner_web_console"),
                      ("src/aipd_os/state/server.py", "state_rpc")):
        text = (repo / rel).read_text(encoding="utf-8")
        methods = [m for m in ("do_GET", "do_POST") if re.search(rf"def {m}\b", text)]
        rows.append(_row("http_surface", name, [rel],
                         ["tests/test_owner_web_console.py", "tests/test_authorization.py"]
                         if name == "owner_web_console" else
                         ["tests/test_authorization.py", "tests/test_tenant_boundaries.py"],
                         methods=methods,
                         authenticated=bool(re.search(r"require_|token|principal", text))))
    return rows


def egress_rows(repo: Path) -> list[dict[str, Any]]:
    """HTTP 消费面：谁真的经由唯一出网点访问外部。"""
    consumers = [r for r in scan_consumers(repo, "aipd_os.net.http")
                 if not r.endswith("net/http.py")]
    return [_row("egress_consumer", rel, ["src/aipd_os/net/http.py"],
                 ["tests/test_net_http.py", "tests/test_net_egress_convergence.py"],
                 direction="consumes",
                 counterpart="外部 HTTP 端点（各家 provider）")
            for rel in sorted(consumers)]


def resolve_tests(repo: Path, spec: str) -> tuple[bool, int]:
    """`tests/x.py` 或 `tests/x.py::Class::func` 解析成「文件在、符号在、收得到 test」。

    AST 解析而不是跑 pytest：跑一次全仓 collect 太慢，但**有一条常驻用例**用
    `--collect-only` 复核对齐（见 tests/test_interface_contract.py），
    所以这里不是自说自话。
    """
    path, _, tail = spec.partition("::")
    file = repo / path
    if not file.is_file():
        return False, 0
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False, 0
    names: set[str] = set()
    count = 0
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            names.add(node.name)
            count += sum(1 for sub in node.body
                         if isinstance(sub, ast.FunctionDef) and sub.name.startswith("test_"))
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            names.add(node.name)
            count += 1
    if not tail:
        return count > 0, count
    parts = tail.split("::")
    if parts[0] not in names:
        return False, 0
    if len(parts) == 2:
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == parts[0]),
                   None)
        if cls is None or not any(isinstance(s, ast.FunctionDef) and s.name == parts[1]
                                  for s in cls.body):
            return False, 0
    return True, count


def build(repo: Path | str) -> dict[str, Any]:
    """装配整份接口清单与契约证据（不落盘）。"""
    root = Path(repo)
    rows: list[dict[str, Any]] = []
    rows.extend(cli_rows(root))
    rows.extend(mcp_rows(root))
    rows.extend(schema_rows(root))
    for spec in FILE_FORMAT_CONTRACTS:
        rows.append(_row("file_format", spec["id"].split(":", 1)[1], spec["defines"],
                         _format_tests(spec["id"]), note=spec["note"]))
    rows.extend(http_rows(root))
    rows.extend(egress_rows(root))

    unverified: list[str] = []
    missing_defines: list[str] = []
    unconsumed: list[str] = []
    for row in rows:
        for rel in row["defines"]:
            if not (root / rel).is_file():
                missing_defines.append(f"{row['id']} → {rel}")
        resolved = []
        for spec in row["verified_by"]:
            ok, n = resolve_tests(root, spec)
            if ok:
                resolved.append({"spec": spec, "tests": n})
        row["verified_by_resolved"] = resolved
        if not resolved:
            unverified.append(row["id"])
        if row["kind"] == "json_schema" and not row.get("consumers"):
            unconsumed.append(row["name"])

    digest = {rel: _sha256(root / rel) for row in rows for rel in row["defines"]
              if (root / rel).is_file()}
    return {
        "kind": CONTRACT_KIND,
        "title": "接口清单与契约证据（不是 ICD）",
        "not_icd_because": "ICD 的「责任与变更授权」「接口职责」两节只能由对侧给；"
                           "本仓单方产它等于伪造签署（NASA SE Handbook 附录 L 实读，2026-09-25）",
        "repo": str(root),
        "counts": {"rows": len(rows),
                   "by_kind": _tally(rows),
                   "unverified": len(unverified),
                   "declared_but_unconsumed": len(unconsumed),
                   "missing_defines": len(missing_defines)},
        "verdict": ("complete" if not (unverified or missing_defines or unconsumed)
                    else "incomplete"),
        "unverified": unverified,
        "declared_but_unconsumed": unconsumed,
        "missing_defines": missing_defines,
        "definition_digests": digest,
        "interfaces": rows,
    }


def _tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row["kind"]] = out.get(row["kind"], 0) + 1
    return out


def _format_tests(ident: str) -> list[str]:
    return {
        "file_format:evidence_sidecar": ["tests/test_evidence_sidecar_paths.py"],
        "file_format:delivery_baseline": ["tests/test_delivery_baseline.py"],
        "file_format:source_manifest": ["tests/test_packaging.py"],
        "file_format:provenance": ["tests/test_release_evidence.py"],
        "file_format:release_manifest": ["tests/test_packaging.py"],
    }[ident]


def verdict_rc(doc: dict[str, Any], *, strict: bool = False) -> int:
    """三态退出码：定义件缺失 ⇒ 必拦（与 --strict 无关）；判定不是 complete ⇒ 只在 --strict 拦。

    不把「没取证」折算成通过，也不把它做成一条永远红：孤儿契约要有人去接，
    但那是另一片的活；今天由 --strict 让 CI 自己选要不要拦。
    """
    if doc["missing_defines"]:
        return 4
    if strict and doc["verdict"] != "complete":
        return 4
    return 0


def write(doc: dict[str, Any], out_path: Path | str) -> Path:
    from aipd_os.cad.evidence import sidecar_path

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    sidecar = sidecar_path(target)
    sidecar.write_text(json.dumps({
        "kind": "aipd.interface_contract.sidecar.v1",
        "document": target.name,
        "document_sha256": _sha256(target),
        "verdict": doc["verdict"],
        "counts": doc["counts"],
        "not_icd_because": doc["not_icd_because"],
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
