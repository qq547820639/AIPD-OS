#!/usr/bin/env python3
"""一次性迁移：把旧 scripts/capability_matrix.py 的静态 CAPABILITIES 长表
转换为 src/aipd_os/registry_data.py（Registry 数据，不含静态写死的 classification）。

转换规则：
- 保留全部证据字段（declaration/implementation/entry_point/run_command/input_output/
  unit_test/integration_test/e2e_evidence/current_limitation）。
- 把 ``classification == "external_dependency"`` 转为事实性布尔 ``external_dependency``。
- 去掉静态 classification，交由 registry.probe_classification 在运行时推导。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.capability_matrix as cm  # noqa: E402

KEY_ORDER = [
    "id", "name", "domain", "external_dependency",
    "declaration_file", "implementation_file", "entry_point", "run_command",
    "input_output", "unit_test", "integration_test", "e2e_evidence",
    "current_limitation",
]


def _py_literal(value) -> str:
    """把值序列化为合法 Python 字面量（而非 JSON 字面量，避免 false/true/null 报错）。"""
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    return repr(value)


def _item_literal(row: dict) -> str:
    parts = [f"{k!r}: {_py_literal(v)}" for k, v in row.items()]
    return "{" + ", ".join(parts) + "}"


def _cap_row(cap: dict) -> dict:
    row = {
        "id": cap["id"],
        "name": cap["name"],
        "domain": cap["domain"],
        "external_dependency": cap["classification"] == "external_dependency",
    }
    for k in KEY_ORDER:
        if k in row:
            continue
        v = cap.get(k)
        if v is None:
            row[k] = None
        else:
            row[k] = v
    return row


def _emit(cap: dict) -> str:
    return _item_literal(_cap_row(cap))


def main() -> int:
    items = [_cap_row(c) for c in cm.CAPABILITIES]
    lines = [
        '"""AIPD-OS v5.6 能力登记数据（自动生成，勿手改）。',
        "",
        "来源：scripts/migrate_capability_registry.py 从旧静态表迁移。",
        "分类不再写死，由 registry.probe_classification 依据运行时证据推导。",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "CAPABILITIES = [",
    ]
    for item in items:
        lines.append("    " + _item_literal(item) + ",")
    lines.append("]")
    lines.append("")

    out = Path(__file__).resolve().parent.parent / "src" / "aipd_os" / "registry_data.py"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"写入 {out}：{len(items)} 项能力")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())