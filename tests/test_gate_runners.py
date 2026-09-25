"""第 33 片：把「门没人跑」这一族闭掉。

实测前提（2026-09-25，全部为今天真跑的读数，不是引用旧登记）：

- `references/end-to-end-closure-model.md:10` 把 `scripts/e2e_acceptance.py` 写成
  「数字全链路已打通」的**唯一**判据，`references/local-cad-fallback.md:25` 第 8 步要求跑它，
  `scripts/runtime_preflight.py:46` 也明写 preflight 不宣布闭环、闭环要它；
  但**全仓没有任何 CI 或用例调用这三个脚本**（`selftest_quality.py`、`e2e_acceptance.py`、
  `selftest_v4.py`）——去掉 `| head` 截断重跑 `grep -rn` 才敢说这句。
- 旧版 `selftest_quality.py` 两条判据**都只断言子进程 `rc != 0`**，没有一支合规侧对照 ⇒
  把任一台门改成「任何输入都退 1」，它照样绿。
- `outcome_acceptance.py` 报 `missing` 时那句 `errors=["标了交付，但文件不在"]`
  是越界断言：这个函数拿不到交付清单，对**空目录**也回同一句（实测）。

本片把「谁跑这些门」变成常驻断言，并把 `selftest_quality.py` 补成四支两两对照。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os import schema_binding as sb

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
E2E = SCRIPTS / "e2e_acceptance.py"
ACCEPT = SCRIPTS / "outcome_acceptance.py"
SELFTEST_Q = SCRIPTS / "selftest_quality.py"
SELFTEST_V4 = SCRIPTS / "selftest_v4.py"
GATE = SCRIPTS / "quality_gate.py"
GOOD = json.loads((ROOT / "assets" / "templates"
                   / "project_checkpoint.json").read_text(encoding="utf-8"))
THREAD = ["requirements/requirements.md", "engineering/v1_engineering.md", "manual/manual.pdf",
          "cad/model.step", "cad/inspection_report.json", "manufacturing/bom.xlsx"]

#: 契约点名的、以及自称是自检的门 —— 每一支都要有「除自身之外」的真读者
RUNNABLE_GATES = ["e2e_acceptance.py", "selftest_quality.py", "selftest_v4.py"]

# 普查只排除脚本自己。注意这条问的是「谁**调用**它」（要求 subprocess/argv 形态），
# 不是第 30 片那种「按字面量反查谁引用它」——后者才必须排除量具本身，
# 否则光写一条断言就把分母 +1。本用例确实以子进程跑了这三台门，所以它自己就是合法读者。


def _read(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode in (0, 5, 6, 7), f"rc={proc.returncode}\n{proc.stdout[-600:]}"
    out: dict = json.loads(proc.stdout)
    return out


def _full_thread(root: Path, *, with_review: bool = True) -> Path:
    for rel in THREAD:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    ck = root / "state" / "project_checkpoint.json"
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(json.dumps(GOOD, ensure_ascii=False), encoding="utf-8")
    (root / "quality").mkdir(parents=True, exist_ok=True)
    (root / "quality" / "outcome_contract.json").write_text("{}", encoding="utf-8")
    if with_review:
        (root / "manual" / "manual_quality_review.json").write_text(json.dumps(
            {"golden_reference_compared": True,
             "owner_or_independent_visual_acceptance": True,
             "score": 9.2, "threshold": 8.0}, ensure_ascii=False), encoding="utf-8")
    return root


class TestContractNamedGatesHaveAReader:
    """契约点名的门不许停在「写了但没人跑」；普查面排除脚本自身与本用例。"""

    def _readers(self, name: str) -> list[str]:
        self_path = {"scripts/" + name}
        readers = []
        for base in ("src", "scripts", "tests", "state_service"):
            for path in (ROOT / base).rglob("*.py"):
                rel = str(path.relative_to(ROOT))
                if rel in self_path:
                    continue
                if name in path.read_text(encoding="utf-8"):
                    readers.append(rel)
        for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
            if name in wf.read_text(encoding="utf-8"):
                readers.append(str(wf.relative_to(ROOT)))
        return readers

    @pytest.mark.parametrize("name", RUNNABLE_GATES)
    def test_each_gate_is_actually_invoked_by_someone(self, name: str):
        readers = self._readers(name)
        assert readers, (f"{name} 没有任何调用者 ⇒ 契约里那句「只有它能宣布闭环」"
                         f"落在一台没人跑的门上")
        # 只被注释提过不算跑过：至少有一处是子进程调用或 import
        invoked = [r for r in readers if self._looks_like_invocation(ROOT / r, name)]
        assert invoked, f"{name} 只被文本提到，没人真跑：{readers}"

    @staticmethod
    def _looks_like_invocation(path: Path, name: str) -> bool:
        """「跑过」的判据取到名字级即可（这是普查，不是逐调用点证明）：
        同一文件里既出现脚本名、又出现真的 spawn 调用。CI workflow 也算。"""
        if path.suffix == ".yml":
            return name in path.read_text(encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        spawns = ("subprocess.run(", "subprocess.call(", "subprocess.check_call(",
                  "subprocess.Popen(")
        return name in text and any(spawn in text for spawn in spawns)


class TestWrapperForwardsTheInnerVerdict:
    """包装器只做一件事：把内层判据的退出码原样交出去。不许自己判、不许吞码。"""

    def test_green_arm_returns_zero(self, tmp_path):
        root = _full_thread(tmp_path / "green")
        proc = subprocess.run([sys.executable, str(E2E), "--project-root", str(root)],
                              capture_output=True, text=True, cwd=str(ROOT))
        out = _read(proc)
        assert proc.returncode == 0, out
        assert out["communication_accepted"] is True
        assert out["classification"] == "communication_accepted"

    def test_withdrawal_arm_is_not_read_as_passing(self, tmp_path):
        """合规侧先绿，再只撤一样东西 ⇒ 红必须来自这一样。"""
        root = _full_thread(tmp_path / "withdraw")
        (root / "manual" / "manual_quality_review.json").write_text(json.dumps(
            {"golden_reference_compared": True,
             "owner_or_independent_visual_acceptance": True,
             "score": 7.9, "threshold": 8.0}), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(E2E), "--project-root", str(root)],
                              capture_output=True, text=True, cwd=str(ROOT))
        out = _read(proc)
        assert proc.returncode == 5, out
        assert out["digital_thread_complete"] is True   # 链还在
        assert out["communication_accepted"] is False   # 只有验收那一格掉了

    def test_require_full_maps_to_the_production_gate(self, tmp_path):
        root = _full_thread(tmp_path / "full")
        proc = subprocess.run([sys.executable, str(E2E), "--project-root", str(root),
                               "--require-full"],
                              capture_output=True, text=True, cwd=str(ROOT))
        out = _read(proc)
        assert out["requested_gate"] == "production"
        assert proc.returncode == 5, "通信级绿不许被读成「全链路 + 量产发布」都绿"

    def test_json_out_actually_lands_on_disk(self, tmp_path):
        root = _full_thread(tmp_path / "json")
        target = tmp_path / "written.json"
        proc = subprocess.run([sys.executable, str(E2E), "--project-root", str(root),
                               "--json-out", str(target)],
                              capture_output=True, text=True, cwd=str(ROOT))
        assert proc.returncode == 0
        assert target.is_file() and target.stat().st_size > 0
        assert json.loads(target.read_text(encoding="utf-8"))["communication_accepted"]


class TestSelftestsAreRunAndBothSided:
    """两台自检脚本：一是真被跑，二是**每支判据都带合规侧**（防止「永远红」冒充有牙）。"""

    def test_selftest_quality_passes_and_reports_four_named_checks(self):
        proc = subprocess.run([sys.executable, str(SELFTEST_Q)],
                              capture_output=True, text=True, cwd=str(ROOT))
        out = _read(proc)
        assert proc.returncode == 0, out
        assert out["passed"] is True
        ids = [c["id"] for c in out["checks"]]
        assert ids == ["A1_artifact_only_holds_communication",
                       "A2_full_thread_passes_communication",
                       "B1_faceted_brep_cannot_reach_C7",
                       "B2_native_brep_reaches_C7"], ids
        # 两支合规侧必须在场，删掉任何一支都算把判据退回单向
        assert "A2_full_thread_passes_communication" in ids
        assert "B2_native_brep_reaches_C7" in ids
        # 每支都要把**判决字段**交出来：只报退出码的自检读不出它在拦什么
        read = {c["id"]: c["read"] for c in out["checks"]}
        a1 = read["A1_artifact_only_holds_communication"]
        assert a1["artifact_complete"] is True and a1["communication_accepted"] is False, a1
        assert read["A2_full_thread_passes_communication"]["shape"] == "valid"
        assert read["A2_full_thread_passes_communication"]["communication_accepted"] is True
        assert set(read["A1_artifact_only_holds_communication"]) >= {"rc"}

    def test_selftest_quality_asserts_the_reason_not_just_the_exit_code(self):
        """旧版只看 `rc != 0`：把门改成永远红它就绿了。这里钉住「读的是判决字段」。"""
        tree = ast.parse(SELFTEST_Q.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        assert "communication_accepted" in text, "A1 不许退回只看退出码"
        assert "checkpoint_shape" in text or "shape" in text, "A2 要看形状判据的字段"

    def test_selftest_v4_passes(self):
        proc = subprocess.run([sys.executable, str(SELFTEST_V4)],
                              capture_output=True, text=True, cwd=str(ROOT),
                              timeout=600)
        assert proc.returncode == 0, proc.stdout[-800:] + proc.stderr[-800:]
        assert "v4 supervisor selftest passed" in proc.stdout


class TestMissingMessageOnlySaysWhatItKnows:
    """`missing` 的文案不许断言「标了交付」；那半句只有拿着交付清单的调用方能说。"""

    def test_the_binder_reports_only_that_the_file_is_absent(self, tmp_path):
        got = sb.validate_artifact_file(tmp_path, "state/project_checkpoint.json")
        assert got["status"] == sb.MISSING
        assert got["errors"] == ["文件不在盘上"], got
        assert not any("交付" in e for e in got["errors"]), \
            "校验器不知道有没有人声明过，不许写进它的错误串"

    def test_the_gate_that_knows_the_declaration_adds_it(self, tmp_path):
        """反向对照：同一件事在**有清单可读**的门那里要能说明「已标 complete」。"""
        root = tmp_path / "proj"
        (root / "state").mkdir(parents=True)
        from aipd_os.state.db import AIPDStateDB
        db = AIPDStateDB(str(root / "state.db"))
        db.ensure_default_tenant()
        db.init_project("default", "P33", "声明侧文案", "slice 33")
        db.add_deliverable("default", "P33", "cad_contract",
                           path="cad/cad_contract.json", status="complete", gate="G3")
        proc = subprocess.run([sys.executable, str(GATE), "--db", str(root / "state.db"),
                               "--project", "P33", "--gate", "G3", "--root", str(root)],
                              capture_output=True, text=True, cwd=str(ROOT))
        # 门的退出码口径与验收脚本不同：0 放行 / 1 不放行 / 3 读不到声明（第 31 片）
        assert proc.returncode in (0, 1, 3), proc.stdout[-500:]
        out = json.loads(proc.stdout)
        findings = [f for f in out["shape_findings"] if f["type"] == "cad_contract"]
        assert [f["finding"] for f in findings] == ["missing"], out["shape_findings"]
        assert "文件不在盘上" in findings[0]["detail"]
        assert "已标 complete" in findings[0]["detail"], findings[0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
