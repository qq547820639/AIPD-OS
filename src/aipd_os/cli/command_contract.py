"""Canonical Command Contract — 命令元数据的 Single Source of Truth。

本模块定义所有 CLI 命令的权威元数据，被以下消费者使用：
- CLI registry（commands.py 的 COMMAND_FUNCS）
- SKILL.md 命令清单
- skill_quality_audit.py 审计脚本
- test_command_coverage.py 覆盖测试

任何新增/修改/废弃命令必须在此处登记，而非在审计脚本中硬编码。

用法：
    from aipd_os.cli.command_contract import PUBLIC_COMMANDS, DEPRECATED_COMMANDS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CommandStatus(str, Enum):
    """命令生命周期状态。"""
    PUBLIC = "public"           # 当前公开命令，应出现在 SKILL.md
    DEPRECATED = "deprecated"   # 已废弃，保留向后兼容
    INTERNAL = "internal"       # 内部命令，不对外暴露
    PLANNED = "planned"         # 计划中，尚未实现


class CommandCategory(str, Enum):
    """命令功能分类。"""
    CORE = "core"                       # 核心流程
    OWNER_EXPERIENCE = "owner"          # 所有者体验
    MANUAL = "manual"                   # 手册链
    CAD = "cad"                         # CAD
    PRODUCT = "product"                 # 产品定义
    INDUSTRIALIZATION = "industrialize" # 工业化
    MANUFACTURING = "manufacturing"     # 制造就绪
    VALIDATION = "validation"           # 验证/Issue/Readiness
    AUDIT_RELEASE = "audit_release"     # 审计与发布
    OPERATIONS = "operations"           # 运维体检
    LEGACY = "legacy"                   # 遗留兼容


@dataclass(frozen=True)
class CommandEntry:
    """单个命令的元数据。"""
    name: str                                    # 命令名（如 "init"、"manual plan"）
    status: CommandStatus                        # 生命周期状态
    category: CommandCategory                    # 功能分类
    introduced_in: str = ""                      # 引入版本（如 "5.1"）
    deprecated_in: str = ""                      # 废弃版本
    replacement: str = ""                        # 废弃后替代命令
    requires_args: frozenset[str] = field(       # 必需参数（如 "--db"、"--project"）
        default_factory=frozenset)
    description: str = ""                        # 简短描述


# ==========================================================================
# 命令注册表 — 这是唯一的 Single Source of Truth
# ==========================================================================

_COMMAND_REGISTRY: list[CommandEntry] = [
    # ---- 核心流程 ----
    CommandEntry("init", CommandStatus.PUBLIC, CommandCategory.CORE, "5.1",
                 description="初始化新项目"),
    CommandEntry("intake", CommandStatus.PUBLIC, CommandCategory.CORE, "5.1",
                 description="从自然语言需求创建项目和 Idea"),
    CommandEntry("resume", CommandStatus.PUBLIC, CommandCategory.CORE, "5.1",
                 description="恢复/迁移旧版项目"),
    CommandEntry("status", CommandStatus.PUBLIC, CommandCategory.CORE, "5.1",
                 description="查看项目状态"),
    CommandEntry("run", CommandStatus.PUBLIC, CommandCategory.CORE, "5.1",
                 description="运行监督器直到决策或步骤耗尽"),
    CommandEntry("decide", CommandStatus.PUBLIC, CommandCategory.CORE, "5.1",
                 description="裁定决策"),

    # ---- 所有者体验 ----
    CommandEntry("onboard", CommandStatus.PUBLIC, CommandCategory.OWNER_EXPERIENCE, "5.5",
                 description="新手引导"),
    CommandEntry("dashboard", CommandStatus.PUBLIC, CommandCategory.OWNER_EXPERIENCE, "5.5",
                 description="仪表盘视图"),
    CommandEntry("operate", CommandStatus.PUBLIC, CommandCategory.OWNER_EXPERIENCE, "5.5",
                 description="运维操作"),
    CommandEntry("ui", CommandStatus.PUBLIC, CommandCategory.OWNER_EXPERIENCE, "5.6",
                 description="Owner Web Console"),
    CommandEntry("reset", CommandStatus.PUBLIC, CommandCategory.OWNER_EXPERIENCE, "5.5",
                 description="重置项目状态"),
    CommandEntry("recover", CommandStatus.PUBLIC, CommandCategory.OWNER_EXPERIENCE, "5.5",
                 description="恢复项目"),

    # ---- 手册链 ----
    CommandEntry("manual plan", CommandStatus.PUBLIC, CommandCategory.MANUAL, "5.1",
                 description="规划手册批次"),
    CommandEntry("manual generate", CommandStatus.PUBLIC, CommandCategory.MANUAL, "5.1",
                 description="生成手册页面"),

    # ---- CAD ----
    CommandEntry("cad preflight", CommandStatus.PUBLIC, CommandCategory.CAD, "5.1",
                 description="CAD 预检"),
    CommandEntry("cad build", CommandStatus.PUBLIC, CommandCategory.CAD, "5.1",
                 description="构建 CAD 模型"),
    CommandEntry("drawing generate", CommandStatus.PUBLIC, CommandCategory.CAD, "5.10",
                 requires_args=frozenset({"--part"}),
                 description="从 3D 模型出二维工程图 DXF（可见线+隐藏线+尺寸+标题栏）"),
    CommandEntry("drawing spec", CommandStatus.PUBLIC, CommandCategory.CAD, "5.10",
                 requires_args=frozenset({"--db", "--out"}),
                 description="从 Product Truth 的 CTQ 生成 --spec 用的公差声明（缺口即不写文件）"),
    CommandEntry("drawing assembly", CommandStatus.PUBLIC, CommandCategory.CAD, "5.10",
                 requires_args=frozenset({"--manifest", "--part"}),
                 description="多零件装配图：逐件投影 + 序号球标 + 明细表（编号只认 manifest）"),
    CommandEntry("drawing assembly-steps", CommandStatus.PUBLIC, CommandCategory.CAD, "5.11",
                 requires_args=frozenset({"--manifest", "--out", "--part"}),
                 description="装配步骤文档：步骤号与引用球标都由 manifest 声明，"
                             "断档/引用未声明的号/写了不承载的字段一律拒绝（C6 装配那一半）"),
    CommandEntry("drawing assembly-step", CommandStatus.PUBLIC, CommandCategory.CAD, "5.11",
                 requires_args=frozenset({"--manifest", "--out", "--part"}),
                 description="按装配清单出总装 STEP：摆放只用 manifest 声明的 offset，"
                             "写完逐件回读中心与体积，对不上就删文件并报错"),
    CommandEntry("drawing dfm", CommandStatus.PUBLIC, CommandCategory.CAD, "5.11",
                 requires_args=frozenset({"--step", "--out", "--part"}),
                 description="DFM/DFA 分析：壁厚/深径比/内圆角/同轴孔系由内核实测，"
                             "阈值一律带来源；测不出来的记盲区，不折算成合格"),

    # ---- 结构化事实的失效传播（F-TRUTH-PROP-01）----
    CommandEntry("truth propagate", CommandStatus.PUBLIC, CommandCategory.PRODUCT, "5.11",
                 requires_args=frozenset({"--db", "--project", "--upstream"}),
                 description="沿血缘把下游标 stale 并生成有界返工任务（有待返工即退出码 4）"),
    CommandEntry("truth tasks", CommandStatus.PUBLIC, CommandCategory.PRODUCT, "5.11",
                 requires_args=frozenset({"--db", "--project"}),
                 description="列本作用域的返工待办（只读，不改任何状态）"),

    # ---- 对外副作用（outbox）----
    CommandEntry("outbox drain", CommandStatus.PUBLIC, CommandCategory.OPERATIONS, "5.10",
                 requires_args=frozenset({"--db"}),
                 description="消费 outbox 事件：真发外部副作用并按幂等台账去重"),
    CommandEntry("outbox review", CommandStatus.PUBLIC, CommandCategory.OPERATIONS, "5.10",
                 requires_args=frozenset({"--db"}),
                 description="核对未收口的外部操作（结果未知/在飞/可重试），有则非零退出"),

    # ---- 产品定义 ----
    CommandEntry("product show", CommandStatus.PUBLIC, CommandCategory.PRODUCT, "5.9",
                 description="查看产品定义"),
    CommandEntry("product gate", CommandStatus.PUBLIC, CommandCategory.PRODUCT, "5.9",
                 description="产品定义门禁"),

    # ---- 工业化 ----
    CommandEntry("industrialize", CommandStatus.PUBLIC, CommandCategory.INDUSTRIALIZATION, "5.1",
                 description="工业化流程"),
    CommandEntry("validate", CommandStatus.PUBLIC, CommandCategory.INDUSTRIALIZATION, "5.1",
                 description="验证流程"),

    # ---- 制造就绪 ----
    CommandEntry("bom show", CommandStatus.PUBLIC, CommandCategory.MANUFACTURING, "5.10",
                 description="查看 BOM 物料清单"),
    CommandEntry("bom add", CommandStatus.PUBLIC, CommandCategory.MANUFACTURING, "5.10",
                 description="添加 BOM 条目"),
    CommandEntry("bom release", CommandStatus.PUBLIC, CommandCategory.MANUFACTURING, "5.10",
                 requires_args=frozenset({"--db"}),
                 description="把 BOM 置为 released；发布检查清单未过则拒绝并非零退出"),
    CommandEntry("quote apply", CommandStatus.PUBLIC, CommandCategory.MANUFACTURING, "5.10",
                 requires_args=frozenset({"--db", "--file"}),
                 description="报价文件登记→落 Product Truth→写入 BOM 行单价"),
    CommandEntry("cost calc", CommandStatus.PUBLIC, CommandCategory.MANUFACTURING, "5.10",
                 description="成本核算"),

    # ---- 审计与发布 ----
    CommandEntry("audit", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE, "5.1",
                 description="仓库审计"),
    CommandEntry("interfaces", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE, "5.12",
                 description="接口清单与契约证据：逐条列本机声明的接口、定义件哈希与取证用例"
                             "（刻意不叫 ICD：对侧签的那两节本仓产不了）"),
    CommandEntry("release check", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE, "5.1",
                 description="发布检查"),
    CommandEntry("release manifest", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE,
                 "5.10", description="现取装配发布就绪证据文档（CTQ/图纸/BOM 对账）"),
    CommandEntry("test", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE, "5.1",
                 description="运行测试套件"),
    CommandEntry("eval", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE, "5.1",
                 description="运行评估套件"),
    CommandEntry("package", CommandStatus.PUBLIC, CommandCategory.AUDIT_RELEASE, "5.1",
                 description="打包发布"),

    # ---- 运维体检 ----
    CommandEntry("doctor", CommandStatus.PUBLIC, CommandCategory.OPERATIONS, "5.5",
                 description="运维体检"),
    CommandEntry("version", CommandStatus.PUBLIC, CommandCategory.OPERATIONS, "5.5",
                 description="显示版本信息（--verbose 显示详细信息）"),

    # ---- Validation / Issue / Readiness（v5.10） ----
    CommandEntry("validation plan", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="创建验证计划"),
    CommandEntry("validation list", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="列出验证计划/测试/结果"),
    CommandEntry("validation show", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="显示验证详情"),
    CommandEntry("validation import", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="导入 EVT/DVT/PVT 数据"),
    CommandEntry("issue list", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="列出 Issue"),
    CommandEntry("eco create", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.12",
                 requires_args=frozenset({"--db", "--project", "--title", "--creator"}),
                 description="开一张 ECR/ECO 变更单（DRAFT；作者必须是人）"),
    CommandEntry("eco affected", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.12",
                 requires_args=frozenset({"--db", "--project", "--id", "--object-type",
                                          "--object-id", "--change"}),
                 description="给变更单加一行影响对象（UPDATE 必须同时交改前/改后 sha256）"),
    CommandEntry("eco transition", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.12",
                 requires_args=frozenset({"--db", "--project", "--id", "--to", "--actor"}),
                 description="走一步状态；不许自批、空清单不可批准、已实施/已复验要交凭据"),
    CommandEntry("eco show", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.12",
                 requires_args=frozenset({"--db", "--project"}),
                 description="看一张单的详情与流水，或列出未闭合的变更单"),
    CommandEntry("issue show", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="显示 Issue 详情"),
    CommandEntry("issue resolve", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="解决 Issue"),
    CommandEntry("readiness check", CommandStatus.PUBLIC, CommandCategory.VALIDATION, "5.10",
                 description="检查制造就绪度"),

    # ---- 遗留兼容（deprecated） ----
    CommandEntry("init-project", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="init",
                 description="初始化项目（旧版）"),
    CommandEntry("restore-project", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="resume",
                 description="恢复项目（旧版）"),
    CommandEntry("run-supervisor", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="run",
                 description="运行监督器（旧版）"),
    CommandEntry("project-summary", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="status",
                 description="项目摘要（旧版）"),
    CommandEntry("submit-decision", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="decide",
                 description="提交决策（旧版）"),
    CommandEntry("run-manual-chain", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="manual generate",
                 description="运行手册链（旧版）"),
    CommandEntry("run-cad-chain", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="cad build",
                 description="运行 CAD 链（旧版）"),
    CommandEntry("run-tests", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="test",
                 description="运行测试（旧版）"),
    CommandEntry("run-evals", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="eval",
                 description="运行评估（旧版）"),
    CommandEntry("build-release", CommandStatus.DEPRECATED, CommandCategory.LEGACY, "5.0",
                 deprecated_in="5.1", replacement="package",
                 description="构建发布（旧版）"),
]

# ==========================================================================
# 便捷查询接口
# ==========================================================================

# 以 name 为 key 的映射
_BY_NAME: dict[str, CommandEntry] = {e.name: e for e in _COMMAND_REGISTRY}


def get_all_commands() -> list[CommandEntry]:
    """返回所有已注册命令。"""
    return list(_COMMAND_REGISTRY)


def get_commands_by_status(status: CommandStatus) -> list[CommandEntry]:
    """按状态筛选命令。"""
    return [e for e in _COMMAND_REGISTRY if e.status == status]


def get_command_entry(name: str) -> CommandEntry | None:
    """按名称查找命令元数据。"""
    return _BY_NAME.get(name)


# 公开命令集合（SKILL.md 应声明的命令）
PUBLIC_COMMANDS: frozenset[str] = frozenset(
    e.name for e in _COMMAND_REGISTRY
    if e.status == CommandStatus.PUBLIC
)

# 已废弃命令集合
DEPRECATED_COMMANDS: frozenset[str] = frozenset(
    e.name for e in _COMMAND_REGISTRY
    if e.status == CommandStatus.DEPRECATED
)

# 内部命令集合
INTERNAL_COMMANDS: frozenset[str] = frozenset(
    e.name for e in _COMMAND_REGISTRY
    if e.status == CommandStatus.INTERNAL
)

# 所有已注册命令（public + deprecated + internal，不含 planned）
ALL_REGISTERED_COMMANDS: frozenset[str] = frozenset(
    e.name for e in _COMMAND_REGISTRY
    if e.status != CommandStatus.PLANNED
)

# 审计时的 sanity check。**刻意不写死数字**：写死过一次的注释停在了「当前为 29」，
# 而真实命令面早已是 56 条——一条会过期的数不如没有。
EXPECTED_PUBLIC_COUNT = len(PUBLIC_COMMANDS)
