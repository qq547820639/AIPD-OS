#!/usr/bin/env python3
"""CLI 命令面「有没有被常驻用例真调过」普查（F-CLI-COV 第 39 片）。

它回答的问题只有一句：**这条命令的 CLI 入口（argv → argparse → 分发）在常驻测试里
被走过没有？** 走没走过不是文本问题，所以判据用 AST 读调用形态，不用子串匹配。

为什么换判据（本轮量出的读数，全部可复算）：
`tests/test_command_coverage.py` 原来把 `tests/` 整个拼成一个大字符串，再用
`cmd in blob` 判「被测」。同一个命令名在测试里有好几种毫不相干的出现方式，
于是读数两头都错（两错互相抵掉，47/66 这个总数看着还挺合理）：

- **假未测 15 条**：`main(["drawing", "dfm", ...])` 是两个相邻字符串常量，
  子串 `"drawing dfm"` 匹配不上；`main(["eco", *argv, ...])` 这种转发器更是看不见
  （eco 四条命令全靠它）。受影响：`bom release`、`drawing assembly-step(s)`、
  `drawing dfm`、`eco` 四条、`issue` 三条、`readiness check`、`validation` 三条。
- **假已测 7 条**（一次 CLI 没走，也没有任何别的凭据）：`from ezdxf import recover`
  顶了 `recover`，dict 键 `"version"` 顶了 `version`，`test_new_commands_registered`
  里那张名字清单顶了 `cad preflight`，`owner_dashboard` / `onboarding` / `def _reset()`
  这类同名 import 顶了 `dashboard` / `onboard` / `reset`，而 `ui` 干脆撞在
  `builtin`、`build` 这些词的中间——两个字符的名字连子串判据都不该信。
- **另有 6 条判对但理由错**：`cad build` / `package` / `resume` / `test` 只被
  deprecated 别名走过，`doctor` 只被直接调处理函数走过，`outbox drain` 调的是
  与 `outbox review` 共用的 `cmd_outbox`——都不是「这条命令的 CLI 入口被走过」。

档位（每条命令恰好落一档，Σ 档位 == 分母是硬断言）：

- ``cli``               argv 位真调：`main(["bom", "release", ...])` 或经转发器
                        `main(["eco", *argv, ...])` 且实参里带上该 verb。
- ``alias``             只被 deprecated 别名调过（别名↔真名由 CLI 契约的
                        ``replacement`` 派生，不手抄）。用户输入的公开名没走过。
- ``handler``           只被直接调用处理函数（`cmd_doctor(...)`）——到得了处理器，
                        到不了 argparse 面。
- ``handler_ambiguous`` 同上，但那个处理函数被多条命令共用（`cmd_outbox` 同时管
                        drain 与 review），直接调用分不清 verb，所以不算证据。
- ``none``              测试里一次都没有真调过这条命令的 CLI 面。

本脚本是**诊断档**：它只出错数，不判放行；棘轮在
`tests/test_command_surface_census.py` 里钉（低于 ``cli`` 的集合必须与登记基线
完全相等，双向）。退出码：0 读数可信，4 读数不可信（语料为空/解析失败/Σ 对不上）。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# 量具自身与它的用例、以及只做文本核对的同类量具：按字面量反查的探针必须排除自己，
# 否则"写一条断言就把分母 +1"。
EXCLUDE_TESTS = (
    "test_command_coverage.py",
    "test_command_surface_census.py",
    "test_skill_command_surface.py",
    "test_gate_runners.py",
)

TIER_CLI = "cli"
TIER_ALIAS = "alias"
TIER_HANDLER = "handler"
TIER_HANDLER_AMBIGUOUS = "handler_ambiguous"
TIER_NONE = "none"

TIER_ORDER = (TIER_CLI, TIER_ALIAS, TIER_HANDLER, TIER_HANDLER_AMBIGUOUS, TIER_NONE)


def _txt(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


@dataclass(frozen=True)
class Shapes:
    """命令面的形状：单 token 命令、双 token 命令的 (头 → verb 集合)。"""

    singles: frozenset[str]
    heads: dict[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def of(cls, commands: Iterable[str]) -> Shapes:
        singles: set[str] = set()
        heads: dict[str, set[str]] = {}
        for cmd in commands:
            parts = cmd.split(" ", 1)
            if len(parts) == 1:
                singles.add(cmd)
            else:
                heads.setdefault(parts[0], set()).add(parts[1])
        return cls(frozenset(singles), {k: frozenset(v) for k, v in heads.items()})

    def verb_of(self, head: str, verb: str) -> str | None:
        if verb in self.heads.get(head, frozenset()):
            return f"{head} {verb}"
        return None


def scan_corpus(tests_dir: Path, commands: Iterable[str], shapes: Shapes, *,
                alias_of: Mapping[str, str] | None = None,
                handler_of: Mapping[str, str] | None = None,
                handler_siblings: Mapping[str, tuple[str, ...]] | None = None,
                exclude: tuple[str, ...] = EXCLUDE_TESTS) -> dict[str, Any]:
    """扫一目录的测试源码，按调用形态给出每条命令的证据。

    ``commands`` 是分母（档位表按它闭集生成，Σ 档位 == 分母才成立）；
    ``alias_of`` 是 别名命令 → 真名命令；``handler_of`` 是 命令 → 处理函数名；
    ``handler_siblings`` 是 处理函数名 → 共用它的命令清单（>1 即歧义）。
    """
    commands = sorted(set(commands))
    alias_of = alias_of or {}
    handler_of = handler_of or {}
    handler_siblings = handler_siblings or {}
    cmds_by_handler: dict[str, list[str]] = {}
    for cmd, hname in handler_of.items():
        cmds_by_handler.setdefault(hname, []).append(cmd)

    cli: dict[str, list[str]] = {}
    alias_hits: dict[str, list[str]] = {}
    handler_hits: dict[str, list[str]] = {}
    ambiguous_hits: dict[str, list[str]] = {}
    parse_failures: list[str] = []
    files_read = 0

    def add(bucket: dict[str, list[str]], cmd: str, where: str) -> None:
        at = bucket.setdefault(cmd, [])
        if where not in at:
            at.append(where)

    def record_head(head: str, where: str) -> None:
        """一个出现在 argv 头部的 token：可能是单 token 命令，也可能是别名。"""
        if head in shapes.singles:
            add(cli, head, where)
        real = alias_of.get(head)
        if real:
            add(alias_hits, real, f"{where}（经别名 {head}）")

    for path in sorted(tests_dir.glob("test_*.py")):
        if path.name in exclude:
            continue
        files_read += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:      # 解析失败不能静默跳过：那一档读数就没了依据
            parse_failures.append(f"{path.name}: {exc}")
            continue
        stem = path.name[:-3]

        # 1) 转发器：函数体里出现 `["<头>", *argv, ...]` ⇒ 该函数的实参带 verb 即算调过
        runners: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for sub in ast.walk(node):
                if not (isinstance(sub, ast.List) and sub.elts):
                    continue
                head = _txt(sub.elts[0])
                if head in shapes.heads and any(isinstance(e, ast.Starred) for e in sub.elts):
                    runners.setdefault(node.name, set()).add(head)

        for node in ast.walk(tree):
            # 2) argv 列表：单 token 命令看首位；双 token 命令看相邻对（首位或带前缀都行）
            if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
                head = _txt(node.elts[0])
                if head is not None:
                    record_head(head, f"{stem}:{node.lineno}")
                for i in range(len(node.elts) - 1):
                    a, b = _txt(node.elts[i]), _txt(node.elts[i + 1])
                    if a is None or b is None:
                        continue
                    pair = shapes.verb_of(a, b)
                    if pair:
                        add(cli, pair, f"{stem}:{node.lineno}")
            # 3) 转发器的调用点：实参里出现该头的 verb 才算（交集，避免把 "改孔位" 当命令）
            elif isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in runners:
                    for arg in node.args:
                        verb = _txt(arg)
                        if verb is None:
                            continue
                        for head in runners[name]:
                            spread = shapes.verb_of(head, verb)
                            if spread:
                                add(cli, spread, f"{stem}:{node.lineno}（经转发器 {name}）")
                # 4) 直接调处理函数：到不了 argparse 面，单独一档；
                #    共用处理函数（cmd_outbox 同管两条命令）分不清 verb，另记一档
                for cmd in cmds_by_handler.get(name or "", ()):
                    where = f"{stem}:{node.lineno}"
                    if len(handler_siblings.get(name or "", (cmd,))) > 1:
                        add(ambiguous_hits, cmd, where)
                    else:
                        add(handler_hits, cmd, where)

    tiers: dict[str, str] = {}
    evidence: dict[str, list[str]] = {}
    for cmd in commands:
        if cmd in cli:
            tiers[cmd] = TIER_CLI
            evidence[cmd] = cli[cmd]
        elif cmd in alias_hits:
            tiers[cmd] = TIER_ALIAS
            evidence[cmd] = alias_hits[cmd]
        elif cmd in handler_hits:
            tiers[cmd] = TIER_HANDLER
            evidence[cmd] = handler_hits[cmd]
        elif cmd in ambiguous_hits:
            h = handler_of[cmd]
            tiers[cmd] = TIER_HANDLER_AMBIGUOUS
            evidence[cmd] = [f"{'; '.join(ambiguous_hits[cmd])} 调的是共用处理函数 {h}"
                             f"（{'、'.join(handler_siblings[h])} 共用，分不清 verb）"]
        else:
            tiers[cmd] = TIER_NONE
            evidence[cmd] = []

    return {
        "files_read": files_read,
        "parse_failures": parse_failures,
        "tiers": tiers,
        "evidence": evidence,
    }


def _repo_shapes() -> tuple[list[str], Shapes, dict[str, str], dict[str, str],
                            dict[str, tuple[str, ...]]]:
    from aipd_os.cli.command_contract import CommandStatus, get_all_commands
    from aipd_os.cli.commands import COMMAND_FUNCS

    commands = sorted(COMMAND_FUNCS)
    alias_of = {e.name: e.replacement for e in get_all_commands()
                if e.status is CommandStatus.DEPRECATED and e.replacement}
    handler_of = {c: str(COMMAND_FUNCS[c].__name__) for c in commands}
    siblings: dict[str, list[str]] = {}
    for cmd, name in handler_of.items():
        siblings.setdefault(name, []).append(cmd)
    return commands, Shapes.of(commands), alias_of, handler_of, {
        k: tuple(v) for k, v in siblings.items()}


def audit(repo: Path) -> dict[str, Any]:
    commands, shapes, alias_of, handler_of, siblings = _repo_shapes()
    result = scan_corpus(repo / "tests", commands, shapes, alias_of=alias_of,
                         handler_of=handler_of, handler_siblings=siblings)
    tiers = result["tiers"]
    problems: list[str] = []
    if not result["files_read"]:
        problems.append("empty_corpus：一册测试源码都没读到，档位读数没有依据")
    if result["parse_failures"]:
        problems.append("parse_failures：" + "; ".join(result["parse_failures"]))
    missing = sorted(set(commands) - set(tiers))
    extra = sorted(set(tiers) - set(commands))
    if missing or extra:
        problems.append(f"Σ 对不上：分母 {len(commands)}，档位 {len(tiers)}，"
                        f"缺 {missing} 多 {extra}")

    buckets: dict[str, list[str]] = {t: [] for t in TIER_ORDER}
    for cmd, tier in tiers.items():
        buckets[tier].append(cmd)
    for lst in buckets.values():
        lst.sort()

    return {
        "ok": not problems,
        "problems": problems,
        "denominator": len(commands),
        "files_read": result["files_read"],
        "parse_failures": result["parse_failures"],
        "tiers": tiers,
        "evidence": result["evidence"],
        "buckets": buckets,
        "below_cli": sorted(c for c, t in tiers.items() if t != TIER_CLI),
    }


def render(report: dict[str, Any]) -> str:
    lines = ["=" * 62,
             "CLI 命令面真调普查（argv 位 / 别名 / 直接调处理函数 / 无证据）",
             f"已注册命令 {report['denominator']} 条，读过的测试文件 "
             f"{report['files_read']} 个",
             "=" * 62]
    for tier in TIER_ORDER:
        names = report["buckets"][tier]
        lines.append(f"[{tier}] {len(names)} 条")
        if tier != TIER_CLI:
            for cmd in names:
                why = report["evidence"].get(cmd) or []
                lines.append(f"    {cmd:24} {'; '.join(why) if why else '无证据'}")
    lines.append(f"低于 cli 档合计：{len(report['below_cli'])} 条")
    if report["problems"]:
        lines.append("读数不可信：")
        lines.extend(f"  ! {p}" for p in report["problems"])
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 判据自测：合成语料，正反两向都要开火
# --------------------------------------------------------------------------

_SYN_SINGLES = ("doctor", "recover", "version", "reset")
_SYN_PAIRS = ("bom release", "drawing dfm", "eco create", "eco show")
SYN_COMMANDS = tuple(_SYN_SINGLES) + _SYN_PAIRS


def _write(dir_path: Path, name: str, source: str) -> None:
    (dir_path / name).write_text(source, encoding="utf-8")


def _self_test(tmp_root: Path) -> int:
    shapes = Shapes.of(SYN_COMMANDS)
    alias_of = {"rescue": "recover"}
    handler_of = {"doctor": "cmd_doctor", "reset": "cmd_reset",
                  "bom release": "cmd_bom", "drawing dfm": "cmd_bom"}
    siblings = {"cmd_bom": ("bom release", "drawing dfm")}

    cases: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def corpus(dirname: str, files: dict[str, str]) -> dict[str, str]:
        d = tmp_root / dirname
        d.mkdir(parents=True, exist_ok=True)
        for name, src in files.items():
            _write(d, name, src)
        out = scan_corpus(d, SYN_COMMANDS, shapes, alias_of=alias_of,
                          handler_of=handler_of, handler_siblings=siblings)
        return {str(k): str(v) for k, v in out["tiers"].items()}

    # A 正向：argv 位真调必须判 cli
    t = corpus("a", {"test_a.py": "def test_x(main):\n"
                                 "    main([\"bom\", \"release\", \"--db\", \"d\"])\n"})
    cases.append(("argv 直调判 cli", t, {"bom release": TIER_CLI}))

    # B 正向（旧探针的盲区）：转发器带 verb 必须判 cli
    t = corpus("b", {"test_b.py":
                     "def _run(main, *argv):\n"
                     "    return main([\"eco\", *argv, \"--db\", \"d\"])\n"
                     "def test_y(main):\n"
                     "    _run(main, \"create\", \"--title\", \"t\")\n"})
    cases.append(("转发器判 cli（旧探针盲区）", t, {"eco create": TIER_CLI}))

    # C 反向：同名字符串不是证据（dict 键 / 模块属性 / 注释 / docstring）
    t = corpus("c", {"test_c.py":
                     "from ezdxf import recover\n"
                     "K = {\"version\": 1, \"reset\": True}\n"
                     "# aipd doctor 一下\n"
                     "def test_z():\n"
                     "    \"\"\"跑 aipd doctor 看引导\"\"\"\n"
                     "    assert recover.readfile\n"})
    cases.append(("同名字符串不开火", t, {"version": TIER_NONE, "recover": TIER_NONE,
                                       "reset": TIER_NONE, "doctor": TIER_NONE}))

    # D 极性：别名 argv 只给真名 alias 档，不给 cli 档
    t = corpus("d", {"test_d.py": "def test_w(main):\n"
                                 "    main([\"rescue\", \"--db\", \"d\"])\n"})
    cases.append(("别名只到 alias 档", t, {"recover": TIER_ALIAS}))

    # E 极性：直接调处理函数只到 handler 档
    t = corpus("e", {"test_e.py": "def test_v():\n    cmd_doctor(Args())\n"})
    cases.append(("直接调处理函数只到 handler 档", t, {"doctor": TIER_HANDLER}))

    # F 共用处理函数不算证据：cmd_bom 同时管两条命令，调它分不清 verb
    t = corpus("f", {"test_f.py": "def test_u():\n    cmd_bom(Args())\n"})
    cases.append(("共用处理函数判 handler_ambiguous", t,
                  {"bom release": TIER_HANDLER_AMBIGUOUS,
                   "drawing dfm": TIER_HANDLER_AMBIGUOUS}))

    # G 转发器不得把无关实参当 verb（"改孔位" 不是命令）
    t = corpus("g", {"test_g.py":
                     "def _run(main, *argv):\n"
                     "    return main([\"eco\", *argv])\n"
                     "def test_t(main):\n"
                     "    _run(main, \"改孔位\")\n"})
    cases.append(("转发器实参须与 verb 求交", t, {"eco create": TIER_NONE,
                                               "eco show": TIER_NONE}))

    # H 自排除：量具自己的用例文件不算证据
    t = corpus("h", {"test_command_surface_census.py":
                     "main([\"bom\", \"release\"])\n"})
    cases.append(("量具自身文件不算证据", t, {"bom release": TIER_NONE}))

    survived: list[str] = []
    for label, tiers, expect in cases:
        wrong = {k: (tiers.get(k), want) for k, want in expect.items()
                 if tiers.get(k) != want}
        if wrong:
            survived.append(f"{label}: {wrong}")
        print(f"{'✓立住' if not wrong else '✗没立住'} {label}")

    # I 解析失败必须被记成问题，而不是静默少读
    bad = tmp_root / "i"
    bad.mkdir(parents=True, exist_ok=True)
    _write(bad, "test_i.py", "def broken(:\n")
    out = scan_corpus(bad, SYN_COMMANDS, shapes, alias_of=alias_of,
                      handler_of=handler_of, handler_siblings=siblings)
    if not out["parse_failures"]:
        survived.append("I 语法错误的测试文件被静默跳过")
    print(f"{'✓开火' if out['parse_failures'] else '✗没开火'} 语法错误不静默跳过")

    # J Σ 档位 == 分母：每条合成命令都恰好一档
    if sorted(out["tiers"]) != sorted(SYN_COMMANDS):
        survived.append(f"J Σ 档位 ≠ 分母：{sorted(out['tiers'])}")
    print(f"{'✓立住' if not survived else '✗没立住'} Σ 档位 == 分母")

    if survived:
        print("反证没立住的判据：")
        for s in survived:
            print("  ", s)
        return 1
    print(f"--self-test：{len(cases) + 2}/{len(cases) + 2} 条注入都被抓住")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CLI 命令面真调普查")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--json", dest="json_out", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true",
                    help="注入反证：每条判据都必须能红/该不开的都不开")
    args = ap.parse_args(argv)
    root = Path(args.repo).resolve()

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))

    report = audit(root)
    print(render(report))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2,
                                                  ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return 0 if report["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
