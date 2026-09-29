#!/usr/bin/env python3
"""文档里的代码引用 ↔ 代码事实：一条 `path[:line]` 还指得回东西吗（F-DOC-REF 第 41 片）。

为什么要有这根轴（本轮真实来由）：第 40 片收尾时按这条轴普查，抓到的**第一条真缺陷
是我自己上一轮写进 CHANGELOG 的**一句「与同仓 `ts_interface_shape.py`(tree-sitter) 同形」——
那个文件不在本仓，全仓也没用 tree-sitter。登记侧写得很像有出处，代码侧根本没有。

判据只吃「代码引用」，不吃五类看着像引用的东西——这是第一版普查最大的教训：
它把 CLI 示例操作数（`out/bracket.dxf`）、第三方内部路径（`ezdxf/…:212`）、
省略写法（`src/...py`）、模块简写（`cad/assembly.py` 实指 `src/aipd_os/cad/assembly.py`）
全算成缺陷，量出 514 条 missing，纯属判据自己造的假数。

六类（每条引用恰好落一类）：

- ``external``      外部/第三方/绝对路径/临时目录 ⇒ 不归本仓核。
- ``cli-operand``   在代码块内，或行首是 `aipd ` / 紧跟某个 `--flag` ⇒ 它是命令的操作数，不是出处。
- ``elided``        含 `...` 或 `…` 的省略写法 ⇒ 没有可比对的字面路径。
- ``shorthand``     只有文件名能唯一解析到盘上某文件（`backends.py`）⇒ 算解析成功，不要求写全路径。
- ``multi``         简写但同名多处 ⇒ **只报不判**：散文里用裸文件名合法，判红等于禁掉一种写法。
- ``repo``          带目录的本仓引用 ⇒ 必须解析得到；给了行号还必须落在那份文件的行数内。

判与不判分两档面：**现状面**（README/SKILL/docs 非 audit/references/docs 架构文档）判红；
**历史面**（CHANGELOG 与 docs/audit，逐轮记当时事实）只出错数不改写——
这条取舍借自外部同类工具 dsh-doc-guard 的「现状核对时忽略历史 changelog 行」。
退出码：0 现状面干净；4 现状面有缺陷，或语料读不到/Σ 对不上（读数不可信）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

EXTS = ("py", "md", "json", "yaml", "yml", "sql", "toml", "step", "dxf", "csv",
        "txt", "html", "sh", "mjs", "ts", "tsx")
# 扩展名必须前面有个点，且整段不能从词中间起——否则 `ezdxf` 会被 `dxf` 这个扩展名
# 就地吃掉，一段路径裂成 "ezdxf" + "/entities/polygon.py" 两段（本判据的第一版就栽在这）。
# 点号前必须至少有一个词字符：否则散文里的 "`.py`""`.evidence.json`" 这类**后缀提法**
# 会被切成一条"路径引用"（第一版就在这里造出 3 条现状面假缺陷）。
REF_RE = re.compile(
    r"(?<![\w./\-])([A-Za-z0-9_.\-/<>]*[A-Za-z0-9_\-]\.(?:" + "|".join(EXTS) +
    r"))(?![A-Za-z0-9])(?::(\d{1,5}))?")
# (?![A-Za-z0-9]) 收尾：否则 `aipd_state.sqlite` 会被 `.sql` 这个扩展名切成一条
# "aipd_state.sql 引用"——扩展名必须是**整个 token 的结尾**，不是某个后缀的前缀。
ELIDED = ("...", "…")
EXTERNAL_PREFIXES = ("ezdxf/", "cadquery/", "site-packages/", "urllib3/", "pytest/",
                     "odoo/", "addons/", "node_modules/", "usr/", "lib/python")

# 符号锚（第 103 片）：`路径::符号`，符号可带类限定 `AIPDStateDB.add_audit`。
# 为什么要它：`路径:123` 这种裸行钉只在**写下那一刻**是对的——文件一长，行号照样 ≤ 总行数，
# 现有那条 `line_beyond_eof` 就永远不开火（第 102 片实测：`docs/audit/v5.4/` 里钉
# `manual_chain.py:146/147/130-137` 的真身已到 `:193/:195/:134`，漂了约 47 行，四轮门禁全绿）。
# 符号锚把"指哪儿"写成身份而不是位置，文件怎么长都还指得回同一件事。
SYM_RE = re.compile(r"([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+)::([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)")
SYMBOL_KINDS = ("resolved", "symbol-resolved")
# 历史面不能改写，但可以**报**："这句散文点名的符号现在还在你写的行号上吗"。
# 认的是同一行里反引号包住的标识符（不含 `/`、不含扩展名），取第一个当候选。
HINT_RE = re.compile(r"`([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)`")
ROOTS = ("", "src", "src/aipd_os", "tests", "scripts", "docs", "docs/architecture",
         "references", "state_service", "openspec", ".github")

# 现状面：这些文档里的代码引用必须解析得到（判红档）。
LIVE = ("README.md", "SKILL.md")
LIVE_DIRS = ("docs/architecture", "docs/contracts", "references")
# 历史面：只报不判（当时的事实，改写等于篡改记录）。
HISTORY = ("CHANGELOG.md", "docs/audit")


def _is_history(rel: str) -> bool:
    return rel in HISTORY or any(rel.startswith(p + "/") for p in HISTORY)


def _is_live(rel: str) -> bool:
    if _is_history(rel):
        return False
    return rel in LIVE or any(rel.startswith(p + "/") for p in LIVE_DIRS)


def corpus(root: Path) -> list[Path]:
    out = [root / n for n in LIVE if (root / n).is_file()]
    for d in ("docs", "references", "openspec"):
        out += sorted((root / d).rglob("*.md"))
    if (root / "CHANGELOG.md").is_file():
        out.append(root / "CHANGELOG.md")
    return sorted({p for p in out if p.is_file()})


SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "releases"}
_index_cache: dict[str, list[str]] = {}


def _index(root: Path) -> list[str]:
    """整仓文件清单读一次就缓存：逐条引用去 rglob 会让常驻用例跑到分钟级（实测 100s）。"""
    key = str(root)
    if key not in _index_cache:
        _index_cache[key] = [
            str(f.relative_to(root)).replace("\\", "/")
            for f in root.rglob("*")
            if f.is_file() and not (set(f.relative_to(root).parts) & SKIP_DIRS)]
    return _index_cache[key]


def resolve(rel: str, root: Path) -> tuple[Path | None, int]:
    """解析 + 同名/后缀候选数（全在缓存清单上做子串匹配，不再触磁盘）。"""
    paths = _index(root)
    for r in ROOTS:
        cand = f"{r}/{rel}" if r else rel
        if cand in paths:
            return root / cand, 1
    needle = "/" + rel
    tail = [p for p in paths if p.endswith(needle) or p == rel]
    if len(tail) == 1:
        return root / tail[0], 1
    if tail:
        return None, len(tail)
    return None, 0


@dataclass
class Ref:
    doc: str
    target: str
    line: int | None
    klass: str
    detail: str = ""
    sym_hint: str = ""            # 同句里点名的符号（只用于 history 面的漂移档，不参与判红）

    def key(self) -> tuple[str, str, str]:
        return (self.doc, self.target, self.line or "")


def classify_line(line: str) -> str:
    """一行的语境：是命令示例，还是散文引用。"""
    s = line.lstrip()
    if s.startswith("aipd ") or s.startswith("$ ") or s.startswith("# aipd"):
        return "cli-operand"
    if re.search(r"--[A-Za-z][\w-]*\s+[\"']?$", line):
        return "cli-operand"
    return "prose"


def scan_doc(path: Path, root: Path) -> list[Ref]:
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(root))
    lines = text.splitlines()
    fence = False
    refs: list[Ref] = []
    for lineno, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue                       # 代码块内一律是示例/命令，不是出处引用
        ctx = classify_line(line)
        spans = [(m.start(), m.end()) for m in SYM_RE.finditer(line)]
        for m in SYM_RE.finditer(line):
            refs.append(_classify_symbol(rel, m.group(1), m.group(2), ctx, root))
        for m in REF_RE.finditer(line):
            if any(a <= m.start() < b for a, b in spans):
                continue                   # 这段路径已被 `路径::符号` 那条吃掉，不重复计一条
            target, line_ref = m.group(1), m.group(2)
            line_no = int(line_ref) if line_ref else None
            r = _classify(rel, target, line_no, ctx, root)
            if r.klass in ("missing", "line_beyond_eof", "bare-line-pin"):
                r.detail = f"{r.detail}（文档第 {lineno} 行）"
            if line_no is not None:
                hint = [h.group(1) for h in HINT_RE.finditer(line) if "/" not in h.group(1)]
                r.sym_hint = hint[0] if hint else ""
            refs.append(r)
    return refs


def _symbol_span(path: Path, symbol: str) -> tuple[int, int] | None:
    """返回符号在目标文件里的定义区间；取不到 ⇒ None（不可判或不存在，由调用方分档）。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parts = symbol.split(".")
    name = parts[-1]
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return None
        cands: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            lo = hi = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and node.name == name:
                lo, hi = node.lineno, node.end_lineno or node.lineno
                if len(parts) > 1:                       # 要求它嵌在 `类.` 里
                    owners = [c for c in ast.walk(tree)
                              if isinstance(c, ast.ClassDef) and c.name == parts[-2]
                              and any(x is node for x in ast.walk(c))]
                    if not owners:
                        lo = None
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        lo, hi = node.lineno, node.lineno
            if lo is not None:
                cands.append((lo, hi))
        return min(cands) if cands else None
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(rf"\b{re.escape(name)}\b", line):
            return i, i
    return None


