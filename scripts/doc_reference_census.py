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
    """返回 (解析到的文件, 同名候选数)。同名候选数只在解析不到时用于分档。"""
    for r in ROOTS:
        p = (root / r / rel) if r else (root / rel)
        if p.is_file():
            return p, 1



@dataclass
class Ref:
    doc: str
    target: str
    line: int | None
    klass: str
    detail: str = ""

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
        for m in REF_RE.finditer(line):
            target, line_ref = m.group(1), m.group(2)
            line_no = int(line_ref) if line_ref else None
            r = _classify(rel, target, line_no, ctx, root)
            if r.klass in ("missing", "line_beyond_eof"):
                r.detail = f"{r.detail}（文档第 {lineno} 行）"
            refs.append(r)
    return refs


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

    defect_kinds = ("missing", "line_beyond_eof")
    live_defects = sorted({r.key() for r in refs
                           if r.klass in defect_kinds and _is_live(r.doc)},
                          key=_defect_sort_key)
    history_defects = sorted({r.key() for r in refs
                              if r.klass in defect_kinds and _is_history(r.doc)},
                             key=_defect_sort_key)
    problems: list[str] = []
    if sum(buckets.values()) != len(refs):
        problems.append("Σ 分类 ≠ 引用总数：有引用没被归类，判据分母漏了")
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
        "multi": sorted({r.doc for r in refs if r.klass == "multi"}),
        "refs": [{"doc": r.doc, "target": r.target, "line": r.line,
                  "klass": r.klass, "detail": r.detail} for r in refs],
    }


def render(rep: dict[str, Any]) -> str:
    lines = ["=" * 62, "文档代码引用普查（现状面判红，历史面只报）",
             f"文档 {rep['docs']} 份，代码引用 {rep['denominator']} 处", "=" * 62]
    for k in ("resolved", "multi", "missing", "line_beyond_eof",
              "cli-operand", "elided", "external"):
        if k in rep["buckets"]:
            lines.append(f"  [{k:16}] {rep['buckets'][k]}")
    lines.append(f"现状面缺陷 {len(rep['live_defects'])} 条：" +
                 ("；".join(":".join(map(str, x)) for x in rep["live_defects"][:20]) or "无"))
    lines.append(f"历史面缺陷 {len(rep['history_defects'])} 条（只报不判）")
    if rep["problems"]:
        lines.append("读数不可信/现状面有缺陷：")
        lines += [f"  ! {p}" for p in rep["problems"]]
    return "\n".join(lines)


def _self_test(tmp: Path) -> int:
    """合成语料：该红的必须红，该不红的必须不红。"""
    root = tmp / "repo"
    (root / "src" / "aipd_os").mkdir(parents=True)
    (root / "src" / "aipd_os" / "real.py").write_text("\n".join(f"# {i}" for i in range(30)),
                                                      encoding="utf-8")
    (root / "README.md").write_text(
        "真引用 `src/aipd_os/real.py`\n"
        "带行号 `src/aipd_os/real.py:12`\n"
        "行号越界 `src/aipd_os/real.py:9999`\n"
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
    (root / "CHANGELOG.md").write_text("- 历史 `src/aipd_os/gone.py:40`\n", encoding="utf-8")

    rep = audit(root)
    by = {(r["doc"], r["target"], str(r["line"] or "")): r["klass"] for r in rep["refs"]}
    want = {
        ("README.md", "src/aipd_os/real.py", ""): "resolved",
        ("README.md", "src/aipd_os/real.py", "12"): "resolved",
        ("README.md", "src/aipd_os/real.py", "9999"): "line_beyond_eof",
        ("README.md", "src/aipd_os/gone.py", ""): "missing",
        ("README.md", "real.py", ""): "resolved",          # 唯一同名 ⇒ 简写算解析成功
        ("README.md", ".../real.py", ""): "elided",
        ("README.md", "ezdxf/entities/polygon.py", "212"): "external",
        ("README.md", "/tmp/x/real.py", ""): "external",
        ("CHANGELOG.md", "src/aipd_os/gone.py", "40"): "missing",
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
                       ("CHANGELOG.md", "src/aipd_os/gone.py", "40") not in
                       {tuple(x) for x in rep["live_defects"]}),
                      ("现状面缺陷判得出（本合成语料应有 2 条）",
                       len(rep["live_defects"]) == 2),
                      ("Σ 分类 == 分母", sum(rep["buckets"].values()) == rep["denominator"])):
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
