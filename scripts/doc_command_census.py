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
     （条目"现在能解析了"或"再没被引用"都算「登记册该撤」，**但后半只在 git 读得出的树上判**——
     降级出来的 `tracked` 不是"已入库"的证据，拿它开火等于让降级自己造出一条违规）。
     语料含 `docs/audit/`——
     历轮取证文档的复算入口小节就是案发现场，排除它判据就只剩象征意义。
     `scripts/…` **只在真被面 ④ 收进那一行时才免责**（第 89 片）：面 ④ 的语料不含
     `docs/audit/`、正则只认行首扁平的 `python scripts/X.py`，所以从取证文档点名的
     `scripts/gone.py` 与嵌套路径过去两把尺都不判；现在这类行落回上面四档由这里判存在性。
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

面 ⑤ 的形状在**第 90 片**加宽过一次，代价与对策都记在
`docs/audit/RECOGNITION_WIDENING_S90_2026-09-28.md`：识别面原先只认
"解释器 + 一个空格 + ASCII 路径"，于是 `/abs/…/.venv/bin/python`、`python3.11`、
`python -u x.py`、中文命名的脚本**连一行读数都不产生**（漏判不留痕迹，比分错档更坏）。
加宽的当场代价：真仓库一次多出 9 条死链红，其中 **7 条是取证文档里"描述这条判据自己"
的虚构假名**——所以同片补了点名式举例注释 `<!-- aipd-census:example 路径… -->`：
它只免判被点名的那一处（同一行未被点名的仍判），并且**点了名却点不到 occurrence
就判「举例标记失效」**，否则豁免会变成只涨不消的注释。归属因此是六档
（`tracked / untracked / dead / delegated / placeholder / example`），
`..` 也不再当占位免判，而是先 `posixpath.normpath` 再判存在性。

退码（与同族量具同形）：0 现状面干净；4 现状面有未注册命令；2 前提不成立
（权威面建不起来、判红面为空、或有文件解析失败——**空读数一律不当通过**）。
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import posixpath
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


ENTRY_PY = r"(?:\.venv/bin/)?python3?(?:\.\d+)?"
ENTRY_SHELL = r"(?:bash|sh|zsh)"
# 解释器可以带目录前缀（`/abs/x/.venv/bin/python`），也可以带版本后缀；
# 解释器与路径之间允许夹**短旗**（`python -u x.py`）。第 90 片之前的形状是
# "解释器 + 一个空格 + 路径"，于是整族写法**连一行都不产生**——
# 不是免判，是分母里没有它（漏判不留读数）。
ENTRY_INTERP = r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_./-]+/)?(?:" + ENTRY_PY + \
               r"|" + ENTRY_SHELL + r")"
ENTRY_FLAGS = r"(?:\s+-{1,2}[A-Za-z][\w-]*)*"
# 路径字符集：第 90 片把 CJK 基本区放进来。理由是**对称**而不是现状——本仓取证文档的
# 文件名一半是中文（`docs/audit/DRIFT_SCAN_COST_F-DRIFT-4_2026-09-26.md` 这类），
# 而 `tracked_paths()` 那一侧第 89 片已经修成能读非 ASCII 入库名
# （`-c core.quotePath=false`），识别面却还只认 ASCII ⇒ 一条中文命名的入口脚本
# 会被整条**看不见**（不是误判，是漏判，而漏判不留读数）。
# 范围只到 CJK 统一表意文字基本区：假名/谚文/生僻扩展区仍不认，写在取证文档 §一之二。
# 模板字符（`{` `}` `$` `*` `…` `<` `>`）也在类里：否则下面 `ENTRY_PLACEHOLDER_RE`
# 的三个分支永远不可达（第 87 片 §九#6），模板形态会变成"零读数"而不是"计为占位"。
# 故意**不含** `[` `]`：那会把 markdown 链接的 `](` 一起吞进来，覆盖面变噪声。
ENTRY_PATH_CHARS = r"A-Za-z0-9_\u4e00-\u9fff./\-\{\}$<>*…"
# 前缀用"否定型 lookbehind"而不是固定字符类：中文文档里这条常写成
# 「复算入口：bash x.sh」「跑 `python foo.py`」，只列 ASCII 空白/反引号/竖线会把
# 全角冒号后面的那些整批漏掉——一种拼写≠全部形态（第 78 片记过的文本面病）。
ENTRY_LINE_RE = re.compile(ENTRY_INTERP + ENTRY_FLAGS +
                           r"\s+([" + ENTRY_PATH_CHARS + r"]+\.(?:py|sh))\b")
# 行内"这是举例"标记（第 90 片）。形状借 markdownlint 的行级 disable 注释
# （`<!-- markdownlint-disable-line MDxxx -->`，官方文档明说只能整行、不能整跨），
# 语义借 Vale 的"点名到具体匹配"（`<!-- vale Style.Rule["ACT test"] = NO -->`）：
# **必须把免判的那几个路径写进注释里**。差别不是洁癖：
# 整行式标记会让后来人往同一行里加一条真死链而无人知，
# 点名式标记则要求作者写出他到底在豁免谁，写不出来就红。
# 被点名的 occurrence 仍产出一行 `example` 读数——免判与看不见必须是两件事。
ENTRY_EXAMPLE_RE = re.compile(r"<!--\s*aipd-census:example(?P<paths>[^>]*?)-->")
# 模板/区间/变量形态不是"给人照抄的具体命令"：写了 X.py、sNN、`..`、尖括号、通配、
# `${VAR}` 的都走**不判**，单列读数。第 85 片量分母时 README:508 那行
# `python scripts/X.py` 就是这种形状——把它判红等于让尺子咬自己：
# 那一行正是在描述本判据的占位写法。
ENTRY_PLACEHOLDER_RE = re.compile(r"(?:X\.(?:py|sh)$|NN|\.\.|…|[<>{}*]|\$\{|s\d+\.\.s)")
ENTRY_FILES = ("README.md", "SKILL.md", "QUICKSTART.md")
ENTRY_DIRS = ("docs", "references")
ENTRY_REGISTER_REL = "docs/audit/RECOMPUTE_ENTRYPOINT_REGISTER.json"