def _classify_symbol(doc: str, target: str, symbol: str, ctx: str, root: Path) -> Ref:
    r = Ref(doc, f"{target}::{symbol}", None, "")
    if any(e in target for e in ELIDED) or target.startswith("./") or "<" in target:
        r.klass, r.detail = "elided", "省略写法 / 尖括号占位，没有可比对的字面路径"
        return r
    if target.startswith("/") or any(target.startswith(p) for p in EXTERNAL_PREFIXES):
        r.klass, r.detail = "external", "绝对路径或第三方包内路径"
        return r
    if ctx == "cli-operand":
        r.klass, r.detail = "cli-operand", "行语境是命令示例 ⇒ 操作数不是出处"
        return r
    p, n = resolve(target, root)
    if p is None:
        r.klass = "missing" if n == 0 else "multi"
        r.detail = ("符号锚的载体解析不到（全路径、后缀、同名三种解法都试完）"
                    if n == 0 else f"{n} 个候选，简写无法唯一定位")
        return r
    span = _symbol_span(p, symbol)
    if span is None:
        r.klass = "symbol-missing"
        r.detail = (f"{p.relative_to(root)} 里找不到符号 {symbol!r}"
                    "（改名/删掉了，或该文件语法不过而不可判）")
        return r
    r.klass = "symbol-resolved"
    r.detail = f"{p.relative_to(root)}:{span[0]}-{span[1]} ← {symbol}"
    return r


