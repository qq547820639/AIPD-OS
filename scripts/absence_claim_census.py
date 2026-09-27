"""登记表里"某样东西还没有"这类否定句，必须配一个能把它证伪的锚点（F-STALE-ABSENCE 第 65 片）。

## 为什么开这一面

第 53 片接上 BOM 版本记录的返工执行器（`src/aipd_os/bom/bom_rework.py`）之后，
登记表里那句「BOM 版本记录仍没有」一直没人改；同一行的另一句「执行器只认图纸声明这一类制品」
也一样漂着。第 65 片派出的只读普查把它们抓回来，而**抓回来靠的是人不是机器**——
这与第 59/60 片同族：那次缺的判据是"文档点名的命令要注册着"，于是有了
`doc_command_census.py`；这次缺的是"文档承诺的缺口要真的还缺着"，
而成熟工具里没有这一面（选型见取证文档：doorstop 判的是 YAML item 之间的断链，
doctest 判的是正文里的可执行 Python，中文否定句两者都不是）。

## 判据形状（三态，不把"看不见"折成任何一种判决）

一条登记 = (能力 id, 字段, 锚点原文, 反证锚点)。锚点在语料里**找不到** ⇒ 判红（账本与正文脱钩：
本轮就是把两句过期话删掉的那一轮，删话不删账必须响）；反证锚点**存在** ⇒ 判红（这句话已经过期）；
反证锚点**不存在** ⇒ 成立；反证锚点**解析不出来**（要一跳解析的常量指不到模块）⇒ 前提不成立退 2，
绝不折算成"这句话是对的"。

登记表里带否定词的句子远不止登记的这几条（现算值看 `--json` 的 `corpus`，本文不抄绝对数——
抄一份就会漂，这是第 60 片在自己 docstring 里犯过的错）。**自动从散文里判"这句是不是过期"
今天不开**：第 65 片实测把 15 个否定词打进登记表，命中的句子里大量是合法写法
（「不静默退回『没有基线』」「所以『没有执行器』不会被伪装成返工失败三次」这类谈设计的句子），
判红面一宽就会惩罚"把缺口写下来"这件事。所以散文面只报不红，并报出"登记了几条 / 还有几条没登记"，
让覆盖率成为一个看得见、会变的数。

## 第四面：同一个 id 不许两份登记表各说各话

`duplicate_divergence`：同一个能力 id 在两处登记表里对同一字段给出不同文本 ⇒ 判红。
这条不是设计出来的，是第 65 片自己被抓出来的：`product.*` 七行的**权威**在
`scripts/product_capabilities_extra.py`（`src/aipd_os/registry_data.py` 顶部就写着
"由生成脚本合并、勿手改本文件"），第一轮我只改了生成物那一侧，两份当场不一致，
而当时那一句「生产 Provider 未接入」在权威里活得好好的。同一 id 两处的分母与差异
都由 `--json` 的 `divergence` 现报。

退码：0 全部成立；4 有过期句或悬空账；2 前提不成立（账本空、登记表读不出、锚点解析不出）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

REGISTRY_FILES = ("src/aipd_os/registry_data.py",
                  "scripts/product_capabilities_extra.py")
# `truth_lineage` 的唯一 SQL 写入口。它自己不算"生产者"，但必须出现在权威面上，
# 否则读到一个空集合会被当成"没有生产者"。
SQL_ENTRY_FILE = "src/aipd_os/product_truth/lineage.py"

# 只报面的分母用这套否定词。刻意**不**拿它判红，理由见模块 docstring。
NEGATION_MARKERS = ("仍没有", "还没有", "尚未", "未实现", "未接入", "未做", "仍未",
                    "不支持", "不存在", "没有", "无执行", "暂无", "未提供", "未覆盖")

# ---- 第 67 片：把"带否定词的句子"收窄成"能力缺失句"，只有后者要求逐条处置 ----
# 宽档量过就是噪声：37 句里 17 句谈的是判决与行为（「圆内没有图线即判未收口」
# 「三种都不算收口」「未声明则不写任何公差」），拿它当分母去逼"每条都要登记"，
# 逼出来的只会是一堆豁免条——判据该收窄，不是把例外堆高（第 67 片实测：
# 宽档 37 / 窄档 20，被挡掉的 17 句全是行为描述）。
# 窄档 = 缺失谓词 × 能力名词同句，再排掉两类明确在谈"判决/口径"的写法。
ABSENCE_PREDICATES = ("仍没有", "还没有", "尚未", "未实现", "未接入", "未做", "仍未",
                      "未建", "不建模", "没有", "无")
CAPABILITY_NOUNS = ("执行器", "生产者", "实现", "接入", "映射", "路", "入口", "求解",
                    "表", "工序", "工艺路线", "剖", "图框", "身份源", "投影",
                    "语义", "CAE", "工时", "成本", "自动")
NON_CLAIM_PATTERNS = ("不算收口", "不写任何公差", "即判未收口", "记成盲区",
                      "不会被伪装成", "不能用来放行", "读者不会把")

HOLDS = "HOLDS"                        # 反证锚点确实不在 ⇒ 这句"还没有"是活的
CONTRADICTED = "CONTRADICTED"          # 反证锚点在了 ⇒ 这句话过期（判红）
CLAIM_TEXT_ABSENT = "CLAIM_TEXT_ABSENT"  # 账里有、正文里已经找不到这句（判红：账文脱钩）
UNACCOUNTED = "UNACCOUNTED"            # 能力缺失句既没登记也没豁免（第 67 片，判红）
PRECONDITION = "PRECONDITION"          # 锚点解析不出来 ⇒ 不判，退 2

# ---------------------------------------------------------------------------
# 账本：每条都是一个"仍缺着"的承诺 + 什么一旦出现它就过期。
# anchor 必须是登记表里**逐字**出现的片段；改那句话时必须同批改这里。
# ---------------------------------------------------------------------------
CLAIMS: tuple[dict[str, Any], ...] = (
    {
        "id": "REWORK-EXECUTOR-QUOTE-BATCH",
        "capability": "product_truth.impact_propagation",
        "field": "current_limitation",
        "anchor": "仍没有执行器的是 **quote_batch**",
        "check": {"kind": "artifact_executor", "artifact": "quote_batch"},
        "why": "返工执行器按 `SUPPORTED_ARTIFACT = \"<制品类型>\"` 这条惯例登记"
               "（第 47/49/53 片四个执行器都是这个形状），报价批次哪天接上就过期",
    },
    {
        "id": "FACT-LINEAGE-WIRED",
        "capability": "supervisor.fact_writeback",
        "field": "current_limitation",
        "anchor": "evidence 现在会连上游 truth 边",
        "check": {"kind": "external_callers", "symbol": "write_fact_lineage",
                  "expect": "present"},
        "why": "第 65/66 片那条「还没有映射」的缺席式登记在第 70 片被接线闭合 ⇒ 同批撤掉；"
               "换成存在式：句子里说会连边，反证 = `write_fact_lineage` 在生产面 0 处外部调用点",
    },
    {
        "id": "CAD-ASSEMBLY-CONSTRAINT-SOLVER",
        "capability": "cad.2d_drawings",
        "field": "current_limitation",
        "anchor": "仍未实现：装配约束/配合与爆炸位移的自动求解",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                  "symbols": ["AssemblyConstraint", "solve_constraints"]},
        "why": "约束对象/求解器一旦出现（本仓不建约束对象是这句话的内容本身），这句要就地改",
    },
    {
        "id": "QUOTE-FX-CONVERSION",
        "capability": "industrialize.quote_to_bom_cost",
        "field": "current_limitation",
        "anchor": "跨币种折算未实现",
        "check": {"kind": "identifier",
                  "paths": ["src/aipd_os/supply_chain", "src/aipd_os/bom"],
                  "symbols": ["convert_currency", "currency_rate", "fx_conversion"]},
        "why": "折算要么显式名要么汇率字段名；两者都不在时拒绝折算才是真的没做",
    },
    {
        "id": "FULLTEXT-STEP-WIRED",
        "capability": "research.fulltext_fetch",
        "field": "current_limitation",
        "anchor": "是库里 fetch_fulltext 的消费者",
        "check": {"kind": "external_callers", "symbol": "fetch_fulltext",
                  "expect": "present"},
        "why": "第 65 片那条缺席式登记（「没有一个连接器消费它」）在第 76 片被接上 ⇒ 同批撤掉；"
               "换成存在式：反证 = 生产面里再没人调用 `fetch_fulltext`（库里的定义不算调用点）",
    },
    {
        "id": "PRODUCER-COUNT-REGISTRY",
        "capability": "product_truth.impact_propagation",
        "field": "current_limitation",
        "anchor": "血缘边的生产者今天有 9 个",
        "check": {"kind": "producer_count", "scope": "truth"},
        "why": "权威 = AST 现读「含 `add_edge` 属性调用且文件里出现 `LineageGraph`」的文件集，"
               "SQL 写入口 `product_truth/lineage.py` 自己单列不算生产者；"
               "数字从**这句话里**现读，账本不抄第二份",
    },
    {
        "id": "PRODUCER-COUNT-ARCH",
        "file": "docs/architecture/truth_architecture.md",
        "anchor": "血缘边有** 9 个**生产者",
        "check": {"kind": "producer_count", "scope": "truth"},
        "why": "同一件事在架构文档里的第二个副本；两档面各判各的，谁漂了当场点名",
    },
    # ---- 第 67 片：把"能力缺失句"逐条挂上反证锚点 ----
    {
        "id": "EVIDENCE-REWORK-WIRED",
        "capability": "industrialize.physical_writeback",
        "field": "current_limitation",
        "anchor": "第 71 片：拿记下来的工作项再执行一次",
        "check": {"kind": "external_callers", "symbol": "rework_evidence_artifact",
                  "expect": "present"},
        "why": "存在式：登记说这一类制品收得了口，反证 = 执行器在生产面 0 处外部调用点。"
               "第 70 片让证据能被标 stale 之后，这一格才成为缺口，本片补上",
    },
    {
        "id": "BOM-COST-TO-CTQ-REVERSE-PATH",
        "capability": "product_truth.impact_propagation",
        "field": "current_limitation",
        "anchor": "BOM/成本变动要反向影响 CTQ 结论（上游方向）也还没有路",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/bom"],
                  "symbols": ["ctq", "CTQ"]},
        "why": "反向那条边一旦存在，BOM/成本侧必然要引用 CTQ 身份；"
               "锚点取在 BOM 侧而不是 cad 侧，取在 cad 侧会因为正方向已有边而假红",
    },
    {
        "id": "DRAWING-SECTION-TYPES",
        "capability": "cad.2d_drawings",
        "field": "current_limitation",
        "anchor": "未做阶梯剖/旋转剖",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                  "symbols": ["stepped_section", "aligned_section", "rotated_section"]},
        "why": "阶梯剖在 ASME/ISO 里叫 aligned/offset section、旋转剖叫 revolved；"
               "三个名字都不在才敢说两样都没做",
    },
    {
        "id": "ASSEMBLY-OPERATIONS-TABLE",
        "capability": "cad.assembly_instructions",
        "field": "current_limitation",
        "anchor": "多工序工艺路线仍未建 operations 表",
        "check": {"kind": "table_ddl", "table": "operations"},
        "why": "权威是 DDL：`src/`+`migrations/`+`state_service/` 里出现 "
               "`CREATE TABLE operations(` 即过期（`external_operations` 不算——"
               "正则要求表名后紧跟左括号，就是为了不吃前缀碰撞）",
    },
    {
        "id": "GATE-COMMIT-CLI-ENTRY-WIRED",
        "capability": "product.definition_gate",
        "field": "current_limitation",
        "anchor": "aipd product gate --commit",
        "check": {"kind": "external_callers", "symbol": "commit_approved",
                  "expect": "present"},
        "why": "第 68 片那两条「没有生产入口」在第 69 片被 CLI 接上 ⇒ 同批撤掉；"
               "这一条是**存在式**登记（账本里第一条）：句子里说走 `--commit`，"
               "反证 = `commit_approved` 在生产面 0 处外部调用点 ⇒ 旗子被摘掉就翻红",
    },
    {
        "id": "ASSEMBLY-STEPS-PDF-LAYOUT",
        "capability": "cad.assembly_instructions",
        "field": "current_limitation",
        "anchor": "版式只有 Markdown，PDF/图框未做",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                  "symbols": ["compose_pdf", "pdfgen", "to_pdf"]},
        "why": "库里 `layout/composer.py` 确实用 reportlab 出手册 PDF——所以锚点必须取在"
               "**装配步骤文档那一侧**（`src/aipd_os/cad`），取在库里会把这句真话判成过期"
               "（第 67 片实测的第二条窄法，与 RESEARCH-CONNECTOR-FULLTEXT 同因）",
    },
)

SELF_STEMS = {"absence_claim_census", "test_absence_claim_census"}
SKIP_DIRS = {".git", ".venv", ".venv-ci", "__pycache__", ".mypy_cache", ".pytest_cache",
             "build", "dist", "node_modules", "releases", ".pytest", ".ruff_cache"}


# ------------------------------------------------------------------ 语料读取
def registry_strings(root: Path) -> tuple[dict[str, dict[str, list[tuple[str, int, str]]]],
                                          list[str]]:
    """AST 读登记表：`{能力 id: {字段: [(文件, 行号, 文本)]}}`。

    不 import 登记表：它 import 了产品包，判据跑起来不该有副作用，也不该被一次导入失败
    整个吞掉（那样"看不见"会被读成"没有否定句"）。
    **文件名必须进读数**：`src/aipd_os/registry_data.py` 顶部写着"7 项 product.* 由
    `scripts/product_capabilities_extra.py` 合并生成、勿手改本文件"——第 65 片我就是只改了
    生成物那一侧，靠这条读数才看见两份不一致（见 `duplicate_divergence`）。
    """
    out: dict[str, dict[str, list[tuple[str, int, str]]]] = {}
    problems: list[str] = []
    found_any = False
    for rel in REGISTRY_FILES:
        path = root / rel
        if not path.is_file():
            continue
        found_any = True
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"registry_unparseable: {rel}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            cid = ""
            fields: dict[str, list[tuple[str, int, str]]] = {}
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                if key.value == "id":
                    cid = value.value
                fields.setdefault(key.value, []).append((rel, value.lineno, value.value))
            if cid:
                bucket = out.setdefault(cid, {})
                for fname, rows in fields.items():
                    bucket.setdefault(fname, []).extend(rows)
    if not found_any:
        problems.append("registry_missing: 登记表一个都没读到")
    return out, problems


def duplicate_divergence(corpus: dict[str, dict[str, list[tuple[str, int, str]]]]) -> list[dict]:
    """同一个能力 id 在两份登记表里对同一字段各说各话 ⇒ 至少有一份是错的。

    这一面与"否定句过期"同轴的理由很简单：它就是把同一句话登记在两处时，
    改一处会被读成两处都改完的那个失效模式（第 65 片实测抓到一次）。
    """
    out: list[dict] = []
    for cid, fields in sorted(corpus.items()):
        for fname, rows in sorted(fields.items()):
            per_file: dict[str, set[str]] = {}
            for rel, _lineno, text in rows:
                per_file.setdefault(rel, set()).add(text)
            if len(per_file) < 2:
                continue
            distinct = {t for texts in per_file.values() for t in texts}
            if len(distinct) > 1:
                out.append({"capability": cid, "field": fname,
                            "files": sorted(per_file),
                            "lines": [f"{rel}:{lineno}" for rel, lineno, _t in rows]})
    return out


# ---------------------------------------------------------------------------
# 三档"挡掉"的具名样本（第 74 片）：每档至少一句真实登记表文本 + 它该落的轴。
#
# 为什么不只钉计数：第 73 片的下界是"每档 > 0"，那意味着**把窄档的两句挪去无名词档、
# 再把无名词档的两句挪去谈判决档**，总数与三档都还是非空，读数一片祥和。
# 具名样本钉的是分布：某句今天算不算能力缺失，是判据的**结论**，不是它的作用域。
# 三个失败面都算前提不成立（退 2）：样本找不到（登记表漂了）、样本落错轴（词表被改坏）、
# 某档没有样本（有人为了让判据"更严"而悄悄删掉一条对照）。
AXIS_SAMPLES: dict[str, tuple[str, ...]] = {
    "narrow": ("仍没有执行器的是 quote_batch",
               "BOM/成本变动要反向影响 CTQ 结论"),
    "no-predicate": ("内置族为常用成年男女/儿童百分位示例",
                     "尺寸实测值是否落在 CTQ 合格域内由图纸侧判"),
    "no-noun": ("项目里还没有 BOM 版本记录时记录照写",
                "条目里仍不写 drawing_feature"),
    "non-claim": ("圆内没有图线即判未收口",
                  "三种都不算收口"),
}


def check_axis_samples(sentences: list[str]) -> list[str]:
    """按现读语料核对具名样本：返回问题列表（空 ⇒ 分布没被改坏）。"""
    problems: list[str] = []
    normed = [(acc_norm(s.split("|", 2)[-1]), classify_absence(s.split("|", 2)[-1])[0])
              for s in sentences]
    for axis, keys in AXIS_SAMPLES.items():
        if not keys:
            problems.append(f"axis_without_sample: 档 {axis} 没有具名样本")
        for key in keys:
            k = acc_norm(key)
            hits = [(body, got) for body, got in normed if k in body]
            if not hits:
                problems.append(f"sample_missing: 档 {axis} 的样本「{key[:28]}」"
                                "在语料里找不到（登记表改了文案，样本要跟着改，不能删了事）")
                continue
            if not any(got == axis for _b, got in hits):
                problems.append(
                    f"sample_axis_mismatch: 「{key[:28]}」现在落在 "
                    f"{sorted({got for _b, got in hits})}，声明的轴是 {axis}")
    return problems


def acc_norm(text: str) -> str:
    """`_norm` 的模块内别名（样本比对与锚点比对必须同一套剥号规则）。"""
    return _norm(text)


def _sample_problems_for(root: Path, sentences: list[str]) -> list[str]:
    """具名样本只核对**本仓的登记表文本**——它们本身就是"这一句在本仓算哪一档"的主张。

    拿一份两句话的合成语料去核对八条本仓样本，得到的必然是 8 条"样本找不到"，
    那是夹具的尺寸而不是判据的问题；合成侧的三种失败面由 `check_axis_samples` 直接驱动
    （见 `--self-test` 与 `tests/test_absence_claim_census.py`）。
    """
    if root.resolve() != Path(__file__).resolve().parent.parent:
        return []
    return check_axis_samples(sentences)


def classify_absence(body: str) -> tuple[str, str]:
    """这句"带否定词的话"属于哪一档，以及为什么。

    第 71/72 片之后才发现：判据必须落到**子句**粒度。
    原来整句判，于是这两句被一起挡掉的其实是真正的能力缺失断言——
      · 「…所以「没有执行器」不会被伪装成「返工失败三次」。
         四类之外到今天仍没有执行器的是 quote_batch」——谈口径的那半
         把同一句里真缺失的那半一起挡掉了
      · 「C6 的「装配/维护」里**维护指引没有生产者**（内容要属主给）…读者不会把骨架当…」
    按子句判之后，谈判决的那半被丢掉、缺失的那半留下，两侧都对了。

    返回值：("narrow", axis) 或 (axis, "")，axis ∈
    narrow / no-predicate / no-noun / non-claim。
    """
    clauses = [c for c in re.split(r"[。；;，、]", body) if c.strip()]
    for clause in clauses:
        if (any(p in clause for p in ABSENCE_PREDICATES)
                and any(n in clause for n in CAPABILITY_NOUNS)
                and not any(k in clause for k in NON_CLAIM_PATTERNS)):
            return "narrow", ""
    if not any(any(p in c for p in ABSENCE_PREDICATES) for c in clauses):
        return "no-predicate", ""
    if any(any(k in c for k in NON_CLAIM_PATTERNS) for c in clauses):
        return "non-claim", ""
    return "no-noun", ""


def is_capability_absence(body: str) -> bool:
    """这句算不算"某项能力还没有"（子句粒度，理由见 `classify_absence`）。"""
    return classify_absence(body)[0] == "narrow"


def _norm(text: str) -> str:
    """比较锚点前先剥 markdown 强调：登记表与文档都写 `**quote_batch**`，
    只剥 anchor 不剥句子就会把"已登记"读成"未登记"（第 67 片实测的第 2 例假缺席）。
    """
    return text.replace("*", "")


# ------------------------------------------------------------------ 处置台账
# 窄档里的每一句都必须有去处：**登记**（挂反证锚点，见 CLAIMS）或**豁免**（写清为什么不登记）。
# 豁免理由为空 ⇒ 前提不成立（一条空理由的豁免等于没有豁免）。
EXEMPTIONS: dict[str, str] = {
    "依赖外部法规库/专业数据源": "条件式声明：核的是「没配数据源时行为是否诚实降级」，"
                                 "那是运行时外部依赖，静态锚点定不出来；"
                                 "降级行为由 tests/ 里 research 那一族常驻用例钉",
    "依赖外部专利/竞品数据源": "同上：外部数据源可用性不在仓库里，没有静态反证锚点",
    "没有身份源，署名是声明不是证据": "要证伪得先接外部身份源（IdP/LDAP），"
                                      "不是一句代码里「还没有 X」的形状，属线下裁决项",
    "不自动求拆卸方向": "前提与「装配约束/配合与爆炸位移的自动求解」同一条，"
                        "已由 CAD-ASSEMBLY-CONSTRAINT-SOLVER 那条登记吃住，不再单列锚点",
    "DFA 只报同轴孔系数量这一件事实": "范围声明（列这一格装哪些事实），"
                                      "不是单点可证伪的缺失断言；其中「工序工时与成本不建模」"
                                      "由 ASSEMBLY-OPERATIONS-TABLE 那条登记吃住",
    "放大图不做重新投影与局部剖": "与「剖视的阶梯剖/旋转剖未做」是同一条代码事实，"
                                  "由 DRAWING-SECTION-TYPES 一条登记吃住（两处文案同因）",
    "仍只吃手写 JSON 的是尺寸链各段": "不按名字自动映射是第 46 片写下的产品裁决，"
                                      "不是一次能被单个符号证伪的缺失",
    "读数正确但没有「沉孔底厚」这类特征语义": "几何语义分类是整族工作（要建特征本体），"
                                              "没有「某个符号出现即过期」的形状；先只报不判",
    "叠加/形位声明的自动生成仍未接入": "「自动生成」的范围（从 CTQ 反推叠加链）跨 cad 与 CTQ "
                                        "两侧，要先有产品裁决才定得出锚点",
    "两侧口径刻意不同": "谈两档口径的取舍（生产者记盲区、门判不通过），不是缺失断言",
    "仍未做：多工序工艺路线": "与 cad.assembly_instructions 那句是同一条事实（同一张 "
                              "operations 表），由 ASSEMBLY-OPERATIONS-TABLE 一条登记吃住；"
                              "两处文案同因，不各挂一条锚点",
    "维护指引没有生产者": "内容由属主给是人的裁决；机器能核的「有没有 producer 代码」"
                          "已由 C6 覆盖度普查按档位盯住（scripts/c6_coverage.py）",
}


def table_created(root: Path, name: str) -> tuple[bool, list[str], list[str]]:
    """DDL 里有没有建过名为 `name` 的表（含 `IF NOT EXISTS` 与迁移里的重建）。"""
    pat = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`']?"
                     + re.escape(name) + r"[\"`']?\s*\(", re.I)
    hits: list[str] = []
    problems: list[str] = []
    bases = ["src", "migrations", "state_service"]
    seen_any = False
    for rel in bases:
        base = root / rel
        if not base.exists():
            continue
        seen_any = True
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".sql"):
                continue
            if "__pycache__" in path.parts or path.stem in SELF_STEMS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"unreadable: {path.relative_to(root)}: {exc}")
                continue
            for no, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    hits.append(f"{path.relative_to(root)}:{no}")
    if not seen_any:
        problems.append(f"authority_missing: {bases} 都读不到，判不了表 {name!r} 建没建")
    return (bool(hits), hits, problems)


_CALLER_CACHE: dict[tuple[str, str], tuple[list[str], list[str]]] = {}


def external_callers(root: Path, symbol: str) -> tuple[list[str], list[str]]:
    """`symbol` 在生产面（`src/`+`scripts/`+`state_service/`）的**外部**调用点。

    "外部"= 不在定义它的那个文件里。这一档是为「某个能力其实没有生产入口」这句话服务的：
    `ProductDefinitionGate.commit_snapshot` 只被同文件的 `commit_approved` 调，
    而 `commit_approved` 在 src/scripts 里 0 处被调用——**测试能跑通不等于产品接上了**。
    定义文件可能有多处（同名方法），取"该符号出现为 `def` 的文件集合"当排除集。
    """
    key = (str(root), symbol)
    if key in _CALLER_CACHE:
        return _CALLER_CACHE[key]
    dirs = ["src", "scripts", "state_service"]
    defining: set[str] = set()
    hits: list[str] = []
    problems: list[str] = []
    scanned = 0
    only_registry_files = 0
    registry_rels = set(REGISTRY_FILES)
    for rel in dirs:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts or path.stem in SELF_STEMS:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                problems.append(f"authority_unreadable: {path.relative_to(root)}: {exc}")
                continue
            here = str(path.relative_to(root))
            scanned += 1
            if here in registry_rels:
                only_registry_files += 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                        and node.name == symbol:
                    defining.add(here)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else (
                    f.id if isinstance(f, ast.Name) else None)
                if name == symbol:
                    hits.append(f"{here}:{node.lineno}")
    # 只读到登记表自己（或什么都没读到）时，"0 处调用点"不是证据而是盲区：
    #  scanned==0 这一支在任何能被解析的语料上都不可达，写它就是写一条永远不开火的守卫。
    if scanned - only_registry_files <= 0:
        problems.append("authority_thin: 生产面除登记表自身外没读到任何 .py（调用点判不了）")
    external = [h for h in hits if h.split(":", 1)[0] not in defining]
    _CALLER_CACHE[key] = (external, problems)
    return external, problems


def absence_sentences(corpus: dict[str, dict[str, list[tuple[str, int, str]]]]) -> list[str]:
    """语料里所有带否定词的句子片段（只用于分母与覆盖率，不判红）。"""
    hits: list[str] = []
    for cid, fields in corpus.items():
        for fname, rows in fields.items():
            for _rel, _lineno, text in rows:
                for sent in text.replace("\n", " ").split("；"):
                    if any(m in sent for m in NEGATION_MARKERS):
                        hits.append(f"{cid}|{fname}|{sent.strip()[:80]}")
    return hits


def locate(corpus: dict[str, dict[str, list[tuple[str, int, str]]]], capability: str,
           field: str, anchor: str) -> tuple[str, str, int] | None:
    """锚点在**声明的那个能力的那个字段**里逐字出现 ⇒ (文件, 字段, 行号)；否则 None。

    刻意绑到 (capability, field)：只在全文里找得到不算数——第 65 片实测登记表里有
    三条不同能力共用同一句「生产 Provider 未接入」，不绑字段就会一条改完三条假装都改完。
    同一 id 在两处文件都出现时返回**每一条**位点（`duplicate_divergence` 那一面负责差异）。
    """
    for rel, lineno, text in corpus.get(capability, {}).get(field, []):
        if anchor in text:
            return rel, field, lineno
    return None


# ------------------------------------------------------------------ 反证锚点
def _iter_py(root: Path, rel_dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for rel in rel_dirs:
        base = root / rel
        if base.is_file() and base.suffix == ".py":
            files.append(base)
        elif base.is_dir():
            for path in sorted(base.rglob("*.py")):
                if set(path.parts) & SKIP_DIRS or path.stem in SELF_STEMS:
                    continue
                files.append(path)
    return files


def _literal_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def artifact_executors(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """`{制品类型: ["文件:行", ...]}`：谁登记了自己是哪类制品的返工执行器。

    惯例是模块级 `SUPPORTED_ARTIFACT = ...`（右值可以是字面量，也可以是同模块或一跳
    import 来的常量）。一跳解析不出来 ⇒ 记一条前提问题，不许悄悄当"没有这个执行器"。
    """
    out: dict[str, list[str]] = {}
    problems: list[str] = []
    files = _iter_py(root, ["src"])
    trees: dict[Path, ast.Module] = {}
    for path in files:
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"unreadable: {path.relative_to(root)}: {exc}")
    for path, tree in trees.items():
        module_consts = _module_string_consts(tree)
        imports = _module_import_map(tree)
        for node in tree.body:
            targets, value = _assign_targets_value(node)
            if "SUPPORTED_ARTIFACT" not in targets:
                continue
            literal = _literal_str(value)
            where = f"{path.relative_to(root)}:{getattr(node, 'lineno', 0)}"
            if literal is not None:
                out.setdefault(literal, []).append(where)
                continue
            if isinstance(value, ast.Name):
                resolved = module_consts.get(value.id)
                if resolved is None:
                    resolved = _resolve_imported(root, imports, path, value.id)
                    if resolved == "__UNRESOLVED__":
                        problems.append(
                            f"anchor_unresolvable: {where} 的 {value.id} 一跳解析不到")
                        continue
                if isinstance(resolved, str):
                    out.setdefault(resolved, []).append(where)
                else:
                    problems.append(
                        f"anchor_unresolvable: {where} 的 {value.id} 不是字符串常量")
    return out, problems


def _module_string_consts(tree: ast.Module) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in tree.body:
        targets, value = _assign_targets_value(node)
        literal = _literal_str(value)
        if literal is not None:
            for name in targets:
                consts[name] = literal
    return consts


def _module_import_map(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """`{本地名: (来源模块点分路径, 源名)}`，只收 `from X import Y` 与 `import X`。"""
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out[alias.asname or alias.name.split(".")[0]] = (alias.name, "")
    return out


def _resolve_imported(root: Path, imports: dict[str, tuple[str, str]], here: Path,
                      name: str) -> Any:
    """一跳解析 `NAME`：到来源模块里取模块级字符串常量。

    返回 str（解出）、None（本地/来源都不是常量 ⇒ 交给调用方判"不是字符串常量"）、
    或字符串 `"__UNRESOLVED__"`（来源文件根本找不到 ⇒ 前提不成立，不许折算成"执行器不存在"）。
    """
    src = imports.get(name)
    if src is None:
        return None
    module, _src_name = src
    candidate = root / "src" / Path(*module.split("."))
    if not candidate.with_suffix(".py").is_file() and not (candidate / "__init__.py").is_file():
        return "__UNRESOLVED__"
    target = candidate.with_suffix(".py") if candidate.with_suffix(".py").is_file() \
        else candidate / "__init__.py"
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    except (SyntaxError, UnicodeDecodeError):
        return "__UNRESOLVED__"
    return _module_string_consts(tree).get(name)


def _assign_targets_value(node: ast.AST) -> tuple[list[str], ast.expr | None]:
    if isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        return names, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id], node.value
    return [], None


def identifier_hits(root: Path, dirs: list[str], symbols: list[str]) -> list[str]:
    """AST 面上的标识符引用（`Name`/`Attribute`/`def`/`class`/import 名）。

    **只走 AST 不走文本**：这些锚点的否定句自己就要在注释与 docstring 里写"不做 X"，
    文本扫描会把"写清楚了没做"读成"做了"（第 45 片 `run_rework` 那条判据的同一条理由）。
    """
    want = set(symbols)
    hits: list[str] = []
    for path in _iter_py(root, dirs):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root)
        for node in ast.walk(tree):
            named: str | None = None
            lineno = getattr(node, "lineno", 0)
            if isinstance(node, ast.Name):
                named = node.id
            elif isinstance(node, ast.Attribute):
                named = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                named = node.name
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # Python 3.9 的 `ast.alias` 没有 lineno，取 import 语句那一行的号
                if any((a.name.split(".")[0]) in want or a.name in want
                       for a in node.names):
                    hits.append(f"{rel}:{lineno}")
                continue
            if named is not None and named in want:
                hits.append(f"{rel}:{lineno}")
    return hits


def locate_claim(root: Path, claim: dict[str, Any]) -> tuple[str, str, int, str] | None:
    """⇒ (文件, 字段或 'text', 行号, 命中那行的原文)；找不到这句 ⇒ None。

    登记表条目走 `registry_strings`（绑 capability+field）；带 `file` 的条目走那份**现状文档**
    的逐行文本（第 66 片要吃的就是 `docs/architecture/*.md` 里那种"有三个生产者"的叙述——
    它不在登记表里，但同样是要被代码事实管住的一句话）。
    返回原文是为了让"数量词"这类判据**从这句话里现读数字**，而不是我在账本里再抄一遍
    （抄一份就会漂，且抄错会把判据变成自证）。
    """
    anchor = str(claim.get("anchor", ""))
    rel = str(claim.get("file", ""))
    if rel:
        path = root / rel
        if not path.is_file():
            return None
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return None
        for no, line in enumerate(lines, 1):
            if anchor and anchor in line:
                return rel, "text", no, line
        return None
    corpus, _problems = registry_strings(root)
    for file, lineno, text in corpus.get(str(claim.get("capability", "")), {}).get(
            str(claim.get("field", "")), []):
        if anchor and anchor in text:
            return file, str(claim.get("field", "")), lineno, text
    return None


# ------------------------------------------------------------------ 边生产者权威面
def edge_producers(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """AST 现读「谁在写边」，分两档：写 `truth_lineage` 的与只写 canonical 的。

    分类判据是**文件里有没有 `LineageGraph`**：`LineageGraph.add_edge` 是唯一
    进 `truth_lineage` 的入口（`tests/test_drawing_spec_lineage.py:226` 钉着这条），
    而 canonical 侧走 `state.lineage.LineageService`，两档不能混成一个数。
    本体 `src/aipd_os/product_truth/lineage.py` 是 SQL 写入口自己，单列不算"生产者"。
    读不出来的文件 ⇒ 记盲区，绝不静默少算一个生产者（少算会把"有三个"读成对）。
    """
    out = {"truth": [], "canonical": [], "sql_entry": []}
    blind: list[str] = []
    base = root / "src" / "aipd_os"
    if not base.is_dir():
        return out, ["authority_missing: src/aipd_os 不存在，权威面建不起来"]
    for path in sorted(base.rglob("*.py")):
        rel = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            blind.append(f"authority_unreadable: {rel}: {type(exc).__name__}")
            continue
        writes = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "add_edge" for n in ast.walk(tree))
        if not writes:
            continue
        if rel == SQL_ENTRY_FILE:
            out["sql_entry"].append(rel)
        elif "LineageGraph" in text:
            out["truth"].append(rel)
        else:
            out["canonical"].append(rel)
    if not (out["truth"] or out["canonical"] or out["sql_entry"]):
        blind.append("authority_empty: 一个 add_edge 位点都没读到（这把尺子读空了）")
    return out, blind


def count_words(text: str) -> list[int]:
    """从句子里取阿拉伯数字或中文数词（「有五个」「有 8 个」都算）。

    先剥掉 markdown 的 `*`：现状文档与登记表的强调写法是 `有**三个**生产者`，
    不剥就读不到数，那一档会静默降级成"前提不成立"——听起来安全，实际是这面判据
    在**唯一需要它开火的文档面上**永远不开火（第 66 片第一版就是这样，靠真仓库读数才发现）。
    """
    cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10, "两": 2}
    text = text.replace("*", "")
    out: list[int] = []
    for m in re.finditer(r"(?:有|共|为)\s*(\d+|[一二三四五六七八九十两])\s*个", text):
        tok = m.group(1)
        out.append(int(tok) if tok.isdigit() else cn.get(tok, 0))
    return out


def run_check(root: Path, check: dict[str, Any],
              text: str = "") -> tuple[bool, list[str], list[str]]:
    """⇒ （反证成不成立, 位点, 盲区）。

    前三种的"成不成立"都是"锚点在不在"；`producer_count` 那一支的"成不成立"是
    **"这句话写的个数与代码现读不符"** ⇒ 两种都归到 `CONTRADICTED`，判决方向一致，
    但读数消息要写清是哪一种，否则读者会把"文件存在"当成"这句话被证伪的方式"。
    """
    kind = check.get("kind")
    if kind == "artifact_executor":
        executors, blind = artifact_executors(root)
        sites = executors.get(str(check.get("artifact", "")), [])
        return (bool(sites), sites, blind)
    if kind == "identifier":
        dirs = list(check.get("paths", []))
        symbols = list(check.get("symbols", []))
        if not dirs or not symbols:
            return (False, [],
                    ["check_malformed: identifier 锚点缺 paths 或 symbols"])
        hits = identifier_hits(root, dirs, symbols)
        return (bool(hits), hits, [])
    if kind == "producer_count":
        scope = str(check.get("scope", "truth"))
        producers, blind = edge_producers(root)
        if scope not in producers:
            return (False, [], [f"check_kind_unknown: 权威档 {scope!r} 不存在"])
        authority = producers[scope]
        # 计数档的优先级与存在档**相反**：存在档里"已经找到东西"可以无视别处盲区，
        # 而计数档的数就是从这批位点数出来的——盲区或空集合意味着这个数**量不出来**，
        # 把"看不见"折成"句里写的数不对"就是拿判据造违规（第 66 片被自家新用例抓出来的）。
        if blind or not authority:
            return (False, [], (blind or [f"authority_empty: {scope} 档一个位点都没读到"]))
        written = count_words(text)
        if not written:
            return (False, [], [f"count_unreadable: 这句里读不到「有 N 个」数量词：{text[:50]}"])
        got = written[0]
        sites = [f"现读 {scope} 生产者 = {len(authority)} 个，句里写 {got} 个"] + authority
        return (got != len(authority), sites, [])
    if kind == "table_ddl":
        name = str(check.get("table", ""))
        if not name:
            return (False, [], ["check_malformed: table_ddl 锚点缺 table"])
        return table_created(root, name)
    if kind == "external_callers":
        symbol = str(check.get("symbol", ""))
        if not symbol:
            return (False, [], ["check_malformed: external_callers 锚点缺 symbol"])
        external, problems = external_callers(root, symbol)
        has = bool(external)
        head = f"{symbol} 生产面外部调用点 = {len(external)} 处"
        # expect="present" 把这一档从"缺席式"翻成"存在式"：
        #   缺席式（默认）= 句子里说"没人调用"，调用点在 ⇒ 这句话过期；
        #   存在式 = 句子里说"有入口"，调用点为 0 ⇒ 这句话过期。
        # 两档共用同一个 CONTRADICTED 位点（"这句话被证伪"），只是取反方向。
        if str(check.get("expect", "absent")) == "present":
            return (not has, [head] + external, problems)
        return (has, [head] + external, problems)
    return (False, [], [f"check_kind_unknown: {kind!r}"])


def slice_sentence(text: str, anchor: str) -> str:
    """从锚点起点切到本句末尾（`；`/`。`/换行）。

    必须切句再取数字：登记表一行装一整段限制句，拿整段去找「有 N 个」会读到
    别的小句的数，然后把别人的数字算在这句账上。
    """
    idx = text.find(anchor)
    if idx < 0:
        return text
    rest = text[idx:]
    for stop in ("；", "。", ";", "\n"):
        cut = rest.find(stop)
        if cut >= 0:
            rest = rest[:cut]
            break
    return rest


# ------------------------------------------------------------------ 判决
def audit(root: Path, claims: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    corpus, problems = registry_strings(root)
    if not corpus:
        problems.append("corpus_empty: 登记表一个能力都没读到（空分母不算绿）")
    if not claims:
        problems.append("claims_empty: 账本一条都没登记")

    rows: list[dict[str, Any]] = []
    for claim in claims:
        found = locate_claim(root, claim)
        anchor = str(claim.get("anchor", ""))
        if found is None:
            home = str(claim.get("file")
                       or f"{claim.get('capability')}.{claim.get('field')}")
            rows.append({"id": claim.get("id"), "verdict": CLAIM_TEXT_ABSENT,
                         "evidence": [], "problems": [],
                         "detail": f"账里有这条，{home} 里已找不到原句锚点"})
            continue
        file, field, lineno, text = found
        present, sites, check_problems = run_check(
            root, dict(claim.get("check", {})), slice_sentence(text, anchor))
        if present:
            verdict = CONTRADICTED
        elif check_problems:
            verdict = PRECONDITION
        else:
            verdict = HOLDS
        rows.append({"id": claim.get("id"), "verdict": verdict, "evidence": sites[:5],
                     "problems": check_problems,
                     "anchor_at": f"{file}:{field}:{lineno}",
                     "detail": str(claim.get("why", ""))})

    claim_ids = [str(c.get("id")) for c in claims]
    dupes = sorted({i for i in claim_ids if claim_ids.count(i) > 1})
    if dupes:
        # 第 76 片我自己踩出来的：一次 index 切片替换写反了区间，
        # 把四块登记复制了一份。id 重复不会改变任何一条判决（同一句被同一规则判两次），
        # 所以只能在这里显式红——否则账本会悄悄长出一批没人维护的僵尸条目。
        problems.append(f"duplicate_claim_id: 账本里这些 id 出现了不止一次：{dupes}")
    sentences = absence_sentences(corpus)
    anchored = {_norm(str(c.get("anchor"))) for c in claims if c.get("anchor")}
    wide_unanchored = [s for s in sentences
                       if not any(a and a in _norm(s) for a in anchored if a)]
    narrow: list[str] = []
    dropped = {"no-predicate": 0, "no-noun": 0, "non-claim": 0, "unknown-axis": 0}
    for s in sentences:
        axis = classify_absence(s.split("|", 2)[-1])[0]
        if axis == "narrow":
            narrow.append(s)
        elif axis in dropped:
            dropped[axis] += 1
        else:
            dropped["unknown-axis"] += 1
    problems.extend(_sample_problems_for(root, sentences))
    if dropped["unknown-axis"]:
        # 分类器吐出一个没登记的轴 ⇒ 词表被改坏了，不许当成"这句不算"
        problems.append(f"classifier_unknown_axis: "
                        f"{dropped['unknown-axis']} 句落进未登记的轴，词表改动没对齐")
    accounted: list[str] = []
    exempted: list[str] = []
    unaccounted: list[str] = []
    for s in narrow:
        body = _norm(s.split("|", 2)[-1])
        if any(a and a in body for a in anchored if a):
            accounted.append(s)
        elif any(_norm(key) in body for key in EXEMPTIONS):
            exempted.append(s)
        else:
            unaccounted.append(s)
    for s in unaccounted:
        rows.append({"id": f"UNACCOUNTED:{s.split('|', 1)[0]}",
                     "verdict": UNACCOUNTED, "evidence": [], "problems": [],
                     "detail": s.split("|", 2)[-1][:90]})
    for key, reason in sorted(EXEMPTIONS.items()):
        if len(reason.strip()) < 8:
            problems.append(f"exemption_reason_thin: 豁免「{key}」的理由是空的或太短，"
                            "空理由的豁免等于没有豁免")
        # 陈旧性按**宽档**判，不按窄档：豁免记的是"这句我看过、决定不登记"，
        # 而窄档会因为同句里另一处谈判决的写法把整句挡住，那时豁免仍然是有效记录。
        if not any(_norm(key) in _norm(s.split("|", 2)[-1]) for s in sentences):
            rows.append({"id": f"EXEMPT:{key[:24]}", "verdict": CLAIM_TEXT_ABSENT,
                         "evidence": [], "problems": [],
                         "detail": "豁免台账里还留着这条，语料里已经没有这句了 ⇒ 删掉这条豁免"})
    judged = [r for r in rows if r["verdict"] in (CONTRADICTED, CLAIM_TEXT_ABSENT,
                                                  UNACCOUNTED)]
    divergence = duplicate_divergence(corpus)
    seen_problems: set[str] = set()
    for row in rows:
        if row["verdict"] != PRECONDITION:
            continue
        for one in row["problems"]:
            if one not in seen_problems:
                seen_problems.add(one)
                problems.append(one)
    return {
        "ok": not judged and not divergence and not problems,
        "corpus": {"capabilities": len(corpus),
                   "absence_sentences": len(sentences),
                   "capability_absence_sentences": len(narrow),
                   "dropped_no_predicate": dropped["no-predicate"],
                   "dropped_no_noun": dropped["no-noun"],
                   "dropped_non_claim": dropped["non-claim"],
                   "narrow_registered": len(accounted),
                   "narrow_exempted": len(exempted),
                   "narrow_unaccounted": len(unaccounted),
                   "claims_registered": len(claims),
                   "absence_sentences_unanchored": len(wide_unanchored)},
        "rows": rows,
        "judged": judged,
        "unaccounted": unaccounted,
        "divergence": divergence,
        "problems": problems,
        "sample_unanchored": wide_unanchored[:8],
    }


def render(rep: dict[str, Any]) -> str:
    lines = ["=" * 60, "登记表否定句 × 反证锚点对账（F-STALE-ABSENCE）", "=" * 60]
    c = rep["corpus"]
    lines.append(f"语料：{c['capabilities']} 个能力，带否定词的句子 {c['absence_sentences']} 句；"
                 f"账本登记 {c['claims_registered']} 条，"
                 f"未挂锚点 {c['absence_sentences_unanchored']} 句（宽档，只报不判）")
    n_samples = sum(len(v) for v in AXIS_SAMPLES.values())
    sample_problems = sum(1 for pr in rep["problems"]
                          if "sample" in str(pr) or "axis_without" in str(pr))
    lines.append(f"能力缺失句（窄档＝判据面）：{c['capability_absence_sentences']} 句 = "
                 f"登记 {c['narrow_registered']} + 豁免 {c['narrow_exempted']} + "
                 f"**未处置 {c['narrow_unaccounted']}**")
    lines.append(f"被挡在窄档外的 {c['absence_sentences'] - c['capability_absence_sentences']} 句，"
                 f"按轴分开：无缺失谓词 {c['dropped_no_predicate']}、"
                 f"无能力名词 {c['dropped_no_noun']}、谈判决/谈口径 {c['dropped_non_claim']}"
                 f"（三档各有常驻用例钉住它非空）；具名样本 {n_samples} 句、"
                 f"样本问题 {sample_problems} 条")
    mark_map = {"HOLDS": "✓", "CONTRADICTED": "✗", "CLAIM_TEXT_ABSENT": "✗",
                "UNACCOUNTED": "✗", "PRECONDITION": "!"}
    for row in rep["rows"]:
        mark = mark_map.get(str(row["verdict"]), "?")
        at = row.get("anchor_at", "")
        ev = "、".join(row["evidence"][:3]) if row["evidence"] else "—"
        blind = ""
        if row["verdict"] == CONTRADICTED and row["problems"]:
            blind = f"（另有 {len(row['problems'])} 处盲区，不影响本条判决：锚点已经找到）"
        lines.append(f"  {mark} {row['id']} [{row['verdict']}] 锚点 {at} | 反证位点 {ev}{blind}")
    for one in rep["unaccounted"]:
        lines.append(f"      · 未处置：{one[:150]}")
    for d in rep["divergence"]:
        lines.append(f"  ✗ 同一个能力 id 在两份登记表里对同一字段各说各话："
                     f"{d['capability']}.{d['field']}（{' vs '.join(d['files'])}"
                     f"，位点 {'、'.join(d['lines'][:4])}）")
    for prob in rep["problems"]:
        lines.append(f"  ! 前提不成立：{prob}")
    if rep["sample_unanchored"]:
        lines.append("  · 未挂锚点的否定句（前 8 条，供下一轮挑）：")
        for one in rep["sample_unanchored"]:
            lines.append(f"      - {one}")
    if not rep["judged"] and not rep["divergence"] and not rep["problems"]:
        lines.append(f"判红 0 条：登记的 {c['claims_registered']} 句「仍缺着」现在都还缺着")
    return "\n".join(lines)


def _mark(marks: list, text: str) -> None:
    print("✓立住 " + text)
    marks.append(text)


def _self_test(tmp: Path) -> int:
    """合成语料：七种判决与两面台账都要能各自开火，合规侧各自不开火。"""
    marks: list[str] = []
    (tmp / "src/aipd_os/bom").mkdir(parents=True)
    (tmp / "src/aipd_os/supervisor").mkdir(parents=True)
    (tmp / "migrations").mkdir()
    # 反证锚点在 ⇒ 判红（CONTRADICTED）
    (tmp / "src/aipd_os/bom/bom_rework.py").write_text(
        'from aipd_os.bom.cost_lineage import ARTIFACT_BOM\n'
        'SUPPORTED_ARTIFACT = ARTIFACT_BOM\n', encoding="utf-8")
    (tmp / "src/aipd_os/bom/cost_lineage.py").write_text(
        'ARTIFACT_BOM = "bom"\n', encoding="utf-8")
    # 一跳解析不到 ⇒ 前提不成立，不许读成"这个执行器不存在"
    (tmp / "src/aipd_os/bom/ghost_rework.py").write_text(
        'from aipd_os.nowhere import ARTIFACT_GHOST\n'
        'SUPPORTED_ARTIFACT = ARTIFACT_GHOST\n', encoding="utf-8")
    (tmp / "src/aipd_os/supervisor/supervisor.py").write_text(
        'def f():\n    # 这里**不做**装配约束求解，也不写血缘边\n    return 1\n',
        encoding="utf-8")
    # DDL 权威面：operations 建成 ⇒ 「没建 operations 表」被判红；routing_rules 没建 ⇒ 成立
    (tmp / "migrations/v1.sql").write_text(
        'CREATE TABLE operations (id TEXT PRIMARY KEY);\n', encoding="utf-8")
    # 语料：cap.d 那两句是**宽档命中、窄档必须挡住**的假阳性（谈判决与谈口径）
    (tmp / "src/aipd_os/registry_data.py").write_text(
        'CAPABILITIES = [\n'
        ' {"id": "cap.a", "name": "同一个能力",\n'
        '  "current_limitation": "bom 这一类仍没有执行器；跨币种折算未实现"},\n'
        ' {"id": "cap.b", "name": "另一个能力",\n'
        '  "current_limitation": "工作项与上游 truth 之间还没有映射；'
        '反向那条路还没有，要等 **quote_batch** 接上才有"},\n'
        ' {"id": "cap.c", "name": "第三个能力",\n'
        '  "current_limitation": "装配约束未实现；PDF/图框未做"},\n'
        ' {"id": "cap.d", "name": "第四个能力",\n'
        '  "current_limitation": "圆内没有图线即判未收口，不编号不画圈；'
        '所以「没有执行器」不会被伪装成返工失败三次"},\n'
        ' {"id": "cap.e", "name": "第五个能力",\n'
        '  "current_limitation": "内置族为常用示例，未覆盖全部人群数据库；'
        '项目里还没有 BOM 版本记录时记录照写"},\n'
        ']\n', encoding="utf-8")
    extra_dir = tmp / "scripts"
    extra_dir.mkdir(exist_ok=True)
    EXTRA_ROW = ('PRODUCT_CAPABILITIES = [\n'
                 ' {"id": "cap.a", "name": "同一个能力",\n'
                 '  "current_limitation": "bom 这一类仍没有执行器；跨币种折算未实现"},\n'
                 ']\n')
    (extra_dir / "product_capabilities_extra.py").write_text(EXTRA_ROW, encoding="utf-8")
    claims = (
        {"id": "FIRED", "capability": "cap.a", "field": "current_limitation",
         "anchor": "仍没有执行器",
         "check": {"kind": "artifact_executor", "artifact": "bom"}},
        {"id": "QUIET", "capability": "cap.a", "field": "current_limitation",
         "anchor": "跨币种折算未实现",
         "check": {"kind": "identifier", "paths": ["src/aipd_os/bom"],
                   "symbols": ["convert_currency"]}},
        {"id": "HOLDS", "capability": "cap.b", "field": "current_limitation",
         "anchor": "工作项与上游 truth 之间还没有映射",
         "check": {"kind": "identifier", "paths": ["src/aipd_os/supervisor"],
                   "symbols": ["LineageGraph"]}},
        {"id": "BOLD", "capability": "cap.b", "field": "current_limitation",
         "anchor": "反向那条路还没有，要等 **quote_batch** 接上才有",
         "check": {"kind": "identifier", "paths": ["src/aipd_os/supervisor"],
                   "symbols": ["zzz-no-such-symbol"]}},
        {"id": "PRE", "capability": "cap.c", "field": "current_limitation",
         "anchor": "装配约束未实现",
         "check": {"kind": "artifact_executor", "artifact": "ghost"}},
        {"id": "TBL", "capability": "cap.c", "field": "current_limitation",
         "anchor": "装配约束未实现",
         "check": {"kind": "table_ddl", "table": "operations"}},
        {"id": "TBL-QUIET", "capability": "cap.c", "field": "current_limitation",
         "anchor": "装配约束未实现",
         "check": {"kind": "table_ddl", "table": "routing_rules"}},
        {"id": "DANGLING", "capability": "cap.c", "field": "current_limitation",
         "anchor": "这句话已经被删掉了",
         "check": {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                   "symbols": ["zzz-no-such-symbol"]}},
    )
    ids = {str(c["id"]) for c in claims}
    saved_ex_main = dict(globals()["EXEMPTIONS"])
    globals()["EXEMPTIONS"] = {}
    try:
        rep = audit(tmp, claims)
    finally:
        globals()["EXEMPTIONS"] = saved_ex_main
    by = {str(r["id"]): str(r["verdict"]) for r in rep["rows"]}
    assert by["FIRED"] == CONTRADICTED, sorted(by)
    assert rep["rows"][0]["evidence"], "判红必须带反证位点"
    _mark(marks, "反证锚点在 ⇒ CONTRADICTED 并带出位点；同批扫描里的盲区不改这条判决")
    assert by["QUIET"] == HOLDS and by["HOLDS"] == HOLDS, sorted(by)
    _mark(marks, "邻居判红不连坐；注释里写「不做 X」不算 X 做了（AST 面，不是文本面）")
    assert by["BOLD"] == HOLDS, sorted(by)
    _mark(marks, "登记句里带 markdown 强调（**quote_batch**）也算已登记 ⇒ 不判「未处置」"
                 "（比较两侧都剥 *，C1 臂专打这条）")
    assert by["PRE"] == PRECONDITION, sorted(by)
    assert any(p.startswith("anchor_unresolvable") for p in rep["problems"]), rep["problems"]
    _mark(marks, "一跳常量解析不到 ⇒ 前提不成立，不折算成 HOLDS/CONTRADICTED")
    assert by["TBL"] == CONTRADICTED and by["TBL-QUIET"] == HOLDS, sorted(by)
    assert any("migrations/v1.sql" in e for e in rep["rows"][5]["evidence"]), rep["rows"][5]
    _mark(marks, "DDL 档双向：建过 operations 表 ⇒ 「没建表」判红；没建 routing_rules ⇒ 成立")
    assert by["DANGLING"] == CLAIM_TEXT_ABSENT, sorted(by)
    _mark(marks, "正文删了句、账里还留着 ⇒ 账文脱钩判红（反向对照：删包装必须翻红）")
    claim_rows = [r for r in rep["rows"] if str(r["id"]) in ids]
    buckets: dict[str, int] = {}
    for row in claim_rows:
        buckets[row["verdict"]] = buckets.get(row["verdict"], 0) + 1
    assert sum(buckets.values()) == len(claims), buckets
    _mark(marks, f"分档之和 == 登记条数（{buckets}；语料级的行另计，不混进这个恒等式）")
    # ---- 第 65 片：两处登记表同 id 的分面 ----
    assert rep["divergence"] == [], rep["divergence"]
    _mark(marks, "同一 id 在两处登记表里逐字相同 ⇒ 不判（这一面也要有合规侧对照）")
    (extra_dir / "product_capabilities_extra.py").write_text(
        EXTRA_ROW.replace('"name": "同一个能力"', '"name": "改了一个名字"'),
        encoding="utf-8")
    rep2 = audit(tmp, claims)
    assert len(rep2["divergence"]) == 1, rep2["divergence"]
    clean_only = tuple(c for c in claims if c["id"] in ("QUIET", "HOLDS", "BOLD",
                                                        "TBL-QUIET"))
    two = ("src/aipd_os/registry_data.py", "scripts/product_capabilities_extra.py")
    assert _rc_with(tmp, clean_only, two, {}) == 4, "两份各说各话要自己退 4"
    _mark(marks, "两份登记表对同一 id 各说各话 ⇒ 判红并独立退 4")
    (extra_dir / "product_capabilities_extra.py").write_text(EXTRA_ROW, encoding="utf-8")
    # ---- 第 66 片：计数档 ----
    for name in ("prod1.py", "prod2.py"):
        (tmp / "src/aipd_os" / name).write_text(
            "from aipd_os.product_truth.lineage import LineageGraph\n\n\n"
            "def f(g):\n    return g.add_edge('a', 'b')\n", encoding="utf-8")
    (tmp / "src/aipd_os/prod3.py").write_text(
        "from aipd_os.state.lineage import LineageService\n\n\n"
        "def f(s):\n    return s.add_edge('a', 'b')\n", encoding="utf-8")
    (tmp / "docs").mkdir(exist_ok=True)
    (tmp / "docs/x.md").write_text(
        "血缘边有**三个**生产者——p1、p2、p3\n"
        "血缘边有**两个**生产者——p1、p2\n"
        "血缘边有**三个**canonical 生产者\n"
        "另有五个说法。血缘边有两个生产者——p1、p2\n", encoding="utf-8")
    count_claims = (
        {"id": "CNT-FIRE", "file": "docs/x.md", "anchor": "血缘边有**三个**生产者——",
         "check": {"kind": "producer_count", "scope": "truth"}},
        {"id": "CNT-QUIET", "file": "docs/x.md", "anchor": "血缘边有**两个**生产者——",
         "check": {"kind": "producer_count", "scope": "truth"}},
        {"id": "CNT-SCOPE", "file": "docs/x.md", "anchor": "血缘边有**三个**生产者——",
         "check": {"kind": "producer_count", "scope": "canonical"}},
        {"id": "CNT-SLICE", "file": "docs/x.md", "anchor": "血缘边有两个生产者——",
         "check": {"kind": "producer_count", "scope": "truth"}},
    )
    rep3 = audit(tmp, count_claims)
    by3 = {str(r["id"]): str(r["verdict"]) for r in rep3["rows"]}
    assert by3["CNT-FIRE"] == CONTRADICTED and by3["CNT-QUIET"] == HOLDS, sorted(by3)
    assert by3["CNT-SLICE"] == HOLDS, sorted(by3)
    _mark(marks, "计数档双向 + 切句：同一行前头有别的数字时，数必须从锚点那句读")
    assert by3["CNT-SCOPE"] == CONTRADICTED, sorted(by3)
    _mark(marks, "权威档选错（拿 canonical 的 1 个核 truth 那句三个）也翻红 ⇒ 数真从代码来")
    empty = tmp / "emptytree"
    (empty / "docs").mkdir(parents=True)
    (empty / "docs/x.md").write_text("血缘边有**三个**生产者——a、b、c\n", encoding="utf-8")
    rep4 = audit(empty, ({"id": "NOAUTH", "file": "docs/x.md",
                          "anchor": "血缘边有**三个**生产者",
                          "check": {"kind": "producer_count", "scope": "truth"}},))
    assert str(rep4["rows"][0]["verdict"]) == PRECONDITION, rep4["rows"]
    assert any(p.startswith("authority_missing") for p in rep4["problems"]), rep4["problems"]
    _mark(marks, "权威面建不起来时计数档不判：0 个位点是量不出来，不是「句里写错」")
    # ---- 第 67 片：能力缺失句必须逐条有去处 ----
    saved_ex = dict(globals()["EXEMPTIONS"])
    saved_rf = globals()["REGISTRY_FILES"]
    globals()["EXEMPTIONS"] = {}
    # 去处台账的分母只吃主登记表：cap.a 在两处文件里各有一份，
    # 双份语料会把宽窄两档一起抬高，读数就不再是"这句有没有去处"而是"这句被数了几遍"。
    globals()["REGISTRY_FILES"] = ("src/aipd_os/registry_data.py",)
    try:
        rep5 = audit(tmp, claims)
        c5 = rep5["corpus"]
        assert c5["capability_absence_sentences"] == 6, c5
        assert c5["absence_sentences"] == 10, c5  # 宽 10 / 窄 6：cap.d、cap.e 四句是假阳性
        assert c5["narrow_registered"] == 5, c5   # 含那句带 **quote_batch** 强调的
        assert c5["narrow_unaccounted"] == 1, c5
        assert c5["capability_absence_sentences"] == \
            c5["narrow_registered"] + c5["narrow_exempted"] + c5["narrow_unaccounted"], c5
        assert all(str(p).startswith("anchor_unresolvable") for p in rep5["problems"]), \
            rep5["problems"]
        un = [r for r in rep5["rows"] if r["verdict"] == UNACCOUNTED]
        assert len(un) == 1 and "PDF/图框未做" in un[0]["detail"], un
        _mark(marks, "窄档＝宽档挡住两句假阳性；没去处的那句判红，且登记+豁免+未处置==分母")
        globals()["EXEMPTIONS"] = {"PDF/图框未做": "夹具里给这条留的豁免理由，字数够"}
        rep6 = audit(tmp, claims)
        assert rep6["corpus"]["narrow_unaccounted"] == 0, rep6["corpus"]
        assert rep6["corpus"]["narrow_exempted"] == 1, rep6["corpus"]
        _mark(marks, "带理由的豁免把那句从「未处置」挪进「已处置」")
        globals()["EXEMPTIONS"] = {"PDF/图框未做": "短"}
        rep7 = audit(tmp, claims)
        assert any(p.startswith("exemption_reason_thin") for p in rep7["problems"]), \
            rep7["problems"]
        _mark(marks, "空/过短理由的豁免读成前提不成立，不当成已处置")
        globals()["EXEMPTIONS"] = {"这句语料里根本没有": "一条写给机器看的、足够长的理由"}
        rep8 = audit(tmp, claims)
        stale = [r for r in rep8["rows"] if str(r["id"]).startswith("EXEMPT:")]
        assert len(stale) == 1 and stale[0]["verdict"] == CLAIM_TEXT_ABSENT, stale
        _mark(marks, "豁免台账自己也会漂：语料里没这句了就必须响")
    finally:
        globals()["EXEMPTIONS"] = saved_ex
        globals()["REGISTRY_FILES"] = saved_rf
    print(render(rep))
    two_all = ("src/aipd_os/registry_data.py",)
    saved = globals()["REGISTRY_FILES"]
    globals()["REGISTRY_FILES"] = two_all
    no_pre = tuple(c for c in claims if c["id"] != "PRE")
    try:
        assert _rc_with(tmp, no_pre, two_all, {}) == 4, \
            "有判红（含未处置）就必须退 4，不退 0"
        _mark(marks, "判红档（含「没去处」这一种）⇒ 退 4")
        # 退 0 只在整个语料"句句有去处"时出现：quiet_only 没覆盖 cap.a 的第一句与 cap.c 的第二句，
        # 那两句就得靠豁免条补位——这正好说明"未处置"是按**当前账本**算的，不是按仓库算的。
        quiet_only = tuple(c for c in claims
                           if c["id"] in ("QUIET", "HOLDS", "BOLD", "TBL-QUIET"))
        assert _rc_with(tmp, quiet_only, two_all,
                        {"PDF/图框未做": "夹具里的豁免理由，字数够长",
                         "仍没有执行器": "夹具里第二条豁免理由，字数也够长"}) == 0, \
            "全部成立且句句有去处 ⇒ 退 0"
        _mark(marks, "每句都有去处且无过期 ⇒ 退 0")
        assert _rc_with(tmp, claims, two_all, {}) == 2, \
            "前提塌优先于判红：三档要分得开，不能糊成一个非零"
        _mark(marks, "前提塌 ⇒ 退 2，压住同一批判红（三档分明）")
        assert _rc_with(tmp, (), two_all, {}) == 2, "空账本不许读成零违规"
        _mark(marks, "空账本读成前提不成立（退 2），不是「零过期句」")
    finally:
        globals()["REGISTRY_FILES"] = saved
    print(render(rep5))
    print(render(rep6))
    # ---- 第 68 片：外部调用点档（"这一步其实没有生产入口"） ----
    (tmp / "src/aipd_os/entry.py").write_text(
        "from aipd_os.own import only_self_called, outward_called\n\n\n"
        "def run():\n    return outward_called()\n", encoding="utf-8")
    (tmp / "src/aipd_os/own.py").write_text(
        "def only_self_called():\n    return 1\n\n\n"
        "def self_caller():\n    return only_self_called()\n\n\n"
        "def outward_called():\n    return 1\n", encoding="utf-8")
    caller_claims = (
        {"id": "CALL-INWARD", "capability": "cap.a", "field": "current_limitation",
         "anchor": "仍没有执行器",
         "check": {"kind": "external_callers", "symbol": "only_self_called"}},
        {"id": "CALL-OUTWARD", "capability": "cap.a", "field": "current_limitation",
         "anchor": "仍没有执行器",
         "check": {"kind": "external_callers", "symbol": "outward_called"}},
    )
    caller_claims = caller_claims + (
        {"id": "CALL-PRESENT", "capability": "cap.a", "field": "current_limitation",
         "anchor": "仍没有执行器",
         "check": {"kind": "external_callers", "symbol": "outward_called",
                   "expect": "present"}},
        {"id": "CALL-PRESENT-BROKE", "capability": "cap.a", "field": "current_limitation",
         "anchor": "仍没有执行器",
         "check": {"kind": "external_callers", "symbol": "only_self_called",
                   "expect": "present"}},
    )
    fixture_samples = {
        "narrow": ("仍没有执行器",),
        "no-predicate": ("未覆盖全部人群数据库",),
        "no-noun": ("还没有 BOM 版本记录",),
        "non-claim": ("即判未收口",),
    }
    saved_samples0 = dict(globals()["AXIS_SAMPLES"])
    globals()["AXIS_SAMPLES"] = fixture_samples
    try:
        sample_ok = check_axis_samples([
            "cap.a|current_limitation|bom 这一类仍没有执行器；跨币种折算未实现",
            "cap.d|current_limitation|圆内没有图线即判未收口",
            "cap.e|current_limitation|内置族为常用示例，未覆盖全部人群数据库",
            "cap.e|current_limitation|项目里还没有 BOM 版本记录时记录照写"])
        assert sample_ok == [], sample_ok
        missing = check_axis_samples(["cap.x|current_limitation|这里什么都没有写"])
        assert any(p.startswith("sample_missing") for p in missing), missing
        misaxis = check_axis_samples([
            "cap.z|current_limitation|项目里还没有 BOM 版本记录时没有执行器"])
        assert any(p.startswith("sample_axis_mismatch") for p in misaxis), misaxis
        globals()["AXIS_SAMPLES"] = {**fixture_samples, "no-noun": ()}
        no_sample = check_axis_samples(
            ["cap.a|current_limitation|bom 这一类仍没有执行器"])
        assert any(p.startswith("axis_without_sample") for p in no_sample), no_sample
    finally:
        globals()["AXIS_SAMPLES"] = saved_samples0
    assert any(p.startswith("axis_without_sample") for p in no_sample), no_sample
    _mark(marks, "具名样本三档控制齐：合规样本不报、样本消失报 sample_missing、"
                 "落错轴报 sample_axis_mismatch、档没样本报 axis_without_sample")
    rep9 = audit(tmp, caller_claims)
    by9 = {str(r["id"]): str(r["verdict"]) for r in rep9["rows"]}
    assert by9["CALL-INWARD"] == HOLDS, sorted(by9)
    assert by9["CALL-OUTWARD"] == CONTRADICTED, sorted(by9)
    assert by9["CALL-PRESENT"] == HOLDS, sorted(by9)
    assert by9["CALL-PRESENT-BROKE"] == CONTRADICTED, sorted(by9)
    _mark(marks, "存在式登记（expect=present）双向：有外部调用点 ⇒ 成立；"
                 "只剩同文件自调用 ⇒ 判红（旗子被摘就响）")
    _mark(marks, "外部调用点档双向：只被同文件调 ⇒ 成立（commit_snapshot 的真实形状）；"
                 "被别的文件调 ⇒ 判红")
    # ---- 第 73 片：分类器按子句判，四档各有一正一反 ----
    cases = (
        ("谈口径的半句不能挡掉真缺失",
         "所以「没有执行器」不会被伪装成失败三次。四类之外仍没有执行器的是 quote_batch",
         "narrow"),
        ("整句都在谈判决 ⇒ 不进判据面",
         "圆内没有图线即判未收口，不编号不画圈", "non-claim"),
        ("有缺失谓词但没有能力名词 ⇒ 不算能力缺失",
         "项目里还没有 BOM 版本记录时记录照写", "no-noun"),
        ("没有缺失谓词（只是陈述范围）⇒ 不算",
         "内置族为常用成年男女/儿童百分位示例，未覆盖全部人群数据库", "no-predicate"),
    )
    for label, body, want in cases:
        assert classify_absence(body)[0] == want, (label, classify_absence(body), want)
    _mark(marks, "分类器四档双向：同一句里谈口径的那半被丢掉、谈缺失的那半留下"
                 "（第 73 片修的就是这个粒度）")
    _mark(marks, f"合计 {len(marks)} 条合成读数全部对上")
    return 0


def _rc_with(root: Path, claims: tuple[dict[str, Any], ...],
             files: tuple[str, ...] = ("src/aipd_os/registry_data.py",),
             exemptions: dict[str, str] | None = None) -> int:
    saved = globals()["REGISTRY_FILES"]
    saved_ex = globals()["EXEMPTIONS"]
    globals()["REGISTRY_FILES"] = files
    if exemptions is not None:
        globals()["EXEMPTIONS"] = exemptions
    try:
        rep = audit(root, claims)
    finally:
        globals()["REGISTRY_FILES"] = saved
        globals()["EXEMPTIONS"] = saved_ex
    if rep["problems"]:
        return 2
    return 4 if (rep["judged"] or rep["divergence"]) else 0


def _load_claims(path: str) -> tuple[dict[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("--claims 指向的必须是登记条目数组")
    return tuple(data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="登记表否定句 × 反证锚点对账")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--claims", default="", help="改用外部 JSON 账本（常驻用例的永久开火对照）")
    ap.add_argument("--json", default="", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    claims = _load_claims(args.claims) if args.claims else CLAIMS
    rep = audit(root, claims)
    print(render(rep))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    if rep["problems"]:
        return 2
    return 4 if (rep["judged"] or rep["divergence"]) else 0


if __name__ == "__main__":
    sys.exit(main())
