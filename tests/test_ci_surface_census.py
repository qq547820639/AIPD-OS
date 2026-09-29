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


# ---- 第 94 片：真实行号 与 「门禁被声明为可失败」 ----

def _wf(tmp: Path, text: str) -> Path:
    rel: str = str(csc.WORKFLOW_REL)          # scripts/ 不在 mypy 的 files 里 ⇒ 落一次注解
    wf = tmp / rel
    wf.parent.mkdir(parents=True)
    wf.write_text(text, encoding="utf-8")
    return wf


def test_every_ci_command_reports_a_line_and_that_line_says_that_command() -> None:
    """真仓库现读：32 条命令**每条**的行号 > 0，且那一行的原文与命令互相对账。

    第 91 片落地时这一格恒 0 ⇒ 判红只能说"哪条命令没人守"，不能指到 `ci.yml:NNN`。
    断的是**关系**（行号处包含这条命令的起始原文），不是钉具体行号——
    命令数与行号都会随 workflow 漂移，关系不漂。
    """
    cmds, probs = csc.ci_commands(ROOT)
    assert not probs, probs
    assert cmds, cmds
    text = (ROOT / csc.WORKFLOW_REL).read_text(encoding="utf-8").splitlines()
    bad = [c for c in cmds if not c["line"] or c["at"] not in text[c["line"] - 1]]
    assert not bad, bad[:3]
    assert all(c["line"] <= len(text) for c in cmds), max(c["line"] for c in cmds)
    rep = csc.audit(ROOT)
    assert rep["corpus"]["ci_commands"] == len(cmds), rep["corpus"]


def test_folded_continuation_and_comment_block_report_the_start_line(tmp_path: Path) -> None:
    """续行折成一条时行号取**起始**行；注释行与空行不占命令但占偏移。

    少了这条，`line` 会指到续行的末尾或跳行——那比 0 更难查，因为它看着像对的。
    """
    wf = _wf(tmp_path, "name: d\njobs:\n  a:\n    steps:\n"
                       "      - name: Lint\n        run: |\n"
                       "          # 注释占一行\n"
                       "          ruff check src \\\n            tests\n\n"
                       "          mypy .\n")
    text = wf.read_text(encoding="utf-8").splitlines()
    rows, probs = csc.ci_commands(tmp_path)
    assert not probs, probs
    by = {r["command"]: r for r in rows}
    assert by["ruff check src tests"]["line"] == 8, by["ruff check src tests"]
    assert by["mypy ."]["line"] == 11, by["mypy ."]
    for cmd, r in by.items():
        assert r["at"] in text[r["line"] - 1], (cmd, r)


def test_a_gate_declared_soft_fires_while_a_hard_gate_does_not(tmp_path: Path) -> None:
    """步骤级 `continue-on-error`、命令级 `--exit-zero` 与 `|| true` 各开一火；硬门不火。

    两极都要在：只测"会火"没法证明它不是恒真，只测"不火"就是第 91 片那条
    "永远 SKIP 的门等于没有门"。
    """
    _wf(tmp_path, "name: s\njobs:\n  a:\n    steps:\n"
                  "      - name: Soft\n        continue-on-error: true\n"
                  "        run: python scripts/whatever.py\n"
                  "      - run: pip-audit -r req.txt --exit-zero\n"
                  "      - run: bash scripts/maybe.sh || true\n"
                  "      - run: ruff check src\n")
    reg = tmp_path / csc.SURFACE_REGISTER_REL
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"entries": [
        {"command": c, "kind": "ci-only", "why": "合成：只在 CI"}
        for c in ("python scripts/whatever.py", "pip-audit -r req.txt --exit-zero",
                  "bash scripts/maybe.sh || true", "ruff check src")]},
        ensure_ascii=False), encoding="utf-8")
    rep = csc.audit(tmp_path)
    fired = {v["written"] for v in rep["violations"] if v["field"] == "CI面被声明为可失败"}
    assert fired == {"python scripts/whatever.py", "pip-audit -r req.txt --exit-zero",
                     "bash scripts/maybe.sh || true"}, fired
    assert rep["buckets"]["soft-declared"] == 3, rep["buckets"]
    # 行号在这一格也要有用：判红能指回文件里的那一行
    for v in rep["violations"]:
        if v["field"] == "CI面被声明为可失败":
            assert v["line"] > 0, v
    assert csc.main(["--repo", str(tmp_path)]) == 4, rep["violations"]


def test_soft_face_reads_zero_on_the_real_repo_and_the_zero_is_a_real_zero() -> None:
    """真仓库这一格现在是 0——必须证明"0"是**真的没有**，不是判据读不到。

    做法：拿量具自己那条正则去扫 workflow 原文，与 buckets 里的计数对一次。
    两数同为零 ⇒ 这一格今天没有活原告；若正则坏了（读不到任何写法），
    扫描侧会数出非零而门里是 0，这条用例当场翻红。
    """
    cmds, probs = csc.ci_commands(ROOT)
    assert not probs, probs
    rep = csc.audit(ROOT)
    assert rep["buckets"]["soft-declared"] == 0, rep["buckets"]
    assert "CI面被声明为可失败" not in {v["field"] for v in rep["violations"]}
    raw = (ROOT / csc.WORKFLOW_REL).read_text(encoding="utf-8")
    import re
    hits = re.findall(r"\|\|\s*(?:true|:)\s*$|\bset\s+\+e\b|--exit-zero\b|"
                      r"--warn-only\b|--ignore-errors\b", raw, re.M)
    coe = len(re.findall(r"continue-on-error", raw))
    assert len(hits) == 0 and coe == 0, (len(hits), coe)