def _classify(doc: str, target: str, line_no: int | None, ctx: str,
              root: Path) -> Ref:
    r = Ref(doc, target, line_no, "")
    if any(e in target for e in ELIDED) or target.startswith("./") or "<" in target \
            or target.startswith("."):
        r.klass, r.detail = "elided", "省略写法 / 尖括号占位 / 裸后缀提法，没有可比对的字面路径"
        return r
    if target.startswith("/") or target.startswith("~") or target == "/tmp":
        r.klass, r.detail = "external", "绝对路径"
        return r
    if any(target.startswith(p) or ("/" + p) in target for p in EXTERNAL_PREFIXES):
        r.klass, r.detail = "external", "第三方/站点包内部路径"
        return r
    if ctx == "cli-operand":
        r.klass, r.detail = "cli-operand", "行语境是命令示例 ⇒ 操作数不是出处"
        return r
    p, n = resolve(target, root)
    if p is None:
        if n == 0:
            r.klass = "missing"
            r.detail = "本仓解析不到（全路径、后缀、同名三种解法都试完，一个都没有）"
        else:
            r.klass, r.detail = "multi", f"{n} 个候选，简写无法唯一定位"
        return r
    if line_no is None:
        r.klass, r.detail = "resolved", str(p.relative_to(root))
        return r
    n_lines = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    if line_no > n_lines:
        r.klass, r.detail = "line_beyond_eof", f"{p.relative_to(root)} 只有 {n_lines} 行"
    elif _is_live(doc):
        # 现状面只认符号锚：文件一变长，行号仍然"合法"，越界那条判据永远不开火（第 102 片实测
        # 漂了约 47 行而四轮门禁全绿）。历史面不判——那行号是**当时**的盘，改写等于篡改记录。
        r.klass, r.detail = "bare-line-pin", (
            f"{p.relative_to(root)}:{line_no} 是裸行钉 ⇒ 换成 {p.relative_to(root)}::符号")
    else:
        r.klass, r.detail = "resolved", f"{p.relative_to(root)}:{line_no}"
    return r


