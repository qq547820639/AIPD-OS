"""文档/登记表点名的 `aipd` 命令必须真的注册着（F-DOC-CMD 第 60 片）。

起因是第 59 片的一处实测事故：重写 `registry_data.py` 的能力行时，我在限制句里写了
一条**根本不存在的命令** `aipd truth show`（从 `truth drift`/`truth sweep` 的命名类推出来的），
而**没有任何常驻判据看得见它**——`capability_matrix.py` 只是把 `run_command` 原样渲染进 markdown。
本轮把它抓回来靠的是派出去的只读普查，不是机器。这一片补的就是那台机器。

权威面（本轮实测决定的，不是抄来的）：
- **不是** `COMMAND_FUNCS`。`aipd usage` 在派发表里查不到，却能跑（`cli/main.py:33` 注册 subparser、
  `_cmd_usage` 处理，实测 `main(["usage"])` 退 0 并打出命令清单）；
- 权威面是 `build_parser()` 走出来的 **argparse 声明树**（条数由 `--json` 的
  `authority_paths` 现读，本文不抄），
  `COMMAND_FUNCS` 是它的真子集（「派发表有而 parser 没有」为空）。CLI 契约里 10 条
  `deprecated` 别名**不再并进权威面**——第 60 片电池实测那是死代码（它们全部还注册在树上），
  改成一条活的前置：契约声称存在的命令必须还在树上（`alias_unregistered`）。

判据分两档，分档理由是本轮量过的假阳性面：
- **判红面（现状面）**＝下面编号 ①②②b③④⑤ 这几处（第 87 片加了 ⑤），语义都是"照着跑/这是真命令"，不存在
  "合法地指向一条不存在的命令"的用法：
  ① 登记表 `run_command` 字段里以 `aipd` 开头的每一段（AST 读常量，不靠 ±N 行窗口）；
  ② 文档里**行首**形如 `aipd …` 的可执行速查行（README / SKILL / QUICKSTART /
     `docs/architecture` / `docs/contracts` / `references`）；
     ②b 同一份速查语料上的**断续行**（第 82 片）：一行以 `\\` 收尾、下一行却另起一条
     `aipd` 命令 ⇒ 照抄只会跑到半条命令。这一格判的是"能不能照抄"，不是"名字存不存在"，
     所以它不走 `record()` 的名字去重，直接进 `violations`（field 写「续行」）；
     语料与 ② 同一份遍历（`quickref_corpus`），两档各走一遍迟早漂出两种"看得见"。
     真仓库今天 **0** 处，而必开火夹具取自 `git show 3784a0a:README.md` 的逐字原件——
     "0"与"看不见"的区别就在这条夹具上（见 `tests/test_doc_command_census.py`）。
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
  ④ 文档里**行首**的 `python scripts/X.py …`（第 85 片）：脚本必须存在，且行内 `--旗子`
     必须在它自己的 argparse 声明里（AST 读，不跑 `--help`——拿执行结果当权威就是把待证的
     东西当用了）。旗子集合静态不封闭（`add_argument(*NAMES)`）的脚本**不判**，
     只进 `corpus.script_rows_unbounded`。立档前量过真语料，并当场抓出 1 处真缺陷
     （`references/cad-runtime-acceptance.md` 的 `--require-cad`，脚本只认 `--require-any-cad`）。
  ⑤ 文档里 `<解释器> 路径.py|.sh` 形态的**复算入口**（第 87 片）：五档归属
     `tracked / untracked / dead / delegated / placeholder`，前两档之外的死链必须出现在
     `docs/audit/RECOMPUTE_ENTRYPOINT_REGISTER.json`，否则判红；登记册还要双向对账
     （条目"现在能解析了"或"再没被引用"都算「登记册该撤」）。语料含 `docs/audit/`——
     历轮取证文档的复算入口小节就是案发现场，排除它判据就只剩象征意义。
     `scripts/…` 交给面 ④，这里只数不判（一个缺陷记两笔红会把半径读歪）。
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

第 75 片把只报面拆成两桶（**当时**的读数是：全量扫描 1389 处提及里 1012 处、即 73% 属于记录面；
今天的对应键是 `corpus.report_total_mentions / report_record_mentions`，别在这里抄数）：
``live`` = 现在还有人在照它敲的文本（src / scripts / templates / docs/architecture / .github / …），
``record`` = 记当时事实的文本（``CHANGELOG.md``、``docs/audit/``、``tests/``、``.trae/``）。
**可行动清单（``report_only_unmatched``）只从 live 出**——拆之前那张名单长期被"当初为什么这么判"
的记录与测试里**故意写的幻影名**（``aipd ctq zzz-listy`` 那类是为了证明判据会开火才写的）占满，
拆之后它是空表，于是"live 文本里不许出现未注册命令"第一次成为可钉的不变量。
两桶都可见（record 的名字与位点在 ``report_record_unmatched`` 里照列），只是都不判红；
每类记录文本还必须真的贡献过内容（``record_bucket_empty``，仅对本仓核对），
否则说明名单与语料脱了钩。

退码（与同族量具同形）：0 现状面干净；4 现状面有未注册命令；2 前提不成立
（权威面建不起来、判红面为空、或有文件解析失败——**空读数一律不当通过**）。
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import subprocess
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

# ---------------------------------------------------------------------------
# 只报面再分两半（第 75 片，占比是现读的，不是猜的）：
#   live   = 现在还有人在照它敲的地方（src / scripts / templates / docs/architecture / …）
#   record = 记当时事实的文本（`CHANGELOG.md`、`docs/audit/`、`tests/`、`.trae/`）
# 第 75 片实测本仓：全量扫描 1389 处提及里，docs/audit 820 + tests 65 + .trae 46 + CHANGELOG 81
# = **1012 处（73%）**落在 record。把它们和 live 混在一个"只报面 1059 处"里，
# 结果就是可行动清单（未命中名）长期被"当初为什么这么判"的记录与测试里的**故意幻影名**占满
# ——`aipd ctq zzz-listy` 那类名字本来就是为了让判据开火才写的。
RECORD_FILES = ("CHANGELOG.md",)
RECORD_DIR_PREFIXES = ("docs/audit", "tests", ".trae")


def is_record_path(rel: str) -> bool:
    """这条提及是不是"记录性引述"（只数不列名）。"""
    norm = rel.replace("\\", "/")
    if norm in RECORD_FILES:
        return True
    return any(norm == pre or norm.startswith(pre + "/") for pre in RECORD_DIR_PREFIXES)


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


def quickref_corpus(root: Path) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """速查语料的**同一份遍历**（相对路径 + 行）。判红面 ② 与"续行断裂"那一格共用。

    分两次各走一遍是本项目记过的老坑：两次的排除档一漂，同一份文件就出现"一档看得见、
    一档看不见"的读数。所以新格一律从这里取语料，不许自己 rglob。
    """
    targets = [root / rel for rel in QUICKREF_FILES if (root / rel).is_file()]
    for rel in QUICKREF_DIRS:
        base = root / rel
        if base.is_dir():
            targets += [f for f in sorted(base.rglob("*.md")) if f.is_file()]
    out: list[tuple[str, list[str]]] = []
    problems: list[str] = []
    for path in targets:
        try:
            out.append((str(path.relative_to(root)),
                        path.read_text(encoding="utf-8").splitlines()))
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"unreadable: {path.relative_to(root)}: {exc}")
    if not out:
        problems.append("quickref_corpus_empty: 一个速查文件都没读到")
    return out, problems


def _quick_body(line: str) -> str:
    """速查行的"正文形状"：去掉行首注释符、列表符、反引号与缩进。"""
    body = line.strip().lstrip("#").strip()
    while body.startswith(("-", "*", "`")):
        body = body[1:].lstrip(" \t")
    return body


def continuation_breaks(root: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """判红面 ②b（第 82 片）：以 `\\` 收尾的那一行，下一行却是**另一条** `aipd` 命令。

    照抄的人只会跑到半条命令——第 81 片修掉的真实事故就是这个形状：
    `git show 3784a0a:README.md:271` 以 `\\` 收尾，`:272` 是另一条
    `aipd drawing assembly-steps …`，于是"上一行的续行反斜杠直接接了另一条命令"。
    这一格**不判**"以 `\\` 收尾"本身（合法续行的下一行是旗子或参数，
    今天 README:274→275 的 `  --db state.db --bom BOM-1` 就是合规侧），
    只判"下一行以 `aipd ` 开头"。语料与判红面 ② 同一份遍历。
    """
    files, problems = quickref_corpus(root)
    out: list[tuple[str, int, str]] = []
    for rel, lines in files:
        for idx in range(len(lines) - 1):
            if (lines[idx].rstrip().endswith("\\")
                    and _quick_body(lines[idx + 1]).startswith("aipd ")):
                out.append((rel, idx + 1, lines[idx].rstrip()))
    return out, problems


def quickref_lines(root: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """行首（可复制执行）的速查行：去掉 `#`/`-`/反引号/空白后以 `aipd ` 开头。"""
    files, problems = quickref_corpus(root)
    out: list[tuple[str, int, str]] = []
    for rel, lines in files:
        for no, line in enumerate(lines, 1):
            body = _quick_body(line)
            if body.startswith("aipd ") or body.startswith("aipd\t"):
                out.append((rel, no, body))
    return out, problems


SCRIPT_ROW_RE = re.compile(r"^python(?:3)? scripts/([A-Za-z0-9_]+)\.py(.*)$")


def script_arg_flags(path: Path) -> tuple[set[str], bool]:
    """AST 取一个脚本 argparse 声明的全部长旗子；第二个返回值＝这个集合是否静态封闭。

    出现 `add_argument(*names)`、`add_argument(var)`、f-string 之类第一实参不是字面量的
    声明时返回 False。**那种脚本一律不判**：读不到全集就把"我没见到"当成"它不存在"，
    是本项目反复记过的假红形状（缺席与看不见的分别）。
    """
    flags: set[str] = set()
    bounded = True
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set(), False
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"):
            continue
        if not n.args:
            bounded = False
            continue
        first = n.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if first.value.startswith("--"):
                flags.add(first.value.split("=", 1)[0])
            continue
        bounded = False
    return flags, bounded


def script_rows(root: Path) -> tuple[list[tuple[str, int, str, list[str]]],
                                     list[str], list[str]]:
    r"""判红面 ④（第 85 片）：文档里行首的 `python scripts/X.py …` 必须真能照着跑。

    第 60 片立这把尺时只覆盖了 `aipd …` 那一面，理由是"那才是产品命令面"；
    但 README 量具目录与 `references/` 里写的是**另一种**照着敲的形状
    （`python scripts/closeout_verifier.py --tag …`），今天一条都不判。
    本轮先量分母：真仓库 4 行、涉及 4 个脚本，其中 **1 行是假话**——
    `references/cad-runtime-acceptance.md:6` 写 `--require-cad`，
    而 `runtime_preflight.py` 只声明 `--require-any-cad`（实跑 rc=2
    `unrecognized arguments: --require-cad`）。所以这一格不是橡皮章。

    语料走 `quickref_corpus` 的**同一份遍历**（判红面 ② 与续行那格也从这里取），
    并在这里把行尾 `\` 的续行折回一行——否则只看得到半条命令，
    而 README 的合规形状（`--tag v5.6.0` 换行 `--expect-test …`）会被读成"没有那个旗子"。
    """
    files, problems = quickref_corpus(root)
    out: list[tuple[str, int, str, list[str]]] = []
    unbounded: list[str] = []
    cache: dict[str, tuple[set[str], bool] | None] = {}
    for rel, lines in files:
        merged: list[tuple[int, str]] = []
        pend_no: int | None = None
        pend = ""
        for no, raw in enumerate(lines, 1):
            body = _quick_body(raw)
            if pend_no is None:
                pend_no, pend = no, body
            else:
                pend = pend.rstrip() + " " + body
            if pend.rstrip().endswith("\\"):
                pend = pend.rstrip()[:-1]
                continue
            merged.append((pend_no, pend))
            pend_no, pend = None, ""
        if pend_no is not None:
            merged.append((pend_no, pend))
        for no, body in merged:
            m = SCRIPT_ROW_RE.match(body.rstrip())
            if not m:
                continue
            stem, rest = m.group(1), m.group(2)
            used = sorted(set(re.findall(r"--[A-Za-z][A-Za-z0-9-]*", rest)))
            out.append((rel, no, stem, used))
            if stem not in cache:
                path = root / "scripts" / f"{stem}.py"
                cache[stem] = None if not path.is_file() else script_arg_flags(path)
            got = cache[stem]
            if got is not None and not got[1] and stem not in unbounded:
                unbounded.append(stem)
    return out, unbounded, problems


ENTRY_INTERP = r"(?:\.venv/bin/python|python3?|bash|sh|zsh)"
# 前缀用"否定型 lookbehind"而不是固定字符类：中文文档里这条常写成
# 「复算入口：bash x.sh」「跑 `python foo.py`」，只列 ASCII 空白/反引号/竖线会把
# 全角冒号后面的那些整批漏掉——一种拼写≠全部形态（第 78 片记过的文本面病）。
ENTRY_LINE_RE = re.compile(r"(?<![A-Za-z0-9_./-])" + ENTRY_INTERP +
                           r"\s+([A-Za-z0-9_./-]+\.(?:py|sh))\b")
# 模板/区间/变量形态不是"给人照抄的具体命令"：写了 X.py、sNN、`..`、尖括号、通配、
# `${VAR}` 的都走**不判**，单列读数。第 85 片量分母时 README:508 那行
# `python scripts/X.py` 就是这种形状——把它判红等于让尺子咬自己：
# 那一行正是在描述本判据的占位写法。
ENTRY_PLACEHOLDER_RE = re.compile(r"(?:X\.(?:py|sh)$|NN|\.\.|…|[<>{}*]|\$\{|s\d+\.\.s)")
ENTRY_FILES = ("README.md", "SKILL.md", "QUICKSTART.md")
ENTRY_DIRS = ("docs", "references")
ENTRY_REGISTER_REL = "docs/audit/RECOMPUTE_ENTRYPOINT_REGISTER.json"


def entry_corpus(root: Path) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """面 ⑤ 的语料：入口清单 + `docs/**` + `references/**` 的 `.md`。

    与 `quickref_corpus` 唯一的差别是这里**必须含 `docs/audit/`**：
    历轮取证文档的「复算入口」小节就是死链集中地（本轮实测 122 处引用指向
    从没入库的 `tmp/` 工件），把案发现场排除在外，判据就只剩象征意义。
    """
    files: list[tuple[str, list[str]]] = []
    problems: list[str] = []
    for rel in ENTRY_FILES:
        p = root / rel
        if not p.is_file():
            continue
        try:
            files.append((rel, p.read_text(encoding="utf-8").splitlines()))
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"entry_corpus_unreadable: {rel} 读不出：{exc}")
    for d in ENTRY_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            try:
                files.append((p.relative_to(root).as_posix(),
                              p.read_text(encoding="utf-8").splitlines()))
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"entry_corpus_unreadable: {p} 读不出：{exc}")
    return files, problems


def tracked_paths(root: Path) -> tuple[set[str] | None, str]:
    """`git ls-files` 的跟踪面。返回 None 表示"这不是 git 仓库/读不出"——
    那是**不知道**，不能折成"未入库"，否则合成语料与镜像仓会整片假红。"""
    try:
        proc = subprocess.run(["git", "-C", str(root), "ls-files"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git 读不出：{exc}"
    if proc.returncode != 0:
        return None, f"git ls-files rc={proc.returncode}"
    return {one for one in proc.stdout.splitlines() if one}, ""


def load_entry_register(root: Path) -> tuple[dict[str, str], list[str]]:
    """死链登记册：`{"path": note}`。文件不存在＝一本空册，
    于是所有不可解析入口都判红——grandfather 必须靠显式登记，不靠"反正没人管"。"""
    p = root / ENTRY_REGISTER_REL
    if not p.is_file():
        return {}, []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, [f"entry_register_unparsable: {ENTRY_REGISTER_REL} 读不出：{exc}"]
    out: dict[str, str] = {}
    problems: list[str] = []
    for e in doc.get("entries", []):
        path = str(e.get("path") or "")
        if not path:
            problems.append("entry_register_entry_without_path: 登记册有条目没有 path")
            continue
        if path in out:
            problems.append(f"entry_register_duplicate: {path!r} 登记了两次")
        out[path] = str(e.get("note") or "")
    return out, problems


def entry_points(root: Path,
                 tracked_override: set[str] | None = None,
                 ) -> tuple[list[tuple[str, int, str, str]], bool, list[str]]:
    """判红面 ⑤（第 87 片）：文档里 `<解释器> <路径>.py|.sh` 形态的复算入口要能落地。

    五种归属：
      tracked     —— 路径在仓库内且已入库 ⇒ 合规；
      untracked   —— 路径在仓库内、磁盘上就在，但 `git ls-files` 里没有 ⇒
                     **只有这台机器跑得动**（本轮就犯过一次：取证件写完没提交）；
      dead        —— 绝对路径（`/tmp/...`）或仓库内不存在 ⇒ 干净签出跑不了，
                     除非在登记册里挂着；
      delegated   —— `scripts/…`，那一批的存在性由判红面 ④ 负责，这里只数不判；
      placeholder —— 模板形态，不判，只数。

    分母**不在本文抄**（与面 ③ 同一条规矩，第 87 片立档时抄过一次、第 88 片复核时
    那份 104/5/18 已经漂成 119/8/20）：现读值看 `--json` 的
    `corpus.entry_points` 与 `corpus.entry_states`，五档之和等于总读数由 `--self-test`
    钉住。立档前确实量过一轮（"先量再立"是第 85 片的纪律），但量到的数是**那一次的**，
    而这一档的语料含 `docs/audit/` —— 文档每多写一行引用，分母就自己往前走。
    """
    files, problems = entry_corpus(root)
    if tracked_override is not None:
        tracked = tracked_override
    else:
        tracked, _git_err = tracked_paths(root)
    rows: list[tuple[str, int, str, str]] = []
    for rel, lines in files:
        for no, line in enumerate(lines, 1):
            for m in ENTRY_LINE_RE.finditer(line):
                path = m.group(1)
                if ENTRY_PLACEHOLDER_RE.search(path):
                    rows.append((rel, no, path, "placeholder"))
                    continue
                if path.startswith("scripts/"):
                    # `scripts/X.py` 的存在性与旗子封闭性已由判红面 ④ 负责（第 85 片）。
                    # 这里再判一次不会多抓一个缺陷，只会把一个缺陷记成两笔红——
                    # 面 ⑤ 的对象是**仓库里没人管过的那一批**入口：docs/、references/、
                    # 历轮 lab 脚本，以及任何绝对路径。
                    rows.append((rel, no, path, "delegated"))
                    continue
                if path.startswith("/"):
                    rows.append((rel, no, path, "dead"))
                    continue
                inside = root / path
                if not inside.exists():
                    rows.append((rel, no, path, "dead"))
                    continue
                if tracked is None:
                    rows.append((rel, no, path, "tracked"))
                    continue
                rows.append((rel, no, path,
                             "tracked" if path in tracked else "untracked"))
    # git 读不出时**不记 problem**：那会把合成语料与无 git 的镜像仓一律打成 rc=2。
    # 未入库那一档在这种树上自然为空（tracked is None ⇒ 按存在即合规），
    # 读数里用 git_unknown 明说"这一档本轮没判"，而不是假装判过。
    return rows, (tracked is None), problems


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
    cont, p5 = continuation_breaks(root)
    code, code_neg, p4 = production_code_mentions(root)
    prose, p3 = prose_mentions(root)
    srows, sunbounded, p6 = script_rows(root)
    problems += p1 + p2 + p3 + p4 + p5 + p6

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
    # 续行断裂不经过 record()：它判的不是"某个名字存不存在"，而是"这一行能不能照抄"，
    # 所以直接进 violations，也别指望它给只报面去重（那按名字去重，形状不同）。
    for rel, no, seg in cont:
        judged.append(("续行", rel, no, seg))

    # 判红面 ④：脚本必须存在，且行内 `--旗子` 必须在它自己的 argparse 声明里。
    # 与 ② / ②b 同一条纪律：语料走 quickref_corpus 那一份遍历，别另起一次 rglob。
    script_rows_judged = 0
    extra: dict[tuple[str, str, int, str], str] = {}
    for rel, no, stem, used in srows:
        path = root / "scripts" / f"{stem}.py"
        if not path.is_file():
            script_rows_judged += 1
            judged.append(("脚本缺失", rel, no, f"scripts/{stem}.py"))
            extra[("脚本缺失", rel, no, f"scripts/{stem}.py")] = (
                "这一行照抄会直接报 `No such file or directory`")
            continue
        decl, bounded = script_arg_flags(path)
        if not bounded:
            continue                      # 读不到全集 ⇒ 不判（也不假装判过）
        script_rows_judged += 1
        for flag in used:
            if flag in decl:
                continue
            key = ("脚本旗子", rel, no, f"{stem}.py {flag}")
            judged.append(key)
            near = difflib.get_close_matches(flag, sorted(decl), n=2, cutoff=0.6)
            extra[key] = (f"`{path.name}` 声明的长旗子共 {len(decl)} 个："
                          f"{' '.join(sorted(decl)) or '（一个都没有）'}"
                          + (f"；近形候选 {' '.join(near)}" if near else ""))

    # 判红面 ⑤（第 87 片）：文档里 `<解释器> 路径.py|.sh` 形态的复算入口，
    # 要么在仓库内且已入库，要么在死链登记册里挂着。登记册缺失＝一本空册，
    # 于是所有死链都判红：grandfather 要显式登记，不靠"反正没人管"。
    erows, egit_unknown, p7 = entry_points(root)
    ereg, p8 = load_entry_register(root)
    problems += p7 + p8
    e_counts = {"tracked": 0, "untracked": 0, "dead": 0, "placeholder": 0,
                "delegated": 0, "dead_registered": 0}
    for rel, no, path, state in erows:
        e_counts[state] += 1
        if state == "untracked":
            key = ("入口未入库", rel, no, path)
            judged.append(key)
            extra[key] = ("文件在这台机器上，但 `git ls-files` 不列它 ⇒ "
                          "干净签出里这条入口跑不了（取证件要提交）")
        elif state == "dead":
            if path in ereg:
                e_counts["dead_registered"] += 1
                continue
            key = ("入口不可解析", rel, no, path)
            judged.append(key)
            extra[key] = (("绝对路径在任何签出里都不可解析" if path.startswith("/")
                           else "仓库内没有这个文件") + "，且没进死链登记册")
    # 登记册要双向对账：只核"引用的都在册"会看不见"在册但已无用"的那一半。
    reg_stale: list[tuple[str, str]] = []
    for path, _note in sorted(ereg.items()):
        states = [s for _r, _n, p, s in erows if p == path]
        if not states:
            reg_stale.append((path, "再没有任何文档引用它 ⇒ 撤登记"))
        elif all(s == "tracked" for s in states):
            reg_stale.append((path, "现在处处都能解析（文件已入库）⇒ 该从死链册撤"))
    for path, why in reg_stale:
        key = ("登记册该撤", ENTRY_REGISTER_REL, 0, path)
        judged.append(key)
        extra[key] = why
    if egit_unknown:
        e_counts["git_unknown"] = 1

    # 只报面 = 全量扫描里**未被按名判过**的提及，再补上"代码里带否定标记"那批中
    # 尚未被全量扫描覆盖的（今天 `CODE_DIRS ⊂ REPORT_ONLY_DIRS` 都含 src，五条全已被覆盖 ⇒
    # 补集为空；第 60 片写成 `+ code_neg` 是把它们数了两遍，report_only 因此恒多 5）。
    # 去重是必须的：docs/architecture 与 src/ 同时落在两档的目录清单里，
    # 不去重的话 Σ 分桶 > 总数，"分桶等于分母"这条自证就成了一句空话。
    kept = [r for r in prose if r not in seen_names]
    have = set(kept)
    report_rows = kept + [r for r in code_neg if r not in have]

    live_rows = [r for r in report_rows if not is_record_path(r[0])]
    record_rows = [r for r in report_rows if is_record_path(r[0])]
    record_dirs: dict[str, int] = {}
    for rel, _no, _seg in record_rows:
        key = rel.split("/", 1)[0] if not rel.startswith("docs/") else "/".join(rel.split("/")[:2])
        record_dirs[key] = record_dirs.get(key, 0) + 1
    # 每一类记录文本都要真的贡献过内容：把某个目录从 RECORD 名单里删掉时，
    # 总数看着没变（它滑进 live 或消失），这里会先红。
    # 只对**本仓**核对（同第 74 片的具名样本：合成语料里没有 CHANGELOG 不是判据的毛病）。
    if root.resolve() == Path(__file__).resolve().parent.parent:
        for label in RECORD_FILES + RECORD_DIR_PREFIXES:
            head = label.split("/", 1)[0]
            if not any(v for k, v in record_dirs.items()
                       if k == head or k.startswith(head)):
                problems.append(
                    f"record_bucket_empty: 记录面里 {label!r} 一处提及都没有"
                    "（名单或语料变了，要么改名单要么删掉这条，别让它挂着）")

    report_bad = []
    for rel, no, seg in live_rows:      # 可行动清单只从 live 出
        first, second = _mentions(seg)[0]
        if resolve(first, second or None, paths, groups) is None:
            report_bad.append((rel, no, seg))
    # 记录面仍然**可查**：它不判红、也不进可行动清单，但名字与位点要能列出来，
    # 否则"拆成两桶"就变成"把一半语料藏起来"（第 75 片拆桶的前提是可见性不降）。
    record_bad = []
    for rel, no, seg in record_rows:
        first, second = _mentions(seg)[0]
        if resolve(first, second or None, paths, groups) is None:
            record_bad.append((rel, no, seg))

    if not (reg and quick and code):
        problems.append(f"judging_face_empty: run_command 段 {len(reg)}、速查行 {len(quick)}、"
                        f"代码提及 {len(code)}（判红面任一档空读都不算绿）")
    ok = not judged and not problems
    return {
        "ok": ok,
        "authority_paths": len(paths),
        "authority_groups": len(groups),
        "corpus": {"run_command_segments": len(reg), "quickref_lines": len(quick),
                   "continuation_breaks": len(cont),
                   "script_rows": len(srows), "script_rows_judged": script_rows_judged,
                   "script_rows_unbounded": sorted(sunbounded),
                   "code_mentions": len(code), "code_negated": len(code_neg),
                   "prose_mentions": len(prose),
                   "report_only_mentions": len(live_rows),
                   "report_record_mentions": len(record_rows),
                   "report_total_mentions": len(report_rows),
                   "report_record_dirs": record_dirs,
                   "entry_points": len(erows), "entry_states": e_counts,
                   "entry_register_size": len(ereg),
                   "entry_register_stale": [p for p, _w in reg_stale]},
        "report_record_unmatched": [{"doc": d, "line": n, "written": w}
                                    for d, n, w in record_bad],
        "violations": [{"field": f, "doc": d, "line": n, "written": w,
                        "detail": extra.get((f, d, n, w), "")}
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
                 f"（另有 {c['code_negated']} 处同行带否定标记 ⇒ 只报）"
                 f"；速查语料里断掉的续行 {c['continuation_breaks']} 处"
                 f"；行首 `python scripts/X.py` 共 {c['script_rows']} 行"
                 f"（判 {c['script_rows_judged']} 行，"
                 f"{len(c['script_rows_unbounded'])} 行因旗子集合静态不封闭而不判："
                 f"{', '.join(c['script_rows_unbounded']) or '无'}）")
    es = c["entry_states"]
    lines.append(f"判红面 ⑤（复算入口）：命令形态 {c['entry_points']} 处 ⇒ "
                 f"入库可解析 {es['tracked']} / 未入库 {es['untracked']} / "
                 f"死链 {es['dead']}（其中已登记 {es['dead_registered']}）/ "
                 f"占位不判 {es['placeholder']}；登记册 {c['entry_register_size']} 条"
                 + (f"，其中该撤 {len(c['entry_register_stale'])} 条"
                    if c["entry_register_stale"] else "")
                 + ("；注意：`git ls-files` 读不出 ⇒ 未入库那档本轮不判"
                    if es.get("git_unknown") else ""))
    lines.append(f"只报面（live，可行动）{c['report_only_mentions']} 处；"
                 f"记录性引述（只数不列名）{c['report_record_mentions']} 处 "
                 f"{c['report_record_dirs']}；全量扫描 {c['prose_mentions']} 处，"
                 f"live + record = {c['report_only_mentions'] + c['report_record_mentions']} 处"
                 "（与减去三档判红面覆盖后的行数同构）")
    for v in rep["violations"]:
        if v["field"] == "脚本旗子":
            lines.append(f"  ✗ 脚本旗子 {v['doc']}:{v['line']} 写了 `{v['written']}`"
                         " ⇒ 这个脚本不接受该旗子，照抄会 rc=2 用法错误"
                         + (f"（{v.get('detail', '')}）" if v.get("detail") else ""))
            continue
        if v["field"] == "脚本缺失":
            lines.append(f"  ✗ 脚本缺失 {v['doc']}:{v['line']} 点名 `{v['written']}`"
                         " ⇒ 仓库里没有这个脚本，那行不可执行")
            continue
        if v["field"] == "入口未入库":
            lines.append(f"  ✗ 入口未入库 {v['doc']}:{v['line']} 让人跑 `{v['written']}`"
                         " ⇒ 文件在本地但没入库，干净签出拿不到它"
                         + (f"（{v.get('detail', '')}）" if v.get("detail") else ""))
            continue
        if v["field"] == "入口不可解析":
            lines.append(f"  ✗ 入口不可解析 {v['doc']}:{v['line']} 让人跑 `{v['written']}`"
                         " ⇒ 这条复算入口已经跑不动了：要么把工件迁进 `docs/audit/sNN/` 并入库，"
                         "要么写进死链登记册并说明它为什么不再可复算"
                         + (f"（{v.get('detail', '')}）" if v.get("detail") else ""))
            continue
        if v["field"] == "登记册该撤":
            lines.append(f"  ✗ 登记册该撤 {v['written']}（登记册自己的格，不指文档行）"
                         f" ⇒ {v.get('detail', '')}")
            continue
        if v["field"] == "续行":
            lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} 以 `\\` 收尾，而下一行是"
                         "另一条 `aipd` 命令 ⇒ 照抄只会跑到半条命令（要么补完旗子，要么"
                         "拆成两条各自完整的示例）")
            continue
        lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} 写了 `{v['written']}`"
                     " ⇒ 权威面上没有这条命令")
    for p in rep["problems"]:
        lines.append(f"  ! 前提不成立：{p}")
    if rep["report_only_unmatched"]:
        uniq: dict[str, list[str]] = {}
        for r in rep["report_only_unmatched"]:
            uniq.setdefault(r["written"], []).append(f"{r['doc']}:{r['line']}")
        lines.append(f"  · live 只报面里点到未注册的命令 {len(uniq)} 个名字："
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

    # 必开火夹具：下面两行是 `git show 3784a0a:README.md` 的 271/272 **逐字**搬来的
    # （第 81 片真实的插坏形状，不是手写相似片段）——一行以 `\` 收尾、下一行另起一条命令。
    broken = ("aipd drawing assembly-steps --manifest assembly.json --out assembly.md "
              "--part ASSY-1 \\")
    legal_tail = "  --db state.db --bom BOM-1"      # 当前 README:275 的合规形状
    (tmp / "README.md").write_text(
        "# t\naipd ctq add --db x --project p\naipd " + ghost_bad + " --db x\n"
        "运行 `aipd usage` 列出全部命令\naipd <命令> --help\naipd-os 与 aipd_os 不算\n"
        + broken + "\n"
        "aipd drawing assembly-steps --manifest assembly.json --out assembly.md --part ASSY-1 "
        "--pdf   # 顺带出 A4 图框矢量 PDF（中文可抽取）\\\n"
        + legal_tail + "\n",
        encoding="utf-8")
    # 判红面 ④ 的夹具：四个脚本、四种判决。名字一律 `zzz_` 前缀（不与产品脚本撞名，
    # 也不会被将来注册的真名反噬——第 60/61 片那两处写死真名的教训）。
    (tmp / "scripts").mkdir(exist_ok=True)
    (tmp / "scripts/zzz_tool.py").write_text(
        "import argparse\nap = argparse.ArgumentParser()\n"
        "ap.add_argument('--alpha')\nap.add_argument('--beta-two')\n", encoding="utf-8")
    (tmp / "scripts/zzz_dyn.py").write_text(
        "import argparse\nNAMES = ['--gamma']\nap = argparse.ArgumentParser()\n"
        "ap.add_argument(*NAMES)\n", encoding="utf-8")
    rows = (tmp / "README.md").read_text(encoding="utf-8")
    (tmp / "README.md").write_text(
        rows + "\npython scripts/zzz_tool.py --alpha            # 合规：旗子真声明着\n"
        "python scripts/zzz_tool.py --zzz-not-a-flag   # 必开火：脚本不认这个旗子\n"
        "python scripts/zzz_missing_tool.py --alpha    # 必开火：仓库里没有这个脚本\n"
        "python scripts/zzz_dyn.py --anything          # 不判：旗子集合静态不封闭\n"
        "python scripts/zzz_tool.py --beta-two \\\n"
        "    --alpha           # 合规续行：折回同一行才判得对\n",
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
              (f"aipd {ghost_bad}", "code"), (broken, "续行"),
              ("zzz_tool.py --zzz-not-a-flag", "脚本旗子"),
              ("scripts/zzz_missing_tool.py", "脚本缺失")}
    assert bad == expect, (sorted(bad), sorted(expect))
    _mark(marks, "三档判红面各抓到一条注入的假命令（速查行、run_command 段、生产代码），"
                 "断掉的续行那格抓到历史原件那一行")
    assert rep["corpus"]["continuation_breaks"] == 1, rep["corpus"]
    # 判红面 ④ 的三格分母：5 行、判 4 行（不封闭那行不判）、不封闭名单只有 zzz_dyn
    assert rep["corpus"]["script_rows"] == 5, rep["corpus"]
    assert rep["corpus"]["script_rows_judged"] == 4, rep["corpus"]
    assert rep["corpus"]["script_rows_unbounded"] == ["zzz_dyn"], rep["corpus"]
    _mark(marks, "判红面 ④：假旗子与不存在的脚本各开火一次；真旗子、折回来的续行、"
                 "以及静态不封闭的脚本一律不开火（看不见不折成违规）")
    assert legal_tail.strip() not in {v["written"] for v in rep["violations"]}
    _mark(marks, "合规侧同批存在：下一行是旗子（`  --db … --bom …`）的合法续行不开火")
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
    assert rep["corpus"]["quickref_lines"] == 5, rep["corpus"]
    assert rep["corpus"]["code_mentions"] == 2, rep["corpus"]
    _mark(marks, "分母自报且与语料一致（run_command 3 段、速查行 3 行、代码 2 处）")
    assert main(["--repo", str(tmp)]) == 4
    empty = tmp / "empty"
    (empty / "src/aipd_os").mkdir(parents=True)
    (empty / "src/aipd_os/registry_data.py").write_text("CAPABILITIES = []\n",
                                                        encoding="utf-8")
    assert main(["--repo", str(empty)]) == 2, "判红面为空必须判前提不成立"
    _mark(marks, "空语料读成「前提不成立」（退 2），不是「零违规」")

    # ---- 判红面 ⑤（第 87 片）：复算入口可解析性 ----
    e = tmp / "entry"
    (e / "docs/audit/zzz").mkdir(parents=True)
    (e / "docs/audit/zzz/live.sh").write_text("echo ok\n", encoding="utf-8")
    (e / "docs/audit/zzz/loose.py").write_text("print(1)\n", encoding="utf-8")
    (e / "docs/audit/zzz/doc.md").write_text(
        "入口 A：bash docs/audit/zzz/live.sh\n"
        "入口 B：python docs/audit/zzz/loose.py\n"
        "入口 C：python /tmp/zzz_dead_battery.py\n"
        "入口 D：bash tmp/zzz_outside.sh\n"
        "入口 E：python scripts/X.py\n"
        "入口 F：python scripts/zzz_missing_tool.py --zzz 1\n", encoding="utf-8")
    reg = e / ENTRY_REGISTER_REL
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"entries": [
        {"path": "/tmp/zzz_dead_battery.py", "note": "历轮电池，写在宿主 /tmp，已不可再生"},
        {"path": "docs/audit/zzz/live.sh", "note": "这条其实早就入库了——专打「该撤」那一档"},
        {"path": "docs/audit/zzz/never_cited.sh", "note": "再没被任何文档引用——另一档「该撤」"},
    ]}, ensure_ascii=False), encoding="utf-8")
    # 真 git 仓库：未入库那一档必须由 `git ls-files` 说，不是由测试注入
    for git_args in (["init", "-q"], ["add", "docs/audit/zzz/live.sh"],
                     ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"]):
        subprocess.run(["git", "-C", str(e), *git_args], capture_output=True, check=True)
    assert tracked_paths(e)[0] == {"docs/audit/zzz/live.sh"}, tracked_paths(e)
    rows, git_unknown, ep = entry_points(e, tracked_override={"docs/audit/zzz/live.sh"})
    state = {p: s for _r, _n, p, s in rows}
    assert git_unknown is False and not ep, (git_unknown, ep)
    assert state == {"docs/audit/zzz/live.sh": "tracked",
                     "docs/audit/zzz/loose.py": "untracked",
                     "/tmp/zzz_dead_battery.py": "dead",
                     "tmp/zzz_outside.sh": "dead",
                     "scripts/X.py": "placeholder",
                     "scripts/zzz_missing_tool.py": "delegated"}, state
    _mark(marks, "面 ⑤ 六格归属各自落位：入库/未入库/两种死链/占位不判/scripts 交给面 ④")
    ereg, rp = load_entry_register(e)
    assert not rp and set(ereg) == {"/tmp/zzz_dead_battery.py", "docs/audit/zzz/live.sh",
                                    "docs/audit/zzz/never_cited.sh"}, (ereg, rp)
    # 「已能解析还挂着」与「再没被引用」两半都由 audit() 自己判，下面端到端断言；
    # 这里不再在测试里重抄一遍筛选逻辑——抄一份只会证明两份抄得一致。
    # 端到端：audit() 在真登记册下的判决集合
    rep5 = audit(e)
    fields5 = {(v["written"], v["field"]) for v in rep5["violations"]}
    assert ("docs/audit/zzz/loose.py", "入口未入库") in fields5, fields5
    assert ("tmp/zzz_outside.sh", "入口不可解析") in fields5, fields5
    assert "/tmp/zzz_dead_battery.py" not in {w for w, _f in fields5}, fields5
    assert ("docs/audit/zzz/live.sh", "登记册该撤") in fields5, fields5
    assert ("docs/audit/zzz/never_cited.sh", "登记册该撤") in fields5, fields5
    assert not any(f.startswith("入口") and w.startswith("scripts/")
                   for w, f in fields5), fields5
    _mark(marks, "面 ⑤ 端到端：未入库开火、未登记死链开火、已登记的不开火、"
                 "登记册里两条「该撤」各按自己的理由开火、scripts/ 一律不重复判")
    c5 = rep5["corpus"]["entry_states"]
    assert c5["tracked"] == 1 and c5["untracked"] == 1 and c5["dead"] == 2, c5
    assert c5["dead_registered"] == 1 and c5["placeholder"] == 1 and c5["delegated"] == 1, c5
    assert rep5["corpus"]["entry_points"] == sum(
        c5[k] for k in ("tracked", "untracked", "dead", "placeholder", "delegated")), c5
    _mark(marks, "面 ⑤ 分母自证：五档之和等于入口总读数，登记掉的另记一格"
                 "（少一档或把已登记的漏计都会在这里红）")
    # 没有 git 的树：未入库那一档要自动退成"不判"，不能把磁盘上存在的件全判成违规
    ng = tmp / "entry_nogit"
    (ng / "docs/audit/zzz").mkdir(parents=True)
    (ng / "docs/audit/zzz/loose.py").write_text("print(1)\n", encoding="utf-8")
    (ng / "docs/audit/zzz/doc.md").write_text("入口 B：python docs/audit/zzz/loose.py\n",
                                              encoding="utf-8")
    ng_rows, ng_unknown, _ng_p = entry_points(ng)
    assert ng_unknown is True, ng_unknown
    assert [s for _r, _n, _p, s in ng_rows] == ["tracked"], ng_rows
    _mark(marks, "git 读不出时按「存在即合规」降级并把 git_unknown 记进读数，"
                 "不把合成语料/镜像仓整片假红")
    reg.unlink()
    assert load_entry_register(e) == ({}, []), "登记册不在时应读成空册而不是报错"
    rep5b = audit(e)
    assert ("/tmp/zzz_dead_battery.py", "入口不可解析") in {
        (v["written"], v["field"]) for v in rep5b["violations"]}, rep5b["violations"]
    _mark(marks, "没有登记册＝一本空册：所有死链判红，grandfather 只能靠显式登记")

    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


# 登记册的五段说明文字**只在代码里写一次**：`emit_register` 把它们整批刷进册子，
# 常驻用例 `test_real_repo_register_shares_the_instrument_constants` 逐字段比。
# 第 87 片的教训是这两份各抄各的——册里的 `rule` 停在"四种归属"而代码写"五种"，
# 没有任何判据看得见，直到本轮复核才读出来。
REGISTER_WHAT = ("文档里点名、但在干净签出中不可解析的复算入口登记册"
                 "（判红面 ⑤ 的 grandfather 名单）")

REGISTER_RULE = (
    "面 ⑤ 对每一条 `<解释器> 路径.py|.sh` 形态的入口判五种归属"
    "（tracked / untracked / dead / delegated / placeholder）；"
    "落不到仓库里的必须在本册 `entries` 里逐条列出，否则判红。列进来不等于放过："
    "判据每次现读语料，某条现在又能解析了、或现读扫不到任何引用它的行时，"
    "会以「登记册该撤」反向开火。")

REGISTER_SNAPSHOT_SEMANTICS = (
    "`cited_by_at_emit_time` 只在 `--emit-register` 那一刻写一次，判据不读它："
    "「再没被引用」那一半由语料现算（`entry_points` 的行集），不由这一列决定。"
    "面 ⑤ 的语料含 `docs/audit/` 下的 `.md`，所以取证文档每多写一行引用就会让这一列过期"
    "（本册是 `.json`，不在语料里）——它是给读者定位原文的路标，不是账。")

REGISTER_NOTE_SEMANTICS = (
    "每条 note 必须自己说清三件事：它是哪一片的什么量具、它当时的判决读数是多少、"
    "那个读数抄在哪篇取证文档的哪一行。缺任何一件就退化成占位文本"
    "（常驻用例只保证非空，不保证有信息量）。")

REGISTER_SHAPE_BORROWED_FROM = (
    "lychee 的 --exclude/--exclude-path/.lycheeignore（豁免是一份显式配置文件"
    "而不是行内注释）；mdBook 的 ignore/no_run/compile_fail"
    "（把「不跑」说成一种被记录的形状）")


def emit_register(root: Path, dst: Path) -> dict:
    """把当前判为死链的入口写成/刷新登记册。

    `--emit-register` 的产物里 note 是空的，由人补"为什么不再可复算"。刷新时**按 path
    把旧 note 带过去**：note 是判据真正消费的豁免理由，草案覆盖式重写会把历轮手写的
    依据一起抹掉（第 87 片复核登记过这条，本轮连同快照列降级一并处理）。
    返回 `{"written": n, "missing_notes": [path…], "refused": ""|"…"}`；
    目标存在但读不出时整批不写。
    """
    erows, _git_unknown, _p = entry_points(root)
    by: dict[str, list[str]] = {}
    for rel, no, path, state in erows:
        if state == "dead":
            by.setdefault(path, []).append(f"{rel}:{no}")
    old_notes: dict[str, str] = {}
    if dst.is_file():
        try:
            existing = json.loads(dst.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"written": 0, "missing_notes": [],
                    "refused": f"目标登记册读不出，草案不落盘以免抹掉手写依据：{exc}"}
        for e in existing.get("entries", []):
            note = str(e.get("note") or "")
            if note:
                old_notes[str(e.get("path") or "")] = note
    doc = {
        "what": REGISTER_WHAT,
        "rule": REGISTER_RULE,
        "cited_by_at_emit_time_semantics": REGISTER_SNAPSHOT_SEMANTICS,
        "note_semantics": REGISTER_NOTE_SEMANTICS,
        "shape_borrowed_from": REGISTER_SHAPE_BORROWED_FROM,
        "entries": [{"path": k, "cited_by_at_emit_time": v,
                     "note": old_notes.get(k, "")} for k, v in sorted(by.items())],
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    return {"written": len(doc["entries"]),
            "missing_notes": [e["path"] for e in doc["entries"] if not e["note"]],
            "refused": ""}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="文档/登记表命令名对账")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--json", default="", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--emit-register", default="",
                    help="把当前死链入口写成登记册草案（人工补 note 后入库；"
                         "已存在的册按 path 保留旧 note）")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    if args.emit_register:
        got = emit_register(root, Path(args.emit_register).resolve())
        if got["refused"]:
            print(f"拒绝：{got['refused']}")
            return 2
        miss = got["missing_notes"]
        print(f"登记册草案：{got['written']} 条死链入口 → {args.emit_register}"
              f"（note 待补 {len(miss)} 条）")
        for p in miss:
            print(f"  缺 note：{p}")
        return 0
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
