"""第 30 片 (C)：交付物**落点形状**被真门核住的常驻用例。

这一格以前是「存在性有门、内容不合形没人管」：`scripts/quality_gate.py` 的 G9 只看
deliverable 的**类型**在不在，`scripts/outcome_acceptance.py:22` 只看
`state/project_checkpoint.json` 存不存在（`exists()` 只要求 size>0）。
两份都不读内容，于是字段改坏了照样绿。

判据不在测试里复刻：每个 case 都**起子进程跑真脚本**，读它自己打出来的 JSON。
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os import schema_binding as sb
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "quality_gate.py"
ACCEPT = ROOT / "scripts" / "outcome_acceptance.py"
CHECKPOINT_ARTIFACT = "state/project_checkpoint.json"
GOOD = json.loads((ROOT / "assets" / "templates"
                   / "project_checkpoint.json").read_text(encoding="utf-8"))
G9_TYPES = ["product_manual", "release_package", "release_audit", "project_checkpoint"]


def _read(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode in (0, 1, 5), \
        f"脚本自己就崩了：rc={proc.returncode}\n{proc.stderr[-600:]}"
    parsed = json.loads(proc.stdout)
    assert isinstance(parsed, dict), f"脚本打出来的不是 JSON 对象：{proc.stdout[:200]}"
    return parsed


@pytest.fixture()
def world(tmp_path: Path) -> dict:
    """一个 G9 项目：四类交付物都标 complete，checkpoint 文件按 case 落。"""
    root = tmp_path / "proj"
    (root / "state").mkdir(parents=True)
    db = AIPDStateDB(str(root / "state.db"))
    db.ensure_default_tenant()
    db.init_project("default", "P-SHAPE", "形状门探针", "slice 30")
    return {"root": root, "db": db, "tmp": tmp_path}


def _seed_deliverables(world: dict, *, checkpoint_path: str | None,
                       status: str = "complete") -> None:
    db = world["db"]
    for t in G9_TYPES:
        if t == "project_checkpoint":
            db.add_deliverable("default", "P-SHAPE", t, path=checkpoint_path,
                               status=status, gate="G9")
        else:
            db.add_deliverable("default", "P-SHAPE", t, path=f"out/{t}.md",
                               status="complete", gate="G9")


def _write_checkpoint(root: Path, doc) -> None:
    (root / CHECKPOINT_ARTIFACT).write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _gate(world: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(GATE), "--db", str(world["root"] / "state.db"),
         "--project", "P-SHAPE", "--gate", "G9", "--root", str(world["root"])],
        capture_output=True, text=True, cwd=str(ROOT))
    return _read(proc)


class TestContractedTypesAreDerived:
    def test_today_exactly_one_type_has_a_contract(self):
        """今天 40 个交付物类型里只有 `project_checkpoint` 有同名契约——数出来，别抄。"""
        assert sb.contract_for_artifact(CHECKPOINT_ARTIFACT) == \
            "project_checkpoint.schema.json"
        assert sb.contract_for_artifact("cad/inspection_report.json") is None

    def test_the_gate_widens_when_a_contract_appears(self, tmp_path, monkeypatch):
        """绑定面来自现算：多一份同名契约，门就多核一类（反证「写死一个类型」）。"""
        import scripts.quality_gate as qg  # noqa: PLC0415 - 被测脚本
        real = sb.list_schemas
        monkeypatch.setattr(sb, "list_schemas",
                            lambda repo: [*real(repo), "product_manual.schema.json"])
        got = qg.contracted_types()
        assert set(got) == {"project_checkpoint", "cad_contract", "product_manual"}, got
        monkeypatch.undo()
        assert set(qg.contracted_types()) == {"project_checkpoint", "cad_contract"}


class TestGateRejectsUncompliantDeliverables:
    def test_a_conforming_checkpoint_stays_green(self, world):
        """must-not-fire：合规的一侧必须绿，否则收紧只是多报。"""
        _seed_deliverables(world, checkpoint_path=CHECKPOINT_ARTIFACT)
        _write_checkpoint(world["root"], GOOD)
        out = _gate(world)
        assert out["shape_findings"] == [] and out["pass"] is True, out

    def test_missing_path_is_a_finding_not_a_skip(self, world):
        """标了 complete 却没填 path：形状无从核起，这一格不许读成过。"""
        _seed_deliverables(world, checkpoint_path=None)
        out = _gate(world)
        assert [f["finding"] for f in out["shape_findings"]] == ["path_missing"]
        assert out["pass"] is False

    def test_declared_but_absent_file_is_a_finding(self, world):
        _seed_deliverables(world, checkpoint_path=CHECKPOINT_ARTIFACT)
        out = _gate(world)
        assert [f["finding"] for f in out["shape_findings"]] == ["missing"]
        assert out["pass"] is False

    def test_a_file_that_is_not_json_is_unreadable_not_invalid(self, world):
        """两种红要分开：一个说「改坏了」，一个说「核不了」，下一步动作不同。"""
        _seed_deliverables(world, checkpoint_path=CHECKPOINT_ARTIFACT)
        (world["root"] / CHECKPOINT_ARTIFACT).write_text("{oops", encoding="utf-8")
        out = _gate(world)
        assert [f["finding"] for f in out["shape_findings"]] == ["unreadable"]

    def test_shape_violation_names_the_offending_path(self, world):
        """契约改了字段 ⇒ 门要点名到哪一条。这里用 `$defs.fact` 单源化后多出来的
        `fact_id` 要求：少它就是一条 named error。"""
        _seed_deliverables(world, checkpoint_path=CHECKPOINT_ARTIFACT)
        bad = copy.deepcopy(GOOD)
        bad["facts"] = [{"key": "k", "value": 1, "status": "U"}]
        _write_checkpoint(world["root"], bad)
        out = _gate(world)
        findings = out["shape_findings"]
        assert [f["finding"] for f in findings] == ["invalid"], findings
        assert "fact_id" in findings[0]["detail"]
        assert out["pass"] is False

    def test_a_status_below_complete_is_not_shape_checked(self, world):
        """还没交付的东西不该被形状门拦——它已经被 `missing_deliverables` 拦了。"""
        _seed_deliverables(world, checkpoint_path=CHECKPOINT_ARTIFACT, status="planned")
        out = _gate(world)
        assert out["shape_findings"] == []
        assert "project_checkpoint" in out["missing_deliverables"]

    def test_types_without_a_contract_are_left_alone(self, world):
        """反向对照：另三类今天没有同名契约，path 指向不存在的文件也不算形状问题
        （否则这条门会把整仓的 .md 交付物一起拦死）。"""
        _seed_deliverables(world, checkpoint_path=CHECKPOINT_ARTIFACT)
        _write_checkpoint(world["root"], GOOD)
        (world["root"] / "out" / "product_manual.md").unlink(missing_ok=True)
        out = _gate(world)
        assert out["shape_findings"] == [] and out["pass"] is True


class TestAcceptanceReportsTheShapeVerdict:
    """验收脚本这一侧要**单独可归因**：其它构件齐备时，翻转只能来自形状判据。"""

    THREAD_ARTIFACTS = ["requirements/requirements.md", "engineering/v1_engineering.md",
                        "manual/manual.pdf", "cad/model.step",
                        "cad/inspection_report.json", "manufacturing/bom.xlsx"]

    def _full_thread(self, world: dict) -> None:
        for rel in self.THREAD_ARTIFACTS:
            path = world["root"] / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")

    def _acceptance(self, world: dict) -> dict:
        proc = subprocess.run([sys.executable, str(ACCEPT),
                               "--project-root", str(world["root"])],
                              capture_output=True, text=True, cwd=str(ROOT))
        return _read(proc)

    def test_conforming_file_reports_valid(self, world):
        self._full_thread(world)
        _write_checkpoint(world["root"], GOOD)
        out = self._acceptance(world)
        assert out["checkpoint_shape"]["status"] == "valid"
        assert out["digital_thread_complete"] is True, \
            "六个前置产物都已铺好；这里若为 False，翻转就不是形状那一格"

    def test_broken_shape_is_the_sole_discriminator(self, world):
        """同一棵树、同一个脚本，只改 checkpoint 的 facts ⇒ 两处必须一起翻。

        刻意先铺满 `digital_thread_complete` 的其它前提：不铺的话那条合取自己就是 False，
        这条用例会在「形状判据被删掉」之后仍然绿（第一次跑电池时就是这样混过去的）。
        """
        self._full_thread(world)
        _write_checkpoint(world["root"], GOOD)
        before = self._acceptance(world)
        bad = copy.deepcopy(GOOD)
        bad["facts"] = [{"key": "k", "value": 1, "status": "U"}]
        _write_checkpoint(world["root"], bad)
        after = self._acceptance(world)
        assert (before["checkpoint_shape"]["status"], before["digital_thread_complete"]) \
            == ("valid", True)
        assert after["checkpoint_shape"]["status"] == "invalid"
        assert after["digital_thread_complete"] is False
        assert "fact_id" in " ".join(after["checkpoint_shape"]["errors"])