def example_names_on(line: str) -> set[str]:
    """这一行的"举例"标记点名免判了哪些路径（没标记就是空集）。"""
    mm = ENTRY_EXAMPLE_RE.search(line)
    if not mm:
        return set()
    return {tok for tok in mm.group("paths").split() if tok}


def stale_example_markers(root: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """标记点了名、而那一行**根本没有那个 occurrence** ⇒ 失效的标记（返回 (失效, 语料问题)）。

    没有这一条，标记就是只涨不消的豁免：脚本改名、示例被删、路径打错，
    三种情况都会留下一行"看起来还在保护什么"的注释，而它已经不保护任何东西。
    失效按**违规**报（不是前提问题）：它的修法是删注释或改名，与树的完整性无关。
    """
    files, problems = entry_corpus(root)
    stale: list[tuple[str, int, str]] = []
    for rel, lines in files:
        for no, line in enumerate(lines, 1):
            named = example_names_on(line)
            if not named:
                continue
            seen: set[str] = set()
            for m in ENTRY_LINE_RE.finditer(line):
                p = m.group(1)
                seen.add(p)
                seen.add(posixpath.normpath(p))
            stale += [(rel, no, tok) for tok in sorted(named - seen)]
    return stale, problems


def entry_corpus(root: Path) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """面 ⑤ 的语料：入口清单 + `docs/**` + `references/**` 的 `.md`。

    与 `quickref_corpus` 唯一的差别是这里**必须含 `docs/audit/`**：
    历轮取证文档的「复算入口」小节就是死链集中地（第 87 片实测：**143 处**引用里 **127 处**
    指向从没入库的 `tmp/` 工件，逐条更正见 `WORKTREE_INVENTORY_2026-09-28.md` §六；
    当前值看 `--json` 的 `corpus.entry_points / entry_states`，别抄这里），把案发现场排除在外，判据就只剩象征意义。
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
    """**HEAD 那棵树**里的文件集合（`git ls-tree -r HEAD --name-only`）。
    返回 None 表示"这不是 git 仓库/读不出/还没有提交"——
    那是**不知道**，不能折成"未入库"，否则合成语料与镜像仓会整片假红。

    第 89 片把 `git ls-files` 换掉的理由：`ls-files` 读的是**索引**，
    于是 `git add` 而没 `git commit` 的文件被算成"已入库"，而面 ⑤ 问的正是
    "干净签出拿不拿得到"——那份文件在别人的签出里根本不存在。
    本轮实测（临时仓库里 `b.py` 只 add 不 commit）：`ls-files=[a.py,b.py]`、
    `ls-tree HEAD=[a.py]`，差集正是 `b.py`。

    `-c core.quotePath=false` 不是排版偏好：git 默认把非 ASCII 路径转义成
    `"\\344\\270\\255\\346\\226\\207 \\347\\233\\256\\345\\275\\225/x.py"` 这种八进制串
    （本轮临时仓库实测；两条 git 命令都一样，不是换命令带来的新问题）。
    不关掉它，任何中文名文件的成员判定都会落空 ⇒ 一条**明明入库**的入口被读成
    "未入库"再判红。本仓跟踪路径**目前**全是 ASCII（条数不抄在这里——它每轮都在长，
    现数：`git ls-tree -r --name-only HEAD | wc -l`），所以这格今天不咬人；
    修它是因为它一旦咬就是假红。
    """
    try:
        proc = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false",
                               "ls-tree", "-r", "--name-only", "HEAD"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git 读不出：{exc}"
    if proc.returncode != 0:
        return None, f"git ls-tree HEAD rc={proc.returncode}"
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
                 face4: dict[tuple[str, int], str] | None = None,
                 ) -> tuple[list[tuple[str, int, str, str]], bool, list[str]]:
    """判红面 ⑤（第 87 片）：文档里 `<解释器> <路径>.py|.sh` 形态的复算入口要能落地。

    六种归属：
      tracked     —— 路径在仓库内且**在 HEAD 的树里** ⇒ 合规；
      untracked   —— 路径在仓库内、磁盘上就在，但 HEAD 的树里没有 ⇒
                     **只有这台机器跑得动**（本轮就犯过一次：取证件写完没提交）；
      dead        —— 绝对路径（`/tmp/...`）或仓库内不存在 ⇒ 干净签出跑不了，
                     除非在登记册里挂着；
      delegated   —— `scripts/…` 且**判红面 ④ 真的看得见这一行**，这里只数不判；
      placeholder —— 模板形态，不判，只数；
      example     —— 作者用 `<!-- aipd-census:example 路径… -->` **点名**豁免的那一处，
                     不判，只数（第 90 片；点名失效由 `stale_example_markers` 判红）。

    `face4` 是面 ④ 自己那一份行集（`{(文档, 行号): 脚本基名}`，由 `audit()` 传入）。
    第 87 片写"让渡给面 ④"时没有核对**让渡对象到底看不看这一行**，而面 ④ 的语料不含
    `docs/audit/`、正则只认行首扁平的 `python scripts/X.py` ⇒ 从取证文档点名的
    `python scripts/gone.py` 与 `python scripts/research/gone.py` 这类形状**两把尺都不判**。
    现在只有真被面 ④ 收进那一行的才 `delegated`，其余落回上面四档由这里判存在性。
    调用方要给 `face4` 就给：`emit_register` 现在**也**自己算一份面 ④ 的行集传进来。
    第 89 片复核件抓到的正是漏传的后果——草案会把一条 `delegated` 路径当成死链列进册子，
    而反向臂的条件是"处处 tracked / 没有行"，`delegated` 两头都不沾 ⇒
    那一行**永远撤不掉**，草案与判决从此各说各话。

    分母**不在本文抄**（与面 ③ 同一条规矩，第 87 片立档时抄过一次、第 88 片复核时
    那份 104/5/18 已经漂成 119/8/20）：现读值看 `--json` 的
    `corpus.entry_points` 与 `corpus.entry_states`。立档前确实量过一轮（"先量再立"是
    第 85 片的纪律），但量到的数是**那一次的**，而这一档的语料含 `docs/audit/` ——
    文档每多写一行引用，分母就自己往前走。
    `--self-test` 钉的是**分桶不重不漏**（每行只落一档，所以五档之和恒等于行数——
    那是构造式恒等，不是能咬人的牙，第 87 片 §九#8 已把它记为待换的弱判据）；
    "某一档今天有几条"这种数**没有任何判据钉着**，只有上面那两个键。
    """
    files, problems = entry_corpus(root)
    if tracked_override is not None:
        tracked = tracked_override
    else:
        tracked, _git_err = tracked_paths(root)
    rows: list[tuple[str, int, str, str]] = []
    for rel, lines in files:
        for no, line in enumerate(lines, 1):
            named = example_names_on(line)
            for m in ENTRY_LINE_RE.finditer(line):
                path = m.group(1)
                if path in named or posixpath.normpath(path) in named:
                    # 作者在这行的标记里**点名**了这个路径：它仍是一行读数（`example`），
                    # 不是被抹掉。没被点名的 occurrence 照判——这是与整行式
                    # disable 的实质差别（后来人往同一行塞真死链不会跟着免判）。
                    rows.append((rel, no, path, "example"))
                    continue
                if ".." in path:
                    # 旧实现把 `..` 当成占位标记来**免判**，于是 `scripts/a/../gone.py`
                    # 这种真会跑不动的写法静默过关（第 87 片 §九#6）。改成先归一化再判：
                    # `..` 不是模板，是一个可以算清楚的路径。区间模板 `s11..s12.py`
                    # 归一化后仍是自己，且仍带 `..` ⇒ 由下面的占位分支接住。
                    path = posixpath.normpath(path)
                if ENTRY_PLACEHOLDER_RE.search(path):
                    rows.append((rel, no, path, "placeholder"))
                    continue
                stem4 = (face4 or {}).get((rel, no))
                if path.startswith("scripts/"):
                    if stem4 is not None and path == f"scripts/{stem4}.py":
                        # 面 ④ 真收了这一行：存在性与旗子封闭性由它判，这里不重复记一笔。
                        # 但"磁盘上有、HEAD 里没有"那一格面 ④ 看不见（它只看 `is_file()`），
                        # 所以仍留在这里判。复核件指出整行让出去等于把刚修好的 §九#7 那一类
                        # 交给更弱的判据；而我第一版将渡得太狠——文件根本不存在的行也被叫成
                        # `untracked`，于是面 ④ 的「脚本缺失」与这里的「入口未入库」把**同一个
                        # 缺陷记成两笔红**，且那句"文件在这台机器上"是假的。
                        # 判据因此是两条：真在磁盘上（面 ④ 那格就没红）且不在 HEAD 的树里。
                        if tracked is not None and (root / path).is_file() \
                                and path not in tracked:
                            rows.append((rel, no, path, "untracked"))
                        else:
                            rows.append((rel, no, path, "delegated"))
                        continue
                    # 让渡落空（第 89 片）：面 ④ 的语料不含 `docs/audit/`，正则又只认
                    # 行首扁平的 `python scripts/X.py` ⇒ 嵌套路径、别的解释器前缀、
                    # 取证文档里点名的那一批，过去两把尺都不判。现在落回下面的通用判法。
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


def _unique_violations(judged: list[tuple[str, str, int, str, str]],
                       extra: dict[tuple[str, str, int, str], str],
                       ) -> list[dict[str, Any]]:
    """缺陷清单按 `(面, 文档, 行, 写法, 位点)` 去重，被合并的引用次数留在 `citations` 里。

    同一行里两处引用同一个不存在的入口（`python /tmp/x.py 与 bash /tmp/x.py`）会各产一行
    归属读数——那是**引用数**，留在 `corpus.entry_states` 里；`violations` 是待修清单，
    一处缺陷记两笔会让"红了几条"与"要改几处"脱钩（第 89 片复核件）。

    第五个键 `位点` 是"要改的那一处"本身：三档名字面带**语料记录的序号**（一行里两个
    capability 记录写了同一条假命令 ⇒ 文本逐字相同，但两处都要改 ⇒ 两笔红），
    其余面的一位点就是一行，留空串 ⇒ 同一行两处引用同一个死链仍合成一笔。
    """
    order: list[tuple[str, str, int, str, str]] = []
    count: dict[tuple[str, str, int, str, str], int] = {}
    for key in judged:
        if key not in count:
            count[key] = 0
            order.append(key)
        count[key] += 1
    out: list[dict[str, Any]] = []
    for key in order:
        f, d, n, w, _site = key
        cite = count[key]
        why = extra.get((f, d, n, w), "")
        if cite > 1:
            # 文本面也要看得见次数：只写在 JSON 里的话，人读到的是一行 ✗，
            # 而这一格实际站在 2 处引用上（README 承诺"次数留在 citations 与 entry_states"）。
            why = (why + "；" if why else "") + f"同一格在 {cite} 处引用上重复出现"
        out.append({"field": f, "doc": d, "line": n, "written": w,
                    "detail": why, "citations": cite})
    return out


def audit(root: Path) -> dict[str, Any]:
    paths, groups, problems = valid_commands()
    judged: list[tuple[str, str, int, str, str]] = []   # (field, 文件, 行, 写法, 位点)
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

    def record(kind: str, rel: str, no: int, seg: str, site: int) -> None:
        for first, second in _mentions(seg):
            name = f"aipd {first}{(' ' + second) if second else ''}"
            seen_names.add((rel, no, name))
            hit = resolve(first, second or None, paths, groups)
            key = f"{kind}|{rel}:{no}|{first} {second}".strip()
            verdicts[key] = hit or "UNMATCHED"
            if hit is None:
                # `site` 是"这一条语料记录"的身份：登记表一行里两个 dict 写了同一条假命令，
                # 文本逐字相同，但那是**两处要改**（第 89 片复核件 #4）。没有它，
                # 四项键会把两处读成一处；有它，同一段里同一名字写两遍仍合成一笔。
                judged.append((kind, rel, no, name, f"#{site}"))

    for i, (rel, no, seg) in enumerate(reg):
        record("run_command", rel, no, seg, i)
    for i, (rel, no, seg) in enumerate(quick):
        record("quickref", rel, no, seg, i)
    for i, (rel, no, seg) in enumerate(code):
        record("code", rel, no, seg, i)
    # 续行断裂不经过 record()：它判的不是"某个名字存不存在"，而是"这一行能不能照抄"，
    # 所以直接进 violations，也别指望它给只报面去重（那按名字去重，形状不同）。
    for rel, no, seg in cont:
        judged.append(("续行", rel, no, seg, ""))

    # 判红面 ④：脚本必须存在，且行内 `--旗子` 必须在它自己的 argparse 声明里。
    # 与 ② / ②b 同一条纪律：语料走 quickref_corpus 那一份遍历，别另起一次 rglob。
    script_rows_judged = 0
    extra: dict[tuple[str, str, int, str], str] = {}
    for rel, no, stem, used in srows:
        path = root / "scripts" / f"{stem}.py"
        if not path.is_file():
            script_rows_judged += 1
            judged.append(("脚本缺失", rel, no, f"scripts/{stem}.py", ""))
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
            judged.append(key + ("",))
            near = difflib.get_close_matches(flag, sorted(decl), n=2, cutoff=0.6)
            extra[key] = (f"`{path.name}` 声明的长旗子共 {len(decl)} 个："
                          f"{' '.join(sorted(decl)) or '（一个都没有）'}"
                          + (f"；近形候选 {' '.join(near)}" if near else ""))

    # 判红面 ⑤（第 87 片）：文档里 `<解释器> 路径.py|.sh` 形态的复算入口，
    # 要么在仓库内且在 HEAD 的树里，要么在死链登记册里挂着。登记册缺失＝一本空册，
    # 于是所有死链都判红：grandfather 要显式登记，不靠"反正没人管"。
    # `face4` 把面 ④ 自己的行集交给面 ⑤：只有真被那边收进那一行的 `scripts/…` 才免责，
    # 否则"让渡"是一个谁都不判的洞（第 87 片 §九#1，本轮闭合）。
    face4_map = {(rel, no): stem for rel, no, stem, _used in srows}
    erows, egit_unknown, p7 = entry_points(root, face4=face4_map)
    ereg, p8 = load_entry_register(root)
    problems += p7 + p8
    e_counts = {"tracked": 0, "untracked": 0, "dead": 0, "placeholder": 0,
                "delegated": 0, "example": 0, "dead_registered": 0}
    for rel, no, path, state in erows:
        e_counts[state] += 1
        if state == "untracked":
            key = ("入口未入库", rel, no, path)
            judged.append(key + ("",))
            extra[key] = ("文件在这台机器上，但 HEAD 的树里没有它 ⇒ "
                          "干净签出里这条入口跑不了（取证件要提交；"
                          "`git add` 不算，判据读的是 `git ls-tree -r HEAD`）")
        elif state == "dead":
            if path in ereg:
                e_counts["dead_registered"] += 1
                continue
            key = ("入口不可解析", rel, no, path)
            judged.append(key + ("",))
            extra[key] = (("绝对路径在任何签出里都不可解析" if path.startswith("/")
                           else "仓库内没有这个文件") + "，且没进死链登记册")
    # 登记册要双向对账：只核"引用的都在册"会看不见"在册但已无用"的那一半。
    # 但"再没被引用"这半边 keyed 在语料上：一处命令形态都没读到时，它不是"没人引用"，
    # 而是"这一面没读到"——与"不知道≠违规"同一条纪律，所以整条反向臂免判并记前提问题。
    reg_stale: list[tuple[str, str]] = []
    reg_unjudged: list[str] = []
    if ereg and not erows:
        problems.append(
            f"entry_face_empty: 死链登记册有 {len(ereg)} 条，而面 ⑤ 的语料一处命令形态都没读到"
            "（入口清单或 `docs/` 没被读到 ⇒「再没被引用」在这棵树上不可判，整条反向臂不判）")
    for path, _note in ([] if (ereg and not erows) else sorted(ereg.items())):
        # 上面那条前提一立，整条反向臂就整体不判：`erows` 为空时"没有 states"
        # 既可能是"真的没人引用"，也可能是"这一面根本没读到语料"，两者不可分。
        states = [s for _r, _n, p, s in erows if p == path]
        if not states:
            reg_stale.append((path, "再没有任何文档引用它 ⇒ 撤登记"))
            continue
        # 「现在处处都能解析」不能只看状态名：`delegated` 也覆盖了"磁盘上就没有这个脚本"
        # 那一格（它由面 ④ 判「脚本缺失」，仍然不是一处跑得动的入口）。所以磁盘事实
        # 要自己核一遍，否则一条注册过的死脚本会因为"没人判它 dead"而永远撤不掉。
        resolved = all(s == "tracked" or (s == "delegated" and (root / path).is_file())
                       for s in states)
        if not resolved:
            continue
        if egit_unknown:
            # 这棵树 git 读不出，`tracked` 是"存在即合规"的降级值，不是"已入库"的证据。
            # 在这里开火等于**降级自己造出一条违规**，还附一句从没证实过的"文件已入库"
            # （第 87 片 §九#2，与"不知道≠违规"这条纪律正面冲突）。只记读数，不判红。
            reg_unjudged.append(path)
            continue
        reg_stale.append((path, "现在处处都能解析（文件在磁盘上，且要么已入库、"
                                "要么由面 ④ 收着同一行）⇒ 该从死链册撤"))
    for path, why in reg_stale:
        key = ("登记册该撤", ENTRY_REGISTER_REL, 0, path)
        judged.append(key + ("",))
        extra[key] = why
    # 点名式豁免必须有牙：写了标记却点不到人 ⇒ 记一条"标记失效"。
    # 语料读不全时不判（与 `entry_face_empty`、`git_unknown` 同一口径：缺席不折成违规）。
    mark_stale, p9 = stale_example_markers(root)
    problems += p9
    if not p9:
        for rel, no, tok in mark_stale:
            key = ("举例标记失效", rel, no, tok)
            judged.append(key + ("",))
            extra[key] = ("这一行的 `aipd-census:example` 点名了它，但按识别面"
                          "扫不到这个 occurrence ⇒ 豁免已经不保护任何东西，"
                          "删掉注释或改成当前的名字")
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
                   "entry_example_stale": [f"{r}:{n}|{t}" for r, n, t in mark_stale],
                   "entry_register_stale": [p for p, _w in reg_stale],
                   "entry_register_stale_unjudged": list(reg_unjudged),
                   "entry_git_unknown": bool(egit_unknown)},
        "report_record_unmatched": [{"doc": d, "line": n, "written": w}
                                    for d, n, w in record_bad],
        "violations": _unique_violations(judged, extra),
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
                 f"占位不判 {es['placeholder']} / 交给面 ④ {es['delegated']} / "
                 f"点名举例 {es['example']}"
                 f"（失效标记 {len(c['entry_example_stale'])} 处）；"
                 f"登记册 {c['entry_register_size']} 条"
                 + (f"，其中该撤 {len(c['entry_register_stale'])} 条"
                    if c["entry_register_stale"] else "")
                 + (f"；另有 {len(c['entry_register_stale_unjudged'])} 条在册条目本应判"
                    f"「该撤」但被降级免判（git 读不出 ⇒ 不让降级自己造红）"
                    if c.get("entry_register_stale_unjudged") else "")
                 + ("；注意：`git ls-tree HEAD` 读不出 ⇒ 未入库那档本轮不判"
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
        if v["field"] == "举例标记失效":
            lines.append(f"  ✗ 举例标记失效 {v['doc']}:{v['line']} 点名 `{v['written']}`"
                         " ⇒ 这一行的 `aipd-census:example` 注释点不到任何 occurrence"
                         "（改名或被删了）；删掉注释或改成当前名字"
                         + (f"（{v.get('detail', '')}）" if v.get("detail") else ""))
            continue
        if v["field"] == "续行":
            lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} 以 `\\` 收尾，而下一行是"
                         "另一条 `aipd` 命令 ⇒ 照抄只会跑到半条命令（要么补完旗子，要么"
                         "拆成两条各自完整的示例）")
            continue
        lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} 写了 `{v['written']}`"
                     " ⇒ 权威面上没有这条命令"
                     + (f"（{v.get('detail', '')}）" if v.get("detail") else ""))
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
        "入口 F：python scripts/zzz_missing_tool.py --zzz 1\n"
        "入口 G：python scripts/nested/zzz_deep.py --x 1\n"
        # 点名式举例：同一行两处引用，**只有被点名的那一处**免判，另一处照判死链。
        # 这就是与 markdownlint 式"整行 disable"的实质差别（它整行吞掉）。
        "入口 H：bash docs/audit/zzz/example.sh 与 python /tmp/zzz_untouched.py"
        " <!-- aipd-census:example docs/audit/zzz/example.sh -->\n"
        # 失效的标记：这一行没有任何命令形态，注释却点了一个名字。
        "说明：本行没有命令形态 <!-- aipd-census:example docs/audit/zzz/ghost_mark.sh -->\n"
        # 第 90 片加宽的四族写法，逐族都要有一行落在这里：撤销臂（battery90 Z4–Z7）
        # 撤掉哪一族，这里就少一行读数——没有这些夹具，加宽与没加宽不可区分。
        "入口 I：bash docs/audit/zzz/../zzz/live.sh 与 python docs/audit/zzz/../gone.py\n"
        "入口 J：python -u /tmp/zzz_flagged.py、python3.11 /tmp/zzz_versioned.py 与 "
        "/abs/tree/.venv/bin/python /tmp/zzz_absinterp.py\n", encoding="utf-8")
    # README 是**面 ④ 的语料**，且第 1 行正是它认得的形状（行首、扁平）；第 2 行是嵌套路径，
    # 面 ④ 的正则 `scripts/([A-Za-z0-9_]+)\.py` 看不见它。两行同文本，差别只在覆盖面。
    (e / "README.md").write_text(
        "python scripts/zzz_missing_tool.py --zzz 1\n"
        "python scripts/nested/zzz_deep.py --x 1\n", encoding="utf-8")
    reg = e / ENTRY_REGISTER_REL
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"entries": [
        {"path": "/tmp/zzz_dead_battery.py", "note": "历轮电池，写在宿主 /tmp，已不可再生"},
        {"path": "docs/audit/zzz/live.sh", "note": "这条其实早就入库了——专打「该撤」那一档"},
        {"path": "docs/audit/zzz/never_cited.sh", "note": "再没被任何文档引用——另一档「该撤」"},
    ]}, ensure_ascii=False), encoding="utf-8")
    # 真 git 仓库：未入库那一档必须由 `git ls-tree -r HEAD` 说，不是由测试注入
    for git_args in (["init", "-q"], ["add", "docs/audit/zzz/live.sh"],
                     ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"]):
        subprocess.run(["git", "-C", str(e), *git_args], capture_output=True, check=True)
    assert tracked_paths(e)[0] == {"docs/audit/zzz/live.sh"}, tracked_paths(e)
    rows, git_unknown, ep = entry_points(e, tracked_override={"docs/audit/zzz/live.sh"})
    state = {p2: s for _r, _n, p2, s in rows}
    assert git_unknown is False and not ep, (git_unknown, ep)
    assert state == {"docs/audit/zzz/live.sh": "tracked",
                     "docs/audit/zzz/loose.py": "untracked",
                     "/tmp/zzz_dead_battery.py": "dead",
                     "tmp/zzz_outside.sh": "dead",
                     "scripts/X.py": "placeholder",
                     "scripts/zzz_missing_tool.py": "dead",
                     "scripts/nested/zzz_deep.py": "dead",
                     "docs/audit/zzz/example.sh": "example",
                     "/tmp/zzz_untouched.py": "dead",
                     "docs/audit/gone.py": "dead",
                     "/tmp/zzz_flagged.py": "dead",
                     "/tmp/zzz_versioned.py": "dead",
                     "/tmp/zzz_absinterp.py": "dead"}, state
    _mark(marks, "面 ⑤ 八格归属各自落位：入库/未入库/三种死链（两条 scripts/ + 绝对 + 仓外）"
                 "/占位/点名举例，且**同一行里未被点名的那条仍判死链**；"
                 "`..` 先归一化再判（`docs/audit/zzz/../gone.py` → `docs/audit/gone.py`），"
                 "短旗、版本后缀、带目录前缀的解释器三族也都读出死链")
    # **让渡可核对**：同一棵树，只是把面 ④ 的行集给它 ⇒ 只有真被那一行收着的才免责。
    f4 = {(rel, no): stem for rel, no, stem, _u in script_rows(e)[0]}
    _r4, _g4, _p4 = entry_points(e, tracked_override={"docs/audit/zzz/live.sh"}, face4=f4)
    tri4 = {(rel, no, p2): s for rel, no, p2, s in _r4}
    assert f4.get(("README.md", 1)) == "zzz_missing_tool", f4
    assert ("README.md", 2) not in f4 and ("docs/audit/zzz/doc.md", 6) not in f4, f4
    assert tri4[("README.md", 1, "scripts/zzz_missing_tool.py")] == "delegated", tri4
    assert tri4[("README.md", 2, "scripts/nested/zzz_deep.py")] == "dead", tri4
    assert tri4[("docs/audit/zzz/doc.md", 6, "scripts/zzz_missing_tool.py")] == "dead", tri4
    _mark(marks, "让渡空洞闭合：面 ④ 语料外（取证文档）与它正则不认的嵌套路径，"
                 "都落回面 ⑤ 判存在性；只有行首扁平那一条才 delegated")
    ereg, rp = load_entry_register(e)
    assert not rp and set(ereg) == {"/tmp/zzz_dead_battery.py", "docs/audit/zzz/live.sh",
                                    "docs/audit/zzz/never_cited.sh"}, (ereg, rp)
    # 端到端：audit() 在真登记册下的判决集合
    rep5 = audit(e)
    fields5 = {(v["written"], v["field"]) for v in rep5["violations"]}
    ent5 = {(v["doc"], v["line"], v["field"]) for v in rep5["violations"]}
    assert ("docs/audit/zzz/loose.py", "入口未入库") in fields5, fields5
    assert ("tmp/zzz_outside.sh", "入口不可解析") in fields5, fields5
    assert "/tmp/zzz_dead_battery.py" not in {w for w, _f in fields5}, fields5
    assert ("docs/audit/zzz/live.sh", "登记册该撤") in fields5, fields5
    assert ("docs/audit/zzz/never_cited.sh", "登记册该撤") in fields5, fields5
    # 免责只发生在"面 ④ 真收了那一行"的位置：同一个 written，README:1 无红、doc.md:6 有红
    assert ("README.md", 1, "入口不可解析") not in ent5, ent5
    assert ("docs/audit/zzz/doc.md", 6, "入口不可解析") in ent5, ent5
    assert ("README.md", 2, "入口不可解析") in ent5, ent5
    assert ("scripts/zzz_missing_tool.py", "脚本缺失") in fields5, fields5
    assert ("docs/audit/zzz/example.sh", "入口不可解析") not in fields5, fields5
    assert ("docs/audit/zzz/ghost_mark.sh", "举例标记失效") in fields5, fields5
    assert rep5["corpus"]["entry_example_stale"] == [
        "docs/audit/zzz/doc.md:9|docs/audit/zzz/ghost_mark.sh"], rep5["corpus"]
    _mark(marks, "面 ⑤ 端到端：未入库开火、未登记死链开火、已登记的不开火、两条「该撤」各按理由"
                 "开火、README:1 由面 ④ 判（脚本缺失）而面 ⑤ 不重复记")
    c5 = rep5["corpus"]["entry_states"]
    assert c5["tracked"] == 2 and c5["untracked"] == 1 and c5["dead"] == 10, c5
    assert c5["dead_registered"] == 1 and c5["placeholder"] == 1 and c5["delegated"] == 1, c5
    assert c5["example"] == 1, c5
    assert rep5["corpus"]["entry_points"] == sum(
        c5[k] for k in ("tracked", "untracked", "dead", "placeholder", "delegated",
                        "example")), c5
    _mark(marks, "面 ⑤ 分桶自证：每行只落一档 ⇒ 六档之和恒等于入口总读数。"
                 "这条是**构造式恒等**（不是能咬人的牙，第 87 片 §九#8）；"
                 "真有牙的是上面逐档的期望值与 `dead == dead_registered` 那条端到端断言")
    # 没有 git 的树：未入库那一档要自动退成"不判"，不能把磁盘上存在的件全判成违规
    ng = tmp / "entry_nogit"
    (ng / "docs/audit/zzz").mkdir(parents=True)
    (ng / "docs/audit/zzz/loose.py").write_text("print(1)\n", encoding="utf-8")
    (ng / "docs/audit/zzz/doc.md").write_text("入口 B：python docs/audit/zzz/loose.py\n",
                                              encoding="utf-8")
    # `git add` 而没 `git commit` 的文件：磁盘上有、HEAD 的树里没有 ⇒ 干净签出拿不到，
    #     必须落 untracked（`git ls-files` 会把它读成已入库，那是第 87 片 §九#7 的洞）。
    (e / "docs" / "audit" / "zzz" / "staged.py").write_text("print(1)\n", encoding="utf-8")
    (e / "docs" / "audit" / "zzz" / "doc2.md").write_text(
        "入口 C：python docs/audit/zzz/staged.py\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(e), "add", "docs/audit/zzz/staged.py"],
                   capture_output=True, check=True)
    _t = tracked_paths(e)[0]
    assert "docs/audit/zzz/staged.py" not in _t, sorted(_t)
    _rows_s, _gs, _ps = entry_points(e)
    _state_s = {p2: s for _r, _n, p2, s in _rows_s}
    assert _state_s["docs/audit/zzz/staged.py"] == "untracked", _state_s
    _mark(marks, "`git add` 未 commit 的取证件判「未入库」——判据读 HEAD 的树，不读索引")
    # ---- 让渡出去的那一行，"在不在 HEAD"仍归面 ⑤ 判；同一个缺陷不记两笔 ----
    # 面 ④ 只看磁盘（`is_file()`）：磁盘上有、HEAD 里没有的脚本，它读成合规。
    # 第 89 片第一版把整行让出去时把这格一起让掉了；把条件写成"面 ④ 收过这一行 ⇒ 只看
    # 入库"又会反过来——文件根本不存在的那条也被叫成 untracked，于是面 ④ 的「脚本缺失」
    # 与这里的「入口未入库」是同一缺陷的两笔红，而且那句解释是假的。两支都要钉。
    (e / "scripts").mkdir(exist_ok=True)
    (e / "scripts" / "zzz_loose.py").write_text(
        "import argparse\nap = argparse.ArgumentParser()\nap.add_argument('--alpha')\n",
        encoding="utf-8")
    (e / "README.md").write_text(
        (e / "README.md").read_text(encoding="utf-8")
        + "python scripts/zzz_loose.py --alpha\n"
        "复算：python /tmp/zzz_twice.py 与 bash /tmp/zzz_twice.py\n", encoding="utf-8")
    f4b = {(rel, no): stem for rel, no, stem, _u in script_rows(e)[0]}
    assert f4b.get(("README.md", 3)) == "zzz_loose", f4b
    _r4b, _g4b, _p4b = entry_points(e, face4=f4b)
    tri4b = {(rel, no, p2): s for rel, no, p2, s in _r4b}
    assert tri4b[("README.md", 3, "scripts/zzz_loose.py")] == "untracked", tri4b
    assert tri4b[("README.md", 1, "scripts/zzz_missing_tool.py")] == "delegated", tri4b
    _mark(marks, "让渡行仍判入库面：磁盘上有而 HEAD 没有 ⇒ untracked；"
                 "磁盘上就没有的那条仍归面 ④ 的「脚本缺失」，不在这里改口")
    rep5c = audit(e)
    line1 = [v for v in rep5c["violations"] if v["doc"] == "README.md" and v["line"] == 1]
    assert {v["field"] for v in line1} == {"脚本缺失"}, line1
    assert {v["field"] for v in rep5c["violations"]
            if v["written"] == "scripts/zzz_loose.py"} == {"入口未入库"}, rep5c["violations"]
    tw = [v for v in rep5c["violations"] if v["written"] == "/tmp/zzz_twice.py"]
    assert len(tw) == 1 and tw[0]["field"] == "入口不可解析", tw
    assert tw[0]["citations"] == 2, tw
    _fired = (rep5c["corpus"]["entry_states"]["dead"]
              - rep5c["corpus"]["entry_states"]["dead_registered"]
              + rep5c["corpus"]["entry_states"]["untracked"])
    assert sum(v["citations"] for v in rep5c["violations"]
               if v["field"] in ("入口不可解析", "入口未入库")) == _fired, rep5c["corpus"]
    _mark(marks, "缺陷清单按（面, 文档, 行, 写法, 位点）去重：同一行两处引用同一个死链只记一笔，"
                 "引用次数留在 `citations` 与 `entry_states` 里；"
                 "而一行只落一档的分桶读数不受去重影响")
    ng_rows, ng_unknown, _ng_p = entry_points(ng)
    assert ng_unknown is True, ng_unknown
    assert [s for _r, _n, _p, s in ng_rows] == ["tracked"], ng_rows
    _mark(marks, "git 读不出时按「存在即合规」降级并把 git_unknown 记进读数，"
                 "不把合成语料/镜像仓整片假红")
    # 同一棵无 git 的树，登记册里挂一条"看起来处处可解析"的相对路径：
    # 旧实现会在这里造出一条从没证实过的"文件已入库 ⇒ 该撤"（§九#2）。
    (ng / "docs" / "audit" / "RECOMPUTE_ENTRYPOINT_REGISTER.json").parent.mkdir(
        parents=True, exist_ok=True)
    (ng / "docs" / "audit" / "RECOMPUTE_ENTRYPOINT_REGISTER.json").write_text(
        json.dumps({"entries": [
            {"path": "docs/audit/zzz/loose.py", "note": "降级会把它读成 tracked"},
            {"path": "docs/audit/zzz/never_written.sh", "note": "这条再没被引用"}]},
            ensure_ascii=False), encoding="utf-8")
    ng_rep = audit(ng)
    ng_f = {(v["written"], v["field"]) for v in ng_rep["violations"]}
    assert ("docs/audit/zzz/loose.py", "登记册该撤") not in ng_f, ng_f
    assert ("docs/audit/zzz/never_written.sh", "登记册该撤") in ng_f, ng_f
    assert ng_rep["corpus"]["entry_register_stale_unjudged"] == ["docs/audit/zzz/loose.py"], \
        ng_rep["corpus"]
    _mark(marks, "降级不自己造红：git 读不出时「已能解析」那一半只记读数"
                 "（`entry_register_stale_unjudged`），而「再没被引用」那一半照旧开火")
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
    "面 ⑤ 对每一条 `<解释器> 路径.py|.sh` 形态的入口判六种归属"
    "（tracked / untracked / dead / delegated / placeholder / example）；"
    "落不到仓库里的必须在本册 `entries` 里逐条列出，否则判红。列进来不等于放过："
    "判据每次现读语料，某条现在又能解析了、或现读扫不到任何引用它的行时，"
    "会以「登记册该撤」反向开火。"
    "`example` 那一档不走本册：它由被引用那一行上的 `<!-- aipd-census:example 路径… -->` "
    "注释**点名**，且点不到 occurrence 时会判「举例标记失效」——豁免不靠一本越来越长的册子攒。"
    "两条边界：① 在 git 读不出的树（合成语料、无 `.git` 的镜像）上，"
    "`tracked` 是「存在即合规」的降级值、不是「已入库」的证据，所以那一轮**不出**"
    "「该撤」判决，只把它们列进 `corpus.entry_register_stale_unjudged` 读数"
    "（第 87 片 §九#2，第 89 片闭合——降级不许自己造红）。"
    "② 反向判据 keyed 在**判据看得见的那种引用**（命令形态）上：把最后一处命令形态"
    "改写成叙述同样会触发「再没被引用」，此时 `dropped` 会把带着手写依据的条目报出来，"
    "但撤不撤仍由人判（§九#3，未修，是措辞与判据的固有接缝）。")

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
    "而不是行内注释；实测其 master README 无行内 ignore 指令）；"
    "mdBook 的 ignore/no_run/compile_fail（把「不跑」说成一种被记录的形状，仅块级）；"
    "markdownlint 的 `<!-- markdownlint-disable-line MDxxx -->`（行级 HTML 注释、"
    "点名哪个检查器，官方明说只能整行）；Vale 的 "
    "`<!-- vale Style.Rule[\"ACT test\"] = NO -->`（点名到具体匹配，但要成对开合）"
    "——本册的 `aipd-census:example` 取前者的行内注释形状 + 后者的点名语义，"
    "两者都不是逐跨（span）级，所以再补一条自家不变量：点了名却点不到就判红")


def emit_register(root: Path, dst: Path) -> dict:
    """把当前判为死链的入口写成/刷新登记册。

    `--emit-register` 的产物里 note 是空的，由人补"为什么不再可复算"。刷新时**按 path
    把旧 note 带过去**：note 是判据真正消费的豁免理由，草案覆盖式重写会把历轮手写的
    依据一起抹掉（第 87 片复核登记过这条，本轮连同快照列降级一并处理）。
    返回 `{"written": n, "missing_notes": [path…], "dropped": [{path, note}…],
    "problems": […], "git_unknown": bool, "refused": ""|"…"}`；
    目标存在但读不出（不是 JSON、或不是字典）时整批不写。
    目标存在但读不出（不是 JSON、或不是字典）、**或语料读不全**（某个 `.md` 读不出）时整批不写：
    后一种情况下"某条从草案里消失"分不清是修好了还是没读到，落盘等于删登记。
    只带了 `path` 而没有 note 的旧条目不算损失，所以 `dropped` 只报**有手写依据却被丢弃**的那些：
    一条死链最常见的离开 `dead` 档的原因不是"修好了"，而是有人把最后一处命令形态改写成了
    叙述（本文件 §八.1 正鼓励这么写）——那种情况下它的依据仍然有效，静默删掉就等于
    把"为什么这条不必再可复算"这条判断从账上抹了。
    """
    srows, _sunbounded, sp = script_rows(root)
    face4_map = {(rel, no): stem for rel, no, stem, _used in srows}
    erows, git_unknown, p7 = entry_points(root, face4=face4_map)
    # 语料读不出与 git 读不出都是**缺席**，不是"这条死链不再存在"。旧实现把两个信号
    # 一起丢进 `_`，于是某个 `.md` 读不出时：那条入口从草案里消失 ⇒ 打印
    # 「本次不再列为死链、但旧册带着手写依据」并退 0，等于让操作员去删一条仍在被引用的登记，
    # 而同棵树上的 `audit()` 会退 2。生成侧与判决侧对"能不能拿这套读数下结论"必须同判。
    problems = list(sp) + list(p7)
    if problems:
        # 缺席先于判决：语料读不全时"某条不在草案里"分不清是修好了还是没读到，
        # 而落盘会把旧册里那些条目**删掉**。拒写，把原因交给操作员。
        return {"written": 0, "missing_notes": [], "dropped": [], "problems": problems,
                "git_unknown": git_unknown,
                "refused": "语料读不全，草案不落盘以免删掉仍在被引用的登记："
                           + "；".join(problems)}
    by: dict[str, list[str]] = {}
    for rel, no, path, state in erows:
        if state == "dead":
            by.setdefault(path, []).append(f"{rel}:{no}")
    old_notes: dict[str, str] = {}
    if dst.is_file():
        try:
            existing = json.loads(dst.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"written": 0, "missing_notes": [], "dropped": [], "problems": problems,
                    "git_unknown": git_unknown,
                    "refused": f"目标登记册读不出，草案不落盘以免抹掉手写依据：{exc}"}
        if not isinstance(existing, dict):
            return {"written": 0, "missing_notes": [], "dropped": [], "problems": problems,
                    "git_unknown": git_unknown,
                    "refused": f"目标登记册不是字典（读到 {type(existing).__name__}），"
                               "草案不落盘以免抹掉手写依据"}
        for e in existing.get("entries", []):
            note = str(e.get("note") or "")
            if note:
                old_notes[str(e.get("path") or "")] = note
    dropped = [{"path": p, "note": n} for p, n in sorted(old_notes.items()) if p not in by]
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
            "dropped": dropped, "problems": problems,
            "git_unknown": git_unknown, "refused": ""}


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
        for d in got["dropped"]:
            print(f"  本次不再列为死链、但旧册带着手写依据：{d['path']}\n"
                  f"    依据原文：{d['note'][:200]}")
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
