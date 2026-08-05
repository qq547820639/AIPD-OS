"""仓库级一致性测试：产品代码不得残留遗留的 CAD-L 成熟度词汇，也不得对
Faceted BREP 过度声称（faceted 路径最高只能达到 C1）。

AIPD-OS v5 统一使用 C0..C7 成熟度体系。任何产品代码（.py/.json/.md/.yaml/
.txt/.html）中被替换的旧体系层级（如 CAD-L0..CAD-L5）出现即视为冲突定义并失败。
同时，faceted（Faceted BREP）表示网格/面片级几何，其成熟度上限为 C1，任何把它
与 C2 及以上成熟度关联的肯定性表述（如 "faceted可达C2"）均视为过度声称并失败。
注意：
  * faceted 一词大小写不敏感，但成熟度层级（C2..C9 / CAD-L2..）保持大小写敏感，
    避免把 sha256 哈希中的小写 c3 等误判为层级。
  * 否定/拦截语境（如 selftest 断言 "cannot reach C7"，eval 夹具 "仅有Faceted
    BREP，目标C3" 期望被阻止）以及 Python 注释（如 audit 工具描述其检测模式）是
    正确行为，不属于过度声称。
tests/ 目录被排除，因为测试需引用旧词汇以验证门脚本的拒绝行为。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 跳过的目录：元数据/任务说明（.trae/specs 描述本次迁移本身）、依赖与缓存。
SKIP_DIRS = {'.git', '.venv', '.pytest_cache', '__pycache__', '.trae', 'tests'}
EXTS = {'.py', '.json', '.md', '.yaml', '.yml', '.txt', '.html'}
PATTERN = re.compile(r'CAD-L\d')
# Faceted BREP 最高 C1：任何与 C2 及以上成熟度关联的表述均视为过度声称。
# faceted 大小写不敏感；层级 C[2-9] 保持大小写敏感以免命中哈希中的小写十六进制。
FACETED_OVERCLAIM = re.compile(
    r'((?i:faceted).{0,40}(?:C[2-9]|成熟度\s*C2|CAD-L[2-9]))',
)
# 否定/拦截语境的关键词：出现则说明该语句是在否认 faceted 可达 C2+，而非过度声称。
NEGATION_HINTS = (
    'cannot', "can't", 'incorrectly', 'not reach', 'not achieve',
    'block', 'blocked', '阻止', '降级', '不能', '不可', '无法', '达不到',
    '无法达到', '不能达到', '不可用于', '不得用于', '仅', '仅有', 'only',
)


def iter_text_files(root: Path):
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in EXTS:
            yield p


def _on_comment_line(text: str, match) -> bool:
    line_start = text.rfind('\n', 0, match.start()) + 1
    line_end = text.find('\n', match.start())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    return line.lstrip().startswith('#')


def test_no_legacy_cad_l_vocabulary():
    hits = []
    for p in iter_text_files(REPO):
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if PATTERN.search(text):
            hits.append(str(p.relative_to(REPO)))
    assert not hits, f"legacy CAD-L vocabulary still present in: {hits}"


def test_no_faceted_overclaim():
    hits = []
    for p in iter_text_files(REPO):
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for m in FACETED_OVERCLAIM.finditer(text):
            start = max(0, m.start() - 30)
            ctx = text[start:m.end()].replace('\n', ' ')
            if any(h in ctx for h in NEGATION_HINTS):
                continue
            if p.suffix == '.py' and _on_comment_line(text, m):
                continue
            hits.append(f"{p.relative_to(REPO)}: {m.group(1)!r}")
    assert not hits, (
        "Faceted BREP over-claim (max C1) still present in:\n" + "\n".join(hits)
    )


def _flagged_as_overclaim(phrase: str) -> bool:
    """True if the scan would flag `phrase` as a faceted over-claim."""
    m = FACETED_OVERCLAIM.search(phrase)
    if not m:
        return False
    ctx = phrase[max(0, m.start() - 30):m.end()]
    return not any(h in ctx for h in NEGATION_HINTS)


def test_scan_flags_faceted_over_c1_conflicts():
    """护栏：扫描必须能识别“Faceted > C1”/“Faceted 可达 CAD-L3”类冲突。

    若这些肯定性表述被误判为“无冲突”，说明扫描正则失效，应失败而不是静默放过。
    """
    conflicts = [
        "Faceted BREP 可达 CAD-L3",
        "Faceted 工具链可达 CAD-L3",
        "faceted 可达 C2",
        "faceted_brep 可达 C3",
        "Faceted BREP 成熟度 C5",
        "faceted 工具链可达到 C4",
        "Faceted BREP 可用于 C2 及以上的正式图纸",
    ]
    unflagged = [p for p in conflicts if not _flagged_as_overclaim(p)]
    assert not unflagged, f"scan failed to flag faceted over-claim conflict: {unflagged}"


def test_scan_allows_faceted_at_or_below_c1():
    """护栏：扫描不得误伤合法的“Faceted ≤ C1”表述与否定/拦截语境。"""
    allowed = [
        "Faceted BREP 最高只能达到 C1",           # ≤C1，合法
        "Faceted 工具链成熟度声明最高只能为 C1",    # ≤C1，合法
        "faceted_brep runtime caps at C1",        # 否定/封顶语境
        "仅有Faceted BREP，目标C3",                # 拦截语境
        "faceted fallback cannot become engineering CAD",  # 否定语境
        "Faceted BREP 不可用于 C2 及以上的正式图纸",  # 否定语境
    ]
    flagged = [p for p in allowed if _flagged_as_overclaim(p)]
    assert not flagged, f"scan falsely flagged legitimate faceted statement: {flagged}"