def _defect_sort_key(key: tuple) -> tuple:
    """给两档缺陷列表一个**全序**。

    `Ref.key()` 的第三元素两种形状混在一起：没写行号 ⇒ `""`，写了 ⇒ `int`。
    直接 `sorted()` 会在同一 (文档, 目标) 下拿 `""` 与 `455` 比大小而抛
    `TypeError: '<' not supported between instances of 'int' and 'str'`——
    第 81 片取证文档里既裸引又带行号引同一个仓外目标，整个普查连同它的 6 条
    常驻用例一起崩掉。崩在排序上不是"这条引用有问题"，是量具自己没牙口，
    所以修法是给序而不是降噪、也不改输出形状（`""` 与 `int` 照原样出）。
    """
    doc, target, line = key
    return (doc, target, -1 if line == "" else int(line))


def _drift_problem(drift: dict[str, int]) -> str:
    """漂移三档必须加和等于带行号引用数；不等 ⇒ 有引用在这一档上凭空消失/被计两遍。

    单独抽成函数（而不是写在 `audit()` 里的一行 `if`）：这条不变量在正常路径上不可能被破坏，
    所以"把调用点改掉"这种变异在真语料上不会有任何可观察差别（第 103 片电池 X3 就是这么活的）。
    可测的是**判据本身**，于是两极由 `--self-test` 直接喂不平衡/平衡两把字典来钉。
    """
    total = drift["ok"] + drift["suspect"] + drift["unhinted"]
    if total != drift["checked"]:
        return f"Σ 漂移档 {total} ≠ 带行号引用 {drift['checked']}"
    return ""


def audit(root: Path) -> dict[str, Any]:
    docs = corpus(root)
    if not docs:
        return {"ok": False, "problems": ["empty_corpus：一份文档都没读到，读数没有依据"],
                "refs": [], "buckets": {}, "live_defects": [], "history_defects": [],
                "docs": 0, "denominator": 0}
    refs: list[Ref] = []
    for d in docs:
        refs += scan_doc(d, root)

    buckets: dict[str, int] = {}
    for r in refs:
        buckets[r.klass] = buckets.get(r.klass, 0) + 1

    defect_kinds = ("missing", "line_beyond_eof", "bare-line-pin", "symbol-missing")
    live_defects = sorted({r.key() for r in refs
                           if r.klass in defect_kinds and _is_live(r.doc)},
                          key=_defect_sort_key)
    history_defects = sorted({r.key() for r in refs
                              if r.klass in defect_kinds and _is_history(r.doc)},
                             key=_defect_sort_key)
    # 漂移档（只报不判，第 103 片）：历史面的裸行钉不许改写，但可以问"这句点名的符号
    # 现在还在你写的行号上吗"。三档加和必须等于有行号的引用数（Σ 闭合在这一档上也成立）：
    # ok=还在区间内 / suspect=符号在但行号已离开它的区间 / unhinted=这句没点名符号（看不见，
    # 不折成 ok，也不折成 suspect）。
    drift = {"ok": 0, "suspect": 0, "unhinted": 0, "checked": 0}
    for r in refs:
        if r.line is None or r.klass in ("missing", "multi", "elided", "external",
                                         "cli-operand"):
            continue
        drift["checked"] += 1
        if not r.sym_hint:
            drift["unhinted"] += 1
            continue
        p, n = resolve(r.target, root)
        span = _symbol_span(p, r.sym_hint) if (p is not None and n == 1) else None
        if span is None:
            drift["unhinted"] += 1
        elif span[0] <= r.line <= span[1]:
            drift["ok"] += 1
        else:
            drift["suspect"] += 1
    problems: list[str] = []
    if sum(buckets.values()) != len(refs):
        problems.append("Σ 分类 ≠ 引用总数：有引用没被归类，判据分母漏了")
    drift_problem = _drift_problem(drift)
    if drift_problem:
        problems.append(drift_problem)
    if live_defects:
        problems.append(f"现状面 {len(live_defects)} 条代码引用指不回事实")
    return {
        "ok": not problems,
        "problems": problems,
        "docs": len(docs),
        "denominator": len(refs),
        "buckets": buckets,
        "live_defects": [list(k) for k in live_defects],
        "history_defects": [list(k) for k in history_defects],
        "drift": drift,
        "multi": sorted({r.doc for r in refs if r.klass == "multi"}),
        "refs": [{"doc": r.doc, "target": r.target, "line": r.line,
                  "klass": r.klass, "detail": r.detail} for r in refs],
    }


