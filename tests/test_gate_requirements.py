"""第 31 片：G 表只许有一个来源（声明文件），差集必须具名。

实测前提（2026-09-25）：`assets/templates/gate_requirements.yaml` 声明 **50** 个交付物类型，
`scripts/quality_gate.py` 的手抄 `REQ` 只强制 **40** 个 —— 方向单边（没有「门要求但没声明」的），
而脚本注释还写着「requirements mirror gate_requirements.yaml」。全仓没有任何解析器读过那份 YAML，
它的名字只出现在那句注释里 ⇒ 两处声明同一张表，已经漂了 10 项。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os import gate_requirements as gr
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "quality_gate.py"
DECLARATION = ROOT / gr.DECLARATION


def _load_gate_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("qg_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDeclarationIsTheOnlySource:
    def test_the_script_no_longer_carries_a_copied_table(self):
        """脚本里不许再出现手抄的 `'G3': [...]`；出现了就是第二份表回来了。"""
        text = GATE.read_text(encoding="utf-8")
        assert not re.search(r"['\"]G\d['\"]\s*:\s*\[", text), \
            "quality_gate.py 里又出现内联的门表了"
        assert "gate_requirements" in text and "gr.load()" in text

    def test_enforced_table_equals_declaration_minus_the_named_gap(self):
        decl = gr.load()
        assert decl["status"] == "ok", decl["why"]
        assert gr.enforced_table(decl["gates"]) == _load_gate_module().REQ

    def test_the_declaration_file_is_actually_parsed_by_something(self):
        """注释说「mirror」不算引用；必须真有解析器读它。"""
        readers = []
        for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")) \
                + list((ROOT / "state_service").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if gr.DECLARATION in text and ("yaml.safe_load" in text or "gr.load()" in text
                                           or "gate_requirements import" in text):
                readers.append(str(path.relative_to(ROOT)))
        assert readers, "没有任何代码读声明文件 ⇒ 它就是第二份手抄表"

    def test_owner_axis_was_never_the_drift(self):
        """如实记下：漂的只有交付物轴，`requires_owner_approval` 两份一直一致。"""
        decl = gr.load()
        assert decl["owner_gates"] == _load_gate_module().OWNER


class TestTheGapIsNamedAndExhaustive:
    def test_declared_minus_enforced_is_exactly_the_nine(self):
        decl = gr.load()["gates"]
        declared = {t for types in decl.values() for t in types}
        enforced = {t for types in gr.enforced_table(decl).values() for t in types}
        assert declared - enforced == set(gr.UNPRODUCED), \
            "差集与具名清单不等 ⇒ 有新项被静默掉出去了（加一项就要在这里具名并写理由）"
        assert sorted(declared - enforced) == [
            "cad_bom_mapping", "cad_inspection_report", "cad_l1_functional_layout",
            "cad_l4_dfm_drawings", "cad_l5_release_package", "cad_parametric_source",
            "cad_primary_step", "cad_snapshot_packet", "evt_cad_configuration"]

    def test_every_gap_item_carries_a_reason(self):
        assert all(v.strip() for v in gr.UNPRODUCED.values()), "空理由的豁免等于没有豁免"
        assert not (set(gr.UNPRODUCED) & set(gr.NEWLY_ENFORCED))

    def test_adding_a_declaration_automatically_becomes_a_requirement(self, tmp_path):
        """声明是权威：往 YAML 加一项，门就要求它（这正是「表只有一处」的意义）。

        反面风险是**自动收紧**——新加的一项若没人能产，门会当场变红；
        所以这一格的行为要写死，而不是留在「大概会自动生效」的想象里。
        """
        target = tmp_path / gr.DECLARATION
        target.parent.mkdir(parents=True)
        target.write_text(DECLARATION.read_text(encoding="utf-8")
                          + "\nGX:\n  required_deliverables: [brand_new_artifact]\n"
                            "  requires_owner_approval: false\n", encoding="utf-8")
        decl = gr.load(tmp_path)["gates"]
        assert gr.enforced_table(decl)["GX"] == ["brand_new_artifact"]
        assert gr.unproduced_in(decl) == sorted(gr.UNPRODUCED)

    def test_removing_an_exemption_promotes_the_type_into_the_gate(self, monkeypatch):
        """从 `UNPRODUCED` 删一项 ⇒ 它立刻进强制集（要么真去产它，要么别删）。"""
        import aipd_os.gate_requirements as mod
        decl = mod.load()["gates"]
        assert "cad_primary_step" not in {t for ts in mod.enforced_table(decl).values()
                                          for t in ts}
        monkeypatch.setattr(mod, "UNPRODUCED",
                            {k: v for k, v in mod.UNPRODUCED.items()
                             if k != "cad_primary_step"})
        promoted = {t for ts in mod.enforced_table(decl).values() for t in ts}
        assert "cad_primary_step" in promoted


class TestProducerProbeCanFire:
    """负向读数（「九项没有产者」）只有在探针被证明能开火之后才算数。"""

    def test_positive_controls_are_found(self):
        hits, sample = gr.producer_literals(ROOT)
        assert "cad_contract" in hits, sample.get("cad_contract")
        assert "project_brief" in hits, "连最基础的交付物类型都探不到 ⇒ 探针在空转"

    def test_the_nine_gap_types_really_have_no_literal(self):
        hits, _ = gr.producer_literals(ROOT)
        assert not (set(gr.UNPRODUCED) & hits), sorted(set(gr.UNPRODUCED) & hits)

    def test_the_scanned_directories_exist(self):
        """扫的目录若不存在，「零命中」就是假的（读不到 ≠ 没有）。"""
        for rel in ("src", "scripts", "state_service", "assets/templates", "references"):
            assert (ROOT / rel).is_dir(), rel


class TestG3NowDemandsTheCadContract:
    """收紧的那一项要真拦得住：G3 少了 `cad_contract` 必须报缺，补齐才过。"""

    CONTRACT_PATH = "cad/cad_contract.json"

    def _world(self, tmp_path: Path, *, with_contract: bool,
               contract_path: str | None = CONTRACT_PATH) -> tuple[Path, Path]:
        root = tmp_path / "proj"
        (root / "state").mkdir(parents=True)
        if contract_path is not None:
            body = json.loads((ROOT / "assets" / "templates"
                               / "cad_contract.json").read_text(encoding="utf-8"))
            target = root / contract_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        db = AIPDStateDB(str(root / "state.db"))
        db.ensure_default_tenant()
        db.init_project("default", "P-G3", "G3 探针", "slice 31")
        for t in ["v1_engineering_definition", "preliminary_bom", "interface_register",
                  "dfmea_draft", "cad_contract"]:
            if t == "cad_contract" and not with_contract:
                continue
            db.add_deliverable("default", "P-G3", t,
                               path=contract_path if t == "cad_contract"
                               else f"out/{t}.md",
                               status="complete", gate="G3")
        return root, db_file(root)

    def test_missing_cad_contract_is_reported(self, tmp_path):
        root, db = self._world(tmp_path, with_contract=False)
        out = _run_gate(root, db)
        assert "cad_contract" in out["missing_deliverables"], out
        assert out["pass"] is False

    def test_with_the_contract_the_gate_is_green(self, tmp_path):
        """must-not-fire 的一侧：补齐就绿，否则这条收紧只是多报。"""
        root, db = self._world(tmp_path, with_contract=True)
        out = _run_gate(root, db)
        assert out["missing_deliverables"] == [], out
        assert out["pass"] is True

    def test_a_pathless_cad_contract_is_a_shape_finding(self, tmp_path):
        """`cad_contract` 进了强制集之后**也**进了形状门那侧：它有同名契约，
        标了完成却没填 path 就要点名（不是「算了，看不见」）。"""
        root, db = self._world(tmp_path, with_contract=True, contract_path=None)
        out = _run_gate(root, db)
        assert [(f["type"], f["finding"]) for f in out["shape_findings"]] \
            == [("cad_contract", "path_missing")], out

    def test_the_report_states_both_numbers(self, tmp_path):
        root, db = self._world(tmp_path, with_contract=True)
        out = _run_gate(root, db)
        assert out["enforced_counts"] == {"declared": 6, "enforced": 5}, out
        assert out["requirement_source"] == gr.DECLARATION
        # 少要求的那一项必须**报出来**，不能只从数字里被看出来
        assert out["declared_unenforced"] == ["cad_l1_functional_layout"], out


def db_file(root: Path) -> Path:
    return root / "state.db"


def _run_gate(root: Path, db: Path) -> dict:
    proc = subprocess.run([sys.executable, str(GATE), "--db", str(db),
                           "--project", "P-G3", "--gate", "G3", "--root", str(root)],
                          capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode in (0, 1, 3), f"rc={proc.returncode}\n{proc.stderr[-500:]}"
    out: dict = json.loads(proc.stdout)
    return out


class TestUnreadableDeclarationFailsClosed:
    def test_missing_file_reports_unreadable_not_empty_requirements(self, tmp_path):
        got = gr.load(tmp_path)
        assert got["status"] == "unreadable" and got["gates"] == {}
        assert "不在盘上" in got["why"]

    def test_malformed_yaml_is_not_read_as_no_gates(self, tmp_path):
        target = tmp_path / gr.DECLARATION
        target.parent.mkdir(parents=True)
        target.write_text("- 一个列表\n- 而不是映射\n", encoding="utf-8")
        got = gr.load(tmp_path)
        assert got["status"] == "malformed", got
        assert got["gates"] == {}

    def test_the_script_refuses_to_judge_when_the_table_is_gone(self, monkeypatch):
        """读不到 ⇒ 退出码非零且**不**给出 pass=false 之类的可被误读的判决。"""
        qg = _load_gate_module()
        monkeypatch.setattr(qg, "_tables", lambda: {
            "ok": False, "why": "测试注入：YAML 不在", "req": {}, "owner": set(),
            "declared": {}, "unenforced": []})
        monkeypatch.setattr(sys, "argv", ["quality_gate.py", "--db", ":memory:",
                                          "--project", "P", "--gate", "G9"])
        out = qg.main()
        assert out == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
