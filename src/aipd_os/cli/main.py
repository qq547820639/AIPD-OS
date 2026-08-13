"""AIPD-OS CLI 入口。

提供 ``--version``、``usage`` 以及 10 个一键子命令。
"""

from __future__ import annotations

import argparse
import json
import sys

from aipd_os import __version__
from aipd_os.cli.commands import COMMAND_FUNCS, PLANNED_COMMANDS
from aipd_os.logging_utils import get_logger, log_event

_logger = get_logger("aipd.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aipd",
        description="AIPD-OS v5.6 命令行工具",
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
    p.add_argument("--project", help="目标项目（多项目时必填；缺省时若单项目自动解析）")
    p.add_argument("--steps", type=int, default=1)
    p.set_defaults(func=COMMAND_FUNCS["run-supervisor"])

    p = sub.add_parser("run", help="运行监督器直到真实决策或步骤耗尽")
    p.add_argument("--project", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--until-decision", action="store_true")
    p.add_argument("--steps", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["run"])

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
    p.add_argument("--provider",
                   choices=["fake", "deterministic-fixture", "contract-test",
                            "model", "real-model", "pure-contract"],
                   default="fake")
    p.add_argument("--out")
    p.add_argument("--threshold", type=float, default=0.1)
    p.add_argument("--baseline")
    p.set_defaults(func=COMMAND_FUNCS["run-evals"])

    p = sub.add_parser("build-release", help="构建发布包")
    p.add_argument("--version", required=True)
    p.add_argument("--out")
    p.add_argument("--no-tests", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["build-release"])

    # ---- v5.1 新增 16 个一键命令 ----
    p = sub.add_parser("init", help="初始化一个新项目（--project/--name/--goal/--db）。"
                                    " Example: aipd init --project p1 --name 外骨骼 --goal 助力 --db state.db")  # noqa: E501
    p.add_argument("--db", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--goal", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["init"])

    p = sub.add_parser("intake", help="由一句自然语言需求初始化项目（确定性）。"
                                      " Example: aipd intake --prompt '做一款外骨骼' --db state.db")
    p.add_argument("--db", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--project")
    # v5.8.1 Commit 11：创建与执行分离 —— 无 --run 不自动 decompose
    p.add_argument("--run", action="store_true",
                   help="显式执行 idea.structure（经 Supervisor → ExecutionRouter）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["intake"])

    p = sub.add_parser("resume", help="恢复/迁移旧项目并打印会话续接摘要。"
                                      " Example: aipd resume --db state.db --backup backups/backup_x")  # noqa: E501
    p.add_argument("--db", required=True)
    p.add_argument("--backup")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["resume"])

    p = sub.add_parser("status", help="打印所有者视图项目摘要。"
                                      " Example: aipd status --db state.db --project p1")
    p.add_argument("--db", required=True)
    p.add_argument("--project")
    p.add_argument("--markdown", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["status"])

    p = sub.add_parser("decide", help="裁定一个决策。可用 --decision-id/--choice 显式裁定，"
                                      "或用 --natural 提供一句自然语言回复（如：批准 / 选A / 保留模块化）。"  # noqa: E501
                                      " Example: aipd decide --db state.db --decision-id D1 --choice 单臂"  # noqa: E501
                                      " | aipd decide --db state.db --natural '选A'")
    p.add_argument("--db", required=True)
    p.add_argument("--project")
    p.add_argument("--decision-id")
    p.add_argument("--choice")
    p.add_argument("--comment")
    p.add_argument("--natural", help="一句自然语言的所有者回复（批准/选A/保留模块化/暂不进入实体制造等）")  # noqa: E501
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["decide"])

    # manual（两级）：manual plan / manual generate
    p_manual = sub.add_parser("manual", help="手工产品手册批次（plan 计划 / generate 生成）。"
                                             " Example: aipd manual plan --db state.db --state m.json")  # noqa: E501
    manual_sub = p_manual.add_subparsers(dest="manual_cmd", required=True)
    mp = manual_sub.add_parser("plan", help="生成手工批次计划。"
                                            " Example: aipd manual plan --db state.db --state m.json --minimum-pages 10")  # noqa: E501
    mp.add_argument("--db")
    mp.add_argument("--state")
    mp.add_argument("--project")
    mp.add_argument("--minimum-pages", type=int, default=10)
    mp.add_argument("--json", action="store_true")
    mp.set_defaults(func=COMMAND_FUNCS["manual plan"])
    mp = manual_sub.add_parser("generate", help="生成一个手工批次（图像后端不可用则生成外部任务包，不造假）。"  # noqa: E501
                                                " Example: aipd manual generate --db state.db --batch-id batch_1 --prompt '封面' --output-dir out")  # noqa: E501
    mp.add_argument("--db")
    mp.add_argument("--state")
    mp.add_argument("--project")
    mp.add_argument("--batch-id", required=True)
    mp.add_argument("--prompt", required=True)
    mp.add_argument("--output-dir", required=True)
    mp.add_argument("--minimum-pages", type=int, default=10)
    mp.add_argument("--json", action="store_true")
    mp.set_defaults(func=COMMAND_FUNCS["manual generate"])

    # cad（两级）：cad preflight / cad build
    p_cad = sub.add_parser("cad", help="CAD 成熟度门禁（preflight 预检 / build 构建门禁）。"
                                       " Example: aipd cad build --manifest m.json --target C2")
    cad_sub = p_cad.add_subparsers(dest="cad_cmd", required=True)
    cp = cad_sub.add_parser("preflight", help="检查运行时上限与成熟度约束。"
                                              " Example: aipd cad preflight --manifest m.json --target C2")  # noqa: E501
    cp.add_argument("--manifest", required=True)
    cp.add_argument("--target", default="C2",
                    choices=["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"])
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=COMMAND_FUNCS["cad preflight"])
    cp = cad_sub.add_parser("build", help="运行 CAD 成熟度门禁/构建链。"
                                          " Example: aipd cad build --manifest m.json --target C2")
    cp.add_argument("--manifest", required=True)
    cp.add_argument("--target", default="C2",
                    choices=["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"])
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=COMMAND_FUNCS["cad build"])

    p = sub.add_parser("industrialize", help="供应链 + 验证执行（报价登记/阶段分析/纠偏任务；无数据则如实报告不虚构）。"  # noqa: E501
                                             " Example: aipd industrialize --db state.db --quote quotes.csv --stage dv --lab-data lab.csv")  # noqa: E501
    p.add_argument("--db")
    p.add_argument("--quote")
    p.add_argument("--stage")
    p.add_argument("--lab-data")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["industrialize"])

    p = sub.add_parser("validate", help="生产发布证据门禁。"
                                        " Example: aipd validate --manifest RELEASE_MANIFEST.json --target C7")  # noqa: E501
    p.add_argument("--manifest", required=True)
    p.add_argument("--target", required=True,
                   choices=["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["validate"])

    p = sub.add_parser("audit", help="生成能力矩阵审计产物（repository_snapshot / capability_matrix）。"  # noqa: E501
                                     " Example: aipd audit --repo . --out docs/audit")
    p.add_argument("--repo")
    p.add_argument("--out", default="docs/audit")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["audit"])

    # release（两级）：release check
    p_release = sub.add_parser("release", help="发布管理（check 就绪检查）。"
                                               " Example: aipd release check --target C7 --repo .")
    release_sub = p_release.add_subparsers(dest="release_cmd", required=True)
    rp = release_sub.add_parser("check", help="发布就绪检查：版本真实性审计 + 生产发布门禁 + 通过性报告。"  # noqa: E501
                                              " Example: aipd release check --target C7 --repo .")
    rp.add_argument("--repo")
    rp.add_argument("--target", required=True,
                    choices=["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"])
    rp.add_argument("--json", action="store_true")
    rp.set_defaults(func=COMMAND_FUNCS["release check"])

    p = sub.add_parser("test", help="运行完整测试套件（pytest）。"
                                    " Example: aipd test")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["test"])

    p = sub.add_parser("eval", help="运行评估套件。"
                                    " Example: aipd eval --evals evals/evals.json --provider fake --out evals_out")  # noqa: E501
    p.add_argument("--evals", default="evals/evals.json")
    p.add_argument("--provider",
                   choices=["fake", "deterministic-fixture", "contract-test",
                            "model", "real-model", "pure-contract"],
                   default="fake")
    p.add_argument("--out")
    p.add_argument("--threshold", type=float, default=0.1)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["eval"])

    p = sub.add_parser("package", help="构建发布包（zip + SHA-256 清单 + 签名）。"
                                       " Example: aipd package --version 5.1.0 --out releases/5.1.0 --no-tests")  # noqa: E501
    p.add_argument("--version", required=True)
    p.add_argument("--out")
    p.add_argument("--no-tests", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["package"])

    # ---- v5.5 新增：运维体检与详细版本 ----
    p = sub.add_parser("version", help="打印包版本。搭配 --verbose 打印 Git HEAD / 构建时间 / 能力矩阵版本 / 发布清单哈希。"  # noqa: E501
                                       " Example: aipd version --verbose")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["version"])

    p = sub.add_parser("doctor", help="一键体检：包版本、依赖可用性、配置、外部能力、数据库、对象存储与权限。"  # noqa: E501
                                      " Example: aipd doctor --json")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["doctor"])

    # ---- P2 所有者 UX ----
    p = sub.add_parser("operate", help="自然语言操作闭环：意图→影响→受影响制品→成本/时间→可撤销预览→批准→自动返工→自动验收→摘要。"  # noqa: E501
                                       " Example: aipd operate --db state.db --project p1 --intent '成本降低20%并且外观更工业化'")  # noqa: E501
    p.add_argument("--db", required=True)
    p.add_argument("--project")
    p.add_argument("--intent", required=True, help="一句自然语言所有者指令")
    p.add_argument("--approve", action="store_true", help="绕过批准门禁直接执行（供 CI/脚本）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["operate"])

    p = sub.add_parser("dashboard", help="统一 Owner Dashboard：默认只展示 10 个所有者区块；--compact 紧凑移动端；--json 输出纯 JSON。"  # noqa: E501
                                         " Example: aipd dashboard --db state.db --project p1")
    p.add_argument("--db", required=True)
    p.add_argument("--project")
    p.add_argument("--compact", action="store_true", help="紧凑/窄终端友好输出")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["dashboard"])

    p = sub.add_parser("onboard", help="首次使用引导：一句话建项→立即产出第一份结果→展示能力与需外部配置项→Provider 引导→示例项目→恢复/重置。"  # noqa: E501
                                       " Example: aipd onboard --db state.db --idea '做一款外骨骼'")
    p.add_argument("--db", required=True)
    p.add_argument("--idea", required=True, help="一句话产品想法")
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["onboard"])

    p = sub.add_parser("reset", help="重置项目（先备份再删除）。"
                                     " Example: aipd reset --db state.db --project p1")
    p.add_argument("--db", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["reset"])

    p = sub.add_parser("recover", help="失败恢复：回滚最近可撤销操作；或 --backup 从备份恢复数据库。"  # noqa: E501
                                       " Example: aipd recover --db state.db --project p1")
    p.add_argument("--db", required=True)
    p.add_argument("--project")
    p.add_argument("--backup", help="备份目录（可选，无则回滚可撤销操作）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["recover"])

    # ---- v5.6 Owner Web Console ----
    p = sub.add_parser("ui", help="启动本地 Owner Web Console（首次向导/项目总览/决策/制品/运行控制/外部等待）。"  # noqa: E501
                                  " Example: aipd ui --db state.db")
    p.add_argument("--db", help="状态数据库路径（默认取配置 db_dir/state.db）")
    p.add_argument("--project", help="默认项目 ID（可选）")
    p.add_argument("--host", help="监听地址（默认取配置，127.0.0.1）")
    p.add_argument("--port", type=int, help="监听端口（默认取配置，8080）")
    p.set_defaults(func=COMMAND_FUNCS["ui"])

    # ---- v5.9 Product Intelligence（产品定义查看 / Gate 操作）----
    p = sub.add_parser(
        "product",
        help="Product Definition（show 查看 / gate Gate 操作）。"
             " Example: aipd product show --db state.db --project p1")
    prod_sub = p.add_subparsers(dest="product_cmd", required=True)
    pp = prod_sub.add_parser(
        "show",
        help="产品定义投影摘要（Opportunity/Principles/Requirements/"
             "Features/Gate）。")
    pp.add_argument("--db", required=True)
    pp.add_argument("--project")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=COMMAND_FUNCS["product show"])
    from aipd_os.product_intelligence import OWNER_CHOICES  # §23 同源
    pg = prod_sub.add_parser(
        "gate",
        help="Product Definition Gate 评估 + Owner 决策（--propose 创建；"
             "--decision-id/--choice 裁定）。")
    pg.add_argument("--db", required=True)
    pg.add_argument("--project")
    pg.add_argument("--json", action="store_true")
    pg.add_argument("--propose", action="store_true",
                    help="创建 Owner Decision（approve/reject/request_revision）")
    pg.add_argument("--decision-id")
    pg.add_argument("--choice",
                    choices=sorted(OWNER_CHOICES))  # §23 与 Gate 同源
    pg.add_argument("--comment")
    pg.add_argument("--waiver-conditions",
                    help="approve_with_waiver 必填：接受的条件（P0-04）")
    pg.add_argument("--waiver-risks", help="approve_with_waiver：接受的已知风险")
    pg.set_defaults(func=COMMAND_FUNCS["product gate"])

    return parser


def _cmd_usage(args: argparse.Namespace) -> int:
    print("AIPD-OS v5.6 支持的命令：")
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
        if getattr(args, "json", False):
            print(json.dumps({"command": args.command, "ok": False, "error": str(exc)},
                             ensure_ascii=False))
        else:
            print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
