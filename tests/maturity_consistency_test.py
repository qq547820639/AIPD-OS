"""仓库级一致性测试：产品代码不得残留遗留的 CAD-L 成熟度词汇。

AIPD-OS v5 统一使用 C0..C7 成熟度体系。任何产品代码（.py/.json/.md/.yaml）
中被替换的旧体系层级（如 CAD-L0..CAD-L5）出现即视为冲突定义并失败。
注意：tests/ 目录被排除，因为测试需引用旧词汇以验证门脚本的拒绝行为。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 跳过的目录：元数据/任务说明（.trae/specs 描述本次迁移本身）、依赖与缓存。
SKIP_DIRS = {'.git', '.venv', '.pytest_cache', '__pycache__', '.trae', 'tests'}
EXTS = {'.py', '.json', '.md', '.yaml', '.yml'}
PATTERN = re.compile(r'CAD-L\d')


def iter_text_files(root: Path):
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix in EXTS:
            yield p


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
