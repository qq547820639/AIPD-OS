"""JSON 模式校验脚本。

遍历 ``assets/schemas/`` 下所有 ``*.schema.json`` 文件，确认每个文件都能被
JSON 解析，且顶层为对象。用于 CI 的 schema-validation 任务。

用法：
    python -m aipd_os.scripts.schema_check [--schemas-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_SCHEMAS_DIR = Path("assets/schemas")


def validate_schemas(schemas_dir: Path) -> int:
    """校验目录下所有 .schema.json 文件，返回校验失败数量。"""
    if not schemas_dir.is_dir():
        print(f"[schema-check] 目录不存在: {schemas_dir}", file=sys.stderr)
        return 1

    files = sorted(schemas_dir.glob("*.schema.json"))
    if not files:
        print(f"[schema-check] 未找到 *.schema.json 文件: {schemas_dir}")
        return 1

    failures = 0
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("顶层必须是 JSON 对象")
            print(f"[schema-check] OK   {path.name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[schema-check] FAIL {path.name}: {exc}")
    return failures


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 assets/schemas 下的 JSON 模式文件")
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=DEFAULT_SCHEMAS_DIR,
        help="模式文件目录（默认 assets/schemas）",
    )
    args = parser.parse_args(argv)

    failures = validate_schemas(args.schemas_dir)
    if failures:
        print(f"[schema-check] 共 {failures} 个文件校验失败", file=sys.stderr)
        return 1
    print("[schema-check] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())