def render(rep: dict[str, Any]) -> str:
    lines = ["=" * 62, "文档代码引用普查（现状面判红，历史面只报）",
             f"文档 {rep['docs']} 份，代码引用 {rep['denominator']} 处", "=" * 62]
    for k in ("resolved", "symbol-resolved", "multi", "missing", "line_beyond_eof",
              "bare-line-pin", "symbol-missing",
              "cli-operand", "elided", "external"):
        if k in rep["buckets"]:
            lines.append(f"  [{k:16}] {rep['buckets'][k]}")
    d = rep.get("drift", {})
    lines.append(f"行钉漂移（只报不判）：带行号 {d.get('checked', 0)} 处 ⇒ "
                 f"还在符号区间 {d.get('ok', 0)}、已离开 {d.get('suspect', 0)}、"
                 f"这句没点名符号 {d.get('unhinted', 0)}")
    lines.append(f"现状面缺陷 {len(rep['live_defects'])} 条：" +
                 ("；".join(":".join(map(str, x)) for x in rep["live_defects"][:20]) or "无"))
    lines.append(f"历史面缺陷 {len(rep['history_defects'])} 条（只报不判）")
    if rep["problems"]:
        lines.append("读数不可信/现状面有缺陷：")
        lines += [f"  ! {p}" for p in rep["problems"]]
    return "\n".join(lines)


def _live_keys(rep: dict[str, Any]) -> set[str]:
    """把 `live_defects` 归一成字符串键。

    `Ref.key()` 的第三格两种形状混着：写了行号是 `int`、没写是 `""`。
    直接拿 `"40"` 去比会**永远不在**集合里（`40 != "40"`），那条断言就成了一只不开火的橡皮章
    ——第 103 片给现状面加档时撞出来的：旧那条「历史面缺陷不进现状判红」正是这样一直"绿"着。
    """
    return {f"{d}|{t}|{ln}" for d, t, ln in rep["live_defects"]}


