"""Task 4 (AIPD-OS v5.3)：命令覆盖一致性测试。

三向：契约/文档声明的命令 ↔ CLI 注册的命令 ↔ 常驻测试真调过的命令。

本文件原先那两条「声明 ⊆ 注册」与「注册 ⊇ 声明」是把 SKILL.md 从
**含「一键命令」的那一行**往后收集反引号命令名——而 SKILL.md 里那一行是标题
`## 0. 一键命令`，下一行是空行，收集循环第一下就 break ⇒ **解析结果恒为 0 条**。
0 ⊆ 任何东西恒真，所以两条断言六轮来一直绿着，报告里同时印出
「声明命令数：0 / 已注册但未声明：66」这种自相矛盾的读数。
（同文件后半的 F-CLI-01 早就给解析器面配了注入反证，这两条却没有——
「探针能不能匹配」这件事在整个文件里只被考虑了一次。）

现在的口径：

- **声明面只有一个权威**：CLI 契约 ``command_contract``（``PUBLIC`` / ``DEPRECATED``
  / ``INTERNAL``）。SKILL.md 的解析交给 ``scripts/skill_quality_audit.py`` 里那份
  **按小节边界取段**的实现（CI 与本文共用一份，不再各写一个解析器），
  并给它配注入反证：真实清单解析出 56 条、坏句式解析出 0 条都必须能判红。
- **「注册 ⊆ 真调」不再是只报不判**：读数换成 ``scripts/command_surface_census.py``
  的 argv 位判据，由 ``tests/test_command_surface_census.py`` 钉成双向棘轮。
  旧的子串探针两头都错（15 条真调过被记成未测、7 条零证据被记成已测、另 6 条判对但理由错），
  所以"不可判定 ⇒ 不失败"这个结论本身就是坏探针造出来的。
"""
from __future__ import annotations

import sys
from pathlib import Path

from aipd_os.cli.command_contract import (
    ALL_REGISTERED_COMMANDS,
    DEPRECATED_COMMANDS,
    INTERNAL_COMMANDS,
    PUBLIC_COMMANDS,
)
from aipd_os.cli.commands import COMMAND_FUNCS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import skill_quality_audit as skill_audit  # noqa: E402


def _registered_commands() -> set[str]:
    return set(COMMAND_FUNCS.keys())


def _contract_commands() -> set[str]:
    """契约里登记过的命令：public ∪ deprecated ∪ internal（三态并集）。"""
    return set(PUBLIC_COMMANDS) | set(DEPRECATED_COMMANDS) | set(INTERNAL_COMMANDS)


def _declared_commands() -> set[str]:
    """SKILL.md「## 0.」清单声明的命令——用 CI 那一份解析器，不另写一套。"""
    # 解析器在 scripts/ 下、不在 mypy 的检索路径上，返回值在类型层面是 Any：
    # 先按 `declared_from_skill()` 自己声明的 set[str] 收下，再进下面的集合差。
    declared: set[str] = skill_audit.declared_from_skill(
        (ROOT / "SKILL.md").read_text(encoding="utf-8"))
    return declared


def _tested_commands() -> set[str]:
    """常驻测试里**走过 CLI 入口**（argv 位/转发器）的已注册命令。"""
    import command_surface_census as census

    _, shapes, alias_of, handler_of, siblings = census._repo_shapes()
    scan = census.scan_corpus(ROOT / "tests", _registered_commands(), shapes,
                              alias_of=alias_of, handler_of=handler_of,
                              handler_siblings=siblings)
    return {c for c, t in scan["tiers"].items() if t == census.TIER_CLI}


def test_registered_matches_the_contract_exactly() -> None:
    """注册表与契约必须**恰好**相等（双向）：只有一边动过就红。"""
    registered, contract = _registered_commands(), _contract_commands()
    assert registered == contract == set(ALL_REGISTERED_COMMANDS), (
        f"只在注册表：{sorted(registered - contract)}；"
        f"只在契约：{sorted(contract - registered)}")


def test_declared_commands_are_registered() -> None:
    """文档声明的每个命令都必须在 CLI 中注册（声明 ⊆ 注册），且声明面非空。"""
    declared = _declared_commands()
    assert declared, (
        "SKILL.md 解析出 0 条 ⇒ 「声明 ⊆ 注册」是空转断言，先修解析器再谈一致")
    missing = declared - _registered_commands()
    assert not missing, f"文档声明但未注册的命令：{sorted(missing)}"


