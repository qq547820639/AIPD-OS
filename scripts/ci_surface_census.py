#!/usr/bin/env python3
"""CI 上跑的门禁，本地收口链到底消费不消费？逐条对账（F-CI-SURFACE 第 91 片）。

起因是第 90 片顺手清的那条 E501：`ruff check src tests state_service` 是 CI 的 `lint` job
的第一条命令，而本仓的收口链（全量 pytest + 发布门 + 收尾验签）**一道都不读它**——
于是那一行从第 84 片活到第 90 片，六轮常驻全绿。同一格里第二条命令 `mypy` 更糟：
`ci.yml:130` 写着「本地硬基线（ruff 0 / mypy 0）」，而第 91 片现读是 **24 个错误 / 20 个文件**
⇒ 那句话是假叙述，且没有任何尺子看过它。

判据形状（与面 ⑤ 的死链登记册同族，只是被审的对象换成了 workflow）：

  consumed     —— 这条命令在《消费表》里挂着，且挂的消费方**真的存在**（测试文件里真有
                  `def test_`）⇒ 合规；
  unwatched    —— CI 里跑着、消费表里没有 ⇒ **判红**（今天那两条就是这么漏的）；
  ci-only      —— 结构性只能在 CI 跑（要容器、要网络安装、要多版本矩阵），登记时**必须写理由**
                  ⇒ 只报不红（看不见≠违规，但必须留下"为什么看不见"）；
  stale-entry  —— 消费表里挂着而 CI 已不再跑 ⇒ **判红**（豁免不许只涨不消）；
  bad-consumer —— 挂的消费方文件不在，或那文件一个 `def test_` 都没有 ⇒ **判红**（空头委托）。

分母**由本工具自报**（`corpus.ci_commands` / `buckets`），不在任何文档里抄数。

选型（AGENTS.md 第三节，四段见 `docs/audit/CI_SURFACE_F-CI-SURFACE_2026-09-28.md` §二）：
候选是 nektos/act（把 workflow 真在本地跑一遍，MIT，依赖 Docker API 与镜像拉取）、
pre-commit（把命令挂成本地钩子），以及**自研一把结构对账尺**。择一：自研——
前两者的执行面都不在"认证链读不读"这个问题上：act 要能在本机起容器并联网装包，
而本仓的收口判据跑在一台不保证有 Docker 的宿主上；pre-commit 是否装钩子按克隆而变，
"没装"与"装了且绿"在读数上完全同形。这里**借的是 act 的思路**：以 workflow 为唯一权威面，
本地不去复制一份命令清单（复制一份就会漂一次）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

WORKFLOW_REL = ".github/workflows/ci.yml"
SURFACE_REGISTER_REL = "docs/audit/CI_SURFACE_REGISTER.json"

def _norm(cmd: str) -> str:
    """命令规范化：连续空白折成一个空格、去首尾，比较用这一份。

    `\` 续行的折叠**不在这里**做，而在 `_split_shell()`——那里逐行读块标量，
    交给本函数的串里永远没有换行。第 91 片这里原本还带一次 `replace("\\\\n", " ")`，
    是条**永不达到的路径**：电池的 A6 臂撤掉它时读数为零变化，才把这件事暴露出来。
    """
    return re.sub(r"\s+", " ", cmd).strip()


def ci_commands(root: Path, workflow_rel: str = WORKFLOW_REL) -> tuple[list[dict], list[str]]:
    r"""从 workflow 里抽出每条**会被单独执行的 shell 命令**。

    权威面是 workflow 文件本身（这是选型里从 act 借来的那一点：本地不复制一份命令清单，
    复制一份就会漂一次）。粒度取"一行一条"，因为 GitHub 就是把 block 标量的每一行
    当一条 shell 命令跑（`set -e` 之下任一非零退码即红）⇒ 一条没被登记的
    `pip install` 与一条没被登记的 `mypy` 在这件事上地位相同。
    `\` 续行折成一条。按命令文本去重（同一条命令在 11 个 job 里跑是一格账），
    出现次数留在 `jobs` 列表里，不折成多条。
    """
    p = root / workflow_rel
    if not p.is_file():
        return [], [f"workflow_unreadable: {workflow_rel} 不在树里"]
    try:
        import yaml
    except ImportError as exc:
        return [], [f"yaml_missing: 解析 workflow 需要 pyyaml（本仓 `full` 档已声明）：{exc}"]
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [], [f"workflow_unreadable: {workflow_rel} 读不出/解析失败：{exc}"]
    jobs = (doc or {}).get("jobs") or {}
    by_cmd: dict[str, dict] = {}
    for job, spec in sorted(jobs.items()):
        for step in (spec or {}).get("steps") or []:
            if not isinstance(step, dict) or "run" not in step:
                continue
            raw = str(step["run"])
            line0 = raw.split("\n", 1)[0].strip()
            for chunk in _split_shell(raw):
                ent = by_cmd.setdefault(chunk, {"command": chunk, "jobs": [],
                                                "step": str(step.get("name") or ""),
                                                "first_line": line0})
                if job not in ent["jobs"]:
                    ent["jobs"].append(job)
    out = [{"job": ",".join(v["jobs"]), "step": v["step"], "line": 0,
            "command": k, "job_count": len(v["jobs"])} for k, v in by_cmd.items()]
    if not out:
        return [], ["workflow_empty: 一条 run 命令都没读到（解析面或文件变了）"]
    return out, []


def _split_shell(raw: str) -> list[str]:
    r"""block 标量 ⇒ 每行一条命令；`\` 续行折回上一条；空行与纯注释行丢掉。"""
    out: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if out and out[-1].endswith("\\"):
            out[-1] = _norm(out[-1][:-1] + " " + s)
        else:
            out.append(_norm(s))
    return [o for o in out if o and o != "|"]



def load_surface_register(root: Path, rel: str = SURFACE_REGISTER_REL
                          ) -> tuple[dict[str, dict], list[str]]:
    """《消费表》：命令 → {consumers, kind, why}。不在树里读成空册（所有命令判「无人守」）。"""
    p = root / rel
    if not p.is_file():
        return {}, []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"register_unreadable: {rel} 解析失败：{exc}"]
    entries: dict[str, dict] = {}
    problems: list[str] = []
    for e in raw.get("entries", []):
        cmd = str(e.get("command") or "")
        if not cmd:
            problems.append(f"register_entry_invalid: {rel} 有条目没有 command")
            continue
        entries[_norm(cmd)] = {"consumers": list(e.get("consumers") or []),
                               "kind": str(e.get("kind") or ""),
                               "why": str(e.get("why") or "")}
    return entries, problems


def consumer_alive(root: Path, rel: str) -> tuple[bool, str]:
    """消费方存在吗？测试文件还要求它**真有用例**（挂一个空文件＝空头委托）。"""
    p = root / rel
    if not p.is_file():
        return False, "文件不在树里"
    if p.suffix == ".py" and rel.startswith("tests/"):
        # 只有 `tests/` 那一档要求"真有用例"。消费方也可以是量具或门禁脚本
        # （如 `scripts/production_release_gate.py` 自己调 audit_repo）——
        # 那些文件里没有 `def test_` 是应当的，拿用例数去卡它们会把合规委托判成空头。
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:            # pragma: no cover
            return False, f"读不出：{exc}"
        if not re.search(r"^def test_|^    def test_", text, re.M):
            return False, "文件在但一个 `def test_` 都没有"
    return True, ""


def audit(root: Path) -> dict[str, Any]:
    cmds, problems = ci_commands(root)
    reg, rproblems = load_surface_register(root)
    problems += rproblems
    violations: list[dict] = []
    buckets = {"consumed": 0, "unwatched": 0, "ci-only": 0}
    seen: set[str] = set()
    for c in cmds:
        key = c["command"]
        seen.add(key)
        ent = reg.get(key)
        if ent is None:
            buckets["unwatched"] += 1
            violations.append({
                "field": "CI面无人守", "doc": WORKFLOW_REL, "line": c["line"],
                "written": key,
                "detail": f"CI 的 {c['job']!r} job 在跑这条命令，而《消费表》里没有它："
                          "本地收口链（全量 + 门 + 验签）一道都不读它 ⇒ 这条门可以长期红"
                          "而所有常驻用例照绿（第 90 片那条 E501 就是这么活了六轮）"})
            continue
        if ent["kind"] == "ci-only":
            if not ent["why"]:
                violations.append({
                    "field": "CI面免跑没理由", "doc": SURFACE_REGISTER_REL, "line": 0,
                    "written": key,
                    "detail": "structural 档位必须写明为什么只能留在 CI（缺什么、卡在哪一环），"
                              "没有理由的免跑就是把自己关掉的门"})
            else:
                buckets["ci-only"] += 1
            continue
        if ent["kind"] != "consumed":
            violations.append({
                "field": "CI面档位未知", "doc": SURFACE_REGISTER_REL, "line": 0,
                "written": key, "detail": f"kind={ent['kind']!r} 不是已定义的档位"})
            continue
        dead = [(r, why) for r in ent["consumers"]
                for ok, why in [consumer_alive(root, r)] if not ok]
        if not ent["consumers"] or dead:
            buckets["unwatched"] += 1
            what = "；".join(f"{r}：{w}" for r, w in dead) or "没挂任何消费方"
            violations.append({
                "field": "CI面空头委托", "doc": SURFACE_REGISTER_REL, "line": 0,
                "written": key,
                "detail": f"登记说这条命令由 {ent['consumers'] or '（空）'} 守着，但"
                          f"{what} ⇒ 受托方没在做这件事，等价于无人守"})
            continue
        buckets[ent["kind"]] += 1
    for key, ent in sorted(reg.items()):
        if key not in seen:
            violations.append({
                "field": "消费表该撤", "doc": SURFACE_REGISTER_REL, "line": 0,
                "written": key,
                "detail": f"登记里挂着这条命令（kind={ent['kind']!r}），而 CI 已经不再跑它"
                          " ⇒ 撤登记，否则册子会攒出一批不做事的条目"})
    if not cmds and not any(p.startswith("workflow_") for p in problems):
        problems.append("workflow_empty: 一条 run 命令都没读到")
    ok = not violations and not problems
    return {"ok": ok, "buckets": buckets,
            "corpus": {"ci_commands": len(cmds), "register_size": len(reg),
                       "jobs": len({c["job"] for c in cmds})},
            "commands": cmds, "violations": violations, "problems": problems}


def render(rep: dict[str, Any]) -> str:
    b = rep["buckets"]
    lines = ["=" * 60, "CI 门禁面 ↔ 本地收口链对账", "=" * 60]
    c = rep["corpus"]
    lines.append(f"CI 命令 {c['ci_commands']} 条（{c['jobs']} 个 job），"
                 f"消费表 {c['register_size']} 条")
    lines.append(f"归属：已接住 {b['consumed']} / 免跑有理由 {b['ci-only']} / "
                 f"无人守 {b['unwatched']}")
    for v in rep["violations"]:
        lines.append(f"  ✗ {v['field']} {v['doc']}:{v['line']} `{v['written']}` ⇒ {v['detail']}")
    for p in rep["problems"]:
        lines.append(f"  ! 前提不成立：{p}")
    if rep["ok"]:
        lines.append("现状面缺陷 0 条：CI 每条门禁都在本地有归宿")
    return "\n".join(lines)


def _mark(marks: list, text: str) -> None:
    print(f"✓立住 {text}")
    marks.append(text)


def _self_test(tmp: Path) -> int:
    marks: list[str] = []
    wf = tmp / WORKFLOW_REL
    wf.parent.mkdir(parents=True)
    wf.write_text(
        "name: CI\njobs:\n"
        "  lint:\n    steps:\n"
        "      - name: Run ruff\n        run: ruff check src tests\n"
        "      - name: Run mypy\n        run: mypy\n"
        "  secret-scan:\n    steps:\n"
        "      - name: Run gitleaks\n"
        "        run: gitleaks detect --source . --redact\n"
        "  newjob:\n    steps:\n"
        "      - name: Something new\n        run: python scripts/zzz_fresh_gate.py\n"
        "      - name: Absent consumer\n"
        "        run: python scripts/zzz_absent_face.py\n",
        encoding="utf-8")
    (tmp / "tests").mkdir()
    (tmp / "tests" / "test_ci_face_gates.py").write_text(
        "def test_ruff_is_clean():\n    assert True\n", encoding="utf-8")
    (tmp / "tests" / "test_empty_face.py").write_text("X = 1\n", encoding="utf-8")
    reg = tmp / SURFACE_REGISTER_REL
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"entries": [
        {"command": "ruff check src tests", "kind": "consumed",
         "consumers": ["tests/test_ci_face_gates.py"]},
        {"command": "mypy", "kind": "consumed",
         "consumers": ["tests/test_empty_face.py"]},
        {"command": "gitleaks detect --source . --redact", "kind": "ci-only",
         "consumers": [], "why": "要下载 gitleaks 二进制并按提交历史扫描，属 CI 侧执行面"},
        {"command": "python scripts/zzz_gone_step.py", "kind": "consumed",
         "consumers": ["tests/test_ci_face_gates.py"]},
        # 消费方**文件不在树里**：与"文件在但没用例"是同一格判据的两极，两极都要各自钉，
        # 否则把存在性检查摘掉时读数不变（第 91 片电池 A8 臂实测就是这个存活形状）。
        {"command": "python scripts/zzz_absent_face.py", "kind": "consumed",
         "consumers": ["tests/test_zzz_absent.py"]},
    ]}, ensure_ascii=False), encoding="utf-8")
    rep = audit(tmp)
    got = {(v["field"], v["written"]) for v in rep["violations"]}
    assert ("CI面空头委托", "mypy") in got, got
    vac = {v["written"]: v["detail"] for v in rep["violations"]
           if v["field"] == "CI面空头委托"}
    assert set(vac) == {"mypy", "python scripts/zzz_absent_face.py"}, rep["violations"]
    assert "一个 `def test_` 都没有" in vac["mypy"], vac
    assert "文件不在树里" in vac["python scripts/zzz_absent_face.py"], vac
    assert ("CI面无人守", "python scripts/zzz_fresh_gate.py") in got, got
    assert ("消费表该撤", "python scripts/zzz_gone_step.py") in got, got
    assert ("CI面无人守", "gitleaks detect --source . --redact") not in got, got
    assert rep["buckets"]["consumed"] == 1 and rep["buckets"]["ci-only"] == 1, rep["buckets"]
    assert rep["corpus"]["ci_commands"] == 5 and rep["corpus"]["jobs"] == 3, rep["corpus"]
    assert rep["corpus"]["register_size"] == 5, rep["corpus"]
    assert main(["--repo", str(tmp)]) == 4, rep["violations"]
    _mark(marks, "五格各开火一次：已接住（ruff）、受托方空转（测试文件在但没有一条用例）、"
                 "受托方文件压根不在树里（同一格的两极，理由文本各不同）、"
                 "CI 里新出现的命令没人登记、登记里的命令 CI 已不再跑；"
                 "免跑那一档**只在写了理由时**才不红，且分母由工具自报（5 条命令 / 3 个 job）")
    # 极性对照：补上真消费方与理由 ⇒ 同一棵树转绿；把理由抹掉 ⇒ 又红
    (tmp / "tests" / "test_empty_face.py").write_text(
        "def test_mypy_is_clean():\n    assert True\n", encoding="utf-8")
    (tmp / "tests" / "test_zzz_absent.py").write_text(
        "def test_absent_face_is_clean():\n    assert True\n", encoding="utf-8")
    data = json.loads(reg.read_text(encoding="utf-8"))
    data["entries"] = [e for e in data["entries"]
                       if e["command"] != "python scripts/zzz_gone_step.py"]
    data["entries"].append({"command": "python scripts/zzz_fresh_gate.py",
                            "kind": "consumed",
                            "consumers": ["tests/test_ci_face_gates.py"]})
    reg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    rep2 = audit(tmp)
    assert not rep2["violations"], rep2["violations"]
    assert main(["--repo", str(tmp)]) == 0, rep2["violations"]
    _mark(marks, "合规侧同批存在：把消费方补成**真有用例的文件**、新命令补登记、"
                 "撤掉不再跑的那条 ⇒ 同一棵树由 4 转 0")
    for e in data["entries"]:
        if e["command"].startswith("gitleaks"):
            e["why"] = ""
    reg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    rep3 = audit(tmp)
    assert ("CI面免跑没理由", "gitleaks detect --source . --redact") in {
        (v["field"], v["written"]) for v in rep3["violations"]}, rep3["violations"]
    _mark(marks, "结构性免跑必须带理由：把理由清空 ⇒ 立刻判红"
                 "（否则\"看不见\"会变成一条随时可以自我豁免的后门）")
    # 前提塌：没有 workflow 文件时不许读成"零违规"
    empty = tmp / "nowf"
    (empty / "tests").mkdir(parents=True)
    assert main(["--repo", str(empty)]) == 2, "读不到 CI 面必须判前提不成立"
    _mark(marks, "没有 workflow 文件＝前提不成立（退 2），不是\"一条命令都没有所以全绿\"")
    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CI 门禁面与本地收口链的对账")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--emit-register", action="store_true",
                    help="把 CI 现读的每条命令写成一份待填的消费表草案")
    args = ap.parse_args(argv)
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    root = Path(args.repo).resolve()
    if args.emit_register:
        cmds, problems = ci_commands(root)
        out = root / SURFACE_REGISTER_REL
        if problems:
            print(f"拒写草案：{problems}")
            return 2
        entries = [{"command": c["command"], "kind": "TODO", "consumers": [],
                    "why": "", "job_at_emit_time": c["job"], "line_at_emit_time": c["line"]}
                   for c in cmds]
        if out.is_file():
            old = {e["command"]: e for e in
                   json.loads(out.read_text(encoding="utf-8")).get("entries", [])}
            for e in entries:
                o = old.get(e["command"])
                if o and o.get("kind") in ("consumed", "ci-only"):
                    e.update({k: o[k] for k in ("kind", "consumers", "why") if k in o})
                    e.pop("job_at_emit_time", None)
                    e.pop("line_at_emit_time", None)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        todo = sum(1 for e in entries if e["kind"] == "TODO")
        print(f"草案已写 {out.relative_to(root)}：{len(entries)} 条，其中待填 kind 的 {todo} 条")
        return 4 if todo else 0
    rep = audit(root)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(render(rep))
    if rep["problems"]:
        return 2
    return 0 if rep["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