def _self_test(tmp: Path) -> int:
    """合成语料：该红的必须红，该不红的必须不红。"""
    root = tmp / "repo"
    (root / "src" / "aipd_os").mkdir(parents=True)
    (root / "src" / "aipd_os" / "real.py").write_text("\n".join(f"# {i}" for i in range(30)),
                                                      encoding="utf-8")
    # 带真符号的文件：符号锚的两极（在/不在）与漂移档都要它
    (root / "src" / "aipd_os" / "mod.py").write_text(
        "def helper(a):\n    return a\n\nclass Widget:\n    def audit(self):\n        return 1\n",
        encoding="utf-8")
    (root / "README.md").write_text(
        "真引用 `src/aipd_os/real.py`\n"
        "带行号 `src/aipd_os/real.py:12`\n"
        "行号越界 `src/aipd_os/real.py:9999`\n"
        "符号锚 `src/aipd_os/mod.py::helper`\n"
        "类方法锚 `src/aipd_os/mod.py::Widget.audit`\n"
        "符号不存在 `src/aipd_os/mod.py::nope`\n"
        "不存在 `src/aipd_os/gone.py`\n"

        "简写歧义 `real.py` 与 `real.py:2`\n"
        "省略 `src/...py` 与 `.../real.py`\n"
        "后缀提法 `.py` 与 `<db>.manual.json` 不是引用\n"
        "数据库文件名 `aipd_state.sqlite` 这种 token 不该被切短成别的扩展名\n"
        "模块相对简写 `aipd_os/real.py`\n"
        "外部 `ezdxf/entities/polygon.py:212` 与绝对 `/tmp/x/real.py`\n"
        "命令操作数见代码块：\n"
        "```\n"
        "aipd release manifest --drawing out/bracket.dxf --bom BOM-1\n"
        '{"drawing": "cfg/nope.dxf", "script": "tools/nope.py"}\n'
        "```\n",
        encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "- 历史 `src/aipd_os/gone.py:40`\n"
        "- 历史钉还在 `src/aipd_os/mod.py:1` 上，点名叫 `helper`\n"
        "- 历史钉已漂走 `src/aipd_os/mod.py:6`，点名叫 `helper`\n",
        encoding="utf-8")

    rep = audit(root)
    d = rep["drift"]
    assert d["ok"] == 1 and d["suspect"] == 1, d
    assert d["checked"] == sum(v for k, v in d.items() if k != "checked"), d
    assert d["unhinted"] >= 1, d          # 那句没点名符号的历史引用不许被折进 ok/suspect
    by = {(r["doc"], r["target"], str(r["line"] or "")): r["klass"] for r in rep["refs"]}
    want = {
        ("README.md", "src/aipd_os/real.py", ""): "resolved",
        ("README.md", "src/aipd_os/real.py", "12"): "bare-line-pin",
        ("README.md", "src/aipd_os/real.py", "9999"): "line_beyond_eof",
        ("README.md", "src/aipd_os/mod.py::helper", ""): "symbol-resolved",
        ("README.md", "src/aipd_os/mod.py::Widget.audit", ""): "symbol-resolved",
        ("README.md", "src/aipd_os/mod.py::nope", ""): "symbol-missing",
        ("README.md", "src/aipd_os/gone.py", ""): "missing",
        ("README.md", "real.py", ""): "resolved",          # 唯一同名 ⇒ 简写算解析成功
        ("README.md", ".../real.py", ""): "elided",
        ("README.md", "ezdxf/entities/polygon.py", "212"): "external",
        ("README.md", "/tmp/x/real.py", ""): "external",
        ("CHANGELOG.md", "src/aipd_os/gone.py", "40"): "missing",
        ("CHANGELOG.md", "src/aipd_os/mod.py", "1"): "resolved",
        ("CHANGELOG.md", "src/aipd_os/mod.py", "6"): "resolved",
        ("README.md", "aipd_os/real.py", ""): "resolved",
    }
    # 占位/裸后缀允许被切出来，但必须落进 elided 档（不许进 missing/resolved）
    placeholder = [r["target"] for r in rep["refs"]
                   if r["target"].startswith(".") or "<" in r["target"]]
    bad_placeholder = [t for t, k in
                       ((r["target"], r["klass"]) for r in rep["refs"])
                       if (t.startswith(".") or "<" in t) and k != "elided"]
    sqlite = [r["target"] for r in rep["refs"] if "sqlite" in r["target"]
              or r["target"].endswith(".sql")]
    survived = []
    for k, want_klass in want.items():
        got = by.get(k)
        if got != want_klass:
            survived.append(f"{k} 期望 {want_klass}，实得 {got}")
    whole = [r["target"] for r in rep["refs"] if r["line"] == 212]
    for label, ok in (("占位与裸后缀全部落进 elided 档", bad_placeholder == []),
                      ("sqlite 这类 token 不被切短成 .sql 引用", sqlite == []),
                      ("占位/裸后缀确实被切到了（控制本身能开火）",
                       "<db>.manual.json" in placeholder),
                      ("模块相对简写按后缀唯一解析",
                       by.get(("README.md", "aipd_os/real.py", "")) == "resolved"),
                      ("外部路径只切出一段（防 dxf 这类扩展名吃掉前缀）",
                       whole == ["ezdxf/entities/polygon.py"]),
                      ("越界行号判红", by.get(("README.md", "src/aipd_os/real.py", "9999"))
                       == "line_beyond_eof"),
                      ("不存在路径判红", by.get(("README.md", "src/aipd_os/gone.py", ""))
                       == "missing"),
                      ("CLI 代码块内不出引用（含非 aipd 行，专打 fence 那一支）",
                       not any(r["target"].endswith(("bracket.dxf", "nope.dxf",
                                                     "tools/nope.py"))
                               for r in rep["refs"])),
                      ("历史面缺陷不进现状判红",
                       ("CHANGELOG.md", "src/aipd_os/gone.py", "40") not in _live_keys(rep)),
                      ("现状面缺陷判得出（五类各一条，写成集合而不是条数）",
                       _live_keys(rep) ==
                       {"README.md|src/aipd_os/real.py|12",
                        "README.md|src/aipd_os/real.py|9999",
                        "README.md|real.py|2",
                        "README.md|src/aipd_os/gone.py|",
                        "README.md|src/aipd_os/mod.py::nope|"}),
                      ("Σ 分类 == 分母", sum(rep["buckets"].values()) == rep["denominator"]),
                      ("Σ 漂移档两极各真（闭合时沉默、少一档时开火）",
                       _drift_problem({"ok": 1, "suspect": 1, "unhinted": 1, "checked": 3}) == ""
                       and _drift_problem({"ok": 1, "suspect": 0, "unhinted": 0,
                                           "checked": 5}).startswith("Σ"))):
        if not ok:
            survived.append(f"控制没立住：{label}")
        print(f"{'✓立住' if ok else '✗没立住'} {label}")
    if survived:
        print("没立住的判据：")
        for s in survived:
            print("  ", s)
        return 1
    print(f"--self-test：{len(want) + 10} 条合成读数全部对上")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="文档代码引用普查")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    rep = audit(root)
    print(render(rep))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return 0 if rep["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
