"""收尾验签量具的常驻牙（F-CLOSEOUT-VERIFY 第 64 片）。

这台机器管三件事：**报告是不是绑着现在这份证据**、**汇总数是不是名单自己数出来的**、
**名单与树上那份 def 是不是同一批**。第 62/63 片每轮手写的验签脚本因为落在 `/tmp`
被宿主重启清掉过一整份，下一轮从提交摘要重推配方，代价是两次整套件重跑（锚点传成 HEAD
被判 STALE 一次、PATH 缺 `.venv/bin` 假红一次）。提为常驻件之后，那些坑由这里的用例
长期按住，而不是靠下一次的记忆。

用例分四组：
① 量具被真的 spawn（`--self-test` 17 条合成读数）——孤儿门禁与没有门禁看不出差别；
② 真语料上的"必须不开火"：报告与已提交树之间唯一的名单差额，必须与工作区的未提交
   改动**逐文件相等**（本轮正在写的测试文件当然没被测过；但已提交的用例一条不许缺）；
③ 真语料上的"必须开火"：把锚点换成 HEAD（第 62 片真犯过的错）只点亮
   `pinned_source_binding`；从报告里整文件抽掉一条常驻用例（汇总数与证据同口径改小，
   使 C2 不被牵连）只点亮 `roster_covers_tree`；
④ 夹具侧前提：替身 nodeid 必须真的还长在 `tests/test_packaging.py` 上，否则"测的就是
   这棵树"这句话挂在一条已被删掉的用例上，永远开不了火。

一处形状值得记：`--tests-dir` 比的是**工作树**。收尾配方在 detached 干净检出里取证，
那里 C4 与 C7 都该全绿；在开发中的工作树里，C7 判红、C4 只许报未提交的那几个文件。
所以 ② 组用"两个独立算出来的集合相等"来断言，而不是"差额为空"——后者在这轮必红，
写成"允许任何差额"就又变回恒真。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import closeout_verifier as cov  # noqa: E402

TOOL = ROOT / "scripts" / "closeout_verifier.py"
REPORT = ROOT / "docs" / "audit" / "pytest-report-v5.6.0.json"
PROV = ROOT / "PROVENANCE.json"

ALL_CHECKS = {
    "report_bound_to_provenance", "counts_counted_from_roster", "terminal_clean",
    "roster_covers_tree", "pinned_source_binding", "content_parity_measured",
    "worktree_clean", "plaintiffs_measured", "size_ratchet",
}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _report_files(rep: dict) -> set[str]:
    return {t["nodeid"].split("::")[0] for t in rep["tests"]}


def _uncommitted_test_files() -> set[str]:
    """`git status --porcelain` 里那些还带着 pytest 命名的路径（未跟踪或已改未提交）。"""
    out = set()
    for line in _git("status", "--porcelain").splitlines():
        path = line[3:].strip().strip('"')
        name = Path(path).name
        if path.startswith("tests/") and (name.startswith("test_") or name.endswith("_test.py")):
            out.add(path)
    return out


@pytest.fixture(scope="module")
def pinned() -> str:
    """发布锚点：tag 指向的提交。约定不许 re-anchor 到 HEAD，所以它与 HEAD 不同。"""
    sha = _git("rev-parse", "v5.6.0^{commit}")
    assert len(sha) == 40, sha
    return sha


@pytest.fixture(scope="module")
def baseline(pinned: str) -> dict:
    rep = cov.audit(REPORT, ROOT, PROV, pinned, ROOT / "tests", [],
                    list(cov.PARITY_TESTS), 0)
    assert rep["problems"] == [], rep["problems"]
    return rep


def _clean_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, str]:
    """一座干净的仓库 + 树外的证据目录（对照组的 C7 不该被自己的夹具弄脏）。"""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests/test_one.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    sha = cov._git_init(repo, "fixture")
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    report = cov._pristine_report(evidence, ["tests/test_one.py::test_x"], sha)
    prov = evidence / "PROVENANCE.json"
    cov._bind_provenance(prov, report)
    return repo, evidence, report, prov, sha


def test_instrument_self_test_is_actually_run_and_green() -> None:
    proc = subprocess.run([sys.executable, str(TOOL), "--self-test"],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert "条合成读数全部对上" in proc.stdout, proc.stdout
    marks = proc.stdout.count("[OK]")
    assert marks >= 17, f"--self-test 的臂从 17 条缩水成 {marks} 条：注入没跑满就别谈判据"


def test_check_names_are_the_documented_nine(baseline: dict) -> None:
    """判据名字是文档与 CHANGELOG 引用的面；改名必须在这里一起翻。"""
    names = set(baseline["checks"])
    assert names >= ALL_CHECKS, sorted(ALL_CHECKS - names)
    assert names <= ALL_CHECKS, sorted(names - ALL_CHECKS)


def test_real_report_matches_the_committed_tree(baseline: dict, pinned: str) -> None:
    fired = {v["check"] for v in baseline["violations"]}
    assert fired <= {"worktree_clean", "roster_covers_tree"}, baseline["violations"]
    r = baseline["readings"]
    assert r["report_entries"] >= 2000 and r["tree_files"] >= 200, r
    assert r["report_entries"] > r["tree_defs"], f"参数化条目没进名单：{r}"
    assert r["pinned_commit"] == pinned and r["worktree_head"] != pinned, r
    assert baseline["checks"]["content_parity_measured"]["ok"] is True
    assert baseline["checks"]["counts_counted_from_roster"]["ok"] is True


def test_the_only_roster_gap_is_uncommitted_work(baseline: dict) -> None:
    """两个独立算出来的集合必须相等：名单里缺的测试文件 == 工作区未提交的测试文件。

    写成"差额为空"在这一轮必红；写成"差额随便"就又是恒真。等号两边都自己算，
    任何一侧多算/漏算都会翻。
    """
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    measured = _report_files(data)
    tree = set(cov.tree_roster(ROOT / "tests")[0])
    never_ran = {f for f in tree if f not in measured}
    uncommitted = _uncommitted_test_files()
    assert never_ran == uncommitted, (sorted(never_ran), sorted(uncommitted))
    assert measured <= tree, sorted(measured - tree)


def test_pinning_to_head_instead_of_the_tag_fires_only_that_check(pinned: str) -> None:
    """第 62 片的原件错误：锚点传成 HEAD。真分母上必须只多点亮 `pinned_source_binding`。"""
    head = _git("rev-parse", "HEAD")
    assert head != pinned, "夹具前提：锚点不许已经漂到 HEAD"
    rep = cov.audit(REPORT, ROOT, PROV, head, ROOT / "tests", [], list(cov.PARITY_TESTS), 0)
    fired = {v["check"] for v in rep["violations"]}
    assert fired - {"worktree_clean", "roster_covers_tree"} == {"pinned_source_binding"}, fired
    assert "给定锚点" in rep["checks"]["pinned_source_binding"]["detail"]


def test_dropping_a_whole_resident_file_fires_only_the_roster(tmp_path: Path,
                                                              pinned: str) -> None:
    """只跑了一个子集：整文件从报告里抽掉，并把汇总数与证据同口径改小——
    这时名单↔树那一格该开火，而 C2（现数 vs 两处副本）必须**不**被牵连。
    """
    victim = "tests/test_truth_history.py"
    src = json.loads(REPORT.read_text(encoding="utf-8"))
    kept = [t for t in src["tests"] if not t["nodeid"].startswith(victim + "::")]
    assert len(kept) < len(src["tests"]), f"夹具前提：{victim} 必须在报告里"
    src["tests"] = kept
    hist: dict[str, int] = {}
    for t in kept:
        hist[t["outcome"]] = hist.get(t["outcome"], 0) + 1
    src["summary"] = {"passed": hist.get("passed", 0), "total": len(kept),
                      "collected": len(kept)}
    if hist.get("skipped"):
        src["summary"]["skipped"] = hist["skipped"]
    if hist.get("failed"):
        src["summary"]["failed"] = hist["failed"]
    report = tmp_path / "pytest-report.json"
    report.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
    prov = tmp_path / "PROVENANCE.json"
    cov._bind_provenance(prov, report)
    rep = cov.audit(report, ROOT, prov, pinned, ROOT / "tests", [], list(cov.PARITY_TESTS), 0)
    fired = {v["check"] for v in rep["violations"]}
    assert fired - {"worktree_clean", "roster_covers_tree"} == set(), sorted(
        (v["check"], v["detail"]) for v in rep["violations"])
    assert "roster_covers_tree" in fired
    assert victim in rep["checks"]["roster_covers_tree"]["detail"]


def test_parity_needles_are_still_real_tests_on_the_tree() -> None:
    """替身用例被删掉时 C6 永远开不了火：用 AST 直接确认那两条还长在树上。"""
    src = (ROOT / "tests/test_packaging.py").read_text(encoding="utf-8")
    names = {n.name for n in ast.parse(src).body
             if isinstance(n, ast.FunctionDef) and n.name.startswith("test")}
    for needle in cov.PARITY_TESTS:
        assert needle.startswith("tests/test_packaging.py::"), needle
        assert needle.split("::")[-1] in names, f"替身 {needle} 指向的用例已不在树上"


def test_clean_fixture_is_green_and_omitting_report_uses_provenance(tmp_path: Path) -> None:
    """默认路径（报告从 PROVENANCE 的 `path` 取）在合规夹具上必须走通并全绿。

    `--self-test` 每一支都显式传 `--report`，这条面它碰不到；不另开用例它就是死码。
    """
    repo, _ev, _rp, prov, sha = _clean_fixture(tmp_path)
    argv = ["--provenance", str(prov), "--worktree", str(repo), "--pinned-commit", sha,
            "--no-default-parity", "--parity-test", "tests/test_one.py::test_x"]
    assert cov.main(argv) == 0, "默认 --report 那条路没走通"
    naked = json.loads(prov.read_text(encoding="utf-8"))
    naked["test_report"].pop("path")
    prov.write_text(json.dumps(naked, ensure_ascii=False), encoding="utf-8")
    assert cov.main(argv) == 2, "证据里没写路径时不许瞎猜"


def test_empty_roster_missing_anchor_and_missing_dir_are_all_premature(tmp_path: Path) -> None:
    repo, evidence, report, prov, sha = _clean_fixture(tmp_path)
    base = ["--report", str(report), "--provenance", str(prov), "--worktree", str(repo),
            "--tests-dir", str(repo / "tests"), "--no-default-parity",
            "--parity-test", "tests/test_one.py::test_x", "--pinned-commit", sha]
    assert cov.main(base) == 0
    cov._pristine_report(evidence, [], sha)
    cov._bind_provenance(prov, report)
    assert cov.main(base) == 2, "空名单不算零违规"
    cov._pristine_report(evidence, ["tests/test_one.py::test_x"], sha)
    cov._bind_provenance(prov, report)
    assert cov.main(base[:-2]) == 2, "没给锚点就不判 STALE"
    assert cov.main(base + ["--tests-dir", str(repo / "nope")]) == 2, "读不到分母不是绿"


def test_missing_plaintiff_fires_only_that_check(tmp_path: Path) -> None:
    repo, _ev, report, prov, sha = _clean_fixture(tmp_path)
    rep = cov.audit(report, repo, prov, sha, repo / "tests",
                    ["test_zzz_never_written"], ["tests/test_one.py::test_x"], 0)
    assert {v["check"] for v in rep["violations"]} == {"plaintiffs_measured"}, rep["violations"]
    assert rep["checks"]["report_bound_to_provenance"]["ok"] is True
    ok = cov.audit(report, repo, prov, sha, repo / "tests",
                   ["test_x"], ["tests/test_one.py::test_x"], 0)
    assert ok["ok"] is True, ok["violations"]


def test_min_tests_ratchet_is_opt_in(tmp_path: Path) -> None:
    repo, _ev, report, prov, sha = _clean_fixture(tmp_path)
    ok = cov.audit(report, repo, prov, sha, repo / "tests", [],
                   ["tests/test_one.py::test_x"], 0)
    assert ok["checks"]["size_ratchet"]["kind"] == "skipped", ok["checks"]["size_ratchet"]
    red = cov.audit(report, repo, prov, sha, repo / "tests", [],
                    ["tests/test_one.py::test_x"], 5000)
    assert {v["check"] for v in red["violations"]} == {"size_ratchet"}, red["violations"]


def test_problems_are_not_folded_into_violations(tmp_path: Path) -> None:
    """退 2 与退 4 是两件事：前提塌了不许写成"有 N 处判红"，反之亦然。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    missing = tmp_path / "nope.json"
    rep = cov.audit(missing, repo, missing, "a" * 40, repo / "tests", [], [], 0)
    assert rep["problems"] and not rep["violations"], rep
    junk = tmp_path / "junk.json"
    junk.write_text("{ not json", encoding="utf-8")
    rep2 = cov.audit(junk, repo, missing, "a" * 40, repo / "tests", [], [], 0)
    assert rep2["problems"] and not rep2["violations"], rep2
    assert cov.main(["--report", str(junk), "--provenance", str(missing),
                     "--worktree", str(repo), "--tests-dir", str(repo / "tests"),
                     "--pinned-commit", "a" * 40]) == 2


