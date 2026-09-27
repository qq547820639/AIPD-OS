#!/usr/bin/env python3
"""收尾验签：把"这份报告测的确实是这棵树"做成常驻判据（F-CLOSEOUT-VERIFY 第 64 片）。

起因是本仓每轮收尾都**手写**一份验签脚本（第 62 片 `/tmp/s62/verify62.py`、第 63 片
`/tmp/s63/verify63.py`，25 条读数）。第 63 片收尾时宿主重启把 `/tmp` 清空，那份脚本
连同它验过的判断依据一起没了——下一轮只能从提交摘要重推配方。重推的代价本轮实测到了：
锚点传错（该传发布 tag 指向的提交，传成锚点 HEAD）让门禁判了一次 STALE，外加 PATH 缺
`.venv/bin` 的一次假红，两轮整套件重跑。这台机器的存在就是把那笔成本一次性付清。

权威面（本轮实测决定的，不抄旧摘要）：
- **不是** `scripts/production_release_gate.py`。它的 `_check_test_report`（本轮重开
  `:503-542`）只读 `provenance["test_report"]` 里那几个**已经抄过一遍**的数字，加一条
  `report_sc != anchor` 的 STALE 判决；它既不数 `tests[]`，也不重算报告自己的 sha256。
- 而 `scripts/release_evidence.py:236-278` 的 `failed` 是由 `total - passed - skipped`
  **推导**的——所以"summary 被人改过"与"`tests[]` 被截断但 summary 留着"这两件事，
  现有主线一条都看不见。本量具的 C2 就是把计数**由名单自己数出来**再与两处副本对。
- provenance 记了报告的 `sha256` 却没人事后重算：C1 补上，证明"绑进证据的报告"与
  "现在磁盘上这份"是同一个字节序列。

判据（退码形状沿用本仓常驻量具：0 全绿 / 4 判红 / 2 前提不成立）：
  C1 report_bound_to_provenance   报告文件 sha256 == provenance 记录的那条
                                  （证据里压根没绑这份报告时读成**前提塌**退 2，不判违规：
                                  重锚与绑定之间那段窗口每轮收尾都要经过，把它读成红会让人去"修"正常状态）
  C2 counts_counted_from_roster   汇总数由 tests[] 现数，summary 与 provenance 两处副本都对得上
  C3 terminal_clean               exitcode 0 且没有 failed/error 终态（setup/teardown 也算）
  C4 roster_covers_tree           树上的测试文件与名单里的文件双向求差为空；每文件名单 ≥ 树上 def 数
  C5 pinned_source_binding        报告与 provenance 的 source_commit 都等于给定锚点，且锚点是工作树 HEAD 的祖先
  C6 content_parity_measured      两条清单哈希用例在名单里且 passed——这是"测的就是这棵树"的替身证明
  C7 worktree_clean               工作树 `git status --porcelain` 为空
  C8 plaintiffs_measured          本轮新补的用例（`--expect-test`）确实在名单里跑过并且过了
  C9 size_ratchet                 `--min-tests` 下界（借 dorny/test-reporter 的 `fail-on-empty` 语义，
                                  但把它从"空就红"收紧成"低于下界就红"，因为本仓分母是 2 千量级）
  C10 report_fingerprint_recorded  报告自带 `source_manifest_fingerprint`——生产者没记就是红，
                                  不能读成"值恰好为空的绿"（第 83 片之前 conftest 不写这个键，
                                  所以这条会把那条旧报告打红，直到换绑一份新的）
  C11 report_fingerprint_matches_disk
                                  报告记的清单指纹 == 磁盘当前 `SOURCE_MANIFEST.json` 的内容摘要。
                                  C6 只能证"那份报告里两条清单哈希用例过了"，而清单一旦被之后的
                                  刷新重写，那句证明说的就是旧哈希——这一格把"报告测的是当前这份
                                  清单"变成机器读的数

C11 比的为什么**不是**清单文件的原始 sha256（本轮实测）：`release_evidence.py:133` 每次生成
都重写 `generated_at`，所以"刷清单 → 跑全量 → 绑定"这三步之间原始字节的摘要必然变红。
摘要求 `scripts/release_fingerprint.py` 的**规范摘要**（剥掉 `generated_at` 后排序取 sha256），
"只换时间戳"读成同一份清单，"某个文件的 sha256 变了"才读成不同。

两处形状是本轮实测出来的，不是推的：
- 名单文件面必须同时吃 `test_*.py` **和** `*_test.py`：pytest 默认 `pythonFunctions`/
  `pythonFiles` 是两个模式，只 glob `test_*.py` 会把 `tests/maturity_consistency_test.py`
  读成"报告里有个树上没有的文件"——我在真报告上第一次试跑就是这么红的。
- `summary` 里 `failed`/`error` 键**计数为 0 时根本不存在**（pytest-json-report 的行为），
  所以缺键必须读成 0 而不是缺失；这条与 `release_evidence` 的推导口径必须一致，否则 C2
  会把自己的证据源判红。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
# 兄弟模块：`release_fingerprint` 是清单指纹的唯一一把尺（生产侧 tests/conftest.py 用同一个）。
# 直接被 import 时（tests 已把 scripts/ 放进 sys.path）这条是幂等的，脚本方式运行时它才必要。
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import release_fingerprint  # noqa: E402

# pytest 默认收集两种文件名，只写一种会让 C4 把合法文件读成"树上没有"
PYTEST_FILE_PATTERNS = ("test_*.py", "*_test.py")

# "测的是这棵树"的既有替身：这两条把两份清单里记录的 sha256 与磁盘逐文件比对
PARITY_TESTS = (
    "tests/test_packaging.py::test_release_manifest_hashes_match_disk",
    "tests/test_packaging.py::test_source_manifest_hashes_match_disk",
)

BAD_OUTCOMES = ("failed", "error")
PHASES = ("setup", "call", "teardown")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> tuple[dict | None, str]:
    if not path.is_file():
        return None, f"文件不存在：{path}"
    if path.is_dir():
        return None, f"是目录不是文件：{path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"读不出：{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"顶层不是对象：{type(data).__name__}"
    return data, ""


def _run_git(worktree: Path, args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(["git", "-C", str(worktree), *args],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 128, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _test_defs_in(path: Path) -> tuple[int | None, str]:
    """数一个文件里 pytest 会收到的测试函数定义（模块层 + 类层，不吃函数套函数）。"""
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return None, f"SyntaxError: {exc}"
    count = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                count += 1
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name.startswith("test"):
                    count += 1
    return count, ""


def tree_roster(tests_dir: Path) -> tuple[dict[str, int], list[str]]:
    """{相对 tests_dir 上一级的路径: def 数}；返回 (roster, 前提问题列表)。

    键必须按 rootdir 相对而非 tests_dir 相对：pytest 写进 nodeid 的是**相对 rootdir**
    的 `tests/test_x.py`，按 tests_dir 相对就会双向求差全非空（夹具第一次试跑就是这么红的）。
    """
    out: dict[str, int] = {}
    problems: list[str] = []
    if not tests_dir.is_dir():
        return out, [f"测试目录不存在：{tests_dir}"]
    seen: set[Path] = set()
    for pattern in PYTEST_FILE_PATTERNS:
        for path in tests_dir.rglob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            count, err = _test_defs_in(path)
            if count is None:
                problems.append(f"{path} 解析不了：{err}")
                continue
            out[str(path.relative_to(tests_dir.parent))] = count
    return out, problems


def audit(report_path: Path, worktree: Path, provenance_path: Path,
          pinned: str, tests_dir: Path, expect_tests: list[str],
          parity_tests: list[str], min_tests: int,
          manifest_path: Path | None = None) -> dict[str, Any]:
    rep: dict[str, Any] = {"command": "closeout verify", "problems": [],
                           "violations": [], "checks": {}, "readings": {}}
    if manifest_path is None:
        manifest_path = worktree / "SOURCE_MANIFEST.json"

    def problem(check: str, detail: str) -> None:
        rep["problems"].append({"check": check, "detail": detail})
        rep["checks"][check] = {"ok": False, "detail": detail, "kind": "problem"}

    def judge(check: str, ok: bool, detail: str) -> None:
        rep["checks"][check] = {"ok": ok, "detail": detail, "kind": "violation"}
        if not ok:
            rep["violations"].append({"check": check, "detail": detail})

    prov, err = _load_json(provenance_path)
    if prov is None:
        problem("provenance_readable", err)
        prov = {}
    report, err = _load_json(report_path)
    if report is None:
        problem("report_readable", err)
        rep["ok"] = False
        return rep

    tests = report.get("tests")
    if not isinstance(tests, list):
        problem("report_readable", f"报告没有 tests 数组（拿到 {type(tests).__name__}）")
        rep["ok"] = False
        return rep
    if not tests:
        # 借 dorny/test-reporter 的 fail-on-empty：空清单不算"零违规"
        problem("report_readable", "报告 tests 为空——空读数不算绿")
        rep["ok"] = False
        return rep

    nodes: list[str] = []
    hist: Counter[str] = Counter()
    phase_bad: list[str] = []
    for t in tests:
        if not isinstance(t, dict) or "nodeid" not in t:
            problem("report_readable", f"名单里有一条形如 {str(t)[:60]!r} 的记录")
            rep["ok"] = False
            return rep
        nodes.append(str(t["nodeid"]))
        hist[str(t.get("outcome"))] += 1
        for ph in PHASES:
            got = t.get(ph)
            if isinstance(got, dict) and got.get("outcome") in BAD_OUTCOMES:
                phase_bad.append(f"{t['nodeid']} 的 {ph} 是 {got['outcome']}")
    rep["readings"]["report_entries"] = len(nodes)
    rep["readings"]["outcome_hist"] = dict(sorted(hist.items()))
    rep["readings"]["report_root"] = report.get("root")
    rep["readings"]["report_duration_s"] = report.get("duration")

    # 证据是否已经把这份报告绑进去：没绑是**没有基准**，不是违规（重锚与绑定之间那段窗口
    # 每轮都会经过，把它读成两格判红会让人去"修"一个本来正常的状态）
    tr = prov.get("test_report") if isinstance(prov.get("test_report"), dict) else {}
    bound = bool(tr.get("present")) and bool(tr.get("sha256"))
    rep["readings"]["provenance_binds_report"] = bound

    # C1 报告 ↔ 证据绑定
    if bound:
        rec_sha = tr.get("sha256")
        actual_sha = _sha256_path(report_path)
        judge("report_bound_to_provenance", rec_sha == actual_sha,
              f"报告 sha256={actual_sha[:12]}，PROVENANCE 记的是 "
              f"{str(rec_sha)[:12]}——证据绑定的不是现在这份文件"
              if rec_sha != actual_sha else
              f"报告 sha256={actual_sha[:12]} 与 PROVENANCE 记录一致")
    else:
        problem("provenance_binds_report",
                "PROVENANCE.test_report 里没有 present+sha256——证据还没绑这份报告。"
                "先跑 `release_evidence.py --test-report …` 再验签；这里没有基准可比，不算违规")

    # C2 计数由名单现数，两处副本对账
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    # pytest-json-report 在计数为 0 时**不写那个键**，缺键必须读成 0 而不是缺失
    bad = {k: summary.get(k, 0) for k in ("passed", "skipped", "failed", "error")}
    mism: list[str] = []
    for key in ("passed", "skipped", "failed", "error"):
        want = hist.get(key, 0)
        if bad.get(key) != want:
            mism.append(f"summary.{key}={summary.get(key, '（缺键，按 0 读）')} 而现数={want}")
    total = summary.get("total")
    if total != len(nodes):
        mism.append(f"summary.total={total} 而名单={len(nodes)}")
    collected = summary.get("collected")
    if collected is not None and collected != len(nodes):
        mism.append(f"summary.collected={collected} 而名单={len(nodes)}")
    derived_failed = len(nodes) - hist.get("passed", 0) - hist.get("skipped", 0)
    for field, want in (("passed", hist.get("passed", 0)),
                        ("total", len(nodes)),
                        ("failed", derived_failed)):
        if not bound:
            break
        got = tr.get(field)
        if got != want:
            mism.append(f"PROVENANCE.test_report.{field}={got} 而现数={want}")
    judge("counts_counted_from_roster", not mism,
          "；".join(mism) if mism else
          f"现数 passed={hist.get('passed', 0)} skipped={hist.get('skipped', 0)} "
          f"total={len(nodes)}，summary 与 PROVENANCE 两处副本一致")

    # C3 终局干净
    exitcode = report.get("exitcode")
    if exitcode is None:
        problem("terminal_clean", "报告没有 exitcode 字段，无法判终局")
    else:
        dirty = [f"{t}" for t in phase_bad[:3]]
        n_bad = sum(hist[k] for k in BAD_OUTCOMES)
        judge("terminal_clean", exitcode == 0 and n_bad == 0 and not phase_bad,
              f"exitcode={exitcode}，failed/error 终态 {n_bad} 条"
              + (f"，相位失败：{dirty}" if dirty else "")
              if (exitcode != 0 or n_bad or phase_bad) else
              f"exitcode=0，{len(nodes)} 条无 failed/error")

    # C4 名单 ↔ 树
    roster, tproblems = tree_roster(tests_dir)
    if tproblems:
        problem("roster_covers_tree", "；".join(tproblems))
    if not roster:
        if not tproblems:
            problem("roster_covers_tree", f"{tests_dir} 下一个测试文件都没有——分母为空不算绿")
        rep["ok"] = False
        return rep
    rep["readings"]["tree_files"] = len(roster)
    rep["readings"]["tree_defs"] = sum(roster.values())
    files_in_report: Counter[str] = Counter(n.split("::")[0] for n in nodes)
    rep["readings"]["report_files"] = len(files_in_report)
    never_ran = sorted(f for f in roster if f not in files_in_report)
    ghost = sorted(f for f in files_in_report if f not in roster)
    short = sorted((f, roster[f], files_in_report[f]) for f in roster
                   if f in files_in_report and files_in_report[f] < roster[f])
    dupes = sorted(n for n, c in Counter(nodes).items() if c > 1)
    c4: list[str] = []
    if never_ran:
        c4.append(f"树上有 {len(never_ran)} 个测试文件在报告里一次都没出现：{never_ran[:5]}")
    if ghost:
        c4.append(f"报告里有 {len(ghost)} 个树上没有的文件：{ghost[:5]}")
    if short:
        c4.append(f"名单条数少于树上 def 数（有定义没被收到）：{short[:5]}")
    if dupes:
        c4.append(f"报告里有重复 nodeid：{dupes[:3]}")
    judge("roster_covers_tree", not c4,
          "；".join(c4) if c4 else
          f"树 {len(roster)} 文件 / {sum(roster.values())} 个 def，报告 "
          f"{len(files_in_report)} 文件 / {len(nodes)} 条，双向差集为空")

    # C5 锚点绑定
    rep_head = _run_git(worktree, ["rev-parse", "HEAD"])
    if rep_head[0] != 0:
        problem("pinned_source_binding", f"工作树 {worktree} 不是 git 仓库：{rep_head[1]}")
        rep["ok"] = False
        return rep
    head = rep_head[1]
    rep["readings"]["worktree_head"] = head
    rep["readings"]["pinned_commit"] = pinned
    c5: list[str] = []
    if report.get("source_commit") != pinned:
        c5.append(f"报告 source_commit={report.get('source_commit')} != 给定锚点 {pinned}")
    if prov.get("source_commit") != pinned:
        c5.append(f"PROVENANCE source_commit={prov.get('source_commit')} != 给定锚点 {pinned}")
    anc = _run_git(worktree, ["merge-base", "--is-ancestor", pinned, head])
    if anc[0] != 0:
        c5.append(f"锚点不是工作树 HEAD 的祖先（{anc[1] or 'rev 不在这个仓库的历史里'}）")
    judge("pinned_source_binding", not c5, "；".join(c5) if c5 else
          f"报告与 PROVENANCE 都绑在 {pinned}，且它是 HEAD {head[:8]} 的祖先")

    # C6 内容一致性替身
    by_node = {str(t["nodeid"]): str(t.get("outcome")) for t in tests}
    missing = []
    for node in parity_tests:
        outcome = next((o for n, o in by_node.items() if n == node or n.endswith(node)), None)
        if outcome is None:
            missing.append(f"{node} 不在名单里")
        elif outcome != "passed":
            missing.append(f"{node} 是 {outcome}（跳过等价于没证）")
    judge("content_parity_measured", not missing,
          "；".join(missing) if missing else
          f"{len(parity_tests)} 条清单哈希用例都在名单里并 passed：测的就是这棵树")

    # C10/C11 报告自证「测的是哪一份清单」。C6 只能证"报告里那两条哈希用例过了"，
    # 而清单在跑完之后被重写时，那句证明说的是旧哈希——这两格把它换成可比的数。
    rec_fp = report.get("source_manifest_fingerprint")
    rec_fp = str(rec_fp) if rec_fp else ""
    rep["readings"]["report_fingerprint"] = rec_fp[:12]
    judge("report_fingerprint_recorded", bool(rec_fp),
          "报告里没有 source_manifest_fingerprint——生产它的 conftest 没抄清单指纹"
          "（第 83 片之前的旧报告就是这个形状，或注入被人删了）" if not rec_fp else
          f"报告自带清单指纹 {rec_fp[:12]}")
    disk_fp, fp_err = release_fingerprint.fingerprint_from_file(manifest_path)
    rep["readings"]["disk_manifest_fingerprint"] = disk_fp[:12]
    if fp_err:
        problem("manifest_fingerprint_readable", f"{manifest_path}：{fp_err}"
                "——磁盘清单读不出就没有可比基准，判前提塌而不是违规")
    elif not rec_fp:
        rep["checks"]["report_fingerprint_matches_disk"] = {
            "ok": True, "kind": "skipped",
            "detail": "报告没带指纹（C10 已判红），这一格没有可比基准"}
    else:
        judge("report_fingerprint_matches_disk", rec_fp == disk_fp,
              f"报告记的清单指纹 {rec_fp[:12]} != 磁盘当前清单 {disk_fp[:12]}"
              f"（{manifest_path.name} 在跑完全量之后被重写过：那份报告测的是旧内容，"
              f"要么重跑要么把改动退回报告之前）" if rec_fp != disk_fp else
              f"报告指纹与磁盘清单 {disk_fp[:12]} 同源（只换 generated_at 不算变）")

    # C7 工作树干净
    st = _run_git(worktree, ["status", "--porcelain"])
    if st[0] != 0:
        problem("worktree_clean", f"git status 读不出：{st[1]}")
    else:
        lines = [ln for ln in st[1].splitlines() if ln.strip()]
        judge("worktree_clean", not lines,
              f"工作树有 {len(lines)} 处未提交改动：{lines[:5]}" if lines else "工作树干净")

    # C8 本轮原告的名单在场
    if expect_tests:
        c8 = []
        for needle in expect_tests:
            hits = [n for n in nodes if needle in n]
            if not hits:
                c8.append(f"没有任何测过的用例叫 {needle}")
            elif not any(by_node[h] == "passed" for h in hits):
                c8.append(f"{needle} 在场但没一条 passed（{[by_node[h] for h in hits][:3]}）")
        judge("plaintiffs_measured", not c8, "；".join(c8) if c8 else
              f"{len(expect_tests)} 条本轮原告都在名单里且 passed")
    else:
        rep["checks"]["plaintiffs_measured"] = {
            "ok": True, "kind": "skipped", "detail": "未给 --expect-test（本轮没新用例可点名）"}
        rep["readings"]["expect_tests"] = 0

    # C9 规模下界
    if min_tests:
        judge("size_ratchet", len(nodes) >= min_tests,
              f"名单只有 {len(nodes)} 条，低于下界 {min_tests}" if len(nodes) < min_tests
              else f"名单 {len(nodes)} 条 ≥ 下界 {min_tests}")
    else:
        rep["checks"]["size_ratchet"] = {"ok": True, "kind": "skipped",
                                         "detail": "未给 --min-tests"}
        rep["readings"]["min_tests"] = 0

    rep["ok"] = not rep["problems"] and not rep["violations"]
    return rep


def render(rep: dict[str, Any]) -> str:
    lines = ["收尾验签（报告 ↔ 证据 ↔ 工作树）"]
    r = rep["readings"]
    if r:
        lines.append(f"  读数：报告 {r.get('report_entries')} 条 / "
                     f"{r.get('report_files')} 个文件，树 {r.get('tree_files')} 个文件 / "
                     f"{r.get('tree_defs')} 个 def，终态 {r.get('outcome_hist')}")
        lines.append(f"  锚点 {str(r.get('pinned_commit'))[:12]} ← HEAD "
                     f"{str(r.get('worktree_head'))[:12]}，报告 root={r.get('report_root')}")
    for name, chk in rep["checks"].items():
        tag = {"violation": "✗", "problem": "⚠", "skipped": "·"}.get(chk["kind"], "✓")
        if chk["ok"] and chk["kind"] != "skipped":
            lines.append(f"  ✓ {name}：{chk['detail']}")
        else:
            lines.append(f"  {tag} {name}：{chk['detail']}")
    if rep["problems"]:
        lines.append(f"前提不成立 {len(rep['problems'])} 处（退 2）")
    elif rep["violations"]:
        lines.append(f"判红 {len(rep['violations'])} 处（退 4）")
    else:
        lines.append("全部判据绿")
    return "\n".join(lines)


def _resolve_pinned(args: argparse.Namespace, worktree: Path) -> tuple[str, str]:
    if args.pinned_commit:
        return args.pinned_commit.strip(), ""
    if args.tag:
        rc, out = _run_git(worktree, ["rev-list", "-n1", args.tag.strip()])
        if rc != 0 or not out:
            return "", f"--tag {args.tag} 解不出提交：{out}"
        return out, ""
    return "", "必须给 --pinned-commit 或 --tag：没有锚点就没法判报告 STALE 与否"


def _pristine_report(base: Path, nodeids: list[str], source_commit: str,
                     summary_overrides: dict | None = None,
                     outcomes: dict | None = None, root: str = "",
                     manifest: Path | None = None) -> Path:
    """写一份形状与 pytest-json-report 一致的报告（`--self-test` 与常驻用例共用）。

    `failed`/`error` 键在计数为 0 时**不写**：第 63 片就是把缺键读成了红，夹具必须复现
    生产形状，否则量具对自己的那笔反证是假的。
    `manifest` 给了就照 `tests/conftest.py` 的做法把那份清单的内容指纹抄进报告——
    不抄的话合规对照组会先红在 C10，读起来像判据有病。
    """
    tests = [{"nodeid": n, "outcome": (outcomes or {}).get(n, "passed"),
              "setup": {"outcome": "passed"}, "call": {"outcome": "passed"},
              "teardown": {"outcome": "passed"}} for n in nodeids]
    hist: Counter = Counter(str(t["outcome"]) for t in tests)
    summary: dict = {"passed": hist.get("passed", 0), "total": len(tests),
                     "collected": len(tests)}
    if hist.get("skipped"):
        summary["skipped"] = hist["skipped"]
    if hist.get("failed"):
        summary["failed"] = hist["failed"]
    summary.update(summary_overrides or {})
    payload = {"exitcode": 0, "source_commit": source_commit, "root": root or str(base),
               "package_version": "0.0.0", "duration": 1.0,
               "summary": summary, "tests": tests}
    if manifest is not None:
        fp, _err = release_fingerprint.fingerprint_from_file(manifest)
        if fp:
            payload["source_manifest_fingerprint"] = fp
    out = base / "pytest-report.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _bind_provenance(prov: Path, report: Path) -> None:
    """按 `release_evidence.py:236-278` 的口径重绑证据（`failed` 由汇总推导）。

    夹具必须照抄生产侧那套推导：否则"summary 说谎"这一支会同时点亮两处副本，
    读起来像 C2 抓到了两个独立缺陷，而实际只有一个来源。
    """
    data = json.loads(report.read_text(encoding="utf-8"))
    s = data["summary"]
    passed = int(s.get("passed", 0))
    total = int(s.get("total", 0))
    skipped = int(s.get("skipped", 0))
    prov.write_text(json.dumps({
        "name": "AIPD-OS provenance", "version": "0.0.0",
        "source_commit": data.get("source_commit"),
        "test_report": {"present": True, "parsed": True, "path": str(report),
                        "sha256": _sha256_path(report), "passed": passed,
                        "failed": max(total - passed - skipped, 0), "total": total}},
        ensure_ascii=False, indent=1), encoding="utf-8")


def _git_init(repo: Path, message: str) -> str:
    for args in (["init", "-q"], ["config", "user.email", "selftest@example.invalid"],
                 ["config", "user.name", "selftest"], ["add", "-A"],
                 ["commit", "-q", "-m", message]):
        rc, out = _run_git(repo, args)
        assert rc == 0, (args, out)
    return _run_git(repo, ["rev-parse", "HEAD"])[1]


def _self_test(tmp: Path) -> int:
    """一支合规对照 + 十四支逐格注入 + 五支前提退 2 + 一支「只换时间戳必须绿」的假红控制。

    每支注入都断言"开火的判据集合恰好等于该开的那一格"。这条规矩是第 61 片量出来的：
    一次注入点亮三格时，你分不清是判据强还是夹具脏——第 63 片电池里那支 SURVIVED
    也是同一类（夹具喂的姿势到不了判据那一支）。
    """
    marks: list[str] = []

    def _mark(text: str) -> None:
        marks.append(text)
        print(f"  [OK] {text}")

    repo = tmp / "repo"      # 工作树单独一座：证据文件落在树外，否则对照组先红在 C7
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    evidence = tmp / "evidence"
    evidence.mkdir(exist_ok=True)
    (repo / "tests/test_alpha.py").write_text(
        "def test_a1():\n    assert True\n\n\ndef test_a2():\n    assert True\n",
        encoding="utf-8")
    (repo / "tests/beta_test.py").write_text(      # pytest 默认命名的另半边
        "def test_b1():\n    assert True\n", encoding="utf-8")
    (repo / "tests/test_gamma.py").write_text(
        "class TestG:\n    def test_g1(self):\n        assert True\n\n\n"
        "def not_a_test():\n    def test_inner():\n        pass\n", encoding="utf-8")
    # C11 的对照物：一座真清单（形状照 `release_evidence.generate_source_manifest`）。
    # 必须在 `_git_init` 之前建，否则工作树脏，对照组先红在 C7。
    repo_manifest = repo / "SOURCE_MANIFEST.json"
    manifest_doc = {
        "name": "AIPD-OS source manifest", "version": "0.0.0", "source_commit": "pre",
        "generated_at": "2020-01-01T00:00:00+00:00", "coverage": "fixture",
        "files": [{"path": "tests/test_alpha.py", "size": 64, "sha256": "a" * 64}]}
    repo_manifest.write_text(json.dumps(manifest_doc, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    pinned = _git_init(repo, "fixture")

    def prist(*args: Any, **kw: Any) -> Path:
        """重写报告并当场盖上夹具清单的指纹。

        每支注入都会整份重写报告，指纹必须跟着重写走；不盖的话合规对照组与后面十几支
        注入会一起红在 C10，读起来像判据有病而不是夹具缺一步。
        """
        kw.setdefault("manifest", repo_manifest)
        return _pristine_report(*args, **kw)

    nodeids = ["tests/test_alpha.py::test_a1", "tests/test_alpha.py::test_a2",
               "tests/test_alpha.py::test_a1[x=1]",   # 参数化：名单 5 > 树上 def 4
               "tests/beta_test.py::test_b1", "tests/test_gamma.py::TestG.test_g1"]
    report = evidence / "pytest-report.json"
    prov = evidence / "PROVENANCE.json"
    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)

    roster, _ = tree_roster(repo / "tests")
    assert roster == {"tests/test_alpha.py": 2, "tests/beta_test.py": 1,
                     "tests/test_gamma.py": 1}, roster
    _mark("分母吃 pytest 的两种文件名，类层 def 计入、函数套函数不计"
          "（少一条 `*_test.py` 或多数一个嵌套 def，C4 的 ≥ 关系就假红）")

    out_json = tmp / "out.json"
    base_argv = ["--report", str(report), "--provenance", str(prov),
                 "--worktree", str(repo), "--pinned-commit", pinned,
                 "--tests-dir", str(repo / "tests"), "--no-default-parity",
                 "--parity-test", "tests/test_alpha.py::test_a1", "--expect-test", "test_a1"]

    def run(extra: list[str] | None = None) -> int:
        buf = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            return main(base_argv + list(extra or []) + ["--json", str(out_json)])
        finally:
            sys.stdout.close()
            sys.stdout = buf

    def now() -> dict:
        return json.loads(out_json.read_text(encoding="utf-8"))

    def fired(rep: dict) -> set:
        return {v["check"] for v in rep["violations"]}

    def arm(name: str, expect: set, extra: list[str] | None = None) -> None:
        code = run(extra)
        rep = now()
        assert code == 4, (name, code, rep.get("problems"), rep.get("violations"))
        assert fired(rep) == expect, (name, sorted(fired(rep)), sorted(expect))
        _mark(f"{name} → 只有 {sorted(expect)} 开火")

    assert run() == 0, now()["violations"]
    assert not now()["problems"]
    _mark("合规夹具不开火（对照：参数化条目、`*_test.py` 命名、类层用例都在名单里且 passed）")

    prist(evidence, nodeids, pinned, summary_overrides={"passed": 99})
    _bind_provenance(prov, report)
    arm("C2 注入：summary.passed 被改大", {"counts_counted_from_roster"})

    prist(evidence, nodeids, pinned, summary_overrides={"total": 99})
    _bind_provenance(prov, report)
    arm("C2 注入：summary.total 与名单条数不符（provenance 同口径抄了假汇总）",
        {"counts_counted_from_roster"})

    prist(evidence, [n for n in nodeids if n != "tests/beta_test.py::test_b1"], pinned)
    _bind_provenance(prov, report)
    arm("C4 注入：树上有文件一次都没被测", {"roster_covers_tree"})

    prist(evidence, nodeids + [nodeids[0]], pinned)
    _bind_provenance(prov, report)
    arm("C4 注入：报告里有重复 nodeid", {"roster_covers_tree"})

    prist(evidence, nodeids, "f" * 40)
    _bind_provenance(prov, report)
    arm("C5 注入：报告绑在别的提交上（STALE）", {"pinned_source_binding"})

    other = tmp / "other"        # 一座无关的历史：只让"祖先"那一支翻
    (other / "src").mkdir(parents=True, exist_ok=True)
    (other / "src/x.py").write_text("x = 1\n", encoding="utf-8")
    foreign = _git_init(other, "foreign")
    prist(evidence, nodeids, foreign)
    _bind_provenance(prov, report)
    arm("C5 注入：锚点在这棵树的历史之外（祖先那一支单独翻）",
        {"pinned_source_binding"}, ["--pinned-commit", foreign])

    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    arm("C7 注入：工作树有未提交改动", {"worktree_clean"})
    (repo / "dirty.txt").unlink()

    report.write_text(report.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    arm("C1 注入：报告字节动过而证据没重绑", {"report_bound_to_provenance"})

    prist(evidence, [n for n in nodeids if n != "tests/test_alpha.py::test_a1"], pinned)
    _bind_provenance(prov, report)
    arm("C6 注入：清单哈希替身用例没被测到", {"content_parity_measured"})

    prist(evidence, nodeids, pinned,
                     outcomes={"tests/test_alpha.py::test_a1[x=1]": "failed"})
    _bind_provenance(prov, report)
    arm("C3 注入：终态里有一条 failed", {"terminal_clean"})

    # 复位夹具：上一支留下的 failed 终态若不清掉，这一支会读出两格开火
    # （第 61 片同类坑——退码优先级会把"没复位"伪装成"判据开火"）
    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)
    arm("C8 注入：本轮原告不在测过的名单里", {"plaintiffs_measured"},
        ["--expect-test", "test_zzz_never_written"])

    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)
    arm("C9 注入：名单低于 --min-tests", {"size_ratchet"}, ["--min-tests", "50"])

    # ---- C10 / C11（第 83 片）：报告自证「测的是哪一份清单」----
    _pristine_report(evidence, nodeids, pinned)     # 故意不盖指纹＝第 83 片之前 conftest 的形状
    _bind_provenance(prov, report)
    arm("C10 注入：报告没带清单指纹", {"report_fingerprint_recorded"})
    assert now()["checks"]["report_fingerprint_matches_disk"]["kind"] == "skipped", \
        now()["checks"]["report_fingerprint_matches_disk"]
    _mark("报告没带指纹时只有 C10 开火，C11 读成「没有可比基准」而不是连带判红")

    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)
    drifted = json.loads(json.dumps(manifest_doc))
    drifted["files"].append({"path": "tests/test_beta.py", "size": 7, "sha256": "b" * 64})
    drift_path = tmp / "SOURCE_MANIFEST-drift.json"
    drift_path.write_text(json.dumps(drifted, ensure_ascii=False, indent=1), encoding="utf-8")
    arm("C11 注入：磁盘清单的内容与报告记的指纹不同（多一个文件条目）",
        {"report_fingerprint_matches_disk"}, ["--manifest", str(drift_path)])

    # 假红控制：`release_evidence.py:133` 每次生成都重写 `generated_at`，所以"只换时间戳"
    # 必须读成同一份清单——否则每轮「刷清单 → 跑全量 → 绑定」都会红在正常流程上。
    regen = json.loads(json.dumps(manifest_doc))
    regen["generated_at"] = "2026-01-01T00:00:00+00:00"
    regen_path = tmp / "SOURCE_MANIFEST-regen.json"
    regen_path.write_text(json.dumps(regen, ensure_ascii=False, indent=1), encoding="utf-8")
    assert _sha256_path(repo_manifest) != _sha256_path(regen_path), "夹具前提：两份字节得不同"
    assert run(["--manifest", str(regen_path)]) == 0, now()["violations"]
    _mark("原始字节不同而规范摘要相同 ⇒ 拿文件 sha256 当判据会给正常流程判一条假红；"
          "C11 用内容规范摘要，这一支必须绿")

    assert run(["--manifest", str(tmp / "nope.json")]) == 2, now()
    assert not now()["violations"], now()["violations"]
    _mark("磁盘清单读不出 → 退 2（前提塌），既不折算成「没违规」也不折算成判红")

    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)

    prist(evidence, [], pinned)
    _bind_provenance(prov, report)
    assert run() == 2, now()
    assert not now()["violations"], now()["violations"]
    _mark("报告 tests 为空 → 退 2（空读数不算绿：借 fail-on-empty，但升成前提档）")

    report.write_text("{ not json", encoding="utf-8")
    assert run() == 2
    _mark("报告读不出 → 退 2，不折算成「没违规」")

    # 证据没绑这份报告（重锚与绑定之间那段窗口，每轮收尾都要经过）：算前提塌，不算违规
    prist(evidence, nodeids, pinned)
    unbound = json.loads(prov.read_text(encoding="utf-8"))
    unbound["test_report"] = {"present": False, "path": str(report)}
    prov.write_text(json.dumps(unbound, ensure_ascii=False, indent=1), encoding="utf-8")
    code = run()
    rep = now()
    assert code == 2, (code, rep["violations"])
    assert not rep["violations"], rep["violations"]
    assert "provenance_binds_report" in rep["checks"], sorted(rep["checks"])
    assert "report_bound_to_provenance" not in rep["checks"], "没有基准那一格不该进判红面"
    assert "counts_counted_from_roster" in rep["checks"], "报告内部一致性仍可判，不因未绑定而整格消失"
    _mark("证据没绑这份报告 → 退 2（前提塌），C1 不进判红面而 C2 的 summary↔名单那一半照判")
    _bind_provenance(prov, report)

    prist(evidence, nodeids, pinned)
    _bind_provenance(prov, report)
    buf = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        code = main(["--report", str(report), "--provenance", str(prov),
                     "--worktree", str(repo), "--tests-dir", str(repo / "tests"),
                     "--json", str(out_json)])
    finally:
        sys.stdout.close()
        sys.stdout = buf
    assert code == 2, code
    _mark("没给 --pinned-commit 也没给 --tag → 退 2：没有基准就不判 STALE")

    print(f"--self-test：{len(marks)} 条合成读数全部对上")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="收尾验签：报告 ↔ 证据 ↔ 工作树")
    ap.add_argument("--report", default="", help="pytest JSON 报告（默认取 PROVENANCE 记的路径）")
    ap.add_argument("--provenance", default=str(ROOT / "PROVENANCE.json"))
    ap.add_argument("--worktree", default=str(ROOT), help="取证时那棵工作树")
    ap.add_argument("--tests-dir", default="", help="测试目录（默认 <worktree>/tests）")
    ap.add_argument("--pinned-commit", default="", help="发布锚点提交（不 re-anchor，按约定手给）")
    ap.add_argument("--tag", default="", help="或给 tag，由本仓库现解")
    ap.add_argument("--expect-test", action="append", default=[],
                    help="本轮新用例的子串，可多次")
    ap.add_argument("--parity-test", action="append", default=[],
                    help="追加替身用例 nodeid（默认两条清单哈希用例）")
    ap.add_argument("--no-default-parity", action="store_true",
                    help="不吃那两条默认替身（夹具仓库里没有 test_packaging.py 时用）")
    ap.add_argument("--min-tests", type=int, default=0)
    ap.add_argument("--manifest", default="",
                    help="被验那棵树里的 SOURCE_MANIFEST.json（默认取 <worktree> 下同名文件）")
    ap.add_argument("--json", default="", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))

    worktree = Path(args.worktree).resolve()
    tests_dir = Path(args.tests_dir).resolve() if args.tests_dir else worktree / "tests"
    prov_path = Path(args.provenance).resolve()
    pinned, err = _resolve_pinned(args, worktree)
    if not pinned:
        print(f"前提不成立：{err}")
        return 2
    prov, _ = _load_json(prov_path)
    report_arg = args.report or str((prov or {}).get("test_report", {}).get("path") or "")
    if not report_arg:
        print("前提不成立：PROVENANCE 里没有 test_report.path，也没给 --report")
        return 2
    parity = (list(args.parity_test) if args.no_default_parity
                else list(PARITY_TESTS) + list(args.parity_test))
    rep = audit(Path(report_arg).resolve(), worktree, prov_path, pinned,
                tests_dir, args.expect_test, parity, args.min_tests,
                Path(args.manifest).resolve() if args.manifest else None)
    print(render(rep))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    if rep["problems"]:
        return 2
    return 4 if rep["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
