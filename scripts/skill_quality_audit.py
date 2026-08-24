#!/usr/bin/env python3
"""AIPD-OS SKILL.md 质量自审脚本（v5.10 重构）。

运行：``python3 scripts/skill_quality_audit.py``

审计内容：
1. 命令一致性：SKILL.md「## 0.」命令清单中声明的每个 public 命令都必须在
   ``aipd_os.cli.commands.COMMAND_FUNCS`` 中注册（声明 ⊆ 注册），
   并且声明集合必须恰好等于 ``command_contract.PUBLIC_COMMANDS``。
2. 注册-测试覆盖：每个已注册 public 命令要么被声明，要么被 tests/ 中的测试文件
   引用/覆盖（注册 public ⊆ 声明 ∪ 测试）。对"注册但未声明且未测试"的遗留命令
   只上报为警告，不作为失败。
3. 渐进式披露：SKILL.md 含「## 0.」命令清单；``references/`` 目录存在且非空；
   SKILL.md 正文长度合理（专业细节应集中放在 references/）。

Single Source of Truth：
命令元数据由 ``aipd_os.cli.command_contract`` 提供，
本脚本不再维护硬编码的 EXPECTED_COMMANDS。

退出码：0 = 通过；1 = 存在失败项。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 确保仓库根目录与 src/ 布局在 sys.path 上，以便 import aipd_os（脚本从 scripts/ 运行时）
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# 从 canonical contract 导入，而非硬编码
from aipd_os.cli.command_contract import (
    ALL_REGISTERED_COMMANDS,
    DEPRECATED_COMMANDS,
    PUBLIC_COMMANDS,
)

# 命令名：单/双词小写（如 "manual plan"、"cad preflight"、"release check"）
_CMD_NAME = r"[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)?"
_BACKTICK_RE = re.compile(r"`(" + _CMD_NAME + r")`")
_PAREN_RE = re.compile(r"（([^（）]+)）")

# SKILL.md 正文行数上限（超过则提示把专业细节移入 references/）
_SKILL_BODY_LINE_LIMIT = 500


def _registered_commands() -> set[str]:
    from aipd_os.cli.commands import COMMAND_FUNCS
    return set(COMMAND_FUNCS.keys())


def _tested_commands(registered: set[str]) -> set[str]:
    """返回在 tests/ 中被至少一个测试文件引用/覆盖的已注册命令。"""
    blob = ""
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        if p.name == "test_command_coverage.py":
            continue  # 排除覆盖自检自身，避免文档字符串自引用造成误判
        blob += p.read_text(encoding="utf-8") + "\n"
    return {cmd for cmd in registered if cmd in blob}


def _extract_from_section(section: str) -> set[str]:
    """从一段文本中提取反引号包裹或全角括号内"/"分隔的一键命令名。"""
    cmds = set(_BACKTICK_RE.findall(section))
    for inner in _PAREN_RE.findall(section):
        for tok in inner.split("/"):
            tok = tok.strip()
            if re.fullmatch(_CMD_NAME, tok):
                cmds.add(tok)
    return cmds


def _declared_commands() -> set[str]:
    """从 SKILL.md「## 0.」清单提取声明命令；为空则回退 README.md。"""
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("## 0."):
            section = lines[i + 1:]
            stop = next((j for j, s in enumerate(section) if s.startswith("## ")),
                        len(section))
            declared = _extract_from_section("\n".join(section[:stop]))
            if declared:
                return declared
            break

    # 回退：README.md 中所有含「一键命令」的行
    declared = set()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for ln in readme.splitlines():
        if "一键命令" not in ln:
            continue
        declared.update(_BACKTICK_RE.findall(ln))
        for inner in _PAREN_RE.findall(ln):
            for tok in inner.split("/"):
                tok = tok.strip()
                if re.fullmatch(_CMD_NAME, tok):
                    declared.add(tok)
    return declared


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    registered = _registered_commands()
    declared = _declared_commands()
    tested = _tested_commands(registered)

    print("=" * 60)
    print("AIPD-OS SKILL.md 质量自审（v5.10 canonical contract）")
    print("=" * 60)

    # 1) 命令一致性：声明 ⊆ 注册，且声明 == canonical public commands
    print(f"\n[命令一致性] SKILL.md 声明 {len(declared)} 个，"
          f"CLI 注册 {len(registered)} 个，"
          f"canonical public {len(PUBLIC_COMMANDS)} 个。")
    declared_missing = declared - registered
    if declared_missing:
        failures.append(f"SKILL.md 声明但未注册：{sorted(declared_missing)}")
        print(f"  ✗ {failures[-1]}")
    else:
        print("  ✓ 所有声明命令均已注册")

    # FAIL-closed: 声明集合必须恰好等于 canonical public commands
    if declared != PUBLIC_COMMANDS:
        extra_in_declared = declared - PUBLIC_COMMANDS
        missing_from_declared = PUBLIC_COMMANDS - declared
        parts = []
        if extra_in_declared:
            parts.append(f"声明了非 public 命令：{sorted(extra_in_declared)}")
        if missing_from_declared:
            parts.append(f"缺失 public 命令：{sorted(missing_from_declared)}")
        failures.append(
            "SKILL.md 声明集合与 canonical public commands 不一致：" + "; ".join(parts))
        print(f"  ✗ {failures[-1]}")
    else:
        print("  ✓ SKILL.md 声明了 canonical public commands 的全部命令")

    # 2) 注册-测试覆盖：每个 public 命令必须在注册中
    public_not_registered = PUBLIC_COMMANDS - registered
    if public_not_registered:
        failures.append(
            f"canonical public 命令未在 CLI 注册：{sorted(public_not_registered)}")
        print(f"  ✗ {failures[-1]}")
    else:
        print("  ✓ 所有 canonical public 命令均已注册")

    # 注册 ⊆ 声明 ∪ 测试（public 命令至少被声明或被测试覆盖）
    uncovered_public = PUBLIC_COMMANDS - declared - tested
    print(f"\n[注册-测试覆盖] 测试文件覆盖 {len(tested)} 个。")
    if uncovered_public:
        # public 命令无测试 → FAIL（关键命令必须有测试）
        failures.append(
            f"以下 public 命令既未在 SKILL.md 声明、也无测试文件引用："
            f"{sorted(uncovered_public)}")
        print(f"  ✗ {failures[-1]}")
    else:
        print("  ✓ 每个 public 命令均被声明或被测试覆盖")

    # deprecated/internal 命令无测试 → warning
    non_public_registered = registered - PUBLIC_COMMANDS
    uncovered_non_public = non_public_registered - tested
    if uncovered_non_public:
        warnings.append(
            f"以下非 public 命令无测试覆盖（仅警告）：{sorted(uncovered_non_public)}")
        print(f"  ⚠ {warnings[-1]}")

    # 3) 渐进式披露
    print("\n[渐进式披露]")
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if "## 0." in skill_text:
        print("  ✓ SKILL.md 含「## 0.」命令清单")
    else:
        failures.append("SKILL.md 缺少「## 0.」命令清单")
        print(f"  ✗ {failures[-1]}")

    ref = ROOT / "references"
    if ref.is_dir() and any(ref.iterdir()):
        print(f"  ✓ references/ 存在且非空（{len(list(ref.iterdir()))} 项）")
    else:
        failures.append("references/ 目录缺失或为空，专业细节应放于此")
        print(f"  ✗ {failures[-1]}")

    body_lines = [ln for ln in skill_text.splitlines() if ln.strip() != "---"]
    n = len(body_lines)
    if n <= _SKILL_BODY_LINE_LIMIT:
        print(f"  ✓ SKILL.md 正文长度合理（{n} 行）")
    else:
        warnings.append(
            f"SKILL.md 正文较长（{n} 行），专业细节建议移入 references/")
        print(f"  ⚠ {warnings[-1]}")

    # 4) 版本一致性检查
    print("\n[版本一致性]")
    # 检查文档中是否还有旧版本硬编码引用
    if "v5.3" in skill_text or "v5.5" in skill_text:
        warnings.append("SKILL.md 仍包含 v5.3/v5.5 版本引用，建议清理")
        print(f"  ⚠ {warnings[-1]}")
    else:
        print("  ✓ SKILL.md 无旧版本硬编码引用")

    # 汇总
    print("\n" + "=" * 60)
    if failures:
        print(f"自审失败：{len(failures)} 项失败，{len(warnings)} 项警告 → 退出码 1")
        for f in failures:
            print(f"  ✗ {f}")
        print("=" * 60)
        return 1
    print(f"自审通过：{len(warnings)} 项警告，0 项失败 → 退出码 0")
    for w in warnings:
        print(f"  ⚠ {w}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
