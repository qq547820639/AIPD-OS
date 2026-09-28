"""依赖许可证门禁的常驻牙（F-DEP-LICENSE 第 92 片）。

分四组：① 量具必须被真的 spawn；② 真仓库上分母非空且**退码由判据自己决定**；
③ 注入的两极（看得见但不合规 ⇒ 红；裁对了 ⇒ 绿）；④ 两处信号阶梯的形状，
其中"只有泛化 classifier + 具体 License 字段"那一格就是本面立起的真原因（casadi）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dependency_license_gate as dlg  # noqa: E402

TOOL = ROOT / "scripts" / "dependency_license_gate.py"


def _spawn(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)


def _tree(tmp: Path, deps: list[str]) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "pyproject.toml").write_text(
        "[project]\ndependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]\n",
        encoding="utf-8")
    return tmp


def _rec(name: str, expr: str = "", fields: list[str] | None = None,
         cls: list[str] | None = None, requires: list[str] | None = None) -> dict[str, Any]:
    """`scripts/` 不在 mypy 的 `files` 里 ⇒ 导入进来的构造器是无类型的，落一次注解。"""
    rec: dict[str, Any] = dlg._rec(name, expr=expr, fields=fields, cls=cls, requires=requires)
    return rec


def test_instrument_self_test_is_actually_spawned_and_green() -> None:
    """没有这一条，`--self-test` 与"没有自测"在读数上不可区分（第 60 片的孤儿门禁）。"""
    proc = _spawn("--self-test")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条合成读数全部对上" in proc.stdout, proc.stdout


def test_real_repo_face_is_live_and_return_code_follows_the_verdict() -> None:
    rep = dlg.audit(ROOT)
    c = rep["corpus"]
    assert not rep["problems"], rep["problems"]
    assert c["declared_roots"] >= 10, c
    assert c["closure"] >= 40, c
    assert c["inspected"] >= 35, c
    assert rep["buckets"]["allowed"] >= 30, rep["buckets"]
    # 退码不许钉成绝对数：钉"退码 == 判据自己的结论"，覆盖面变化时它仍成立
    rc = _spawn("--repo", str(ROOT)).returncode
    assert rc == (0 if rep["ok"] else 4), (rc, rep["ok"], rep["violations"])
    assert rep["corpus"]["skipped_optional_requires"] > 100, rep["corpus"]


def test_casadi_stays_red_until_a_human_adjudicates_it() -> None:
    """真仓库的**活原告**：`cadquery ← casadi`，上游自述 LGPL-3.0-or-later。

    这条用例钉的是"它今天还没被拍板"，不是"它永远不合规"。
    要让它转绿：把 `docs/audit/DEPENDENCY_LICENSE_LEDGER.json` 里那条 `decision`
    改成 `accepted`，并按 `docs/security/dependency-license-review.md` §二 补齐三条分发义务
    ——届时这条用例**必须被改**（改成断言"已 accepted 且台账理由非空"），
    不许用放宽判据的方式糊过去。
    """
    rep = dlg.audit(ROOT)
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证未裁定", "casadi") in fired, (fired, rep["buckets"])
    row = next(r for r in rep["rows"] if r["package"] == "casadi")
    assert row["licenses"] == ["lgpl-3.0-or-later"], row
    assert row["via"] == "cadquery", row
    assert dlg.main(["--repo", str(ROOT)]) == 4, fired


def test_generic_classifier_alone_is_invisible_not_compliant(tmp_path: Path) -> None:
    """`License :: OSI Approved`（泛化）不算已标注；同一包的 `License` 字段才是答案。

    两极：只给泛化 classifier ⇒ 判「看不见」；补上具体的 `License` 字段 ⇒ 按字段判档。
    少了第一极，"信号阶梯"会退化成"classifier 优先"，casadi 那一格就会被读成未标注而放过。
    """
    tree = _tree(tmp_path / "t1", ["zzz-only-osi"])
    idx = {"zzz-only-osi": [_rec("zzz-only-osi", cls=["OSI Approved"])]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    assert ("依赖许可证看不见", "zzz-only-osi") in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]

    idx2 = {"zzz-only-osi": [_rec("zzz-only-osi", cls=["OSI Approved"],
                                  fields=["GNU Lesser General Public License v3 or later "
                                          "(LGPLv3+)"])]}
    rep2 = dlg.audit(tree, idx=idx2, declared_not_installed={})
    got2 = {(v["field"], v["doc"]) for v in rep2["violations"]}
    assert ("依赖许可证看不见", "zzz-only-osi") not in got2, got2
    assert ("依赖许可证未裁定", "zzz-only-osi") in got2, got2
    assert dlg._canon("Zzz_Only-OSI") == "zzz-only-osi"


def test_ledger_can_clear_a_review_package_only_with_a_matching_license(tmp_path: Path) -> None:
    """台账要**逐字对上现读的许可证串**且 `decision=accepted` 才放行；差一个字就判「该撤」。"""
    tree = _tree(tmp_path / "t2", ["zzz-lgpl"])
    led = tree / dlg.POLICY_REL
    led.parent.mkdir(parents=True)
    rec = {"zzz-lgpl": [_rec("zzz-lgpl", fields=["GNU Lesser General Public License v3 or later "
                                                 "(LGPLv3+)"])]}

    def write(lic: str, decision: str) -> None:
        led.write_text(json.dumps({"entries": [{"package": "zzz-lgpl", "license": lic,
                                                "decision": decision, "why": "合成裁决"}]},
                                  ensure_ascii=False), encoding="utf-8")

    write("LGPL-3.0-or-later", "accepted")
    rep = dlg.audit(tree, idx=rec, declared_not_installed={})
    assert not rep["violations"], rep["violations"]
    assert rep["buckets"]["adjudicated"] == 1, rep["buckets"]

    write("LGPL-2.1", "accepted")             # 上游换许可证 / 抄错 ⇒ 该撤
    rep2 = dlg.audit(tree, idx=rec, declared_not_installed={})
    assert ("台账该撤", "zzz-lgpl") in {(v["field"], v["doc"]) for v in rep2["violations"]}, \
        rep2["violations"]

    write("LGPL-3.0-or-later", "needs-review")
    rep3 = dlg.audit(tree, idx=rec, declared_not_installed={})
    assert ("依赖许可证未裁定", "zzz-lgpl") in {
        (v["field"], v["doc"]) for v in rep3["violations"]}, rep3["violations"]
    assert rep3["corpus"]["ledger_size"] == 1, rep3["corpus"]


def test_or_branch_is_usable_but_and_pair_is_not(tmp_path: Path) -> None:
    """`A OR B` 任一分支可用即放行；`A AND B` 里有不可用的就要人拍板。

    这是把"许可证集合"与"许可证表达式"分开的唯一反证：拍平之后
    `MIT AND LGPL-2.1` 会因为含 MIT 而变绿——那正是这类门最常见的假绿方向。
    """
    tree = _tree(tmp_path / "t4", ["zzz-dual", "zzz-pair"])
    idx = {"zzz-dual": [_rec("zzz-dual", expr="Apache-2.0 OR BSD-3-Clause")],
           "zzz-pair": [_rec("zzz-pair", expr="MIT AND LGPL-2.1")]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证未裁定", "zzz-pair") in fired, fired
    assert rep["buckets"]["allowed"] == 1, rep["buckets"]
    assert rep["buckets"]["review-required"] == 1, rep["buckets"]


def test_declared_but_uninstalled_needs_a_written_reason(tmp_path: Path) -> None:
    """我们自己声明、这个环境装不上的依赖：没理由就判红（覆盖面缺口要签字）。"""
    tree = _tree(tmp_path / "t5", ["zzz-missing"])
    idx = {"zzz-here": [_rec("zzz-here", expr="MIT")]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    assert ("声明的依赖没查过", "zzz-missing") in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]
    assert dlg.main(["--repo", str(tree)]) == 4, rep["violations"]

    rep2 = dlg.audit(tree, idx=idx, declared_not_installed={"zzz-missing": "合成：不装它的理由"})
    assert not rep2["violations"], rep2["violations"]
    assert rep2["buckets"]["declared-missing"] == 1, rep2["buckets"]


def test_forbidden_family_cannot_be_waived_by_the_ledger(tmp_path: Path) -> None:
    """强 copyleft 不由台账静默吞掉：裁了也要红（两笔：禁用 + 越权放行）。"""
    tree = _tree(tmp_path / "t6", ["zzz-agpl"])
    idx = {"zzz-agpl": [_rec("zzz-agpl", expr="AGPL-3.0-or-later")]}
    led = tree / dlg.POLICY_REL
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps({"entries": [
        {"package": "zzz-agpl", "license": "AGPL-3.0-or-later", "decision": "accepted",
         "why": "想放行"}]}, ensure_ascii=False), encoding="utf-8")
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证禁用", "zzz-agpl") in fired, fired
    assert ("台账越权放行", "zzz-agpl") in fired, fired


def test_premise_missing_pyproject_is_not_zero_risk(tmp_path: Path) -> None:
    """读不到声明面 ⇒ 退 2（前提不成立），不许读成"一个依赖都没有所以零风险"。"""
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert dlg.main(["--repo", str(empty)]) == 2
    rep = dlg.audit(empty)
    assert rep["ok"] is False and any(p.startswith("pyproject_missing") for p in rep["problems"]), \
        rep["problems"]
