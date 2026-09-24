"""SKILL.md 的命令面必须与 CLI 契约同源（F-EXEC-02 接线时量出的漂移）。

`skill_quality_audit.py` 只问「public 命令有没有被声明」，不问「散文里写的总数
对不对」——本轮新增 1 条命令时，SKILL.md 的「主线共 38 个」就已经比契约少 1：
也就是说这个数字在**本轮之前**就已经漂了（实测 public=39，文里写 38）。
所以这里把总数与逐条名字都按权威表核对，而不是再靠人记。
"""
from __future__ import annotations

import re
from pathlib import Path

from aipd_os.cli.command_contract import CommandStatus, get_all_commands

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "SKILL.md"

COUNT_RE = re.compile(r"主线共 (\d+) 个")


def _public_commands():
    return sorted(e.name for e in get_all_commands() if e.status == CommandStatus.PUBLIC)


def _count_disagrees(text: str) -> bool:
    """True 表示 SKILL 的总数与契约不一致（句式失配也算不一致）。"""
    m = COUNT_RE.search(text)
    if not m:
        return True
    return int(m.group(1)) != len(_public_commands())


def test_skill_declared_public_count_matches_contract() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert not _count_disagrees(text), (
        f"SKILL.md 的「主线共 N 个」与契约里的 "
        f"{len(_public_commands())} 条 public 命令对不上")


def test_every_public_command_is_named_in_skill() -> None:
    text = SKILL.read_text(encoding="utf-8")
    missing = [name for name in _public_commands() if f"`{name}`" not in text]
    assert not missing, f"SKILL.md 未逐条声明的 public 命令：{missing}"


def test_checker_can_see_a_wrong_count() -> None:
    """注入反证：把总数改错时必须红（否则上面的断言只是巧合通过）。"""
    text = SKILL.read_text(encoding="utf-8")
    m = COUNT_RE.search(text)
    assert m, "句式漂移"
    mutated = text.replace(m.group(0), f"主线共 {int(m.group(1)) + 7} 个", 1)
    assert mutated != text, "注入没改动输入 ⇒ 这条控制什么都没验"
    assert _count_disagrees(mutated), "总数改错仍不判红 ⇒ 检查器是假的"
    # 句式漂移同样必须红，不能静默放过
    assert _count_disagrees("主线共 N 个")
