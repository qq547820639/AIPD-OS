#!/usr/bin/env python3
"""regenerate ``src/aipd_os/registry_data.py``：70 项核心能力 + 7 项 product.* 合并。

历史背景：本脚本最初是一次性迁移（把旧 ``scripts/capability_matrix.py`` 的静态
``CAPABILITIES`` 长表转成 ``registry_data.py``）。此后 ``capability_matrix.py``
改为 registry 驱动，不再持有静态长表；70 项核心能力的权威数据随之落在
``registry_data.py`` 自身，7 项 product.* 则长期以手写块形式追加在文件末尾。

为保证「重跑不丢手写块」，本脚本现在做**合并**而非覆盖：
- 核心能力（70 项）：读取既有 ``registry_data.py`` 中非 ``product.*`` 的条目，
  内容保持不变，仅重新序列化；
- product.* 手写块（7 项）：读取 ``scripts/product_capabilities_extra.py``
  的 ``PRODUCT_CAPABILITIES``。

重跑后输出 77 项（70 + 7），product.* 手写块不再丢失。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = SRC / "aipd_os" / "registry_data.py"
EXTRA = ROOT / "scripts" / "product_capabilities_extra.py"

HEADER_LINES = [
    "# ruff: noqa: E501",
    '"""AIPD-OS v5.6 能力登记数据（70 项核心能力自动生成 + 7 项 product.* '
    "由生成脚本合并，勿手改本文件）。",
    "",
    "来源：scripts/migrate_capability_registry.py 合并——",
    "  - 70 项核心能力：既有 registry_data.py（历史迁移产物，内容不变）；",
    "  - 7 项 product.*：scripts/product_capabilities_extra.py 手写块"
    "（修改 product.* 请改该文件）。",
    "分类不写死，由 registry.probe_classification 依据运行时证据推导。",
    '"""',
]


def _load_module(name: str, path: Path) -> Any:
    """按文件路径加载一个独立模块（避免依赖 aipd_os 包已安装）。"""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块 {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _py_literal(value: Any) -> str:
    """把值序列化为双引号风格的合法 Python 字面量（保持既有 registry_data 风格）。"""
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def _item_literal(row: dict) -> str:
    parts = [f"{json.dumps(k, ensure_ascii=False)}: {_py_literal(v)}"
             for k, v in row.items()]
    return "{" + ", ".join(parts) + "}"


def main() -> int:
    # 1) 核心 70 项：既有 registry_data.py 的非 product.* 条目（内容保持不变）
    core_mod = _load_module("aipd_os_registry_data_core", OUT)
    core = [dict(e) for e in core_mod.CAPABILITIES
            if not str(e.get("id", "")).startswith("product.")]

    # 2) product.* 7 项：独立手写块
    extra_mod = _load_module("product_capabilities_extra", EXTRA)
    extra = [dict(e) for e in extra_mod.PRODUCT_CAPABILITIES]

    items = core + extra
    lines = list(HEADER_LINES) + ["", "from __future__ import annotations", "",
                                  "CAPABILITIES = ["]
    for item in items:
        lines.append("    " + _item_literal(item) + ",")
    lines.append("]")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"写入 {OUT}：{len(core)} 项核心 + {len(extra)} 项 product.* = {len(items)} 项能力")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