def test_binding_decides_which_copy_of_the_report_is_authority(tmp_path: Path) -> None:
    """报告只有一份是权威：PROVENANCE 记下 sha 的那份。仓库里另放的副本只要字节不同，
    没被绑上就不能当第二张嘴（内容相同而字节不同的副本，也照样读成"不是那一份"）。
    """
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    bound = tmp_path / "bound.json"
    bound.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    unbound = tmp_path / "unbound.json"
    unbound.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    assert cov._sha256_path(bound) != cov._sha256_path(unbound), "夹具前提：两份字节得不同"
    prov_src = json.loads(PROV.read_text(encoding="utf-8"))
    prov_src["test_report"]["path"] = str(bound)
    prov_src["test_report"]["sha256"] = cov._sha256_path(bound)
    prov = tmp_path / "PROVENANCE.json"
    prov.write_text(json.dumps(prov_src, ensure_ascii=False), encoding="utf-8")
    rep = cov.audit(bound, ROOT, prov, payload["source_commit"], ROOT / "tests", [], [], 0)
    assert rep["checks"]["report_bound_to_provenance"]["ok"] is True, \
        rep["checks"]["report_bound_to_provenance"]
    rep2 = cov.audit(unbound, ROOT, prov, payload["source_commit"], ROOT / "tests", [], [], 0)
    fired2 = {v["check"] for v in rep2["violations"]}
    assert "report_bound_to_provenance" in fired2, rep2["violations"]
    # 只有 C1 因这份副本而多出来的判决：其余两格是开发树本来就有的（名单缺本轮新文件、树脏）
    assert fired2 - {"worktree_clean", "roster_covers_tree"} == {"report_bound_to_provenance"}, \
        sorted(fired2)


def test_the_instrument_itself_is_cited_in_the_tool_catalog() -> None:
    """README 的量具目录要有行首可执行写法——第 60 片那把尺子判的就是这个面。"""
    lines = [ln.strip() for ln in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()]
    assert any(ln.startswith("python scripts/closeout_verifier.py") for ln in lines), \
        "README 里要有 `python scripts/closeout_verifier.py …` 这一行（行首、可复制执行）"