def test_declared_set_equals_public_contract() -> None:
    """SKILL.md 的声明集合必须与契约的 public 面相等（不多不少、不靠人记）。"""
    declared, public = _declared_commands(), set(PUBLIC_COMMANDS)
    assert declared == public, (
        f"文档多出的命令：{sorted(declared - public)}；"
        f"文档漏声明的 public 命令：{sorted(public - declared)}")


def test_skill_parser_can_fire() -> None:
    """注入反证：解析器必须既能读出真清单、也能对坏句式读出 0（恒 0 要判红）。"""
    good = "## 0. 一键命令\n\n- 组：`alpha` / `beta two`\n\n## 1. 别的\n- `gamma`\n"
    assert skill_audit.declared_from_skill(good) == {"alpha", "beta two"}
    # 小节外的反引号词不算声明（SECURITY.md 这类文件名就在正文里出现）
    assert "gamma" not in skill_audit.declared_from_skill(good)
    # 旧解析器正是栽在这个形状上：标题行下一行是空行
    assert skill_audit.declared_from_skill("## 0. 一键命令\n\n- 组：`alpha`\n") == {"alpha"}
    assert skill_audit.declared_from_skill("# 没有零号小节\n`alpha`\n") == set()


def test_tested_commands_are_registered() -> None:
    """真调过的命令必须都是真实注册的命令（测试 ⊆ 注册）。"""
    assert _tested_commands() <= _registered_commands()


def test_command_coverage_report() -> None:
    """三向一致性总览。缺口判定在 `test_command_surface_census.py` 的棘轮里。"""
    declared = _declared_commands()
    registered = _registered_commands()
    tested = _tested_commands()

    registered_untested = sorted(registered - tested)
    declared_untested = sorted(declared - tested)
    registered_undeclared = sorted(registered - declared)

    print(f"契约 public 声明命令数：{len(declared)}")
    print(f"注册命令数：{len(registered)}")
    print(f"走过 CLI 入口的命令数：{len(tested)}")
    print(f"已声明但未真调（{len(declared_untested)}）：{declared_untested}")
    print(f"已注册但未真调（{len(registered_untested)}）：{registered_untested}")
    print(f"已注册但未声明（{len(registered_undeclared)}）：{registered_undeclared}")
    # 这里原先断言"必有未测缺口"——那是把第 39 片当时的现状当成了应然，
    # 第 40 片补满 66 条后它自己就成了假红。缺口的存在性由棘轮与闭合账管，报告只管报。


# --------------------------------------------------------------------------
# F-CLI-01：真正的产品面是 argparse 解析器，不是 COMMAND_FUNCS 这张表
# --------------------------------------------------------------------------
#
# 上面三条一致性检查比的是「契约 ↔ COMMAND_FUNCS ↔ 文档」——三份内部副本互相对表。
# 实测：`validation plan/list/show/import`、`issue list/show/resolve`、`readiness check`
# 八条命令在契约里是 PUBLIC、在 SKILL.md 里被逐条声明、函数实现与测试也都在，
# 但 `build_parser()` 从来没有为它们建 subparser ⇒ `aipd validation import` 直接
# "invalid choice"。也就是说这三份副本可以同时对表而产品面上根本不存在这条命令。
# 因此这里把**解析器对象本身**当成权威读数来核对。

import argparse  # noqa: E402

from aipd_os.cli.main import build_parser  # noqa: E402


def _parseable_commands() -> set[str]:
    """从真实 parser 对象里解析出所有可输入的 command / command + verb。"""
    parser = build_parser()
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert subs, "解析器没有子命令动作 ⇒ 本探针在空转"
    top = subs[0]
    out: set[str] = set(top.choices)
    for name, sub in top.choices.items():
        for action in sub._actions:
            if isinstance(action, argparse._SubParsersAction):
                out.update(f"{name} {verb}" for verb in action.choices)
    return out


def test_every_registered_command_is_parseable() -> None:
    """注册进 COMMAND_FUNCS 的每条命令都必须真能被 argparse 接受。"""
    parseable = _parseable_commands()
    missing = sorted(set(COMMAND_FUNCS) - parseable - {"usage"})
    assert not missing, (
        f"这些命令已登记分发但 CLI 解析器没有接线（用户输入即 invalid choice）："
        f"{missing}")


def test_parser_probe_can_fire() -> None:
    """注入反证：解析器面必须能判红（探针读到 0 条或把已接线命令读成缺失都算失效）。"""
    parseable = _parseable_commands()
    assert {"bom add", "quote apply", "outbox drain"} <= parseable, "正向对照失配"
    assert "validation import" in parseable, (
        "validation import 未接线 ⇒ 上一条测试应当判红，而不是被跳过")
