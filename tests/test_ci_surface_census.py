"""`scripts/ci_surface_census.py` 的常驻牙（F-CI-SURFACE 第 91 片）。

四组：
① 量具必须被真的 spawn（`--self-test` 走子进程，孤儿门禁与没有门禁看不出差别）；
② 真仓库上现状面干净，且**三张分母都非空**（空读数不算绿）；
③ 注入必须开火 / 合规侧不开火的两极对照，形状与面 ⑤ 的死链登记册同族；
④ 一档"结构性免跑"不许变成后门：理由被清空 ⇒ 立刻判红。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import ci_surface_census as csc  # noqa: E402

TOOL = ROOT / "scripts" / "ci_surface_census.py"


def _spawn(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)


def test_instrument_self_test_is_actually_spawned_and_green() -> None:
    proc = _spawn("--self-test")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条合成读数全部对上" in proc.stdout, proc.stdout


def test_real_repo_face_is_live_and_every_command_has_a_home() -> None:
    rep = csc.audit(ROOT)
    c = rep["corpus"]
    assert not rep["problems"], rep["problems"]
    # 分母下界：CI 面与本表都不许被静默清空（清空后"零违规"是假的）
    assert c["ci_commands"] >= 30, c
    assert c["jobs"] >= 12, c
    assert c["register_size"] >= 30, c
    assert rep["buckets"]["unwatched"] == 0, rep["violations"]
    assert rep["buckets"]["consumed"] >= 15, rep["buckets"]
    assert rep["buckets"]["ci-only"] >= 10, rep["buckets"]
    assert not rep["violations"], rep["violations"]
    assert _spawn("--repo", ".").returncode == 0


def test_commands_are_read_from_the_workflow_not_from_a_copy() -> None:
    """册子里的每条命令键都必须**逐字**出现在 ci.yml 里。

    这条是"权威面只有一个"的反证：一旦有人把命令抄进册子而不是由 workflow 生成，
    CI 改名时本地会同时得到「无人守」和「该撤」两笔红——而这条用例先一步告诉读者
    那些键是从哪儿来的（`docs/audit/s91/build_ci_surface_register.py` 现读现写）。
    """
    raw = (ROOT / csc.WORKFLOW_REL).read_text(encoding="utf-8")
    reg = json.loads((ROOT / csc.SURFACE_REGISTER_REL).read_text(encoding="utf-8"))
    cmds = {e["command"] for e in reg["entries"]}
    assert cmds, "消费表是空的"
    # 与量具同一套归一化：CI 里的 `\` 续行折成一条命令，比较前先去掉它
    flat = " ".join(raw.replace("\\\n", " ").split())
    for cmd in sorted(cmds):
        assert " ".join(cmd.split()) in flat, f"册子里这条不在 CI 里：{cmd}"


def test_new_ci_command_without_entry_fires_and_reentry_clears(tmp_path: Path) -> None:
    """注入 → 开火 → 补登记 → 转绿 → 撤登记 → 再开火（同一棵树的四步）。

    只测"多一条会红"不够：登记面最常见的退化是**撤不掉**，
    所以第四步步把命令从 CI 里拿掉，要求换档成「消费表该撤」而不是静默通过。
    """
    wf = tmp_path / csc.WORKFLOW_REL
    wf.parent.mkdir(parents=True)
    wf.write_text("name: CI\njobs:\n  lint:\n    steps:\n"
                  "      - name: Run ruff\n        run: ruff check src\n", encoding="utf-8")
    reg = tmp_path / csc.SURFACE_REGISTER_REL
    reg.parent.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_face.py").write_text(
        "def test_ruff():\n    assert True\n", encoding="utf-8")
    reg.write_text(json.dumps({"entries": [
        {"command": "ruff check src", "kind": "consumed",
         "consumers": ["tests/test_face.py"]}]}, ensure_ascii=False), encoding="utf-8")
    assert not csc.audit(tmp_path)["violations"], csc.audit(tmp_path)["violations"]

    wf.write_text("name: CI\njobs:\n  lint:\n    steps:\n"
                  "      - name: Run ruff\n        run: ruff check src\n"
                  "      - name: New\n        run: python scripts/zzz_new_gate.py\n",
                  encoding="utf-8")
    rep = csc.audit(tmp_path)
    fired = {(v["field"], v["written"]) for v in rep["violations"]}
    assert ("CI面无人守", "python scripts/zzz_new_gate.py") in fired, fired
    assert csc.main(["--repo", str(tmp_path)]) == 4, fired

    data = json.loads(reg.read_text(encoding="utf-8"))
    data["entries"].append({"command": "python scripts/zzz_new_gate.py", "kind": "consumed",
                            "consumers": ["tests/test_face.py"]})
    reg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert not csc.audit(tmp_path)["violations"], csc.audit(tmp_path)["violations"]

    wf.write_text("name: CI\njobs:\n  lint:\n    steps:\n"
                  "      - name: Run ruff\n        run: ruff check src\n", encoding="utf-8")
    rep2 = csc.audit(tmp_path)
    assert ("消费表该撤", "python scripts/zzz_new_gate.py") in {
        (v["field"], v["written"]) for v in rep2["violations"]}, rep2["violations"]


def test_structural_exemption_without_a_reason_is_red(tmp_path: Path) -> None:
    """免跑那一档必须带理由：把 `why` 清空 ⇒ 判红。

    没有这条，`kind: ci-only` 就是一张随时可以自己盖的免检条——
    而本尺抓的正是"某道门悄悄没人看"，它自己不能是那个洞。
    """
    wf = tmp_path / csc.WORKFLOW_REL
    wf.parent.mkdir(parents=True)
    wf.write_text("name: CI\njobs:\n  scan:\n    steps:\n"
                  "      - name: Lic\n        run: pip-licenses\n", encoding="utf-8")
    reg = tmp_path / csc.SURFACE_REGISTER_REL
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"entries": [
        {"command": "pip-licenses", "kind": "ci-only", "consumers": [], "why": ""}]},
        ensure_ascii=False), encoding="utf-8")
    rep = csc.audit(tmp_path)
    assert ("CI面免跑没理由", "pip-licenses") in {
        (v["field"], v["written"]) for v in rep["violations"]}, rep["violations"]
    assert rep["buckets"]["ci-only"] == 0, rep["buckets"]
    data = json.loads(reg.read_text(encoding="utf-8"))
    data["entries"][0]["why"] = "本机未装，且那条命令没有可失败的断言"
    reg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    rep2 = csc.audit(tmp_path)
    assert not rep2["violations"] and rep2["buckets"]["ci-only"] == 1, rep2


def test_missing_workflow_reads_as_a_premise_not_as_green(tmp_path: Path) -> None:
    empty = tmp_path / "nowf"
    empty.mkdir()
    assert csc.main(["--repo", str(empty)]) == 2
    rep = csc.audit(empty)
    assert any(p.startswith("workflow_unreadable") for p in rep["problems"]), rep["problems"]
