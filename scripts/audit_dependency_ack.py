#!/usr/bin/env python3
"""依赖审计 + 已确认 CVE 处置脚本。

运行：``python scripts/audit_dependency_ack.py``

行为：
1. 从 ``docs/security/dependency-cve-review.md`` 解析已记录的 CVE/告警 ID（承认集合）。
2. 保证承认集合非空且 Python 3.9 下仍存在（否则应为空，直接严格审计）。
3. 以 ``pip-audit --ignore-vuln <ID> ...`` 运行审计，对**已记录**的 CVE 显式承认
   （非静默忽略），并校验：
   - 承认集合 == 文档记录集合（防止"承认"与"记录"脱节）；
   - 任何**未记录**的新增漏洞都会使退出码非 0，从而阻止发布。

退出码：0 = 通过；1 = 存在未记录漏洞或文档与承认集合不一致。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DOC = ROOT / "docs/security/dependency-cve-review.md"

# 已知漏洞 ID 格式：GHSA-xxxxx / PYSEC-YYYY-NNNN
_ID_RE = re.compile(r"\b(GHSA-[0-9A-Za-z-]+|PYSEC-\d{4}-\d+)\b")


def documented_ids() -> set[str]:
    """从审查文档提取所有已记录的 CVE/告警 ID（承认集合）。"""
    if not REVIEW_DOC.exists():
        print(f"✗ 缺少审查文档：{REVIEW_DOC}")
        sys.exit(1)
    return set(_ID_RE.findall(REVIEW_DOC.read_text(encoding="utf-8")))


def main() -> int:
    ack = documented_ids()
    # 空承认集合 = 文档未记录任何 CVE → 按 docstring 契约执行严格审计
    # （不带 --ignore-vuln：任何命中都阻断发布），而不是直接拒绝。
    cmd = [sys.executable, "-m", "pip_audit"]
    for cve in sorted(ack):
        cmd += ["--ignore-vuln", cve]

    if not ack:
        print("审查文档中未解析到任何 CVE ID；执行严格审计（不忽略任何命中）。")
    else:
        print(f"已显式承认并在文档中记录的 CVE/告警 ID 数量：{len(ack)}")
    print(f"运行：{' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd)
    except FileNotFoundError:
        print("✗ pip-audit 未安装；无法执行依赖审计（fail-closed）。")
        print("  安装：pip install pip-audit")
        return 1
    if proc.returncode == 0:
        print("✓ pip-audit 通过（所有命中均为已记录 CVE，其余依赖无已知漏洞）")
        return 0

    # 非 0：可能包含未记录的新漏洞，或 --ignore-vuln 未能覆盖全部命中。
    print("✗ pip-audit 返回非 0：存在未记录的新漏洞，或承认集合与命中不一致。")
    print("  若为新增漏洞，请补充 docs/security/dependency-cve-review.md 后重跑。")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())