def test_a_step_whose_line_cannot_be_located_is_a_named_diagnostic_not_a_silent_zero(
        tmp_path: Path) -> None:
    """定不到行号时**必须点名**（`run_mark_unmatched`），不许静默记 0。

    形状：折叠标量 `>-` —— 解析时两行并成一条 `ruff check src`，文件里根本没有这样一行，
    包含式匹配必然失败（取证文档 §四.2 那条边界就是这么被兜住的：不是给个错行号，
    而是点名"这一条定不到"）。这一格今天在本仓 ci.yml 里 0 次；把它静默化，
    `line` 就会重新变成恒 0 而看上去一切正常。
    （第一版我用带引号的多空格标量来造这一格，结果**匹配成功**——引号标量的值
    与文件行仍逐字包含，于是那条用例读不到"定不到"这一档。换成折叠标量才真造得出来。）
    """
    _wf(tmp_path, "name: q\njobs:\n  a:\n    steps:\n"
                  "      - run: >-\n          ruff\n          check src\n")
    rows, probs = csc.ci_commands(tmp_path)
    assert not rows or rows[0]["line"] == 0, rows
    assert any(x.startswith("run_mark_unmatched") for x in probs), probs
    rep = csc.audit(tmp_path)
    assert rep["problems"], rep
    assert csc.main(["--repo", str(tmp_path)]) == 2, rep["problems"]


def test_emit_register_writes_line_pins_and_keeps_hand_filled_fields(
        tmp_path: Path) -> None:
    """`--emit-register` 这一整条路之前**没有任何常驻读者**（第 94 片电池 W12 就是这么活下来的）。

    断三件：草案里每条都带**行号 + 那一行的原文 + 是否软门**，且原文确实落在那一行；
    手工填过的 kind/consumers/why 在二次 emit 时必须保住；而一次性的 `line_at_emit_time`
    要被剥掉——把某轮的行号钉成永久断言，下一轮改 workflow 就会误红。
    """
    wf = _wf(tmp_path, "name: e\njobs:\n  a:\n    steps:\n"
                       "      - run: ruff check src\n"
                       "      - run: bash scripts/soft.sh || true\n")
    reg = tmp_path / csc.SURFACE_REGISTER_REL
    assert csc.main(["--repo", str(tmp_path), "--emit-register"]) == 4
    ents = {e["command"]: e for e in json.loads(reg.read_text(encoding="utf-8"))["entries"]}
    assert set(ents) == {"ruff check src", "bash scripts/soft.sh || true"}, ents
    assert all(e["kind"] == "TODO" for e in ents.values()), ents
    wf_lines = wf.read_text(encoding="utf-8").splitlines()
    for cmd, e in ents.items():
        assert e["line_at_emit_time"] > 0, (cmd, e)
        txt = e["line_text_at_emit_time"]
        # 用等式而不是"包含"：`"" in 任何串` 恒真，包含式断言会把**空字段**判成通过
        # （第一版就是这么写的，于是电池 W12「emit 不带原文字段」当场存活）。
        assert txt and txt == wf_lines[e["line_at_emit_time"] - 1].split("run:", 1)[1].strip(), \
            (cmd, e)
    assert ents["bash scripts/soft.sh || true"]["soft_declared_at_emit_time"] is True, ents
    assert ents["ruff check src"]["soft_declared_at_emit_time"] is False, ents

    reg.write_text(json.dumps({"entries": [
        {"command": "ruff check src", "kind": "consumed",
         "consumers": ["tests/test_ci_face_gates.py"], "why": "本地收口链跑同一面",
         "line_at_emit_time": 99, "job_at_emit_time": "过期的一轮"}]},
        ensure_ascii=False), encoding="utf-8")
    assert csc.main(["--repo", str(tmp_path), "--emit-register"]) == 4
    doc2 = json.loads(reg.read_text(encoding="utf-8"))["entries"]
    keep = [e for e in doc2 if e["command"] == "ruff check src"][0]
    assert keep["kind"] == "consumed", keep
    assert keep["consumers"] == ["tests/test_ci_face_gates.py"], keep
    assert keep["why"] == "本地收口链跑同一面", keep
    assert "line_at_emit_time" not in keep and "job_at_emit_time" not in keep, keep
    soft2 = [e for e in doc2 if e["command"] == "bash scripts/soft.sh || true"][0]
    assert soft2["kind"] == "TODO", soft2          # 没登记的那条仍然待填 ⇒ 退 4 不是退 0
