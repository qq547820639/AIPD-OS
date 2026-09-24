"""Task 4 (AIPD-OS v5.3)：命令覆盖一致性测试。

对三类命令集合做三向一致性校验：

1. ``declared_commands``  —— 从 ``SKILL.md`` / ``README.md`` 的一键命令清单解析而来；
2. ``registered_commands`` —— 来自 CLI 的 ``COMMAND_FUNCS`` 分发表；
3. ``tested_commands``    —— 在 ``tests/`` 中被至少一个测试函数引用/覆盖的命令。

已知情况：``SKILL.md`` 只声明了 v5.0 的 10 个命令，而实现已注册 27 个命令
（v5.1 新增 16 个）。因此本测试在「声明侧」保持宽松：
- 硬性断言「声明 ⊆ 注册」（文档声明的命令必须真实注册）；
- 注册集合是声明集合的超集（注册命令可以多于文档声明）；
- 「注册 ⊆ 测试」因 ``run-supervisor`` 等命令暂无测试而不可判定，故只上报不失败，
  由独立的 ``SKILL.md`` 刷新任务补齐声明。
"""
from __future__ import annotations

import re
from pathlib import Path

from aipd_os.cli.commands import COMMAND_FUNCS

ROOT = Path(__file__).resolve().parent.parent

# 命令名：单/双词小写（如 "manual plan"、"cad preflight"、"release check"）
_CMD_NAME = r"[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)?"
_BACKTICK_RE = re.compile(r"`(" + _CMD_NAME + r")`")
_PAREN_RE = re.compile(r"（([^（）]+)）")


def _registered_commands() -> set[str]:
    return set(COMMAND_FUNCS.keys())


def _declared_commands() -> set[str]:
    """解析 SKILL.md / README.md 中「一键命令」清单里实际声明的命令。"""
    declared: set[str] = set()

    # SKILL.md：从含「一键命令」的行开始，向后收集反引号包裹的命令名
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(skill) if "一键命令" in ln)
    for ln in skill[start:]:
        if "`" not in ln:
            break
        declared.update(_BACKTICK_RE.findall(ln))

    # README.md：处理所有含「一键命令」的行
    readme = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    for ln in readme:
        if "一键命令" not in ln:
            continue
        # 反引号包裹的命令（v5.1 的 16 个，含双词命令）
        declared.update(_BACKTICK_RE.findall(ln))
        # 纯文本列表（v5.0 的 10 个，形如 “init-project / restore-project / ...”）
        for inner in _PAREN_RE.findall(ln):
            tokens = [t.strip() for t in inner.split("/")]
            declared.update(t for t in tokens if re.fullmatch(_CMD_NAME, t))
    return declared


def _tested_commands() -> set[str]:
    """在 tests/ 中被至少一个测试引用/覆盖的已注册命令。"""
    blob = ""
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        if p.name == "test_command_coverage.py":
            continue  # 排除本文件自身，避免文档字符串自引用造成误判
        blob += p.read_text(encoding="utf-8") + "\n"
    return {cmd for cmd in _registered_commands() if cmd in blob}


def test_declared_commands_are_registered() -> None:
    """文档声明的每个命令都必须在 CLI 中注册（声明 ⊆ 注册）。"""
    missing = _declared_commands() - _registered_commands()
    assert not missing, f"文档声明但未注册的命令：{sorted(missing)}"


def test_registered_is_superset_of_declared() -> None:
    """注册集合必须是声明集合的超集（注册 ≥ 声明）。"""
    assert _registered_commands() >= _declared_commands()


def test_tested_commands_are_registered() -> None:
    """测试中引用/覆盖的命令必须都是真实注册的命令（测试 ⊆ 注册）。"""
    assert _tested_commands() <= _registered_commands()


def test_command_coverage_report() -> None:
    """三向一致性总览（信息性报告；注册但未测试/未声明的缺口不失败）。"""
    declared = _declared_commands()
    registered = _registered_commands()
    tested = _tested_commands()

    registered_untested = sorted(registered - tested)
    declared_untested = sorted(declared - tested)
    registered_undeclared = sorted(registered - declared)

    print(f"声明命令数：{len(declared)}")
    print(f"注册命令数：{len(registered)}")
    print(f"测试覆盖命令数：{len(tested)}")
    print(f"已声明但未测试（{len(declared_untested)}）：{declared_untested}")
    print(f"已注册但未测试（{len(registered_untested)}）：{registered_untested}")
    print(f"已注册但未声明（{len(registered_undeclared)}）：{registered_undeclared}")


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
