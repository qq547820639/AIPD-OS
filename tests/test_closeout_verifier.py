"""收尾验签量具的常驻牙（F-CLOSEOUT-VERIFY 第 64 片）。

这台机器管三件事：**报告是不是绑着现在这份证据**、**汇总数是不是名单自己数出来的**、
**名单与树上那份 def 是不是同一批**。第 62/63 片每轮手写的验签脚本因为落在 `/tmp`
被宿主重启清掉过一整份，下一轮从提交摘要重推配方，代价是两次整套件重跑（锚点传成 HEAD
被判 STALE 一次、PATH 缺 `.venv/bin` 假红一次）。提为常驻件之后，那些坑由这里的用例
长期按住，而不是靠下一次的记忆。

一条写成本篇才成立的规矩（第一次签出复算就把四条用例打红了，见 §四）：
**常驻用例不许假设仓库处于"刚绑定"那一小段窗口**。仓库里 `PROVENANCE` 与报告的关系在每个
提交上都不一样（重锚后未绑定 ⇒ 未绑；本轮新增的测试文件比报告新 ⇒ 名单缺它），所以这里
凡是拿真语料判"必须绿"的断言，都改成两种写法之一：
① 先把真报告**复制一份并就地绑定**，再让量具对它出判决（C1/C2 与新鲜度无关了）；
② 把"允许缺哪几格"由 git 自己算出来（名单缺口 == 自报告那次提交以来被增改的测试文件），
   而不是写死一个集合或干脆放宽判据。
"""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
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
REPORT_REL = str(REPORT.relative_to(ROOT))

ALL_CHECKS = {
    "report_bound_to_provenance", "counts_counted_from_roster", "terminal_clean",
    "roster_covers_tree", "pinned_source_binding", "content_parity_measured",
    "worktree_clean", "plaintiffs_measured", "size_ratchet",
    "report_fingerprint_recorded", "report_fingerprint_matches_disk",
}
# 与"这份报告新不新、这棵树干不干净、清单被刷写过没有"有关的三格：其余八格与仓库阶段无关，必须绿
STAGE_BOUND = {"roster_covers_tree", "worktree_clean", "report_fingerprint_matches_disk"}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _is_pytest_file(path: str) -> bool:
    name = Path(path).name
    return path.startswith("tests/") and (name.startswith("test_") or name.endswith("_test.py"))


def _report_files(rep: dict) -> set[str]:
    return {t["nodeid"].split("::")[0] for t in rep["tests"]}


@pytest.fixture(scope="module")
def pinned() -> str:
    """发布锚点：tag 指向的提交。约定不许 re-anchor 到 HEAD，所以它与 HEAD 不同。"""
    sha = _git("rev-parse", "v5.6.0^{commit}")
    assert len(sha) == 40, sha
    return sha


@pytest.fixture
def real_pair(tmp_path: Path, pinned: str):
    """把真报告复制一份并就地绑定，这样 C1/C2 的读数就与"仓库正处在配方哪一步"无关。"""
    report = tmp_path / "pytest-report.json"
    shutil.copyfile(REPORT, report)
    prov = tmp_path / "PROVENANCE.json"
    cov._bind_provenance(prov, report)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["source_commit"] == pinned, "夹具前提：仓库那份报告绑的就是 tag 锚点"

    def run(pinned_arg: str = pinned, expect: list[str] | None = None,
            parity: list[str] | None = None, min_tests: int = 0) -> dict:
        return cov.audit(report, ROOT, prov, pinned_arg, ROOT / "tests",
                         expect if expect is not None else ["tests/test_packaging.py"],
                         parity if parity is not None else list(cov.PARITY_TESTS),
                         min_tests)

    return run


