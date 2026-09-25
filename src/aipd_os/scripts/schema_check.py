"""JSON 模式校验脚本（schema 元校验 + 数据文件真实校验）。

1. 遍历 ``assets/schemas/`` 下所有 ``*.schema.json``：JSON 可解析、顶层为对象，
   且必须是合法 JSON Schema（按各文件自己声明的方言元校验，``check_schema``）；
2. 数据文件真实校验：按命名约定，``templates/`` 与 ``assets/templates/`` 中
   与 schema 同名的 ``<name>.json`` 必须通过校验；**跨文件 ``$ref`` 也解得开**
   （交给 ``aipd_os.schema_binding``，它是绑定规则与解析器的唯一出处）。

此前只做「能解析 + 顶层是对象」，templates/evals 数据与 schema 脱节不会被
CI 捕获——「schema 一致性」名不副实。现在任何模板数据违规都会让本脚本（与
CI schema-validation job）失败。

**没有实例文件不再是 INFO**。一份从没被任何实例按它校验过的契约，形状从来没有
被执行过；这类格子报成 ``UNBOUND`` 并计入失败，确实想要「只有契约、暂无实例」的
必须在 ``UNBOUND_EXEMPT`` 里**具名并写理由**（空表是常态）。

``DATA_DIRS`` 是绑定约定的**权威**：仓库另一侧的清单工具
（``aipd_os.interface_contract``）用 AST 从这里现抽，不抄常量。

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


#: 刻意不给实例文件的契约 ⇒ 必须在这里**具名**并写理由。
#: 空表是常态：一份没有实例被校验过的契约，等于这张契约的形状从没被执行过。
UNBOUND_EXEMPT: dict[str, str] = {}


def validate_schemas(schemas_dir: Path, repo: Path | None = None) -> int:
    """校验 schema 自身 + 按约定绑定的实例文件，返回失败条数。

    三态是刻意的：`FAIL`（形状不符 / 契约不合法）、`UNBOUND`（这份契约**从来没有**
    实例被按它校验过）、`OK`。旧的 `INFO …（跳过数据校验）` 会把 UNBOUND 读成绿，
    而「契约写了没人执行」正是这一格要防的东西。
    """
    import jsonschema  # noqa: PLC0415 - 校验功能依赖（pyproject 默认依赖）

    from aipd_os import schema_binding as sb

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
            # 按各文件自己声明的方言元校验（本仓五份都是 2020-12；
            # 用 Draft7 去核 2020-12 的文档会漏掉只有新方言才看得出的问题）
            jsonschema.validators.validator_for(schema).check_schema(schema)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[schema-check] FAIL {path.name} (schema): {exc}")
            continue
        print(f"[schema-check] OK   {path.name} (schema)")

        # 按约定绑定的实例文件必须通过真实校验（跨文件 $ref 也解得开）
        checked = 0
        for rel in DATA_DIRS:
            dp = root / rel / f"{name}.json"
            if not dp.is_file():
                continue
            checked += 1
            try:
                data = _load_json(dp)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"[schema-check] FAIL {dp.relative_to(root)} <- "
                      f"{path.name}: 读不到：{exc}")
                continue
            result = sb.validate_document(root, path.name, data)
            if result["status"] == sb.VALID:
                print(f"[schema-check] OK   {dp.relative_to(root)} <- {path.name}")
            elif result["status"] == sb.INVALID:
                failures += 1
                print(f"[schema-check] FAIL {dp.relative_to(root)} <- "
                      f"{path.name}: {result['errors'][0]}")
            else:
                # 核不了（引用解不开、schema 读不到）：既不是违规也不是通过
                failures += 1
                print(f"[schema-check] UNREADABLE {dp.relative_to(root)} <- "
                      f"{path.name}: {'; '.join(result['errors']) or result['status']}")
        if checked == 0 and path.name not in UNBOUND_EXEMPT:
            failures += 1
            print(f"[schema-check] UNBOUND {path.name} 没有任何实例被按它校验过"
                  f"（找过 {', '.join(DATA_DIRS)}）")
        elif checked == 0:
            print(f"[schema-check] EXEMPT {path.name}：{UNBOUND_EXEMPT[path.name]}")
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
