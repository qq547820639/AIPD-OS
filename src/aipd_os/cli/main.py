"""AIPD-OS CLI 入口。

提供 ``--version``、``usage`` 以及 10 个一键子命令。
"""

from __future__ import annotations

import argparse
import sys

from aipd_os import __version__
from aipd_os.cli.commands import COMMAND_FUNCS, PLANNED_COMMANDS
from aipd_os.logging_utils import get_logger, log_event

_logger = get_logger("aipd.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aipd",
        description="AIPD-OS v5.0 命令行工具",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    sub.add_parser("usage", help="列出所有命令")

    p = sub.add_parser("init-project", help="初始化一个新项目")
    p.add_argument("--db", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--goal", required=True)
    p.set_defaults(func=COMMAND_FUNCS["init-project"])

    p = sub.add_parser("restore-project", help="恢复/迁移旧版项目")
    p.add_argument("--db", required=True)
    p.add_argument("--backup")
    p.set_defaults(func=COMMAND_FUNCS["restore-project"])

    p = sub.add_parser("run-supervisor", help="运行监督器直到需要决策或步骤耗尽")
    p.add_argument("--db", required=True)
    p.add_argument("--steps", type=int, default=1)
    p.set_defaults(func=COMMAND_FUNCS["run-supervisor"])

    p = sub.add_parser("project-summary", help="打印所有者视图项目摘要")
    p.add_argument("--db", required=True)
    p.add_argument("--markdown", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["project-summary"])

    p = sub.add_parser("submit-decision", help="裁定一个决策")
    p.add_argument("--db", required=True)
    p.add_argument("--decision-id", required=True)
    p.add_argument("--choice", required=True)
    p.add_argument("--comment")
    p.set_defaults(func=COMMAND_FUNCS["submit-decision"])

    p = sub.add_parser("run-manual-chain", help="运行一个手工批次")
    p.add_argument("--db", required=True)
    p.add_argument("--batch-id", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--output-dir", required=True)
    p.set_defaults(func=COMMAND_FUNCS["run-manual-chain"])

    p = sub.add_parser("run-cad-chain", help="运行 CAD 成熟度门禁")
    p.add_argument("--db")
    p.add_argument("--manifest", required=True)
    p.add_argument("--target", default="C2",
                   choices=["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"])
    p.set_defaults(func=COMMAND_FUNCS["run-cad-chain"])

    sub.add_parser("run-tests", help="运行完整测试套件（pytest）") \
        .set_defaults(func=COMMAND_FUNCS["run-tests"])

    p = sub.add_parser("run-evals", help="运行评估套件")
    p.add_argument("--evals", default="evals/evals.json")
    p.add_argument("--provider", choices=["fake", "model"], default="fake")
    p.add_argument("--out")
    p.add_argument("--threshold", type=float, default=0.1)
    p.add_argument("--baseline")
    p.set_defaults(func=COMMAND_FUNCS["run-evals"])

    p = sub.add_parser("build-release", help="构建发布包")
    p.add_argument("--version", required=True)
    p.add_argument("--out")
    p.add_argument("--no-tests", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["build-release"])

    return parser


def _cmd_usage(args: argparse.Namespace) -> int:
    print("AIPD-OS v5.0 支持的命令：")
    for cmd in PLANNED_COMMANDS:
        print(f"  aipd {cmd}")
    return 0


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "usage":
        return _cmd_usage(args)

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0
    try:
        return int(func(args))
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001 - CLI 顶层兜底
        log_event(_logger, "cli_error", command=args.command, error=str(exc))
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
