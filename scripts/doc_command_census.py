"""文档/登记表点名的 `aipd` 命令必须真的注册着（F-DOC-CMD 第 60 片）。

起因是第 59 片的一处实测事故：重写 `registry_data.py` 的能力行时，我在限制句里写了
一条**根本不存在的命令** `aipd truth show`（从 `truth drift`/`truth sweep` 的命名类推出来的），
而**没有任何常驻判据看得见它**——`capability_matrix.py` 只是把 `run_command` 原样渲染进 markdown。
本轮把它抓回来靠的是派出去的只读普查，不是机器。这一片补的就是那台机器。

权威面（本轮实测决定的，不是抄来的）：
- **不是** `COMMAND_FUNCS`。`aipd usage` 在派发表里查不到，却能跑（`cli/main.py:33` 注册 subparser、
  `_cmd_usage` 处理，实测 `main(["usage"])` 退 0 并打出命令清单）；
- 权威面是 `build_parser()` 走出来的 **argparse 声明树**（实测 88 条路径），
  `COMMAND_FUNCS` 是它的真子集（「派发表有而 parser 没有」为空）。CLI 契约里 10 条
  `deprecated` 别名**不再并进权威面**——第 60 片电池实测那是死代码（它们全部还注册在树上），
  改成一条活的前置：契约声称存在的命令必须还在树上（`alias_unregistered`）。

判据分两档，分档理由是本轮量过的假阳性面：
- **判红面（现状面）**＝这三处，语义都是"照着跑/这是真命令"，不存在
  "合法地指向一条不存在的命令"的用法：
  ① 登记表 `run_command` 字段里以 `aipd` 开头的每一段（AST 读常量，不靠 ±N 行窗口）；
  ② 文档里**行首**形如 `aipd …` 的可执行速查行（README / SKILL / QUICKSTART /
     `docs/architecture` / `docs/contracts` / `references`）；
  ③ 生产代码（`src/`、`scripts/`、`state_service/`）里的提及——代码写出来就是要跑的，
     第 60 片实测到 `ctq.py` 把一条不存在的命令烙进了**每条**产出记录，比文档里的错更贵。
     这一档带一条**否定例外**：同行有"没有/不存在/尚未…"时按只报处理，
     因为限制句「没有 `aipd X`」是合法写法。第 60 片立这条时的原件是登记表的
     「没有 `aipd ctq list`」，第 62 片把那条命令接上之后，真仓库里**已经没有**
     "带否定标记且指向未注册命令"的代码行——两档对照（把 `NEGATION_MARKERS`
     置空再 `audit(ROOT)`，看 `violations` 与 `corpus.code_negated`）今天不变判决，
     所以这条例外只由 `--self-test` 与常驻用例保持有牙，等下一个真缺口出现时才在实仓库开火。
     分母**不在本文抄**（抄一份就会漂——本轮就抓到自己的 docstring 抄了一份更早范围的读数）：
     现算值看 `--json` 的 `corpus.code_mentions / code_negated`，两个键非空由常驻用例
     `test_real_repo_clean_and_all_three_judging_faces_live` 钉下界。
- **只报面**＝其余一切正文里的 `aipd` 提及。它必须只报不红，因为正文会**合法地**提到
  不存在的命令：第 60 片实测的两处原件——registry 的限制句「没有 `aipd ctq list`」
  （第 62 片已把它接成主线命令）与 CHANGELOG/取证文档里我引用来记错的
  `aipd truth show`（至今未注册，是今天还在的活例）——都属于这一类；把它们判红，
  等于惩罚"把缺口与错误写下来"这件事，下一轮就会没人写。
  量具自己与它的用例（`SELF_STEMS`）**四档全部排除**（第 61 片补一致）：它们**必须**写着幻影命令
  才能证明判据会开火。第 60 片只在判红面 ③ 排了它们，只报面照收 ⇒ 它们写的
  `aipd ghost cmd` 这类**夹具名**会混进"正文点到未注册命令"的名单，
  **报表因此说谎**——读的人以为仓库里有这些缺口。
  去重按**提及**而不是按行（第 61 片补）：只有"被某档真的按名判过的那个名字"不再重复出现，
  同一行里**其他**提及仍要落进只报面。早先按行减会吃掉登记表同一物理行里
  `current_limitation` 等字段点名的命令——档 ① 只读 `run_command`、档 ③ 跳过 `REGISTRY_FILES`、
  只报面再按行减 ⇒ 那个名字**既不判也不报**。
  两处改动的**处数不在本文抄**（抄一份就会漂：本轮就把自己中间态的读数当成终态写进过
  CHANGELOG，被收尾验签器抓回）：机制与判决各由一条常驻用例钉住——
  按名去重见 `test_other_registry_fields_on_a_judged_line_are_still_reported`、
  不重复计数见 `test_report_only_face_counts_each_mention_once`、
  自指排除见 `test_the_instruments_own_files_are_out_of_all_four_faces`；
  真仓库的历史读数与逐档撤销的对照表在
  `docs/audit/DOC_COMMAND_CENSUS_F-DOC-CMD_2026-09-27.md` §九。

退码（与同族量具同形）：0 现状面干净；4 现状面有未注册命令；2 前提不成立
（权威面建不起来、判红面为空、或有文件解析失败——**空读数一律不当通过**）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache",
             "releases", "node_modules", "build", "dist"}
SUFFIXES = (".md", ".py", ".json", ".yaml", ".yml", ".txt", ".rst", ".sh")

# 判红面 ① 登记表文件（按 AST 取 run_command 常量）
REGISTRY_FILES = ("src/aipd_os/registry_data.py",
                  "scripts/product_capabilities_extra.py")
# 判红面 ② 行首速查行的所在文件/目录
QUICKREF_FILES = ("README.md", "SKILL.md", "QUICKSTART.md")
QUICKREF_DIRS = ("docs/architecture", "docs/contracts", "references")

# 判红面 ③ 生产代码里的提及。代码不像正文那样有权写"某命令不存在"——它写出来就是要跑的，
#   所以这里的幻影比文档里的更贵（第 60 片实测：`ctq.py` 把 `aipd truth ctq add` 烙进了
#   **每一条**产出的记录）。但同一行带否定标记时按只报处理：限制句那种
#   「没有 `aipd X`」是合法写法（立条原件与今天是否有原告见模块 docstring 档 ③ 一段）。
#   这条分档是量过假阳性才定的；
#   分母的现算值看 `--json` 的 corpus 两个键，本文不抄绝对数（抄一份就会漂）。
CODE_DIRS = ("src", "scripts", "state_service")
NEGATION_MARKERS = ("没有", "不存在", "尚未", "还没", "仍未", "刻意未", "仍未接",
                    "not registered", "no such", "does not exist")
# 量具与它的用例不许当分母：它们**必须**写着幻影命令才能证明判据会开火
SELF_STEMS = {"doc_command_census", "test_doc_command_census"}

# 只报面
REPORT_ONLY_FILES = ("CHANGELOG.md",)
# `.trae`（轮次 spec/checklist，第 61 片实测 46 处提及、21 个 md）与 `.github`（CI 定义，
# 今天 `aipd ` 命中 0）原先**不在任何一档的遍历面上**——而这两类文本恰恰是会被真的执行的
# （工程师/agent 照 spec 跑、runner 照 yml 跑）。先补进只报面拿到可见性；
# "spec 里的行内命令要不要升成第四档判红面"是裁决项，今天两向都是 0 幻影，
# 所以升不升都不改判决，只改"下一次谁先知道"。
REPORT_ONLY_DIRS = ("docs", "src", "tests", "scripts", "state_service", "templates",
                    "agents", "evals", ".trae", ".github")

# `aipd` 后面跟 1~2 个小写 token；负向后看断言避开 `aipd-os` / `aipd_os`，
# 大写与中文不匹配 ⇒ 自然避开 "aipd CLI"、"`aipd <命令>`" 这类非命令写法。
MENTION_RE = re.compile(
    r"(?<![A-Za-z0-9_.\-])aipd[ \t]+`?([a-z][a-z0-9_\-]*)"
    r"(?:[ \t]+`?([a-z][a-z0-9_\-]*))?"
)


def valid_commands() -> tuple[set[str], set[str], list[str]]:
    """(全部合法路径, 有子命令的组名, 前提问题)。

    权威面**永远取自本仓的 argparse 树**（`ROOT`），不跟着 `--repo` 走：普查别的语料时，
    "什么算存在的命令"这件事只能由被发布的代码回答。这也避免临时目录里的
    `src/aipd_os/` 遮蔽真包（命名空间包的解析顺序不是这里该赌的东西）。
    """
    src = ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    problems: list[str] = []
    try:
        import argparse as _ap

        from aipd_os.cli.main import build_parser  # type: ignore
    except Exception as exc:                              # noqa: BLE001
        return set(), set(), [f"authority_unimportable: {type(exc).__name__}: {exc}"]

    def walk(parser: Any, prefix: tuple[str, ...] = ()) -> set[str]:
        out: set[str] = set()
        for action in parser._actions:
            if isinstance(action, _ap._SubParsersAction):
                for name, sub in action.choices.items():
                    path = prefix + (name,)
                    out.add(" ".join(path))
                    out |= walk(sub, path)
        return out

    paths = walk(build_parser())
    try:
        from aipd_os.cli.command_contract import CommandStatus, get_all_commands  # type: ignore
        aliases = {e.name for e in get_all_commands()
                   if e.status is CommandStatus.DEPRECATED and e.name}
        # 第 60 片电池 B4 实测：把 deprecated 别名"并进权威面"**今天是死代码**——
        # 契约里那 10 个别名全部还注册在 argparse 声明树上（`aliases - paths` 为空集），
        # 撤掉这一步八条用例一条都不红。所以把它换成一条活的不变量：
        # 契约声称存在的命令必须还在树上，否则文档里照抄的别名写法会静默失效，
        # 而语料面只会显示"名字不认识"，看不见原因。
        for one in sorted(aliases - paths):
            problems.append(f"alias_unregistered: 契约里 deprecated 的命令 {one!r} "
                            "不在 argparse 声明树上（文档中的别名写法已失效）")
    except Exception as exc:                              # noqa: BLE001
        problems.append(f"contract_unreadable: {type(exc).__name__}: {exc}")
    groups = {p.split()[0] for p in paths if len(p.split()) > 1}
    if not paths:
        problems.append("authority_empty: argparse 声明树一条路径都没读到")
    return paths, groups, problems


def resolve(first: str, second: str | None, paths: set[str], groups: set[str]) -> str | None:
    """命中的写法解析到合法命令；解不出返回 None。

    规则刻意要求"给了第二段就必须落进那一段"：`aipd truth show` 里 `truth` 是个有子命令的组，
    所以 `show` 是**不存在的子命令**，不许退化成"`truth` 合法 ⇒ 整条合法"。
    """
    if second:
        two = f"{first} {second}"
        if two in paths:
            return two
        return None if first in groups else (first if first in paths else None)
    return first if first in paths else None


def _mentions(text: str) -> list[tuple[str | None, str]]:
    return [(m.group(1), m.group(2) or "") for m in MENTION_RE.finditer(text)]


def registry_run_commands(root: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """AST 取 `run_command` 字符串常量里的每一段 `aipd …` 写法。"""
    out: list[tuple[str, int, str]] = []
    problems: list[str] = []
    for rel in REGISTRY_FILES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"parse_failure: {rel}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "run_command"):
                    continue
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                for seg in value.value.split(" / "):
                    seg = seg.strip()
                    if seg.startswith("aipd"):
                        out.append((rel, value.lineno, seg))
    return out, problems


def quickref_lines(root: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """行首（可复制执行）的速查行：去掉 `#`/`-`/反引号/空白后以 `aipd ` 开头。"""
    out: list[tuple[str, int, str]] = []
    problems: list[str] = []
    targets = [root / rel for rel in QUICKREF_FILES if (root / rel).is_file()]
    for rel in QUICKREF_DIRS:
        base = root / rel
        if base.is_dir():
            targets += [f for f in sorted(base.rglob("*.md")) if f.is_file()]
    if not targets:
        problems.append("quickref_corpus_empty: 一个速查文件都没读到")
    for path in targets:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"unreadable: {path.relative_to(root)}: {exc}")
            continue
        for no, line in enumerate(lines, 1):
            body = line.strip().lstrip("#").strip()
            while body.startswith(("-", "*", "`")):
                body = body[1:].lstrip(" \t")
            if body.startswith("aipd ") or body.startswith("aipd\t"):
                out.append((str(path.relative_to(root)), no, body))
    return out, problems


def production_code_mentions(root: Path) -> tuple[list[tuple[str, int, str]],
                                                  list[tuple[str, int, str]],
                                                  list[str]]:
    """判红面 ③：生产代码里的提及；同行带否定标记的走只报。返回 (判红, 因否定而只报, 问题)。"""
    judged: list[tuple[str, int, str]] = []
    negated: list[tuple[str, int, str]] = []
    problems: list[str] = []
    for rel in CODE_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.stem in SELF_STEMS or "__pycache__" in path.parts:
                continue
            if str(path.relative_to(root)) in REGISTRY_FILES:
                continue        # 登记表整行由判红面 ① 按字段精判，这里不重复数
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"unreadable: {path.relative_to(root)}: {exc}")
                continue
            for no, line in enumerate(lines, 1):
                for first, second in _mentions(line):
                    seg = f"aipd {first}{(' ' + second) if second else ''}"
                    bucket = negated if any(k in line for k in NEGATION_MARKERS) else judged
                    bucket.append((str(path.relative_to(root)), no, seg))
    return judged, negated, problems


def prose_mentions(root: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """只报面：其余文本里的 `aipd …` 提及（正文会合法地提到不存在的命令，见模块 docstring）。"""
    out: list[tuple[str, int, str]] = []
    problems: list[str] = []
    files: list[Path] = [root / rel for rel in REPORT_ONLY_FILES if (root / rel).is_file()]
    for rel in REPORT_ONLY_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in SUFFIXES:
                if path.stem in SELF_STEMS or "__pycache__" in path.parts:
                    continue    # 量具与它的用例**四档全排除**：它们必须写幻影才能证明会开火
                files.append(path)
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for no, line in enumerate(lines, 1):
            for first, second in _mentions(line):
                out.append((str(path.relative_to(root)), no,
                            f"aipd {first}{(' ' + second) if second else ''}"))
    return out, problems


def audit(root: Path) -> dict[str, Any]:
    paths, groups, problems = valid_commands()
    judged: list[tuple[str, int, str, str]] = []      # (field, 文件, 行, 写法)
    # 去重键是**提及**而不是**行**：按行减会把同一行里没被判过的名字一起吞掉——
    # 登记表一条记录常写在一个物理行内，档 ① 只读 run_command、档 ③ 跳过 REGISTRY_FILES，
    # 于是"同一行另一个字段里点名的命令"既不判也不报（第 60 片的双重盲，第 61 片补）。
    seen_names: set[tuple[str, int, str]] = set()
    verdicts: dict[str, str] = {}

    reg, p1 = registry_run_commands(root)
    quick, p2 = quickref_lines(root)
    code, code_neg, p4 = production_code_mentions(root)
    prose, p3 = prose_mentions(root)
    problems += p1 + p2 + p3 + p4

    def record(kind: str, rel: str, no: int, seg: str) -> None:
        for first, second in _mentions(seg):
            name = f"aipd {first}{(' ' + second) if second else ''}"
            seen_names.add((rel, no, name))
            hit = resolve(first, second or None, paths, groups)
            key = f"{kind}|{rel}:{no}|{first} {second}".strip()
            verdicts[key] = hit or "UNMATCHED"
            if hit is None:
                judged.append((kind, rel, no, name))

    for rel, no, seg in reg:
        record("run_command", rel, no, seg)
    for rel, no, seg in quick:
        record("quickref", rel, no, seg)
    for rel, no, seg in code:
        record("code", rel, no, seg)

    # 只报面 = 全量扫描里**未被按名判过**的提及，再补上"代码里带否定标记"那批中
    # 尚未被全量扫描覆盖的（今天 `CODE_DIRS ⊂ REPORT_ONLY_DIRS` 都含 src，五条全已被覆盖 ⇒
    # 补集为空；第 60 片写成 `+ code_neg` 是把它们数了两遍，report_only 因此恒多 5）。
    # 去重是必须的：docs/architecture 与 src/ 同时落在两档的目录清单里，
    # 不去重的话 Σ 分桶 > 总数，"分桶等于分母"这条自证就成了一句空话。
    kept = [r for r in prose if r not in seen_names]
    have = set(kept)
    report_rows = kept + [r for r in code_neg if r not in have]

    report_bad = []
    for rel, no, seg in report_rows:
        first, second = _mentions(seg)[0]
        if resolve(first, second or None, paths, groups) is None:
            report_bad.append((rel, no, seg))

    if not (reg and quick and code):
        problems.append(f"judging_face_empty: run_command 段 {len(reg)}、速查行 {len(quick)}、"
                        f"代码提及 {len(code)}（判红面任一档空读都不算绿）")
    ok = not judged and not problems
    return {
        "ok": ok,
        "authority_paths": len(paths),
        "authority_groups": len(groups),
        "corpus": {"run_command_segments": len(reg), "quickref_lines": len(quick),
                   "code_mentions": len(code), "code_negated": len(code_neg),
                   "prose_mentions": len(prose), "report_only_mentions": len(report_rows)},
        "violations": [{"field": f, "doc": d, "line": n, "written": w}
                       for f, d, n, w in judged],
        "report_only_unmatched": [{"doc": d, "line": n, "written": w}
                                  for d, n, w in report_bad],
        "problems": problems,
    }


def render(rep: dict[str, Any]) -> str:
    lines = ["=" * 60, "文档命令名对账（现状面判红，正文只报）", "=" * 60]
    lines.append(f"权威面：{rep['authority_paths']} 条 argparse 路径"
                 "（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），"
                 f"{rep['authority_groups']} 个组名")
    c = rep["corpus"]
    lines.append(f"判红面语料：run_command {c['run_command_segments']} 段 / "
                 f"速查行 {c['quickref_lines']} 行 / 生产代码 {c['code_mentions']} 处"
                 f"（另有 {c['code_negated']} 处同行带否定标记 ⇒ 只报）")
    lines.append(f"只报面 {c['report_only_mentions']} 处（全量扫描 {c['prose_mentions']} 处，"
                 "减去三档判红面覆盖的行）")
    for v in rep["violations"]:
        lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} 写了 `{v['written']}`"
                     " ⇒ 权威面上没有这条命令")
    for p in rep["problems"]:
        lines.append(f"  ! 前提不成立：{p}")
    if rep["report_only_unmatched"]:
        uniq: dict[str, list[str]] = {}
        for r in rep["report_only_unmatched"]:
            uniq.setdefault(r["written"], []).append(f"{r['doc']}:{r['line']}")
        lines.append(f"  · 只报面（不判红）里点到未注册的命令 {len(uniq)} 个名字："
                     + "；".join(f"{k}（{len(v)} 处）" for k, v in sorted(uniq.items())))
    if not rep["violations"] and not rep["problems"]:
        lines.append("现状面缺陷 0 条：文档与登记表点名的命令都注册着")
    return "\n".join(lines)


def _mark(marks: list, text: str) -> None:
    """打一条开火读数并把它计入分母——末行的"几条"由这里现数，不靠我抄。"""
    print("✓立住 " + text)
    marks.append(text)


def _self_test(tmp: Path) -> int:
    """合成语料：判红面必须抓到假命令、放过真命令；只报面不许判红。"""
    marks: list[str] = []
    paths, groups, problems = valid_commands()
    if problems or not paths:
        print(f"--self-test 前提不成立：{problems}")
        return 2
    # 夹具幻影名一律带 `zzz-` 前缀，且**不写死将来可能被注册的名字**：第 60/61 片两处写的
    # 是 `ctq list`，第 62 片把 `aipd ctq list` 注册成主线命令的那一轮，自测与常驻用例
    # 一起崩（"仍然没有"的夹具读成了合法名）。`zzz-` 不进产品命名空间。
    # 两个名字各司一职，且**不许同名**：ghost_bad 注入三档判红面，ghost_prose 只出现在
    # "记录缺口"的写法里。同名时"只报面不判红"那条断言会被判红面上的同名违规先判红，
    # 于是否定豁免失效与别档开火混成一条读数，分不清是哪一档没牙。
    ghost_bad = "ctq zzz-phantom"
    ghost_prose = "ctq zzz-unlisted"
    for probe, want in (("ctq add", True), ("usage", True), ("truth", True),
                        (ghost_bad, False), (ghost_prose, False),
                        ("zzzghostcmd zzz", False)):
        got = resolve(probe.split()[0], probe.split()[1] if " " in probe else None,
                      paths, groups)
        assert (got is not None) is want, (probe, got, want)
    assert "ctq" in groups, "夹具前提：ctq 必须是组（'组存在而子命令不存在'的形状）"
    _mark(marks, f"权威面按 parser 树判定（{len(paths)} 条路径；`usage` 算存在，"
                 f"`{ghost_bad}`/`{ghost_prose}` 这类组内假子命令与顶层不存在的 "
                 f"`zzzghostcmd zzz` 都不算）")

    (tmp / "README.md").write_text(
        "# t\naipd ctq add --db x --project p\naipd " + ghost_bad + " --db x\n"
        "运行 `aipd usage` 列出全部命令\naipd <命令> --help\naipd-os 与 aipd_os 不算\n",
        encoding="utf-8")
    (tmp / "src/aipd_os").mkdir(parents=True, exist_ok=True)
    (tmp / "src/aipd_os/registry_data.py").write_text(
        'CAPABILITIES = [{"id": "a", "run_command": "aipd ctq revise --db x / '
        'aipd ' + ghost_bad + '"},\n {"id": "b", "run_command": "aipd drawing spec --db x"}]\n',
        encoding="utf-8")
    (tmp / "src/aipd_os" / "handlers.py").write_text(
        'NOTE = "declared via aipd ' + ghost_prose + '"   # 本轮实测：这条命令仍然没有\n'
        'BAD = "先跑 aipd ' + ghost_bad + ' 再看"\n'
        'GOOD = "先跑 aipd ctq add 再看"\n', encoding="utf-8")
    (tmp / "docs").mkdir(exist_ok=True)
    (tmp / "docs/audit").mkdir(exist_ok=True)
    (tmp / "docs/audit/x.md").write_text("本轮实测：库里 `aipd " + ghost_prose + "` 仍然没有\n",
                                         encoding="utf-8")
    saved = (REGISTRY_FILES, QUICKREF_FILES, QUICKREF_DIRS,
             REPORT_ONLY_FILES, REPORT_ONLY_DIRS, CODE_DIRS)
    globals_ = globals()
    globals_["REGISTRY_FILES"] = ("src/aipd_os/registry_data.py",)
    globals_["QUICKREF_FILES"] = ("README.md",)
    globals_["QUICKREF_DIRS"] = ()
    globals_["REPORT_ONLY_FILES"] = ()
    globals_["REPORT_ONLY_DIRS"] = ("docs", "src")
    globals_["CODE_DIRS"] = ("src",)
    try:
        rep = audit(tmp)
    finally:
        (globals_["REGISTRY_FILES"], globals_["QUICKREF_FILES"], globals_["QUICKREF_DIRS"],
         globals_["REPORT_ONLY_FILES"], globals_["REPORT_ONLY_DIRS"],
         globals_["CODE_DIRS"]) = saved
    bad = {(v["written"], v["field"]) for v in rep["violations"]}
    expect = {(f"aipd {ghost_bad}", "quickref"), (f"aipd {ghost_bad}", "run_command"),
              (f"aipd {ghost_bad}", "code")}
    assert bad == expect, (sorted(bad), sorted(expect))
    _mark(marks, "三档判红面各抓到一条注入的假命令（速查行、run_command 段、生产代码）")
    assert not any("aipd ctq add" in b or "aipd usage" in b or "aipd drawing spec" in b
                   for b, _f in bad), bad
    _mark(marks, "真命令与占位符/`aipd-os` 一律不开火（反证：合规侧同批存在）")
    assert (f"aipd {ghost_prose}", "code") not in bad, bad
    assert rep["corpus"]["code_negated"] >= 1, rep["corpus"]
    _mark(marks, "生产代码里带否定标记的那行不判红（登记表的限制句就是这种写法）")
    prose_bad = {r["written"] for r in rep["report_only_unmatched"]}
    assert f"aipd {ghost_prose}" in prose_bad and not any(
        r["written"] == f"aipd {ghost_prose}" for r in rep["violations"]), rep
    _mark(marks, f"只报面记名而不判红（正文里合法写出的「没有 aipd {ghost_prose}」）")
    assert rep["ok"] is False, rep
    assert rep["corpus"]["run_command_segments"] == 3, rep["corpus"]
    assert rep["corpus"]["quickref_lines"] == 3, rep["corpus"]
    assert rep["corpus"]["code_mentions"] == 2, rep["corpus"]
    _mark(marks, "分母自报且与语料一致（run_command 3 段、速查行 3 行、代码 2 处）")
    assert main(["--repo", str(tmp)]) == 4
    empty = tmp / "empty"
    (empty / "src/aipd_os").mkdir(parents=True)
    (empty / "src/aipd_os/registry_data.py").write_text("CAPABILITIES = []\n",
                                                        encoding="utf-8")
    assert main(["--repo", str(empty)]) == 2, "判红面为空必须判前提不成立"
    _mark(marks, "空语料读成「前提不成立」（退 2），不是「零违规」")
    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="文档/登记表命令名对账")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--json", default="", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    rep = audit(root)
    print(render(rep))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    if rep["problems"]:
        return 2
    return 4 if rep["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
