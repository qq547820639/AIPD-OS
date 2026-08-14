"""JSON 模式校验脚本（schema 元校验 + 数据文件真实校验）。

1. 遍历 ``assets/schemas/`` 下所有 ``*.schema.json``：JSON 可解析、顶层为对象，
   且必须是合法 JSON Schema（Draft 7 元校验，``check_schema``）；
2. 数据文件真实校验：按命名约定，``templates/`` 与 ``assets/templates/`` 中
   与 schema 同名的 ``<name>.json`` 必须通过 ``jsonschema.validate``。

此前只做「能解析 + 顶层是对象」，templates/evals 数据与 schema 脱节不会被
CI 捕获——「schema 一致性」名不副实。现在任何模板数据违规都会让本脚本（与
CI schema-validation job）失败。

用法：
    python -m aipd_os.scripts.schema_check [--schemas-dir PATH] [--repo PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_SCHEMAS_DIR = Path("assets/schemas")
# 脚本位于 src/aipd_os/scripts/schema_check.py → parents[3] 为仓库根
DEFAULT_REPO = Path(__file__).resolve().parents[3]

# 数据文件查找目录（相对 repo 根；命名约定：与 schema 同名）
DATA_DIRS = ("templates", "assets/templates")


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("顶层必须是 JSON 对象")
    return data


def validate_schemas(schemas_dir: Path, repo: Path | None = None) -> int:
    """校验 schema 自身 + 同名模板数据文件，返回校验失败数量。"""
    import jsonschema  # noqa: PLC0415 - 校验功能依赖（pyproject 默认依赖）

    if not schemas_dir.is_dir():
        print(f"[schema-check] 目录不存在: {schemas_dir}", file=sys.stderr)
        return 1

    files = sorted(schemas_dir.glob("*.schema.json"))
    if not files:
        print(f"[schema-check] 未找到 *.schema.json 文件: {schemas_dir}")
        return 1

    root = repo or DEFAULT_REPO
    failures = 0
    for path in files:
        name = path.stem.removesuffix(".schema")
        try:
            schema = _load_json(path)
            # 1) schema 自身必须是合法 JSON Schema（Draft 7 元校验）
            jsonschema.validators.Draft7Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[schema-check] FAIL {path.name} (schema): {exc}")
            continue
        print(f"[schema-check] OK   {path.name} (schema)")

        # 2) 同名模板数据文件必须通过真实校验
        data_files = [d / f"{name}.json" for d in (root / rel for rel in DATA_DIRS)]
        validated_any = False
        for dp in data_files:
            if not dp.is_file():
                continue
            validated_any = True
            try:
                data = _load_json(dp)
                jsonschema.validate(data, schema)
                print(f"[schema-check] OK   {dp.relative_to(root)} <- {path.name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"[schema-check] FAIL {dp.relative_to(root)} <- "
                      f"{path.name}: {exc}")
        if not validated_any:
            print(f"[schema-check] INFO {path.name} 无同名模板数据文件（跳过数据校验）")
    return failures


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 JSON 模式文件与模板数据文件")
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=DEFAULT_SCHEMAS_DIR,
        help="模式文件目录（默认 assets/schemas）",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="仓库根目录（定位 templates/assets 数据文件；默认脚本仓库根）",
    )
    args = parser.parse_args(argv)

    failures = validate_schemas(args.schemas_dir, args.repo)
    if failures:
        print(f"[schema-check] 共 {failures} 项校验失败", file=sys.stderr)
        return 1
    print("[schema-check] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
