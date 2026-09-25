"""契约绑定：一份 schema 到底被谁校验、校验的是盘上哪个文件、以及跨文件 `$ref` 怎么解。

为什么单独一个模块：第 29 片的接口清单按**文件名字面量**反查消费者，于是看不见
`src/aipd_os/scripts/schema_check.py` 的**命名约定**绑定（`stem` + `DATA_DIRS`），
把四份「有人按约定校验」的契约报成了孤儿。这里把绑定规则收成**一处**，并且
**从真校验器里现抽**而不是抄常量——抄一份就是第二个会漂移的镜像。

三条规矩，都是这片反复在防的假绿：

1. **读不到 ≠ 没问题**。约定抽不出来、schema 解析不了、`$ref` 解不开，一律返回
   `unreadable` 状态并带着原因，绝不折算成 `valid`，也绝不折算成「没人校验」。
2. **枚举的真值是数据库那一列**。同一形状在 `assets/schemas/` 里有两份定义时
   （`fact.schema.json` 与 `project_checkpoint.schema.json` 的内联 `$defs.fact`），
   两份互比只能证明「抄得一样」；权威取 `src/aipd_os/state/db.py` 的
   `FACT_STATUSES`（AST 现抽），拿它当第四源逐份核对。
3. **落点要看得见**。`scripts/` 里那些 `exists(root, 'x.json')` 是**只判存在**的门，
   本模块把它们和「这个名字有没有同名契约」对起来，形状坏的产物才有地方拦。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_DIR = "assets/schemas"
#: 契约文件所在的仓根（本模块在 `src/aipd_os/` 下 ⇒ parents[2] 是 AIPD-OS 仓根）。
#: 被检的是**别人项目**的产物，契约却长在本仓里，所以产物根与契约根是两个参数。
ASSET_ROOT = Path(__file__).resolve().parents[2]

#: 真跑校验的那个脚本；绑定约定的唯一出处。
VALIDATOR_SCRIPT = "src/aipd_os/scripts/schema_check.py"
DB_MODULE = "src/aipd_os/state/db.py"

#: 校验结果四态。`unreadable` 与 `invalid` 分开，是为了不把「读不到」当成「改坏了」，
#: 也不把「读不到」当成「没问题」。
VALID = "valid"
INVALID = "invalid"
UNREADABLE = "unreadable"
NO_SCHEMA = "no_schema"
MISSING = "missing"

_EXISTS_JSON = re.compile(r"exists\(\s*root\s*,\s*['\"]([^'\"]+\.json)['\"]")


def _root(repo: Path | str) -> Path:
    return Path(repo)


def _load_constant(tree: ast.Module, name: str) -> ast.AST | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    return None


def binding_dirs(repo: Path | str) -> tuple[str, ...] | None:
    """现抽 `schema_check.DATA_DIRS`。读不到 ⇒ None（盲区），**不是**空元组。"""
    src = _root(repo) / VALIDATOR_SCRIPT
    if not src.is_file():
        return None
    try:
        value = _load_constant(ast.parse(src.read_text(encoding="utf-8")), "DATA_DIRS")
        return tuple(ast.literal_eval(value)) if value is not None else None
    except (OSError, SyntaxError, ValueError, TypeError):
        return None


def schema_stem(schema_name: str) -> str:
    """`project_checkpoint.schema.json` → `project_checkpoint`（与 schema_check 同法）。"""
    name = Path(schema_name).name
    return name[:-len(".schema.json")] if name.endswith(".schema.json") else Path(name).stem


def bound_instances(repo: Path | str, schema_name: str) -> list[str]:
    """按约定应该被校验的实例文件（存在的那些），路径相对仓库根。"""
    dirs = binding_dirs(repo)
    if dirs is None:
        return []
    root = _root(repo)
    stem = schema_stem(schema_name)
    out = []
    for d in dirs:
        if d.startswith("..") or d.startswith("/"):
            continue
        if (root / d / f"{stem}.json").is_file():
            out.append(f"{d}/{stem}.json")
    return out


def list_schemas(repo: Path | str) -> list[str]:
    root = _root(repo)
    return sorted(p.name for p in (root / SCHEMA_DIR).glob("*.schema.json"))


def load_schema(repo: Path | str, schema_name: str) -> tuple[dict[str, Any] | None, str]:
    """(文档, 状态)。状态 ∈ {VALID, UNREADABLE, NO_SCHEMA}——**只**说读没读到、能不能解析。"""
    path = _root(repo) / SCHEMA_DIR / Path(schema_name).name
    if not path.is_file():
        return None, NO_SCHEMA
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, UNREADABLE
    return (doc, VALID) if isinstance(doc, dict) else (None, UNREADABLE)


def build_registry(repo: Path | str) -> Any:
    """schemas 目录的 referencing Registry：裸文件名与 file:// URI 都能解析。

    不用 `jsonschema.RefResolver`——它自 4.18 起已弃用；`referencing` 是 jsonschema
    自己的后继（本机 4.25.1 已随包带 0.36.x，零新依赖）。
    """
    import referencing
    import referencing.jsonschema as rj

    root = _root(repo) / SCHEMA_DIR
    draft = rj.DRAFT202012

    def resource_for(name: str):
        return referencing.Resource.from_contents(
            json.loads((root / name).read_text(encoding="utf-8")),
            default_specification=draft)

    def retrieve(uri: str):
        name = str(uri).rsplit("/", 1)[-1]
        if (root / name).is_file():
            return resource_for(name)
        raise referencing.exceptions.Unresolvable(ref=str(uri))

    # referencing 的类型面向 mypy 不可见（它会把 Registry 认成别的名字），这里按运行时用
    registry_cls: Any = referencing.Registry
    reg = registry_cls(retrieve=retrieve)
    for path in sorted(root.glob("*.json")):
        res = resource_for(path.name)
        reg = reg.with_resource(path.absolute().as_uri(), res)
        reg = reg.with_resource(path.name, res)
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("$id"), str):
            reg = reg.with_resource(doc["$id"], res)
    return reg


def validate_document(repo: Path | str, schema_name: str,
                      doc: dict[str, Any]) -> dict[str, Any]:
    """拿 schema 核一份文档，返回 {status, errors, schema}；跨文件 `$ref` 可解析。

    引用解不开 ⇒ `unreadable` 并点名解不开的是谁：这时候既不能说文档合法，
    也不能说它违规——是**核不了**。
    """
    from jsonschema.exceptions import _WrappedReferencingError
    from jsonschema.validators import validator_for

    schema, status = load_schema(repo, schema_name)
    if status != VALID:
        return {"status": status, "errors": [], "schema": schema_name}
    try:
        registry = build_registry(repo)
        validator = validator_for(schema)(schema, registry=registry)
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    except _WrappedReferencingError as exc:
        return {"status": UNREADABLE, "schema": schema_name,
                "errors": [f"unresolvable $ref: {exc.ref}"]}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": UNREADABLE, "schema": schema_name,
                "errors": [f"validator could not run: {type(exc).__name__}: {exc}"]}
    return {"status": VALID if not errors else INVALID, "schema": schema_name,
            "errors": [f"{list(e.absolute_path) or '(root)'}: {e.message}" for e in errors]}


def landing_sites(repo: Path | str) -> list[dict[str, Any]]:
    """`scripts/` 里只判存在的 JSON 落点：{artifact, gate, schema}。

    `gate` 带行号，是为了「谁放的门」这句话能指回原地；`schema` 按同名词干配，
    配不上就是**没有契约**（不等于形状坏）。
    """
    root = _root(repo)
    stems = {schema_stem(n): n for n in list_schemas(root)}
    out: list[dict[str, Any]] = []
    scripts = root / "scripts"
    if not scripts.is_dir():
        return out
    for path in sorted(scripts.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _EXISTS_JSON.finditer(text):
            artifact = match.group(1)
            stem = schema_stem(Path(artifact).name)
            line = text[:match.start()].count("\n") + 1
            out.append({"artifact": artifact,
                        "gate": f"{path.relative_to(root)}:{line}",
                        "schema": stems.get(stem)})
    return out


def contract_for_artifact(artifact_rel: str, schema_root: Path | str | None = None) -> str | None:
    """产物路径 → 同名词干的契约文件名；没有同名契约 ⇒ None（**不等于**形状没问题）。"""
    root = Path(schema_root) if schema_root else ASSET_ROOT
    stem = schema_stem(Path(artifact_rel).name)
    candidates = {schema_stem(n): n for n in list_schemas(root)}
    return candidates.get(stem)


def validate_artifact_file(project_root: Path | str, artifact_rel: str,
                           *, schema_root: Path | str | None = None) -> dict[str, Any]:
    """按契约核**落盘产物**的形状。五态：`valid` / `invalid` / `unreadable` /
    `no_schema` / `missing`。

    五态分开是因为这五种情况的下一步完全不同：`missing` 是「门说交付了但文件不在」，
    `unreadable` 是「文件在但核不了」（不是它违规），`no_schema` 是「这形状今天没契约」。
    后两种都**不许**被读成通过。
    """
    schema_name = contract_for_artifact(artifact_rel, schema_root)
    if schema_name is None:
        return {"status": NO_SCHEMA, "schema": None, "artifact": artifact_rel, "errors": []}
    path = Path(project_root) / artifact_rel
    if not path.is_file():
        return {"status": MISSING, "schema": schema_name, "artifact": artifact_rel,
                "errors": ["标了交付，但文件不在"]}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": UNREADABLE, "schema": schema_name, "artifact": artifact_rel,
                "errors": [f"读不到或不是 JSON：{type(exc).__name__}"]}
    if not isinstance(doc, dict):
        return {"status": UNREADABLE, "schema": schema_name, "artifact": artifact_rel,
                "errors": ["顶层不是 JSON 对象"]}
    result = validate_document(schema_root or ASSET_ROOT, schema_name, doc)
    result["artifact"] = artifact_rel
    return result


def fact_status_authority(repo: Path | str) -> tuple[set[str] | None, str]:
    """(权威枚举, 出处)。取 `state/db.py` 的 `FACT_STATUSES`，AST 现抽，不抄。"""

    src = _root(repo) / DB_MODULE
    if not src.is_file():
        return None, f"{DB_MODULE} 不在盘上"
    try:
        node = _load_constant(ast.parse(src.read_text(encoding="utf-8")), "FACT_STATUSES")
        return (set(ast.literal_eval(node)), f"{DB_MODULE}:FACT_STATUSES") \
            if node is not None else (None, f"{DB_MODULE} 里没有 FACT_STATUSES")
    except (OSError, SyntaxError, ValueError, TypeError) as exc:
        return None, f"{DB_MODULE} 读不到：{type(exc).__name__}"


def _status_enum(node: dict[str, Any]) -> set[str] | None:
    props = node.get("properties")
    if isinstance(props, dict) and isinstance(props.get("status"), dict):
        enum = props["status"].get("enum")
        if isinstance(enum, list):
            return {str(x) for x in enum}
    return None


def shape_sites(repo: Path | str, shape: str) -> list[dict[str, Any]]:
    """所有**声明同一个形状**的地方：`<shape>.schema.json` 顶层，或任一 schema 的 `$defs/<shape>`。

    按形状收而不是「凡是叫 status 的 enum 都算」：checkpoint 里 `project/status`
    是工程生命周期、`$defs/decision/status` 是决议状态，拿事实枚举去比它们是噪声。
    """
    out: list[dict[str, Any]] = []
    for name in list_schemas(repo):
        schema, status = load_schema(repo, name)
        if status != VALID:
            out.append({"schema": name, "at": None, "status": status, "enum": None})
            continue
        assert schema is not None
        if schema_stem(name) == shape:
            enum = _status_enum(schema)
            if enum is not None:
                out.append({"schema": name, "at": "(顶层)", "status": VALID, "enum": enum})
        defs = schema.get("$defs")
        if isinstance(defs, dict) and isinstance(defs.get(shape), dict):
            enum = _status_enum(defs[shape])
            if enum is not None:
                out.append({"schema": name, "at": f"$defs/{shape}", "status": VALID,
                            "enum": enum})
    return out


def shape_vs_authority(repo: Path | str, shape: str = "fact") -> dict[str, Any]:
    """<shape> 形状的 `status` 枚举逐处与**它自己的**数据库权威枚举对照。

    只有 `fact` 有权威可查（`FACT_STATUSES`）；其它形状今天给不出权威源，
    于是 `authority_readable=False` 且各差集留空——**那是盲区，不是「一致」**。
    刻意不给一个总布尔：一处一致、另一处缺值时，「合不合格」读不出差在哪。
    """
    if shape == "fact":
        authority, source = fact_status_authority(repo)
    else:
        authority, source = None, f"（{shape} 形状今天没有数据库权威枚举可查）"
    rows: list[dict[str, Any]] = []
    for site in shape_sites(repo, shape):
        if site.get("status") != VALID:
            rows.append({"schema": site["schema"], "at": None,
                         "status": site.get("status", UNREADABLE),
                         "enum": [], "missing_vs_authority": [], "extra_vs_authority": []})
            continue
        enum = site["enum"] or set()
        rows.append({"schema": site["schema"], "at": site["at"], "status": VALID,
                     "enum": sorted(enum),
                     "missing_vs_authority": sorted(authority - enum) if authority else [],
                     "extra_vs_authority": sorted(enum - authority) if authority else []})
    return {"shape": shape,
            "authority": sorted(authority) if authority else None,
            "authority_source": source,
            "authority_readable": authority is not None,
            "sites": rows,
            "divergent": [f"{r['schema']}#{r['at']}" for r in rows
                          if r["status"] == VALID
                          and (r["missing_vs_authority"] or r["extra_vs_authority"])],
            "unreadable": [r["schema"] for r in rows if r["status"] != VALID]}

