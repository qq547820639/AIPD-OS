"""登记表里"某样东西还没有"这类否定句，必须配一个能把它证伪的锚点（F-STALE-ABSENCE 第 65 片）。

## 为什么开这一面

第 53 片接上 BOM 版本记录的返工执行器（`src/aipd_os/bom/bom_rework.py`）之后，
登记表里那句「BOM 版本记录仍没有」一直没人改；同一行的另一句「执行器只认图纸声明这一类制品」
也一样漂着。第 65 片派出的只读普查把它们抓回来，而**抓回来靠的是人不是机器**——
这与第 59/60 片同族：那次缺的判据是"文档点名的命令要注册着"，于是有了
`doc_command_census.py`；这次缺的是"文档承诺的缺口要真的还缺着"，
而成熟工具里没有这一面（选型见取证文档：doorstop 判的是 YAML item 之间的断链，
doctest 判的是正文里的可执行 Python，中文否定句两者都不是）。

## 判据形状（三态，不把"看不见"折成任何一种判决）

一条登记 = (能力 id, 字段, 锚点原文, 反证锚点)。锚点在语料里**找不到** ⇒ 判红（账本与正文脱钩：
本轮就是把两句过期话删掉的那一轮，删话不删账必须响）；反证锚点**存在** ⇒ 判红（这句话已经过期）；
反证锚点**不存在** ⇒ 成立；反证锚点**解析不出来**（要一跳解析的常量指不到模块）⇒ 前提不成立退 2，
绝不折算成"这句话是对的"。

登记表里带否定词的句子远不止登记的这几条（现算值看 `--json` 的 `corpus`，本文不抄绝对数——
抄一份就会漂，这是第 60 片在自己 docstring 里犯过的错）。**自动从散文里判"这句是不是过期"
今天不开**：第 65 片实测把 15 个否定词打进登记表，命中的句子里大量是合法写法
（「不静默退回『没有基线』」「所以『没有执行器』不会被伪装成返工失败三次」这类谈设计的句子），
判红面一宽就会惩罚"把缺口写下来"这件事。所以散文面只报不红，并报出"登记了几条 / 还有几条没登记"，
让覆盖率成为一个看得见、会变的数。

## 第四面：同一个 id 不许两份登记表各说各话

`duplicate_divergence`：同一个能力 id 在两处登记表里对同一字段给出不同文本 ⇒ 判红。
这条不是设计出来的，是第 65 片自己被抓出来的：`product.*` 七行的**权威**在
`scripts/product_capabilities_extra.py`（`src/aipd_os/registry_data.py` 顶部就写着
"由生成脚本合并、勿手改本文件"），第一轮我只改了生成物那一侧，两份当场不一致，
而当时那一句「生产 Provider 未接入」在权威里活得好好的。同一 id 两处的分母与差异
都由 `--json` 的 `divergence` 现报。

退码：0 全部成立；4 有过期句或悬空账；2 前提不成立（账本空、登记表读不出、锚点解析不出）。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

REGISTRY_FILES = ("src/aipd_os/registry_data.py",
                  "scripts/product_capabilities_extra.py")

# 只报面的分母用这套否定词。刻意**不**拿它判红，理由见模块 docstring。
NEGATION_MARKERS = ("仍没有", "还没有", "尚未", "未实现", "未接入", "未做", "仍未",
                    "不支持", "不存在", "没有", "无执行", "暂无", "未提供", "未覆盖")

HOLDS = "HOLDS"                        # 反证锚点确实不在 ⇒ 这句"还没有"是活的
CONTRADICTED = "CONTRADICTED"          # 反证锚点在了 ⇒ 这句话过期（判红）
CLAIM_TEXT_ABSENT = "CLAIM_TEXT_ABSENT"  # 账里有、正文里已经找不到这句（判红：账文脱钩）
PRECONDITION = "PRECONDITION"          # 锚点解析不出来 ⇒ 不判，退 2

# ---------------------------------------------------------------------------
# 账本：每条都是一个"仍缺着"的承诺 + 什么一旦出现它就过期。
# anchor 必须是登记表里**逐字**出现的片段；改那句话时必须同批改这里。
# ---------------------------------------------------------------------------
CLAIMS: tuple[dict[str, Any], ...] = (
    {
        "id": "REWORK-EXECUTOR-QUOTE-BATCH",
        "capability": "product_truth.impact_propagation",
        "field": "current_limitation",
        "anchor": "仍没有执行器的是 **quote_batch**",
        "check": {"kind": "artifact_executor", "artifact": "quote_batch"},
        "why": "返工执行器按 `SUPPORTED_ARTIFACT = \"<制品类型>\"` 这条惯例登记"
               "（第 47/49/53 片四个执行器都是这个形状），报价批次哪天接上就过期",
    },
    {
        "id": "SUPERVISOR-TRUTH-MAPPING",
        "capability": "supervisor.fact_writeback",
        "field": "current_limitation",
        "anchor": "工作项与上游 truth 之间还没有映射",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/supervisor"],
                  "symbols": ["LineageGraph"]},
        "why": "写 truth_lineage 边的唯一入口是 `LineageGraph.add_edge`；"
               "supervisor 目录里哪天引用它，这句就过期",
    },
    {
        "id": "CAD-ASSEMBLY-CONSTRAINT-SOLVER",
        "capability": "cad.2d_drawings",
        "field": "current_limitation",
        "anchor": "仍未实现：装配约束/配合与爆炸位移的自动求解",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                  "symbols": ["AssemblyConstraint", "solve_constraints"]},
        "why": "约束对象/求解器一旦出现（本仓不建约束对象是这句话的内容本身），这句要就地改",
    },
    {
        "id": "QUOTE-FX-CONVERSION",
        "capability": "industrialize.quote_to_bom_cost",
        "field": "current_limitation",
        "anchor": "跨币种折算未实现",
        "check": {"kind": "identifier",
                  "paths": ["src/aipd_os/supply_chain", "src/aipd_os/bom"],
                  "symbols": ["convert_currency", "currency_rate", "fx_conversion"]},
        "why": "折算要么显式名要么汇率字段名；两者都不在时拒绝折算才是真的没做",
    },
    {
        "id": "RESEARCH-CONNECTOR-FULLTEXT",
        "capability": "research.fulltext_fetch",
        "field": "current_limitation",
        "anchor": "各连接器当前仅取摘要",
        "check": {"kind": "identifier", "paths": ["scripts/research"],
                  "symbols": ["fetch_fulltext"]},
        "why": "库里有 `src/aipd_os/research/fulltext.py`，但这句话判的是**连接器消费不消费它**——"
               "锚点取在连接器目录，取在库里会把自己判红（第 65 片实测的窄法）",
    },
)

SELF_STEMS = {"absence_claim_census", "test_absence_claim_census"}
SKIP_DIRS = {".git", ".venv", ".venv-ci", "__pycache__", ".mypy_cache", ".pytest_cache",
             "build", "dist", "node_modules", "releases", ".pytest", ".ruff_cache"}


# ------------------------------------------------------------------ 语料读取
def registry_strings(root: Path) -> tuple[dict[str, dict[str, list[tuple[str, int, str]]]],
                                          list[str]]:
    """AST 读登记表：`{能力 id: {字段: [(文件, 行号, 文本)]}}`。

    不 import 登记表：它 import 了产品包，判据跑起来不该有副作用，也不该被一次导入失败
    整个吞掉（那样"看不见"会被读成"没有否定句"）。
    **文件名必须进读数**：`src/aipd_os/registry_data.py` 顶部写着"7 项 product.* 由
    `scripts/product_capabilities_extra.py` 合并生成、勿手改本文件"——第 65 片我就是只改了
    生成物那一侧，靠这条读数才看见两份不一致（见 `duplicate_divergence`）。
    """
    out: dict[str, dict[str, list[tuple[str, int, str]]]] = {}
    problems: list[str] = []
    found_any = False
    for rel in REGISTRY_FILES:
        path = root / rel
        if not path.is_file():
            continue
        found_any = True
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"registry_unparseable: {rel}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            cid = ""
            fields: dict[str, list[tuple[str, int, str]]] = {}
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                if key.value == "id":
                    cid = value.value
                fields.setdefault(key.value, []).append((rel, value.lineno, value.value))
            if cid:
                bucket = out.setdefault(cid, {})
                for fname, rows in fields.items():
                    bucket.setdefault(fname, []).extend(rows)
    if not found_any:
        problems.append("registry_missing: 登记表一个都没读到")
    return out, problems


def duplicate_divergence(corpus: dict[str, dict[str, list[tuple[str, int, str]]]]) -> list[dict]:
    """同一个能力 id 在两份登记表里对同一字段各说各话 ⇒ 至少有一份是错的。

    这一面与"否定句过期"同轴的理由很简单：它就是把同一句话登记在两处时，
    改一处会被读成两处都改完的那个失效模式（第 65 片实测抓到一次）。
    """
    out: list[dict] = []
    for cid, fields in sorted(corpus.items()):
        for fname, rows in sorted(fields.items()):
            per_file: dict[str, set[str]] = {}
            for rel, _lineno, text in rows:
                per_file.setdefault(rel, set()).add(text)
            if len(per_file) < 2:
                continue
            distinct = {t for texts in per_file.values() for t in texts}
            if len(distinct) > 1:
                out.append({"capability": cid, "field": fname,
                            "files": sorted(per_file),
                            "lines": [f"{rel}:{lineno}" for rel, lineno, _t in rows]})
    return out


def absence_sentences(corpus: dict[str, dict[str, list[tuple[str, int, str]]]]) -> list[str]:
    """语料里所有带否定词的句子片段（只用于分母与覆盖率，不判红）。"""
    hits: list[str] = []
    for cid, fields in corpus.items():
        for fname, rows in fields.items():
            for _rel, _lineno, text in rows:
                for sent in text.replace("\n", " ").split("；"):
                    if any(m in sent for m in NEGATION_MARKERS):
                        hits.append(f"{cid}|{fname}|{sent.strip()[:80]}")
    return hits


def locate(corpus: dict[str, dict[str, list[tuple[str, int, str]]]], capability: str,
           field: str, anchor: str) -> tuple[str, str, int] | None:
    """锚点在**声明的那个能力的那个字段**里逐字出现 ⇒ (文件, 字段, 行号)；否则 None。

    刻意绑到 (capability, field)：只在全文里找得到不算数——第 65 片实测登记表里有
    三条不同能力共用同一句「生产 Provider 未接入」，不绑字段就会一条改完三条假装都改完。
    同一 id 在两处文件都出现时返回**每一条**位点（`duplicate_divergence` 那一面负责差异）。
    """
    for rel, lineno, text in corpus.get(capability, {}).get(field, []):
        if anchor in text:
            return rel, field, lineno
    return None


# ------------------------------------------------------------------ 反证锚点
def _iter_py(root: Path, rel_dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for rel in rel_dirs:
        base = root / rel
        if base.is_file() and base.suffix == ".py":
            files.append(base)
        elif base.is_dir():
            for path in sorted(base.rglob("*.py")):
                if set(path.parts) & SKIP_DIRS or path.stem in SELF_STEMS:
                    continue
                files.append(path)
    return files


def _literal_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def artifact_executors(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """`{制品类型: ["文件:行", ...]}`：谁登记了自己是哪类制品的返工执行器。

    惯例是模块级 `SUPPORTED_ARTIFACT = ...`（右值可以是字面量，也可以是同模块或一跳
    import 来的常量）。一跳解析不出来 ⇒ 记一条前提问题，不许悄悄当"没有这个执行器"。
    """
    out: dict[str, list[str]] = {}
    problems: list[str] = []
    files = _iter_py(root, ["src"])
    trees: dict[Path, ast.Module] = {}
    for path in files:
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"unreadable: {path.relative_to(root)}: {exc}")
    for path, tree in trees.items():
        module_consts = _module_string_consts(tree)
        imports = _module_import_map(tree)
        for node in tree.body:
            targets, value = _assign_targets_value(node)
            if "SUPPORTED_ARTIFACT" not in targets:
                continue
            literal = _literal_str(value)
            where = f"{path.relative_to(root)}:{getattr(node, 'lineno', 0)}"
            if literal is not None:
                out.setdefault(literal, []).append(where)
                continue
            if isinstance(value, ast.Name):
                resolved = module_consts.get(value.id)
                if resolved is None:
                    resolved = _resolve_imported(root, imports, path, value.id)
                    if resolved == "__UNRESOLVED__":
                        problems.append(
                            f"anchor_unresolvable: {where} 的 {value.id} 一跳解析不到")
                        continue
                if isinstance(resolved, str):
                    out.setdefault(resolved, []).append(where)
                else:
                    problems.append(
                        f"anchor_unresolvable: {where} 的 {value.id} 不是字符串常量")
    return out, problems


def _module_string_consts(tree: ast.Module) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in tree.body:
        targets, value = _assign_targets_value(node)
        literal = _literal_str(value)
        if literal is not None:
            for name in targets:
                consts[name] = literal
    return consts


def _module_import_map(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """`{本地名: (来源模块点分路径, 源名)}`，只收 `from X import Y` 与 `import X`。"""
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out[alias.asname or alias.name.split(".")[0]] = (alias.name, "")
    return out


def _resolve_imported(root: Path, imports: dict[str, tuple[str, str]], here: Path,
                      name: str) -> Any:
    """一跳解析 `NAME`：到来源模块里取模块级字符串常量。

    返回 str（解出）、None（本地/来源都不是常量 ⇒ 交给调用方判"不是字符串常量"）、
    或字符串 `"__UNRESOLVED__"`（来源文件根本找不到 ⇒ 前提不成立，不许折算成"执行器不存在"）。
    """
    src = imports.get(name)
    if src is None:
        return None
    module, _src_name = src
    candidate = root / "src" / Path(*module.split("."))
    if not candidate.with_suffix(".py").is_file() and not (candidate / "__init__.py").is_file():
        return "__UNRESOLVED__"
    target = candidate.with_suffix(".py") if candidate.with_suffix(".py").is_file() \
        else candidate / "__init__.py"
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    except (SyntaxError, UnicodeDecodeError):
        return "__UNRESOLVED__"
    return _module_string_consts(tree).get(name)


def _assign_targets_value(node: ast.AST) -> tuple[list[str], ast.expr | None]:
    if isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        return names, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id], node.value
    return [], None


def identifier_hits(root: Path, dirs: list[str], symbols: list[str]) -> list[str]:
    """AST 面上的标识符引用（`Name`/`Attribute`/`def`/`class`/import 名）。

    **只走 AST 不走文本**：这些锚点的否定句自己就要在注释与 docstring 里写"不做 X"，
    文本扫描会把"写清楚了没做"读成"做了"（第 45 片 `run_rework` 那条判据的同一条理由）。
    """
    want = set(symbols)
    hits: list[str] = []
    for path in _iter_py(root, dirs):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root)
        for node in ast.walk(tree):
            named: str | None = None
            lineno = getattr(node, "lineno", 0)
            if isinstance(node, ast.Name):
                named = node.id
            elif isinstance(node, ast.Attribute):
                named = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                named = node.name
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # Python 3.9 的 `ast.alias` 没有 lineno，取 import 语句那一行的号
                if any((a.name.split(".")[0]) in want or a.name in want
                       for a in node.names):
                    hits.append(f"{rel}:{lineno}")
                continue
            if named is not None and named in want:
                hits.append(f"{rel}:{lineno}")
    return hits


def run_check(root: Path, check: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    """⇒ (反证锚点在不在, 位点, 盲区)。

    锚点**在** ⇒ 这句话过期，与别处有没有盲区无关（判决已经拿到证据）。
    锚点**不在** + 有盲区 ⇒ 前提不成立：盲区完全可能正藏着那个执行器，不许读成"这句话对"。
    锚点**不在** + 无盲区 ⇒ 这句话仍然成立。
    """
    kind = check.get("kind")
    if kind == "artifact_executor":
        executors, blind = artifact_executors(root)
        sites = executors.get(str(check.get("artifact", "")), [])
        return (bool(sites), sites, blind)
    if kind == "identifier":
        dirs = list(check.get("paths", []))
        symbols = list(check.get("symbols", []))
        if not dirs or not symbols:
            return (False, [],
                    ["check_malformed: identifier 锚点缺 paths 或 symbols"])
        hits = identifier_hits(root, dirs, symbols)
        return (bool(hits), hits, [])
    return (False, [], [f"check_kind_unknown: {kind!r}"])


# ------------------------------------------------------------------ 判决
def audit(root: Path, claims: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    corpus, problems = registry_strings(root)
    if not corpus:
        problems.append("corpus_empty: 登记表一个能力都没读到（空分母不算绿）")
    if not claims:
        problems.append("claims_empty: 账本一条都没登记")

    rows: list[dict[str, Any]] = []
    for claim in claims:
        where = locate(corpus, str(claim.get("capability", "")),
                       str(claim.get("field", "")), str(claim.get("anchor", "")))
        if where is None:
            rows.append({"id": claim.get("id"), "verdict": CLAIM_TEXT_ABSENT,
                         "evidence": [], "problems": [],
                         "detail": f"账里有这条，登记表 {claim.get('capability')}."
                                   f"{claim.get('field')} 里已找不到原句锚点"})
            continue
        present, sites, check_problems = run_check(root, dict(claim.get("check", {})))
        if present:
            verdict = CONTRADICTED
        elif check_problems:
            verdict = PRECONDITION
        else:
            verdict = HOLDS
        rows.append({"id": claim.get("id"), "verdict": verdict, "evidence": sites[:5],
                     "problems": check_problems,
                     "anchor_at": f"{where[0]}:{where[1]}:{where[2]}",
                     "detail": str(claim.get("why", ""))})

    sentences = absence_sentences(corpus)
    anchored = {str(c.get("anchor")) for c in claims}
    unregistered = [s for s in sentences
                    if not any(a and a.replace("**", "") in s for a in anchored)]
    judged = [r for r in rows if r["verdict"] in (CONTRADICTED, CLAIM_TEXT_ABSENT)]
    divergence = duplicate_divergence(corpus)
    seen_problems: set[str] = set()
    for row in rows:
        if row["verdict"] != PRECONDITION:
            continue
        for one in row["problems"]:
            if one not in seen_problems:
                seen_problems.add(one)
                problems.append(one)
    return {
        "ok": not judged and not divergence and not problems,
        "corpus": {"capabilities": len(corpus),
                   "absence_sentences": len(sentences),
                   "claims_registered": len(claims),
                   "absence_sentences_unanchored": len(unregistered)},
        "rows": rows,
        "judged": judged,
        "divergence": divergence,
        "problems": problems,
        "sample_unanchored": unregistered[:8],
    }


def render(rep: dict[str, Any]) -> str:
    lines = ["=" * 60, "登记表否定句 × 反证锚点对账（F-STALE-ABSENCE）", "=" * 60]
    c = rep["corpus"]
    lines.append(f"语料：{c['capabilities']} 个能力，带否定词的句子 {c['absence_sentences']} 句；"
                 f"账本登记 {c['claims_registered']} 条，"
                 f"未挂锚点 {c['absence_sentences_unanchored']} 句（只报，不判红）")
    for row in rep["rows"]:
        mark = {"HOLDS": "✓", "CONTRADICTED": "✗", "CLAIM_TEXT_ABSENT": "✗",
                "PRECONDITION": "!"}.get(str(row["verdict"]), "?")
        at = row.get("anchor_at", "")
        ev = "、".join(row["evidence"][:3]) if row["evidence"] else "—"
        blind = ""
        if row["verdict"] == CONTRADICTED and row["problems"]:
            blind = f"（另有 {len(row['problems'])} 处盲区，不影响本条判决：锚点已经找到）"
        lines.append(f"  {mark} {row['id']} [{row['verdict']}] 锚点 {at} | 反证位点 {ev}{blind}")
    for d in rep["divergence"]:
        lines.append(f"  ✗ 同一个能力 id 在两份登记表里对同一字段各说各话："
                     f"{d['capability']}.{d['field']}（{' vs '.join(d['files'])}"
                     f"，位点 {'、'.join(d['lines'][:4])}）")
    for prob in rep["problems"]:
        lines.append(f"  ! 前提不成立：{prob}")
    if rep["sample_unanchored"]:
        lines.append("  · 未挂锚点的否定句（前 8 条，供下一轮挑）：")
        for one in rep["sample_unanchored"]:
            lines.append(f"      - {one}")
    if not rep["judged"] and not rep["divergence"] and not rep["problems"]:
        lines.append(f"判红 0 条：登记的 {c['claims_registered']} 句「仍缺着」现在都还缺着")
    return "\n".join(lines)


def _mark(marks: list, text: str) -> None:
    print("✓立住 " + text)
    marks.append(text)


def _self_test(tmp: Path) -> int:
    """合成语料：四种判决各要能真的出现，且互不折算。"""
    marks: list[str] = []
    (tmp / "src/aipd_os/bom").mkdir(parents=True)
    (tmp / "src/aipd_os/supervisor").mkdir(parents=True)
    (tmp / "scripts").mkdir(parents=True)
    # 反证锚点在 ⇒ 判红（CONTRADICTED）
    (tmp / "src/aipd_os/bom/bom_rework.py").write_text(
        'from aipd_os.bom.cost_lineage import ARTIFACT_BOM\n'
        'SUPPORTED_ARTIFACT = ARTIFACT_BOM\n', encoding="utf-8")
    (tmp / "src/aipd_os/bom/cost_lineage.py").write_text(
        'ARTIFACT_BOM = "bom"\n', encoding="utf-8")
    # 一跳解析不到 ⇒ 前提不成立，不许读成"这个执行器不存在"
    (tmp / "src/aipd_os/bom/ghost_rework.py").write_text(
        'from aipd_os.nowhere import ARTIFACT_GHOST\n'
        'SUPPORTED_ARTIFACT = ARTIFACT_GHOST\n', encoding="utf-8")
    (tmp / "src/aipd_os/supervisor/supervisor.py").write_text(
        'def f():\n    # 这里**不做**装配约束求解，也不写血缘边\n    return 1\n',
        encoding="utf-8")
    (tmp / "src/aipd_os/registry_data.py").write_text(
        'CAPABILITIES = [\n'
        ' {"id": "cap.a", "name": "同一个能力", '
        '"current_limitation": "bom 这一类仍没有执行器；跨币种折算未实现"},\n'
        ' {"id": "cap.b", "name": "另一个能力",\n'
        '  "current_limitation": "工作项与上游 truth 之间还没有映射"},\n'
        ' {"id": "cap.c", "name": "第三个能力", "current_limitation": "装配约束未实现"},\n'
        ']\n', encoding="utf-8")
    # 第二份登记表：同一个 id 的同一批字段。两份逐字相同 ⇒ 不判；改一处不改另一处 ⇒ 判
    # （第 65 片就是这么被抓到的：`product.*` 七行的权威在 `scripts/product_capabilities_extra.py`，
    #   我按登记表字面改的是生成物那一侧，两份当场不一致。）
    extra_dir = tmp / "scripts"
    extra_dir.mkdir(exist_ok=True)
    EXTRA_ROW = ('PRODUCT_CAPABILITIES = [\n'
                 ' {"id": "cap.a", "name": "同一个能力", '
                 '"current_limitation": "bom 这一类仍没有执行器；跨币种折算未实现"},\n'
                 ']\n')
    (extra_dir / "product_capabilities_extra.py").write_text(EXTRA_ROW, encoding="utf-8")
    claims = (
        {"id": "FIRED", "capability": "cap.a", "field": "current_limitation",
         "anchor": "仍没有执行器", "check": {"kind": "artifact_executor", "artifact": "bom"}},
        {"id": "QUIET", "capability": "cap.a", "field": "current_limitation",
         "anchor": "跨币种折算未实现",
         "check": {"kind": "identifier", "paths": ["src/aipd_os/bom"],
                   "symbols": ["convert_currency"]}},
        {"id": "HOLDS", "capability": "cap.b", "field": "current_limitation",
         "anchor": "工作项与上游 truth 之间还没有映射",
         "check": {"kind": "identifier", "paths": ["src/aipd_os/supervisor"],
                   "symbols": ["LineageGraph"]}},
        {"id": "PRE", "capability": "cap.c", "field": "current_limitation",
         "anchor": "装配约束未实现",
         "check": {"kind": "artifact_executor", "artifact": "ghost"}},
        {"id": "DANGLING", "capability": "cap.c", "field": "current_limitation",
         "anchor": "这句话已经被删掉了", "check": {"kind": "file", "path": "x"}},
    )
    rep = audit(tmp, claims)
    by = {str(r["id"]): r for r in rep["rows"]}
    assert by["FIRED"]["verdict"] == CONTRADICTED, rep
    assert by["FIRED"]["evidence"], "判红必须带反证位点，不然读者不知道是谁推翻的"
    assert by["FIRED"]["problems"], \
        "别处的盲区要照报，但不许改本条判决（锚点已经找到，判决不需要全覆盖）"
    _mark(marks, "反证锚点在 ⇒ CONTRADICTED 并带出位点（第 53 片漏改那两句的形状）；"
                 "同批扫描里的盲区不改这一条判决")
    assert by["QUIET"]["verdict"] == HOLDS, rep
    _mark(marks, "同一条登记里另一句「未实现」的锚点不在 ⇒ 成立（不因邻居判红而连坐）")
    assert by["HOLDS"]["verdict"] == HOLDS, rep
    assert not identifier_hits(tmp, ["src/aipd_os/supervisor"], ["LineageGraph"])
    _mark(marks, "注释里写着「不做 X」不算 X 做了（AST 面，不是文本面）")
    assert by["PRE"]["verdict"] == PRECONDITION, rep
    assert any(p.startswith("anchor_unresolvable") for p in rep["problems"]), rep
    _mark(marks, "一跳常量解析不到 ⇒ 前提不成立，不折算成 HOLDS/CONTRADICTED")
    assert by["DANGLING"]["verdict"] == CLAIM_TEXT_ABSENT, rep
    _mark(marks, "正文删了句、账里还留着 ⇒ 账文脱钩判红（反向对照：删包装必须翻红）")
    assert len(rep["judged"]) == 2, rep
    assert len(claims) == sum(1 for _ in rep["rows"]), "Σ 档位必须等于分母"
    buckets = {}
    for row in rep["rows"]:
        buckets[row["verdict"]] = buckets.get(row["verdict"], 0) + 1
    assert sum(buckets.values()) == len(claims), buckets
    _mark(marks, f"四档分桶之和 == 登记条数（{buckets}）")
    assert rep["divergence"] == [], rep["divergence"]
    _mark(marks, "同一 id 在两处登记表里逐字相同 ⇒ 不判（这一面也要有合规侧对照）")
    (extra_dir / "product_capabilities_extra.py").write_text(
        EXTRA_ROW.replace('"name": "同一个能力"', '"name": "改了一个名字"'), encoding="utf-8")
    rep2 = audit(tmp, claims)
    assert len(rep2["divergence"]) == 1, rep2["divergence"]
    assert rep2["divergence"][0]["capability"] == "cap.a", rep2["divergence"]
    clean_only = tuple(c for c in claims if c["id"] in ("QUIET", "HOLDS"))
    two = ("src/aipd_os/registry_data.py", "scripts/product_capabilities_extra.py")
    assert _rc_with(tmp, clean_only, two) == 4, "两份各说各话要自己退 4，不靠别的判红凑出来"
    _mark(marks, "两份登记表对同一 id 各说各话 ⇒ 判红并独立退 4（第 65 片的真实失效形状）")
    (extra_dir / "product_capabilities_extra.py").write_text(EXTRA_ROW, encoding="utf-8")
    print(render(rep))   # 四档判决都要在 stdout 上留名，常驻用例按这个形状断言"真走了一遍"
    saved = globals()["REGISTRY_FILES"]
    globals()["REGISTRY_FILES"] = ("src/aipd_os/registry_data.py",)
    try:
        ledger = tmp / "claims.json"
        ledger.write_text(json.dumps([claims[0]], ensure_ascii=False), encoding="utf-8")
        assert main(["--repo", str(tmp), "--claims", str(ledger)]) == 4, \
            "--claims 换账本必须真被吃到（常驻用例靠它做永久的开火对照）"
        _mark(marks, "--claims 外部账本与内置账本走同一条判决路径（退 4）")
        rc = _rc_with(tmp, claims)
        assert rc == 2, f"有前提塌就必须退 2，实际 {rc}"
        _mark(marks, "前提不成立退 2（既不是 0 也不是 4）")
        without_pre = tuple(c for c in claims if c["id"] != "PRE")
        assert _rc_with(tmp, without_pre) == 4, "判红面在有 CONTRADICTED 时必须退 4"
        _mark(marks, "撤掉前提那条 ⇒ 判红仍是 4（两档不互盖）")
        clean = tuple(c for c in without_pre
                      if c["id"] not in ("FIRED", "DANGLING"))
        assert _rc_with(tmp, clean) == 0, "全部成立时退 0"
        _mark(marks, "全部成立 ⇒ 退 0")
        assert _rc_with(tmp, ()) == 2, "空账本不许读成零违规"
        _mark(marks, "空账本读成前提不成立（退 2），不是「零过期句」")
    finally:
        globals()["REGISTRY_FILES"] = saved
    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


def _rc_with(root: Path, claims: tuple[dict[str, Any], ...],
             files: tuple[str, ...] = ("src/aipd_os/registry_data.py",)) -> int:
    saved = globals()["REGISTRY_FILES"]
    globals()["REGISTRY_FILES"] = files
    try:
        rep = audit(root, claims)
    finally:
        globals()["REGISTRY_FILES"] = saved
    if rep["problems"]:
        return 2
    return 4 if (rep["judged"] or rep["divergence"]) else 0


def _load_claims(path: str) -> tuple[dict[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("--claims 指向的必须是登记条目数组")
    return tuple(data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="登记表否定句 × 反证锚点对账")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--claims", default="", help="改用外部 JSON 账本（常驻用例的永久开火对照）")
    ap.add_argument("--json", default="", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    claims = _load_claims(args.claims) if args.claims else CLAIMS
    rep = audit(root, claims)
    print(render(rep))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    if rep["problems"]:
        return 2
    return 4 if (rep["judged"] or rep["divergence"]) else 0


if __name__ == "__main__":
    sys.exit(main())
