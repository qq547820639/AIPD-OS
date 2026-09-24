"""AIPD-OS CLI 入口。

提供 ``--version``、``usage``、30+ 个 one-click 主线子命令，以及
10 个向后兼容的 deprecated 别名命令。
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings

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
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["init-project"])

    p = sub.add_parser("restore-project", help="恢复/迁移旧版项目")
    p.add_argument("--db", required=True)
    p.add_argument("--backup")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["restore-project"])

    p = sub.add_parser("run-supervisor", help="运行监督器直到需要决策或步骤耗尽")
    p.add_argument("--db", required=True)
    p.add_argument("--project", help="目标项目（多项目时必填；缺省时若单项目自动解析）")
    p.add_argument("--steps", type=int, default=1)
    p.add_argument("--json", action="store_true")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["project-summary"])

    p = sub.add_parser("submit-decision", help="裁定一个决策")
    p.add_argument("--db", required=True)
    p.add_argument("--decision-id", required=True)
    p.add_argument("--choice", required=True)
    p.add_argument("--comment")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["submit-decision"])

    p = sub.add_parser("run-manual-chain", help="运行一个手工批次")
    p.add_argument("--db", required=True)
    p.add_argument("--batch-id", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["run-manual-chain"])

    p = sub.add_parser("run-cad-chain", help="运行 CAD 成熟度门禁")
    p.add_argument("--db")
    p.add_argument("--manifest", required=True)
    p.add_argument("--target", default="C2",
                   choices=["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["run-cad-chain"])

    p = sub.add_parser("run-tests", help="运行完整测试套件（pytest）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["run-tests"])

    p = sub.add_parser("run-evals", help="运行评估套件")
    p.add_argument("--evals", default="evals/evals.json")
    p.add_argument("--provider",
                   choices=["fake", "deterministic-fixture", "contract-test",
                            "model", "real-model", "pure-contract"],
                   default="model",
                   help="默认真实模型端点；fake/contract-test 仅供开发测试")
    p.add_argument("--out")
    p.add_argument("--threshold", type=float, default=0.1)
    p.add_argument("--baseline")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["run-evals"])

    p = sub.add_parser("build-release", help="构建发布包")
    p.add_argument("--version", required=True)
    p.add_argument("--out")
    p.add_argument("--no-tests", action="store_true")
    p.add_argument("--json", action="store_true")
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

    p_drawing = sub.add_parser("drawing", help="从 3D 模型出二维工程图（DXF）。"
                                               " Example: aipd drawing generate --step part.step --out part.dxf --part P-1")  # noqa: E501
    drawing_sub = p_drawing.add_subparsers(dest="drawing_cmd", required=True)
    dp = drawing_sub.add_parser("generate", help="生成 DXF 图纸 + 机器可核验证据 JSON。"
                                                 " Example: aipd drawing generate --part bracket --revision A")  # noqa: E501
    dp.add_argument("--step", help="STEP 模型路径（与 --native 二选一）")
    dp.add_argument("--native", help="可编辑原生源 .py（缺省用内置黄金模型）")
    dp.add_argument("--out", required=True, help="DXF 输出路径")
    dp.add_argument("--part", required=True, help="标题栏 PART 字段")
    dp.add_argument("--revision", default="A", help="标题栏 REV 字段")
    dp.add_argument("--views", default="FRONT,TOP,RIGHT",
                    help="逗号分隔视图：FRONT/TOP/RIGHT/REAR/LEFT/BOTTOM")
    dp.add_argument("--scale", type=float, default=1.0, help="比例（1 表示 1:1）")
    dp.add_argument("--material", default="-", help="标题栏材料")
    dp.add_argument("--sheet", default="A3", choices=["A3", "A4"], help="图纸幅面")
    dp.add_argument("--section", action="append",
                    help="剖切平面，形如 Y=0（可重复；轴 X/Y/Z，偏移为模型单位）。"
                         "例：aipd drawing generate --part bracket --views TOP --section Y=0")
    dp.add_argument("--detail", action="append",
                    help="局部放大，形如 TOP@(-30,0)/12=2（可重复）："
                         "母视图@(母视图局部坐标 u,v)/放大圆半径=相对母视图的放大倍数（须 >1）。"
                         "圆心与半径用模型单位，可直接抄证据里的孔心。"
                         "例：aipd drawing generate --part bracket --views TOP "
                         "--detail \"TOP@(-30,0)/12=2\"")
    dp.add_argument("--spec", help="公差声明 JSON 路径："
                                   '{"features":[{"feature":"TOP.hole_2",'
                                   '"tolerance":{"upper":0.05,"lower":-0.05},'
                                   '"limits":{"min":5.95,"max":6.05}}],'
                                   '"global_tolerance":{"upper":0.2,"lower":-0.2}}'
                                   "；不传则整张图不含公差。这份声明可由 "
                                   "aipd drawing spec 从 Product Truth 的 CTQ 生成")
    dp.add_argument("--json", action="store_true")
    dp.set_defaults(func=COMMAND_FUNCS["drawing generate"])

    ds = drawing_sub.add_parser("spec", help="从 Product Truth 的 CTQ 生成 --spec 用的公差声明。"
                                             " Example: aipd drawing spec --db state.db "
                                             "--out tolerances.json")
    ds.add_argument("--db", required=True, help="Product Truth 状态库路径")
    ds.add_argument("--tenant", default="default")
    ds.add_argument("--project", default="default")
    ds.add_argument("--out", required=True, help="声明 JSON 输出路径（有缺口则不写）")
    ds.add_argument("--json", action="store_true")
    ds.set_defaults(func=COMMAND_FUNCS["drawing spec"])

    da = drawing_sub.add_parser(
        "assembly", help="多零件装配图：逐件投影 + 序号球标 + 明细表。"
                         " Example: aipd drawing assembly --manifest assembly.json "
                         "--out assy.dxf --part ASSY-1")
    da.add_argument("--manifest", required=True,
                    help='装配清单 JSON：{"parts":[{"name":"支架","step":"a.step",'
                         '"balloon":1,"offset":[0,0,0]}]}。'
                         "balloon 是作者声明的件号（正整数、不重复），"
                         "缺号/重号/写 0/零件重名/STEP 不存在一律 rc=2，不按遍历顺序发号")
    da.add_argument("--out", required=True, help="DXF 输出路径")
    da.add_argument("--part", required=True, help="标题栏 PART 字段（装配体代号）")
    da.add_argument("--revision", default="A", help="标题栏 REV 字段")
    da.add_argument("--views", default="FRONT,TOP",
                    help="逗号分隔装配视图：FRONT/TOP/RIGHT/REAR/LEFT/BOTTOM。"
                         "球标只标在**第一个**请求的视图上（装配图惯例）")
    da.add_argument("--explode", action="store_true",
                    help="按 manifest 里每个零件声明的 explode 位移出爆炸视图；"
                         "有一个零件没声明就直接拒绝（不画摆开一半的爆炸图）")
    da.add_argument("--scale", type=float, default=1.0, help="比例（1 表示 1:1）")
    da.add_argument("--material", default="-", help="标题栏材料")
    da.add_argument("--sheet", default="A3", choices=["A3", "A4"], help="图纸幅面")
    da.add_argument("--db", help="状态库路径（与 --bom 一起给）：给了才交叉核对球标↔BOM 行")
    da.add_argument("--bom", help="BOM 编号：明细表的数量、单位与材料取自这张 BOM 的行")
    da.add_argument("--tenant", default="default", help="BOM 所属租户")
    da.add_argument("--project", default="default", help="BOM 所属项目")
    da.add_argument("--json", action="store_true")
    da.set_defaults(func=COMMAND_FUNCS["drawing assembly"])

    p_outbox = sub.add_parser("outbox", help="消费对外副作用事件（RFQ 邮件等）。"
                                            " Example: aipd outbox drain --db state.db")
    outbox_sub = p_outbox.add_subparsers(dest="outbox_cmd", required=True)
    op = outbox_sub.add_parser("drain", help="领一批 outbox 事件并执行，打印每台操作结果。"
                                             " Example: aipd outbox drain --db state.db --limit 20")
    op.add_argument("--db", required=True)
    op.add_argument("--limit", type=int, default=10)
    op.add_argument("--worker-id", default="cli-outbox")
    op.add_argument("--json", action="store_true")
    op.set_defaults(func=COMMAND_FUNCS["outbox drain"])
    rv = outbox_sub.add_parser(
        "review",
        help="列出未收口的外部操作（结果未知/在飞/可重试），有则非零退出。"
             " Example: aipd outbox review --db state.db")
    rv.add_argument("--db", required=True)
    rv.add_argument("--limit", type=int, default=100)
    rv.add_argument("--json", action="store_true")
    rv.set_defaults(func=COMMAND_FUNCS["outbox review"])

    p = sub.add_parser("industrialize", help="供应链 + 验证执行（报价登记/阶段分析/纠偏任务；无数据则如实报告不虚构）。"  # noqa: E501
                                             " Example: aipd industrialize --db state.db --quote quotes.csv --stage dvt --lab-data lab.csv")  # noqa: E501
    p.add_argument("--db")
    p.add_argument("--project", help="影响传播需要定位 BOM 与制品时的项目（缺省：库内唯一项目）")
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
    mp = release_sub.add_parser("manifest", help="现取装配发布就绪证据文档（CTQ/图纸/BOM 对账）。"
                                               " Example: aipd release manifest --db state.db "
                                               "--drawing out/bracket.dxf --out evidence.json")
    mp.add_argument("--db", required=True, help="状态库路径（Product Truth 所在）")
    mp.add_argument("--tenant", default="default")
    mp.add_argument("--project", default="default")
    mp.add_argument("--drawing", action="append",
                    help="图纸 DXF 路径（可重复）；读其 .evidence.json 侧车")
    mp.add_argument("--bom", default=None, help="BOM id（不传则不写 bom_version）")
    mp.add_argument("--model", default=None, help="模型文件（.step）路径")
    mp.add_argument("--units", default="mm")
    mp.add_argument("--datum_scheme", default="unspecified")
    mp.add_argument("--approval-status", dest="approval_status", default="unapproved",
                    help="审批状态由属主填；缺省 unapproved，不代为置 approved")
    mp.add_argument("--out", default=None, help="证据文档输出路径")
    mp.add_argument("--json", action="store_true")
    mp.set_defaults(func=COMMAND_FUNCS["release manifest"])

    p = sub.add_parser("test", help="运行完整测试套件（pytest）。"
                                    " Example: aipd test")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=COMMAND_FUNCS["test"])

    p = sub.add_parser("eval", help="运行评估套件。"
                                    " Example: aipd eval --evals evals/evals.json --provider model --out evals_out")  # noqa: E501
    p.add_argument("--evals", default="evals/evals.json")
    p.add_argument("--provider",
                   choices=["fake", "deterministic-fixture", "contract-test",
                            "model", "real-model", "pure-contract"],
                   default="model",
                   help="默认真实模型端点；fake/contract-test 仅供开发测试")
    p.add_argument("--out")
    p.add_argument("--threshold", type=float, default=0.1)
    p.add_argument("--baseline")
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

    p = sub.add_parser("onboard", help="首次使用引导：一句话建项→立即产出第一份结果→展示能力与需外部配置项→Provider 引导→恢复/重置。"  # noqa: E501
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

    # ---- v5.11 结构化事实的失效传播（F-TRUTH-PROP-01）----
    p = sub.add_parser(
        "truth",
        help="Product Truth 失效传播（propagate 标 stale + 建返工任务 / "
             "tasks 看待办）。 Example: aipd truth propagate --db state.db "
             "--project p1 --upstream T-3")
    truth_sub = p.add_subparsers(dest="truth_cmd", required=True)
    tp = truth_sub.add_parser(
        "propagate",
        help="沿血缘把下游事实标 stale 并生成有界返工任务；有下游待返工即退出码 4。"
             "只接传播这半条链，返工的**执行**（run_rework）本仓尚未接线。")
    tp.add_argument("--db", required=True)
    tp.add_argument("--project", required=True)
    tp.add_argument("--tenant", default="default")
    tp.add_argument("--upstream", required=True,
                    help="上游 id：truth 记录 id，或 Product Intelligence 对象 id"
                         "（认不出时会如实标成 intelligence_or_external）")
    tp.add_argument("--reason", help="变更原因，写进每条返工任务")
    tp.add_argument("--max-attempts", type=int,
                    help="返工上限（缺省 3）；必须 > 0")
    tp.add_argument("--json", action="store_true")
    tp.set_defaults(func=COMMAND_FUNCS["truth propagate"])
    tt = truth_sub.add_parser(
        "tasks",
        help="列本作用域的返工待办（只读）。")
    tt.add_argument("--db", required=True)
    tt.add_argument("--project", required=True)
    tt.add_argument("--tenant", default="default")
    tt.add_argument("--status", help="按任务状态过滤，如 pending / blocked / succeeded")
    tt.add_argument("--json", action="store_true")
    tt.set_defaults(func=COMMAND_FUNCS["truth tasks"])

    # ---- v5.10 制造就绪（bom 物料清单 / cost 成本核算）----
    p_bom = sub.add_parser(
        "bom", help="物料清单（show 汇总+发布检查 / add 添加行 / release 检查后发布）。"
                    " Example: aipd bom add --db state.db --part 外壳 --quantity 1")
    bom_sub = p_bom.add_subparsers(dest="bom_cmd", required=True)
    bp = bom_sub.add_parser("show", help="BOM 汇总 + 开模可用物料清单发布检查清单。")
    bp.add_argument("--db", required=True)
    bp.add_argument("--project")
    bp.add_argument("--tooling", type=float, default=0.0, help="模具费（检查口径）")
    bp.add_argument("--quantity", type=int, default=1000, help="目标生产数量")
    bp.add_argument("--amortize-over", type=int, help="摊销数量（缺省=quantity）")
    bp.add_argument("--nre", type=float, default=0.0)
    bp.add_argument("--margin", type=float, default=0.0)
    bp.add_argument("--json", action="store_true")
    bp.set_defaults(func=COMMAND_FUNCS["bom show"])
    bp = bom_sub.add_parser("add", help="给最新 BOM 添加一行（自动创建 BOM）。")
    bp.add_argument("--db", required=True)
    bp.add_argument("--project")
    bp.add_argument("--part", required=True, help="零件/料号名称")
    bp.add_argument("--parent", help="父项（层级）；缺省为根件")
    bp.add_argument("--description", default="")
    bp.add_argument("--quantity", type=float, default=1.0)
    bp.add_argument("--unit", default="pcs")
    bp.add_argument("--material")
    bp.add_argument("--process", help="该行的主工艺/表面工艺（明细表那一格）")
    bp.add_argument("--supplier")
    bp.add_argument("--unit-cost", type=float, help="单位成本（缺省不填=未报价）")
    bp.add_argument("--currency", default="CNY")
    bp.add_argument("--deliverable", help="关联图纸/制品 deliverable_id")
    bp.add_argument("--quote-ref", help="关联报价引用")
    bp.add_argument("--status", default="planned",
                    choices=["planned", "quoted", "released", "obsolete"])
    bp.add_argument("--json", action="store_true")
    bp.set_defaults(func=COMMAND_FUNCS["bom add"])

    # bom release：与 show 同一套成本口径 + 发布检查清单，未过即拒绝（exit 4）
    bp = bom_sub.add_parser(
        "release", help="按发布检查清单校验后置为 released（未过则拒绝）。")
    bp.add_argument("--db", required=True)
    bp.add_argument("--project")
    bp.add_argument("--reason", default="", help="发布依据（如首件确认）")
    bp.add_argument("--tooling", type=float, default=0.0, help="模具费（检查口径）")
    bp.add_argument("--quantity", type=int, default=1000, help="目标生产数量")
    bp.add_argument("--amortize-over", type=int, help="摊销数量（缺省=quantity）")
    bp.add_argument("--nre", type=float, default=0.0)
    bp.add_argument("--margin", type=float, default=0.0)
    bp.add_argument("--json", action="store_true")
    bp.set_defaults(func=COMMAND_FUNCS["bom release"])

    # quote apply：报价文件 → Product Truth 事实 → BOM 行单价（F-SUPPLY-01）
    p_quote = sub.add_parser(
        "quote", help="询价/报价链（apply：把报价文件落到 BOM 上）。"
                      " Example: aipd quote apply --db state.db --file quotes.csv")
    quote_sub = p_quote.add_subparsers(dest="quote_cmd", required=True)
    qp = quote_sub.add_parser(
        "apply", help="解析报价 → 登记版本 → 写 quote.* 事实 → 写入 BOM 单价。")
    qp.add_argument("--db", required=True)
    qp.add_argument("--project")
    qp.add_argument("--file", required=True, help="报价 CSV/JSON 文件")
    qp.add_argument("--currency", default="CNY",
                    help="报价单价的币种（报价文件表头无币种列，必须显式声明）")
    qp.add_argument("--json", action="store_true")
    qp.set_defaults(func=COMMAND_FUNCS["quote apply"])

    # ---- v5.10 验证 / Issue / 就绪度 ----
    # 这 8 条命令此前只有实现、契约与文档，parser 从未接线（F-CLI-01）：
    # `aipd validation import` 在真实 CLI 上是 invalid choice。
    p_val = sub.add_parser(
        "validation", help="验证计划与 EVT/DVT/PVT 数据。"
                           " Example: aipd validation import --db state.db --project p1"
                           " --stage dvt --file lab.csv")
    val_sub = p_val.add_subparsers(dest="validation_cmd", required=True)

    vp = val_sub.add_parser("plan", help="创建验证计划。")
    vp.add_argument("--db", required=True)
    vp.add_argument("--project", required=True)
    vp.add_argument("--tenant", default="default")
    vp.add_argument("--stage", required=True, choices=["evt", "dvt", "pvt"])
    vp.add_argument("--title", required=True)
    vp.add_argument("--objective", default="")
    vp.add_argument("--json", action="store_true")
    vp.set_defaults(func=COMMAND_FUNCS["validation plan"])

    vp = val_sub.add_parser("list", help="列出验证计划/测试/结果。")
    vp.add_argument("--db", required=True)
    vp.add_argument("--project", required=True)
    vp.add_argument("--tenant", default="default")
    vp.add_argument("--what", default="plans", choices=["plans", "tests", "results"])
    vp.add_argument("--json", action="store_true")
    vp.set_defaults(func=COMMAND_FUNCS["validation list"])

    vp = val_sub.add_parser("show", help="显示验证计划/测试详情。")
    vp.add_argument("--db", required=True)
    vp.add_argument("--project", required=True)
    vp.add_argument("--tenant", default="default")
    vp.add_argument("--what", default="plan", choices=["plan", "test"])
    vp.add_argument("--id", required=True, help="VP- / VT- 编号")
    vp.add_argument("--json", action="store_true")
    vp.set_defaults(func=COMMAND_FUNCS["validation show"])

    vp = val_sub.add_parser(
        "import", help="导入 EVT/DVT/PVT 数据（失败项会传播到 BOM/制品）。")
    vp.add_argument("--db", required=True)
    vp.add_argument("--project", required=True)
    vp.add_argument("--tenant", default="default")
    vp.add_argument("--stage", required=True, choices=["evt", "dvt", "pvt"])
    vp.add_argument("--file", required=True, help="实验室数据文件（CSV/XLSX/JSON）")
    vp.add_argument("--plan-id", default="", help="关联的验证计划 ID（可选）")
    vp.add_argument("--json", action="store_true")
    vp.set_defaults(func=COMMAND_FUNCS["validation import"])

    p_iss = sub.add_parser(
        "issue", help="验证 Issue 列表/详情/处置。"
                           " Example: aipd issue list --db state.db --project p1")
    iss_sub = p_iss.add_subparsers(dest="issue_cmd", required=True)

    ip = iss_sub.add_parser("list", help="列出 Issue。")
    ip.add_argument("--db", required=True)
    ip.add_argument("--project", required=True)
    ip.add_argument("--tenant", default="default")
    ip.add_argument("--status", help="按状态过滤（如 OPEN / RESOLVED）")
    ip.add_argument("--blocking", action="store_true", help="只看阻塞发布的 Issue")
    ip.add_argument("--json", action="store_true")
    ip.set_defaults(func=COMMAND_FUNCS["issue list"])

    ip = iss_sub.add_parser("show", help="显示 Issue 详情。")
    ip.add_argument("--db", required=True)
    ip.add_argument("--project", required=True)
    ip.add_argument("--tenant", default="default")
    ip.add_argument("--id", required=True, help="IS- 编号")
    ip.add_argument("--json", action="store_true")
    ip.set_defaults(func=COMMAND_FUNCS["issue show"])

    ip = iss_sub.add_parser("resolve", help="记录处置并把 Issue 置为 RESOLVED。")
    ip.add_argument("--db", required=True)
    ip.add_argument("--project", required=True)
    ip.add_argument("--tenant", default="default")
    ip.add_argument("--id", required=True)
    ip.add_argument("--disposition", required=True,
                    choices=["FIX", "WAIVE", "DESIGN_CHANGE", "NOT_APPLICABLE"])
    ip.add_argument("--root-cause", default="")
    ip.add_argument("--revalidation", action="store_true", help="要求复验")
    ip.add_argument("--json", action="store_true")
    ip.set_defaults(func=COMMAND_FUNCS["issue resolve"])

    p_ready = sub.add_parser(
        "readiness", help="制造就绪度评估。"
                          " Example: aipd readiness check --db state.db --project p1")
    ready_sub = p_ready.add_subparsers(dest="readiness_cmd", required=True)
    rp = ready_sub.add_parser("check", help="按验证/Issue 事实评估就绪度。")
    rp.add_argument("--db", required=True)
    rp.add_argument("--project", required=True)
    rp.add_argument("--tenant", default="default")
    rp.add_argument("--json", action="store_true")
    rp.set_defaults(func=COMMAND_FUNCS["readiness check"])

    p_cost = sub.add_parser(
        "cost", help="成本核算（BOM 材料 + 模具摊销 + NRE + 毛利，写回 Product Truth）。"
                     " Example: aipd cost calc --db state.db --tooling 50000 --quantity 1000")
    cost_sub = p_cost.add_subparsers(dest="cost_cmd", required=True)
    cp = cost_sub.add_parser("calc", help="确定性成本核算。")
    cp.add_argument("--db", required=True)
    cp.add_argument("--project")
    cp.add_argument("--tooling", type=float, default=0.0, help="模具费")
    cp.add_argument("--quantity", type=int, default=1000, help="目标生产数量")
    cp.add_argument("--amortize-over", type=int, help="模具/NRE 摊销数量（缺省=quantity）")
    cp.add_argument("--nre", type=float, default=0.0, help="一次性工程费 NRE")
    cp.add_argument("--margin", type=float, default=0.0, help="毛利百分比（如 20）")
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=COMMAND_FUNCS["cost calc"])

    return parser


def _cmd_usage(args: argparse.Namespace) -> int:
    print("AIPD-OS v5.6 支持的命令：")
    for cmd in PLANNED_COMMANDS:
        print(f"  aipd {cmd}")
    return 0


def main(argv: list | None = None) -> int:
    warnings.simplefilter("default", DeprecationWarning)
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
        code = exc.code
        if code is None:
            return 0
        try:
            return int(code)
        except (TypeError, ValueError):
            # SystemExit 带字符串消息（如 eval --provider pure-contract）
            print(f"错误：{code}", file=sys.stderr)
            return 1
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
