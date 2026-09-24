"""F-SUPPLY-03：验证失败 → BOM/图纸 影响传播必须真的落库。

接线前的实测事实（`git grep` + AST 普查，本机）：
- `industrialize.physical_writeback` 声明「测试结果 -> 事实主表更新 -> BOM/CAD 影响传播」，
  且 `current_limitation=None`（= 自称完整实现）；
- 其 entry_point `supply_chain.analysis.propagate_impact` 全仓**唯一**产品调用点是
  `tool_adapters/evt_dvt_pvt_adapter.py:76`，而它喂进去的是
  `input.get("facts") or {}` / `input.get("bom") or []` —— 调用方自带、实际不传；
- 该适配器 id `validation.import-evt-dvt-pvt` 在 `src/` + `scripts/` + `tests/` 里
  除了适配器自身之外**零引用**（同 `manual.layout`、`supply.supplier-files`），
  而产品侧唯一会排产 capability 的模块是 `supervisor/idea_capabilities.py`
  （只排 `idea.*` / `product.*`）⇒ 这条声明的能力在软件上不可达。

修法：把传播接到**已经可达且已持久化**的路径上（`aipd validation import` 会建
Test/Run/Result/Issue；`aipd industrialize --lab-data` 会做阶段分析），传播复用仓内
既有语义：受影响行 → 其关联 deliverable 按 CAS 置 `stale`（与
`experience/instructions._mark_stale` 同一纪律：released/archived 不动），并把结果写进
事实主表（`impact.<item>`，status P=待返工），且**可重放**。
"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.bom import BomLine, BomStore
from aipd_os.cli._helpers import DEFAULT_TENANT
from aipd_os.cli.main import main
from aipd_os.state.db import AIPDStateDB
from aipd_os.supply_chain.impact import propagate_lab_impact

T = DEFAULT_TENANT
REPO = Path(__file__).resolve().parents[1]


def _project(tmp_path) -> str:
    db_path = tmp_path / "state.db"
    db = AIPDStateDB(str(db_path))
    db.ensure_default_tenant(T)
    db.init_project(T, "P-1", "支架项目", "把支架做成可开模的量产件")
    return str(db_path)


def _store(tmp_path) -> BomStore:
    store = BomStore(str(Path(tmp_path) / "bom.db"))
    store.create_bom(T, "P-1", "支架主 BOM")
    return store


def _line(store, item, deliverable=None, **kw) -> BomLine:
    base = {"bom_id": store.get_bom(T, "P-1").bom_id, "tenant_id": T,
            "project_id": "P-1", "item": item, "quantity": 1.0, "unit": "pcs",
            "source_deliverable": deliverable}
    base.update(kw)
    line: BomLine = store.add_line(BomLine(line_id="", **base))
    return line


def _run(argv, capsys, *, expect: int = 0) -> dict:
    capsys.readouterr()
    rc = main(argv)
    out = capsys.readouterr().out.strip()
    assert rc == expect, f"rc={rc}（期望 {expect}）：{out}"
    payload: dict = json.loads(out)
    return payload


def _facts(db_path) -> dict:
    db = AIPDStateDB(db_path)
    return {f["key"]: f for f in db.list_facts(T, "P-1")
            if str(f["key"]).startswith("impact.")}


def _deliverables(db_path) -> dict:
    db = AIPDStateDB(db_path)
    return {d["deliverable_id"]: d for d in db.list_deliverables(T, "P-1")}


class TestImpactPropagation:
    def test_failing_item_stales_the_linked_deliverable(self, tmp_path):
        db_path = _project(tmp_path)
        db = AIPDStateDB(db_path)
        deliv = db.add_deliverable(T, "P-1", "drawing", path="bracket.dxf",
                                   status="draft")
        store = _store(tmp_path)
        line = _line(store, "支架", deliverable=deliv)

        report = propagate_lab_impact(db, store, T, "P-1", ["支架"], source="unit")

        assert [a["line_id"] for a in report.to_dict()["affected_lines"]] == [line.line_id]
        assert report.to_dict()["stale_deliverables"] == [deliv]
        assert _deliverables(db_path)[deliv]["status"] == "stale"
        # 声明里那句「事实主表更新」必须真的留下可查的行
        fact = _facts(db_path)["impact.支架"]
        assert fact["status"] == "P"
        assert fact["value"]["affected_line_ids"] == [line.line_id]
        assert fact["value"]["source"] == "unit"

    def test_line_without_linked_deliverable_is_reported_not_invented(self, tmp_path):
        """关联不到图纸就只报关联不到——不凭空造一条 deliverable，也不假装传播过了。"""
        db_path = _project(tmp_path)
        store = _store(tmp_path)
        line = _line(store, "支架", deliverable=None)

        report = propagate_lab_impact(AIPDStateDB(db_path), store, T, "P-1",
                                      ["支架"], source="unit")
        d = report.to_dict()
        assert d["stale_deliverables"] == []
        assert d["unresolved_lines"] == [line.line_id]
        assert d["clean"] is False, "有受影响行但无法落到制品上，不得算干净收口"
        assert _facts(db_path)["impact.支架"]["value"]["unresolved_line_ids"] == \
            [line.line_id]

    def test_released_deliverable_is_never_silently_staled(self, tmp_path):
        """已发布/已归档的制品不能被失败回溯悄悄改写（与 _mark_stale 同一纪律）。"""
        db_path = _project(tmp_path)
        db = AIPDStateDB(db_path)
        kept = db.add_deliverable(T, "P-1", "drawing", status="released")
        store = _store(tmp_path)
        _line(store, "支架", deliverable=kept)

        d = propagate_lab_impact(db, store, T, "P-1", ["支架"],
                                 source="unit").to_dict()
        assert d["stale_deliverables"] == []
        assert d["unresolved_lines"] == []
        assert _deliverables(db_path)[kept]["status"] == "released"

    def test_item_matching_is_normalised_and_bounded(self, tmp_path):
        """匹配走归一化（去空格、大小写不敏感），但绝不子串猜：'支架' 不带出 '支架座'。"""
        db_path = _project(tmp_path)
        store = _store(tmp_path)
        hit = _line(store, " 支架 ")
        _line(store, "支架座")

        d = propagate_lab_impact(AIPDStateDB(db_path), store, T, "P-1",
                                 ["支架"], source="unit").to_dict()
        assert [a["line_id"] for a in d["affected_lines"]] == [hit.line_id]

    def test_replay_is_the_repair_action(self, tmp_path):
        """重放不得撞 UNIQUE、不得翻倍：与 F-SUPPLY-02 同一教训（崩溃后补跑=修复）。"""
        db_path = _project(tmp_path)
        db = AIPDStateDB(db_path)
        deliv = db.add_deliverable(T, "P-1", "drawing", status="draft")
        store = _store(tmp_path)
        _line(store, "支架", deliverable=deliv)

        first = propagate_lab_impact(db, store, T, "P-1", ["支架"],
                                     source="unit").to_dict()
        second = propagate_lab_impact(AIPDStateDB(db_path), store, T, "P-1",
                                      ["支架"], source="unit").to_dict()
        assert list(_facts(db_path)) == ["impact.支架"]
        assert second["stale_deliverables"] == []      # 已 stale，不重复标记
        assert second["already_stale_deliverables"] == [deliv]   # 但要如实说"它已过期"
        assert first["stale_deliverables"] == [deliv]
        assert first["already_stale_deliverables"] == []
        assert first["clean"] is True and second["clean"] is True

    def test_no_affected_line_writes_no_fact(self, tmp_path):
        """无关失败项不产事实——否则事实表会被'什么都没影响到'的行淹没。"""
        db_path = _project(tmp_path)
        store = _store(tmp_path)
        _line(store, "支架")
        d = propagate_lab_impact(AIPDStateDB(db_path), store, T, "P-1",
                                 ["与项目无关的测试项"], source="unit").to_dict()
        assert d["affected_lines"] == []
        assert _facts(db_path) == {}


class TestReachableFromProductPath:
    """声明的能力必须有一条真命令能走到（这条就是本轮缺陷本体）。"""

    def _lab_csv(self, tmp_path, verdict="fail") -> str:
        lab = tmp_path / "lab.csv"
        lab.write_text(
            "stage,test_item,sample_id,result,pass_fail,notes\n"
            f"dvt,支架,S1,0.4,{verdict},拉力不足\n", encoding="utf-8")
        return str(lab)

    def test_industrialize_lab_data_reports_and_persists_impact(self, tmp_path, capsys):
        db_path = _project(tmp_path)
        db = AIPDStateDB(db_path)
        deliv = db.add_deliverable(T, "P-1", "drawing", status="draft")
        store = _store(tmp_path)
        _line(store, "支架", deliverable=deliv)
        capsys.readouterr()

        payload = _run(["industrialize", "--db", db_path, "--project", "P-1",
                        "--stage", "dvt", "--lab-data", self._lab_csv(tmp_path),
                        "--json"], capsys, expect=4)   # 阶段未通过 → 原本就 exit 4
        assert payload["analysis"]["failed"] == 1
        assert payload["impact"]["stale_deliverables"] == [deliv]
        assert _deliverables(db_path)[deliv]["status"] == "stale"
        assert list(_facts(db_path)) == ["impact.支架"]

    def test_passing_lab_data_creates_no_impact(self, tmp_path, capsys):
        db_path = _project(tmp_path)
        db = AIPDStateDB(db_path)
        deliv = db.add_deliverable(T, "P-1", "drawing", status="draft")
        store = _store(tmp_path)
        _line(store, "支架", deliverable=deliv)
        capsys.readouterr()

        payload = _run(["industrialize", "--db", db_path, "--project", "P-1",
                        "--stage", "dvt",
                        "--lab-data", self._lab_csv(tmp_path, "pass"), "--json"],
                       capsys)
        assert payload["impact"]["affected_lines"] == []
        assert _deliverables(db_path)[deliv]["status"] == "draft"
        assert _facts(db_path) == {}


# ---------------------------------------------------------------- 可达性守卫
#
# F-SUPPLY-03 的本体不是"传播算错了"，而是"传播没人能调到"。所以除上面的行为用例外，
# 还要一条常驻守卫：登记进适配器注册表的每个 capability id，要么真的被产品侧排产
# （`add_work(..., capability_floor=...)`），要么在本清单里写明"未接线"的理由。
# 允许存在未接线的适配器（它们是 CLI 之外的第二实现面），**不允许它悄悄存在**。

UNREACHABLE_ADAPTERS = {
    "cad.faceted-fallback": "faceted 兜底由 cad/backends 直接调用，不经 router 排产",
    "cad.local-brep": "本地 BREP 构建由 cad 命令直接调用，不经 router 排产",
    "cad.text-to-cad": "文生 CAD 依赖外部 Provider，产品侧未排产",
    "doc.generate": "文档生成由 manual 命令链直接调用，不经 router 排产",
    "manual.imggen": "配图生成由 manual 命令链直接调用，不经 router 排产",
    "manual.layout": "排版适配器零调用点（含测试），仅注册表里挂着",
    "research.search_papers": "研究检索由 scripts/research 连接器直接调用",
    "supply.rfq": "RFQ 走 outbox 事件 + dispatcher（aipd outbox drain），不经 router 排产",
    "supply.supplier-files": "供应商资料适配器零调用点（含测试），仅注册表里挂着",
    "validation.import-evt-dvt-pvt": "验证导入的产品面是 aipd validation import / "
                                     "aipd industrialize；影响传播已改接 supply_chain.impact",
}


def _scheduled_capability_ids() -> set[str]:
    """AST 扫产品侧：所有 `add_work(..., capability_floor=V)` 里能解析出字面量的 V。"""
    import ast

    def module_consts(tree):
        out = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant) \
                       and isinstance(node.value.value, str):
                        out[tgt.id] = node.value.value
        return out

    roots = [REPO / "src/aipd_os", REPO / "scripts", REPO / "state_service"]
    files = [p for root in roots for p in root.rglob("*.py")]
    # 先收集"模块文件名 -> 该模块的字符串常量"，供跨模块 import 解析
    consts_by_stem: dict[str, dict[str, str]] = {}
    trees = {}
    for p in files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        trees[p] = tree
        consts_by_stem[p.stem] = module_consts(tree)

    scheduled: set[str] = set()
    for tree in trees.values():
        local = module_consts(tree)
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                stem = (node.module or "").split(".")[-1]
                for alias in node.names:
                    imports[alias.asname or alias.name] = (stem, alias.name)

        # 默认参数绑定：闭包直接读循环变量会被 ruff B023 判成"绑错迭代值"
        def resolve(node, _local=local, _imports=imports):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.Name):
                if node.id in _local:
                    return _local[node.id]
                stem, sym = _imports.get(node.id, ("", ""))
                return consts_by_stem.get(stem, {}).get(sym)
            if isinstance(node, ast.Call) and node.args:   # str(CONST) 形态
                return resolve(node.args[0])
            return None

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if fname != "add_work":
                continue
            for kw in node.keywords:
                if kw.arg == "capability_floor":
                    value = resolve(kw.value)
                    if value:
                        scheduled.add(value)
    return scheduled


class TestNoSilentDeadCapability:
    def test_registered_adapters_are_scheduled_or_declared(self):
        from aipd_os.tool_adapters.builtin import builtin_adapters

        scheduled = _scheduled_capability_ids()
        ids = sorted({a.capability_id() for a in builtin_adapters()})
        assert ids, "注册表为空 ⇒ 这条守卫在空转"
        undeclared = [i for i in ids if i not in scheduled and i not in UNREACHABLE_ADAPTERS]
        assert not undeclared, (
            f"这些适配器已注册但既不被产品侧排产、也未在 UNREACHABLE_ADAPTERS 里说明："
            f"{undeclared}")

    def test_probe_actually_sees_the_scheduled_chain(self):
        """正向对照：idea/product 链必须被探针读到，否则上一条测试是假绿。"""
        scheduled = _scheduled_capability_ids()
        assert "idea.structure" in scheduled
        assert "product.derive_insights" in scheduled
        assert "validation.import-evt-dvt-pvt" not in scheduled   # 本体：确实没排产

    def test_guard_fires_when_an_unreachable_adapter_is_hidden(self):
        """注入反证：把一个未接线 id 从声明表里抹掉，守卫必须判红。"""
        from aipd_os.tool_adapters.builtin import builtin_adapters

        scheduled = _scheduled_capability_ids()
        ids = {a.capability_id() for a in builtin_adapters()}
        hidden = sorted(ids - scheduled)
        assert hidden, "没有未接线适配器 ⇒ 反证无从构造"
        stripped = {k: v for k, v in UNREACHABLE_ADAPTERS.items() if k != hidden[0]}
        leaked = [i for i in ids if i not in scheduled and i not in stripped]
        assert leaked == [hidden[0]], "抹掉声明却不判红 ⇒ 守卫是假的"
