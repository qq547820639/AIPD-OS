"""门的要求表（G0-G9）：声明文件是权威，脚本里不许再养一份。

为什么单独一个模块：`assets/templates/gate_requirements.yaml` 声明 50 个交付物类型，
`scripts/quality_gate.py` 的 `REQ` 只强制 40 个（实测 2026-09-25，方向单边），
而脚本第 20 行的注释还写着「requirements mirror gate_requirements.yaml」——
**那句话是假的**：全仓没有任何解析器读过那份 YAML，名字只出现在注释里。
两处声明同一张表 ⇒ 必然漂移，这次漂在「声明了但门不要求」这一侧。

三条规矩：

1. **权威只有一个**：表由 `load()` 从 YAML 现读。YAML 读不到 / 解析坏 ⇒ `ok=False`
   （调用方必须 fail-closed），**不许**退回任何内联副本——否则「单源」在故障那天
   就悄悄变回双源，而且变得无声。
2. **不能要求的要具名，不许静默掉出去**：YAML 与强制集之差必须逐项落在
   `UNPRODUCED` 里并写理由。加一项不归类 ⇒ 常驻用例判红；闭合一项 ⇒ 清单必须缩短
   （与第 28 片「每一档状态都要归类」同一族纪律）。
3. **「没有产者」这句话自己也要能被反证**：`producer_literals()` 探的是全仓源码/模板/
   参考文档里的类型名字面量，`cad_contract` 是它的**正向对照**（探得到 ⇒ 探针会开火），
   九项 `UNPRODUCED` 是负向读数。负向读数只有在探针被证明能开火之后才算数。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
DECLARATION = "assets/templates/gate_requirements.yaml"

#: 声明了、但**本仓今天没有任何代码产出这一类型**的交付物 ⇒ 门不能把它接成硬要求
#: （接了就永久红，而永久红的门只会训练人忽略它）。理由与反证方式逐项写明。
UNPRODUCED: dict[str, str] = {
    "cad_l1_functional_layout": "布局草图这一级没有生产者：cad.* 能力里没有产 layout 交付物的入口",
    "cad_parametric_source": "参数化源文件（特征树）没有生产者；cad.text_to_cad 产的是 B-rep/STEP",
    "cad_primary_step": "STEP 导出挂在图纸/装配链里，没有以这一类型登记过交付物的代码",
    "cad_inspection_report": "检验报告由 `production_release_gate` 读，"
                          "但没有写它并按此类型登记的代码",
    "cad_snapshot_packet": "快照包没有生产者（Snapshot 域写的是状态库，不产这个交付物）",
    "cad_bom_mapping": "球标↔BOM 对账在图纸证据里，不以这一类型落库",
    "evt_cad_configuration": "EVT 阶段配置基线没有生产者",
    "cad_l4_dfm_drawings": "DFM 图纸由 `aipd drawing generate` 产 DXF，"
                           "但不以这一类型登记交付物",
    "cad_l5_release_package": "发布包由 `aipd package` 产，但登记类型是 `release_package`",
}

#: 探针的**正向对照**名单：这些声明类型今天真有实体（schema + 模板 + 真门校验），
#: 所以 `producer_literals()` 必须探得到它们——探不到就说明探针坏了，那九个「没有产者」
#: 的负向读数也就不算数了。它们**不参与**强制集的计算（在 YAML 里，减掉 UNPRODUCED 后
#: 自然进强制集），这里只当对照用。
NEWLY_ENFORCED: dict[str, str] = {
    "cad_contract": "G3 详细设计阶段就该交 CAD 合同：`assets/schemas/cad_contract.schema.json` "
                    "与模板在盘上，且 `production_release_gate` 的 `schema_valid` 真在核它",
}

_OK = "ok"
_UNREADABLE = "unreadable"
_MALFORMED = "malformed"


def load(repo: Path | str | None = None) -> dict[str, Any]:
    """读权威表。返回 {status, gates, owner_gates, why}；`status != ok` 时 gates 为空。"""
    root = Path(repo) if repo else REPO_ROOT
    path = root / DECLARATION
    if not path.is_file():
        return {"status": _UNREADABLE, "gates": {}, "owner_gates": set(),
                "why": f"{DECLARATION} 不在盘上"}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {"status": _UNREADABLE, "gates": {}, "owner_gates": set(),
                "why": f"{type(exc).__name__}: {exc}"}
    if not isinstance(raw, dict) or not raw:
        return {"status": _MALFORMED, "gates": {}, "owner_gates": set(),
                "why": "顶层不是非空映射"}
    gates: dict[str, list[str]] = {}
    owner: set[str] = set()
    for gate, body in raw.items():
        if not isinstance(body, dict) or not isinstance(body.get("required_deliverables"), list):
            return {"status": _MALFORMED, "gates": {}, "owner_gates": set(),
                    "why": f"{gate} 的 required_deliverables 不是列表"}
        gates[str(gate)] = [str(t) for t in body["required_deliverables"]]
        if body.get("requires_owner_approval"):
            owner.add(str(gate))
    return {"status": _OK, "gates": gates, "owner_gates": owner, "why": ""}


def enforced_table(decl: dict[str, list[str]]) -> dict[str, list[str]]:
    """强制集 = 声明集 − `UNPRODUCED` + `NEWLY_ENFORCED`（后者已在 YAML 里，减的是前者）。"""
    return {gate: [t for t in types if t not in UNPRODUCED]
            for gate, types in decl.items()}


def unproduced_in(decl: dict[str, list[str]]) -> list[str]:
    """声明里出现、且被判定「今天不能要求」的项（按名排序，好让差集可逐字比对）。"""
    declared = {t for types in decl.values() for t in types}
    return sorted(declared & set(UNPRODUCED))


def producer_literals(repo: Path | str | None = None) -> tuple[set[str], dict[str, str]]:
    """哪些交付物类型名在源码/模板/参考文档里真的出现（判「有没有产者」的探针）。

    返回 (命中的类型名集合, 命中处样本)。这是**字面量**探针，只能证明「提过这个名字」，
    不能证明真产了它——所以正向对照（`cad_contract`）与逐项理由都写在 `UNPRODUCED` 里，
    读的人能看到这条判据的天花板。
    """
    root = Path(repo) if repo else REPO_ROOT
    sample: dict[str, str] = {}
    # 名单从**声明文件**取，不从 `UNPRODUCED` 取：后者写在这些名字的反向证据里，
    # 拿自己的字典当被扫文本，九个负向读数会全被自己点亮（第四种自引用面，实测被抓）。
    where = [root / "src", root / "scripts", root / "state_service",
             root / "assets" / "templates", root / "references"]
    declared = load(root)["gates"]
    names = {t for types in declared.values() for t in types} | {"project_brief"}
    for base in where:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".json", ".md", ".yaml", ".yml"}:
                continue
            if path.resolve() == Path(__file__).resolve():
                continue    # 本模块自己不算产者：那九个名字就写在它的豁免表里
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for name in names - set(sample):
                if f'"{name}"' in text or f"'{name}'" in text or f"{name}:" in text \
                        or f" {name} " in text or f"`{name}`" in text:
                    sample[name] = str(path.relative_to(root))
    return set(sample), sample