def _clean_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, str]:
    """一座干净的仓库 + 树外的证据目录（对照组的 C7 不该被自己的夹具弄脏）。

    仓库里必须有一份真形状的 `SOURCE_MANIFEST.json`，报告也得盖上它的指纹：
    没有这两步，合规对照组会红在 C10，而 C11 永远没有可比对象（第 83 片）。
    """
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests/test_one.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (repo / "SOURCE_MANIFEST.json").write_text(json.dumps({
        "name": "AIPD-OS source manifest", "version": "0.0.0", "source_commit": "pre",
        "generated_at": "2020-01-01T00:00:00+00:00", "coverage": "fixture",
        "files": [{"path": "tests/test_one.py", "size": 30, "sha256": "c" * 64}]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    sha = cov._git_init(repo, "fixture")
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    report = cov._pristine_report(evidence, ["tests/test_one.py::test_x"], sha,
                                  manifest=repo / "SOURCE_MANIFEST.json")
    prov = evidence / "PROVENANCE.json"
    cov._bind_provenance(prov, report)
    return repo, evidence, report, prov, sha


def test_instrument_self_test_is_actually_run_and_green() -> None:
    proc = subprocess.run([sys.executable, str(TOOL), "--self-test"],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert "条合成读数全部对上" in proc.stdout, proc.stdout
    marks = proc.stdout.count("[OK]")
    assert marks >= 23, f"--self-test 的臂从 23 条缩水成 {marks} 条：注入没跑满就别谈判据"


def test_check_names_are_the_documented_eleven(real_pair) -> None:
    """判据名字是文档与 CHANGELOG 引用的面；改名必须在这里一起翻。"""
    names = set(real_pair()["checks"])
    assert names >= ALL_CHECKS, sorted(ALL_CHECKS - names)
    assert names <= ALL_CHECKS, sorted(names - ALL_CHECKS)


def test_eight_checks_are_green_on_the_real_corpus_regardless_of_stage(real_pair,
                                                                       pinned: str) -> None:
    """真语料（两千六百条量级的绑定报告）上，与新鲜度无关的八格必须全绿；只有三格允许因本轮在途而红。"""
    rep = real_pair()
    fired = {v["check"] for v in rep["violations"]}
    assert fired <= STAGE_BOUND, sorted((v["check"], v["detail"]) for v in rep["violations"])
    for name in ALL_CHECKS - STAGE_BOUND:
        assert rep["checks"][name]["ok"] is True, (name, rep["checks"][name])
    r = rep["readings"]
    assert r["report_entries"] >= 2000 and r["tree_files"] >= 200, r
    assert r["report_entries"] > r["tree_defs"], f"参数化条目没进名单：{r}"
    assert r["pinned_commit"] == pinned and r["provenance_binds_report"] is True, r


def _defs_differ(old_src: str | None, new_src: str) -> bool:
    """`def test_` 的条数是否变了（`old_src=None` 表示报告那次提交时还没有这个文件）。

    为什么按"条数"而不是按"文件被 touch 过"：名单能观测的只有"树上有几条、报告里出现几条"，
    一个只改了实现细节、`def test_` 数量不变的修改**不产生任何名单缺口**，
    拿它去要求缺口非空就是把"名字被碰过"当成"覆盖变了"
    （第 69 片实测：加了一条旗子的常驻控制、1:1 替换了两个用例，
    旧写法让收口全量多出 1 条假红，连带把绑定成红报告后又放大成 4 条）。
    已知够不着的地方也写在这：等量改名（删一条加一条）本判据看不见——它的分母是条数。
    """
    def count(src: str) -> int:
        return sum(1 for ln in src.splitlines() if ln.startswith(("def test_", "    def test_")))
    return old_src is None or count(old_src) != count(new_src)


def test_helper_only_fires_when_def_counts_move() -> None:
    """判据自己的双向控制：新增文件 / 加用例 ⇒ 真；1:1 改实现 ⇒ 假。"""
    nl = chr(10)
    two = nl.join(["def test_one():", "    pass", "", "", "def test_two():", "    pass", ""])
    three = two + nl.join(["", "def test_three():", "    pass", ""])
    one = nl.join(["def test_one():", "    pass", ""])
    assert _defs_differ(None, two) is True, "新增文件必须算缺口来源"
    assert _defs_differ(two, two) is False, "内容变了但 def 条数没变 ⇒ 名单没有缺口"
    assert _defs_differ(two, three) is True, "多一条用例要算"
    assert _defs_differ(two, one) is True, "少一条用例也要算（条数动了）"


def _pick_anchor(bound_commits: list[str]) -> str:
    """同一份报告被绑过多次时取**最早**那次（入参按 `git log` 的新→旧排）。

    为什么不是最近一次：刷清单那一步会重写 `PROVENANCE.json`，报告内容没变、sha 相同，
    于是"最近一次绑定"被推到本轮的测试改动**之后** ⇒ `git diff 基准..HEAD -- tests` 读成空集，
    而名单缺口还在 ⇒ 同一种假红。第 81 片实测：中途两次重绑各把基准前推一次，
    最后多烧一整个全量。基准应该是"这份内容第一次成为权威"的那一刻，那之后无论重绑几次都不动。
    """
    return bound_commits[-1]


def _bound_commits_for(digest: str, repo: Path = ROOT) -> list[str]:
    """PROVENANCE 历史里绑着这份 sha256 的提交，按 `git log` 的顺序（新→旧）。"""
    hits: list[str] = []
    for c in subprocess.run(["git", "-C", str(repo), "log", "--format=%H", "--",
                             "PROVENANCE.json"], capture_output=True, text=True,
                            check=True).stdout.splitlines():
        if not c:
            continue
        try:
            doc = json.loads(subprocess.run(["git", "-C", str(repo), "show",
                                             f"{c}:PROVENANCE.json"], capture_output=True,
                                            text=True, check=True).stdout)
        except subprocess.CalledProcessError:
            continue      # 早期的提交里 PROVENANCE.json 还不存在
        bound = str(((doc.get("test_report") or {}).get("sha256")) or "")
        if bound and bound == digest:
            hits.append(c)
    return hits


def _anchor_commit_for_this_report() -> str:
    """这份报告"从哪一次提交起算权威"：PROVENANCE 历史里**最早**一次绑着同一份 sha256 的提交。

    不能用 `git log -1 -- 报告文件`：报告被重新提交过（例如误绑定之后 revert）就会把 touch 点
    推到代码改动**之后** ⇒ "报告以来改过的测试文件"算成空集，而名单缺口还在 ⇒ 假红。
    第 69 片就是这么把 1 条在途红放大成 4 条的。按 sha256 找绑定那次提交，
    在途（PROVENANCE 尚未绑定）与已绑定两种状态都落在同一个基准上。
    """
    digest = hashlib.sha256(REPORT.read_bytes()).hexdigest()
    hits = _bound_commits_for(digest)
    if hits:
        return _pick_anchor(hits)
    return _git("log", "-1", "--format=%H", "--", REPORT_REL)


def _gap_and_changed(report_data: dict, report_commit: str,
                     repo: Path = ROOT) -> tuple[set[str], set[str]]:
    """把判据的两边算出来：左边=名单↔树的缺口，右边=自基准以来 def 条数动过的测试文件。

    抽成函数是因为这两边必须能在**合成历史**上重放：本轮踩的坑正是"重绑把基准推后"，
    只在真仓库上断言就看不见那一支（真仓库里基准只有一个候选时，新旧取法读数相同）。
    """
    changed: set[str] = set()
    for ln in subprocess.run(["git", "-C", str(repo), "diff", "--name-only",
                              "--diff-filter=AM", f"{report_commit}..HEAD", "--", "tests"],
                             capture_output=True, text=True, check=True).stdout.splitlines():
        if not _is_pytest_file(ln):
            continue
        new_src = (repo / ln).read_text(encoding="utf-8")
        try:
            old_src = subprocess.run(["git", "-C", str(repo), "show", f"{report_commit}:{ln}"],
                                     capture_output=True, text=True,
                                     check=True).stdout
        except subprocess.CalledProcessError:
            old_src = None          # 报告那次提交时还没有这个文件
        if _defs_differ(old_src, new_src):
            changed.add(ln)
    tree = cov.tree_roster(repo / "tests")[0]
    measured = {t["nodeid"].split("::")[0] for t in report_data["tests"]}
    counts: dict[str, int] = {}
    for node in report_data["tests"]:
        f = node["nodeid"].split("::")[0]
        counts[f] = counts.get(f, 0) + 1
    never_ran = {f for f in tree if f not in measured}
    short = {f for f in tree if f in measured and counts[f] < tree[f]}
    return never_ran | short, changed



def test_roster_gap_equals_tests_changed_since_the_report(pinned: str) -> None:
    """名单缺的测试文件，必须恰好等于"报告那次提交以来 **def 条数动过**的测试文件"。

    写成"差额为空"在途时必红，写成"差额随便"就是恒真；两边都由 git 现算，任何一侧
    多算或漏算都会翻。报告一旦被重新绑定并提交，`git diff rc..HEAD -- tests` 就是空集。
    """
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    report_commit = _anchor_commit_for_this_report()
    assert report_commit, "报告没在任何提交里？"
    gap, changed = _gap_and_changed(data, report_commit)
    assert gap == changed, (sorted(gap), sorted(changed))
    ghosts = sorted(f for f in _report_files(data) if f not in cov.tree_roster(ROOT / "tests")[0])
    assert ghosts == [], f"报告里有个树上没有的文件（测的不是这棵树）：{ghosts}"
    assert _git("rev-parse", "v5.6.0^{commit}") == data["source_commit"] == pinned


def test_rebinding_the_same_report_does_not_move_the_anchor(tmp_path: Path) -> None:
    """合成历史：同一份报告被重绑过两次，中间动过一条用例 ⇒ 基准必须是**最早**那次绑定。

    这条就是第 81 片那笔代价的形状：为了刷 `SOURCE_MANIFEST` 中途又跑了一次绑定，
    报告内容没变、sha 相同，按"最近一次"取基准就把基准推到测试改动之后，
    于是右边读成空集、左边缺口还在 ⇒ 常驻全量多一条假红，最后多烧一整跑。
    这里两边都断：既断新取法选对，也断旧取法（最近一次）确实会把等式判坏——
    只断"新取法对"抓不到"旧取法错在哪"。
    """
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    prov = repo / "PROVENANCE.json"
    report = repo / "report.json"
    report.write_text(json.dumps({"tests": [{"nodeid": "tests/test_a.py::test_one",
                                             "outcome": "passed"}]}), encoding="utf-8")
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    bound = json.dumps({"test_report": {"sha256": digest}})

    (repo / "tests/test_a.py").write_text("def test_one():\n    assert True\n", encoding="utf-8")
    cov._git_init(repo, "seed")
    prov.write_text(bound, encoding="utf-8")
    first = cov._git_init(repo, "第一次绑定这份报告")
    # 中间加一条用例（名单缺口 +1），随后重绑同一份内容（sha 不变，只多一个时间戳）
    (repo / "tests/test_a.py").write_text("def test_one():\n    assert True\n\n\n"
                                          "def test_two():\n    assert True\n",
                                          encoding="utf-8")
    cov._git_init(repo, "本轮新增一条用例")
    prov.write_text(json.dumps({"test_report": {"sha256": digest},
                                "generated_at": "later"}), encoding="utf-8")
    latest = cov._git_init(repo, "重绑同一份报告")

    hits = _bound_commits_for(digest, repo)
    assert hits == [latest, first], "夹具前提：同一份 sha 得真被绑过两次（新→旧）"
    assert _pick_anchor(hits) == first, "基准取错了"
    payload = json.loads(report.read_text(encoding="utf-8"))
    gap, changed = _gap_and_changed(payload, _pick_anchor(hits), repo)
    assert gap == changed == {"tests/test_a.py"}, (sorted(gap), sorted(changed))
    gap_old, changed_old = _gap_and_changed(payload, latest, repo)
    assert gap_old == {"tests/test_a.py"} and changed_old == set(), \
        f"旧取法的病必须复现（缺口 {sorted(gap_old)} vs 改动 {sorted(changed_old)}）"


def test_worktree_verdict_tracks_git_status_exactly(real_pair) -> None:
    """C7 的开火与 `git status --porcelain` 的实际输出逐次同向（不许自造一套脏判据）。"""
    dirty = bool([ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()])
    ok = real_pair()["checks"]["worktree_clean"]["ok"]
    assert ok is not dirty, f"工作树 dirty={dirty} 而判据 ok={ok}"


def test_pinning_to_head_instead_of_the_tag_fires_only_that_check(real_pair) -> None:
    """第 62 片的原件错误：锚点传成 HEAD。真分母上必须只多点亮 `pinned_source_binding`。"""
    head = _git("rev-parse", "HEAD")
    pinned = _git("rev-parse", "v5.6.0^{commit}")
    assert head != pinned, "夹具前提：锚点不许已经漂到 HEAD"
    rep = real_pair(pinned_arg=head)
    fired = {v["check"] for v in rep["violations"]}
    assert fired - STAGE_BOUND == {"pinned_source_binding"}, sorted(fired)
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
    rep = cov.audit(report, ROOT, prov, pinned, ROOT / "tests", ["tests/test_packaging.py"],
                    list(cov.PARITY_TESTS), 0)
    fired = {v["check"] for v in rep["violations"]}
    assert fired - {"worktree_clean"} == {"roster_covers_tree"}, sorted(
        (v["check"], v["detail"]) for v in rep["violations"])
    assert rep["checks"]["counts_counted_from_roster"]["ok"] is True, \
        "汇总数与两处副本同口径改小时，C2 不该被名单那一格牵连"
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


def test_unbound_provenance_is_premature_not_two_violations(tmp_path: Path) -> None:
    """重锚之后、绑定之前那段窗口每轮都要经过：没基准可比就读成前提塌。

    这一条是第一次签出复算教我的：那时 `PROVENANCE.test_report` 是 `{"present": false}`，
    量具报了两格判红，读者会去"修"一个本来正常的状态。
    """
    repo, _ev, report, prov, sha = _clean_fixture(tmp_path)
    unbound = json.loads(prov.read_text(encoding="utf-8"))
    unbound["test_report"] = {"present": False, "path": str(report)}
    prov.write_text(json.dumps(unbound, ensure_ascii=False), encoding="utf-8")
    rep = cov.audit(report, repo, prov, sha, repo / "tests", [], ["tests/test_one.py::test_x"], 0)
    assert rep["problems"] and not rep["violations"], (rep["problems"], rep["violations"])
    assert "provenance_binds_report" in rep["checks"]
    assert "report_bound_to_provenance" not in rep["checks"], "没基准那一格不该进判红面"
    assert rep["checks"]["counts_counted_from_roster"]["ok"] is True, "报告内部那一半照判"
    assert cov.main(["--report", str(report), "--provenance", str(prov),
                     "--worktree", str(repo), "--tests-dir", str(repo / "tests"),
                     "--pinned-commit", sha, "--no-default-parity",
                     "--parity-test", "tests/test_one.py::test_x"]) == 2


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
    """报告只有一份是权威：PROVENANCE 记下 sha 的那份。字节不同的副本没被绑上，
    就不能当第二张嘴（内容相同而字节不同的那份也照样读成"不是那一份"）。
    """
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    bound = tmp_path / "bound.json"
    bound.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    unbound = tmp_path / "unbound.json"
    unbound.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    assert cov._sha256_path(bound) != cov._sha256_path(unbound), "夹具前提：两份字节得不同"
    prov = tmp_path / "PROVENANCE.json"
    cov._bind_provenance(prov, bound)
    rep = cov.audit(bound, ROOT, prov, payload["source_commit"], ROOT / "tests",
                    ["tests/test_packaging.py"], [], 0)
    assert rep["checks"]["report_bound_to_provenance"]["ok"] is True, \
        rep["checks"]["report_bound_to_provenance"]
    rep2 = cov.audit(unbound, ROOT, prov, payload["source_commit"], ROOT / "tests",
                     ["tests/test_packaging.py"], [], 0)
    fired2 = {v["check"] for v in rep2["violations"]}
    assert fired2 - STAGE_BOUND == {"report_bound_to_provenance"}, sorted(fired2)


def test_the_instrument_itself_is_cited_in_the_tool_catalog() -> None:
    """README 的量具目录要有行首可执行写法——第 60 片那把尺子判的就是这个面。"""
    lines = [ln.strip() for ln in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()]
    assert any(ln.startswith("python scripts/closeout_verifier.py") for ln in lines), \
        "README 里要有 `python scripts/closeout_verifier.py …` 这一行（行首、可复制执行）"


def test_bound_production_report_carries_its_manifest_fingerprint() -> None:
    """C10 的牙落在真产物上：绑进证据的那份报告必须自带 64 位清单指纹。

    手写夹具能盖上指纹也能不盖，只有真报告证明 `tests/conftest.py` 的注入在生产里跑过。
    第 83 片换绑之前这条是红的——那是有意的强制装置（旧报告出自没有注入的 conftest），
    不是判据写坏了；它红了就把报告重跑重绑，别把判据改宽。
    """
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    fp = data.get("source_manifest_fingerprint")
    assert isinstance(fp, str) and len(fp) == 64 and fp == fp.lower(), sorted(data)


def test_fingerprint_verdict_always_has_a_content_level_explanation(real_pair) -> None:
    """C11 允许在途红，但红与绿都得能由清单**内容**解释——解释不了就是判据在造假读数。

    绿的一侧：报告记的指纹 == 报告锚点那次提交里那份清单的内容摘要（证明"报告测的确实是
    那一份"）。红的一侧：磁盘清单的 `files` 与锚点那次必然不同（同一片内容只换 `generated_at`
    却判红，就是判据写成了比原始字节 sha 那种病）。
    """
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    anchor = _anchor_commit_for_this_report()
    at_anchor = json.loads(_git("show", f"{anchor}:SOURCE_MANIFEST.json"))
    disk = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    rep = real_pair()
    fired = {v["check"] for v in rep["violations"]}
    kind = rep["checks"]["report_fingerprint_matches_disk"]["kind"]
    if kind == "skipped":
        assert "report_fingerprint_recorded" in fired, \
            "C11 因为报告没带指纹而沉默时，必须由 C10 开火——两处都沉默等于这条判据被删了"
        return
    if "report_fingerprint_matches_disk" in fired:
        assert disk["files"] != at_anchor["files"], \
            "清单内容与锚点那次同一份（只换 generated_at）却判红 ⇒ C11 在造假红"
    else:
        assert payload["source_manifest_fingerprint"] == \
            cov.release_fingerprint.fingerprint_of_document(at_anchor), \
            "判绿但报告记的指纹对不上锚点那次的清单内容 ⇒ C11 在造假绿"
