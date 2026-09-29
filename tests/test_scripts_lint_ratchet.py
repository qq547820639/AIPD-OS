r"""`scripts/scripts_lint_ratchet.py` 的常驻牙（F-SCRIPT-LINT 第 100 片）。

这一片把 `scripts/` 接进 CI 的 lint 面，用**测量基线 + 棘轮**而不是 ruff 的
`per-file-ignores`。分五组，每档都配"开火"与"合规"两极：
① 量具必须被真的 spawn（条数下限 + 自报数与逐条打印行数两格同源）；
② 真仓库上分母非空、Σ(五档) == 并集、直连清单 == 今天的 0 债集合；
③ 四档判决各配一支合成注入（上涨 / 缺条目 / 该撤 / 未覆盖），外加"可下调只报不红"；
④ 前提塌两档（基线不在、语料空）读成退 2 而不是"零债"；
⑤ 基线这份生成件与判据共用同一次测量（不许手写数字进册子）。

`_mod()` 从**源码文本现编译**，不走字节码缓存：第 96 片实测过 `py_compile` 的缓存
会在"同长度变异 + 同秒还原"时把变异体当成有效源，于是判据读的是旧机器件、
`inspect.getsource` 读的是新源——两面各说各话。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "scripts_lint_ratchet.py"
BASELINE = ROOT / "docs" / "audit" / "SCRIPTS_LINT_BASELINE.json"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _mod() -> ModuleType:
    code = compile(TOOL.read_text(encoding="utf-8"), str(TOOL), "exec")
    spec = importlib.util.spec_from_loader("slr100", loader=None)
    assert spec is not None, "构造不出 ModuleSpec ⇒ 量具根本没被载入，别说它绿了"
    m = importlib.util.module_from_spec(spec)
    m.__file__ = str(TOOL)
    exec(code, m.__dict__)
    return m


slr = _mod()


def _spawn(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=600)


def _need_ruff() -> None:
    if importlib.util.find_spec("ruff") is None:
        import pytest
        pytest.skip("ruff 未安装——这一面在本环境未覆盖（不是绿）")


def _tree(tmp: Path, name: str, files: dict[str, str], face: list[str]) -> Path:
    # `slr` 是从源码文本 exec 出来的，类型层面只能是 Any ⇒ 这里按声明的 Path 收下，
    # 免得 Any 顺着返回值漏进后面的断言（mypy 的 no-any-return 正是拦这一手）。
    built: Path = slr._tree(tmp / name, files, face)
    return built


def test_instrument_self_test_is_actually_spawned_and_green() -> None:
    """没有这一条，`--self-test` 与"没有自测"在读片上不可区分（第 60 片的孤儿门禁）。"""
    _need_ruff()
    proc = _spawn("--self-test")
    assert proc.returncode == 0, proc.stdout[-2500:]
    marks = proc.stdout.count("✓立住")
    assert marks >= 9, f"--self-test 的臂从 9 条缩水成 {marks} 条：注入没跑满就别谈判据"
    # 第 99 片的教训原样用在这里：逐条打印是无条件的，工具自报的总数才跟着注入走。
    tail = [ln for ln in proc.stdout.splitlines() if "条合成读数全部对上" in ln]
    assert len(tail) == 1, tail
    stated = int(tail[0].split("：")[1].split()[0])
    assert stated == marks, (stated, marks)


def test_real_repo_face_is_live_and_buckets_sum_to_the_union() -> None:
    _need_ruff()
    rep = slr.audit(ROOT)
    assert not rep["problems"], rep["problems"]
    assert not rep["violations"], rep["violations"]
    c, b = rep["corpus"], rep["buckets"]
    assert c["py_files"] >= 50 and c["hits"] > 500, c
    assert c["zero_files"] >= 15 and c["face_files"] == c["zero_files"], c
    assert b["rose"] == b["unregistered"] == b["paid"] == 0, b
    assert b["equal"] + b["rose"] + b["unregistered"] + b["paid"] + b["shrunk"] == b["rows"], b
    rc = _spawn("--repo", str(ROOT)).returncode
    assert rc == (0 if rep["ok"] else 4), (rc, rep["ok"])


def test_the_face_now_reaches_scripts_and_the_ci_command_is_clean() -> None:
    """接面的两件事都要看得见：清单非空、且这条命令在本地逐字跑得出 rc=0。"""
    _need_ruff()
    line = [ln.strip()[len("run: "):] for ln in CI.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("run: ruff check")]
    assert len(line) == 1, line
    toks = line[0].split()
    named = [t for t in toks[2:] if t.startswith("scripts/")]
    assert len(named) >= 15, len(named)
    assert len(named) == len(set(named)), "ci.yml 点名了重复文件 ⇒ 前缀锚把清单贴了两遍"
    proc = subprocess.run([sys.executable, "-m", "ruff", "check", "--no-cache",
                           "--output-format", "concise", *toks[2:]],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout[:800]


def test_a_rising_cell_fires_the_ratchet(tmp_path: Path) -> None:
    """棘轮这一格必须打得响：登记 4 而今天 6 ⇒ 判红；而持平的那几格不许陪红。"""
    _need_ruff()
    tree = _tree(tmp_path, "rose", slr.BASE, slr.FACE)
    assert slr.emit(tree) == 0
    (tree / "scripts/debt.py").write_text(slr.DEBT3, encoding="utf-8")
    rep = slr.audit(tree)
    fired = {(v["field"], v["file"]) for v in rep["violations"]}
    assert fired == {("lint面债上涨", "scripts/debt.py")}, fired


def test_a_brand_new_code_is_not_read_as_zero_rise(tmp_path: Path) -> None:
    """两档不能塌成一档：文件在清单里而"这一格"不在 ⇒ 走缺条目，不是把登记值当 0 算上涨。"""
    _need_ruff()
    tree = _tree(tmp_path, "unreg", slr.BASE, slr.FACE)
    assert slr.emit(tree) == 0
    (tree / "scripts/third.py").write_text(slr.IMPORTED, encoding="utf-8")
    fired = {(v["field"], v["file"], v["code"]) for v in slr.audit(tree)["violations"]}
    assert ("lint面基线缺条目", "scripts/third.py", "F401") in fired, fired
    assert ("lint面文件未覆盖", "scripts/third.py") not in fired, fired


def test_paid_off_debt_makes_the_register_shrink(tmp_path: Path) -> None:
    """债偿完不是"从此太平"：那一行要从册子里撤掉，同时这个文件该被接进 ci.yml。"""
    _need_ruff()
    tree = _tree(tmp_path, "paid", slr.BASE, slr.FACE)
    assert slr.emit(tree) == 0
    for f in ("debt.py", "semi.py", "third.py"):
        (tree / "scripts" / f).write_text(slr.CLEAN, encoding="utf-8")
    fired = {(v["field"], v["file"]) for v in slr.audit(tree)["violations"]}
    assert ("lint面基线该撤", "scripts/debt.py") in fired, fired
    assert ("lint面直连清单不同源", slr.CI_REL) in fired, fired


def test_looser_register_than_reality_is_reported_not_judged(tmp_path: Path) -> None:
    """只报不红那一档：现实比登记紧不是原告，但必须在读数里点名（不许静默）。"""
    _need_ruff()
    tree = _tree(tmp_path, "shrunk", slr.BASE, slr.FACE)
    assert slr.emit(tree) == 0
    (tree / "scripts/debt.py").write_text(slr.DEBT1, encoding="utf-8")
    rep = slr.audit(tree)
    assert rep["ok"], rep["violations"]
    assert rep["buckets"]["shrunk"] == 1 and rep["outside"], rep


def test_premise_missing_baseline_is_not_zero_debt(tmp_path: Path) -> None:
    """读不到基线 ⇒ 退 2。把"没有册子"读成"没有债"就是这把尺自己的假绿。"""
    _need_ruff()
    tree = _tree(tmp_path, "nop", slr.BASE, slr.FACE)
    assert slr.emit(tree) == 0
    (tree / slr.BASELINE_REL).unlink()
    rep = slr.audit(tree)
    assert any(p.startswith("baseline_missing") for p in rep["problems"]), rep["problems"]
    assert slr.main(["--repo", str(tree)]) == 2


def test_empty_corpus_is_refused_by_emit_too(tmp_path: Path) -> None:
    _need_ruff()
    empty = _tree(tmp_path, "empty", {}, slr.FACE)
    assert any(p.startswith("corpus_empty") for p in slr.audit(empty)["problems"])
    assert slr.main(["--repo", str(empty)]) == 2
    assert slr.emit(_tree(tmp_path, "empty2", {}, [])) == 2, "空语料时 --emit 必须拒写"


def test_baseline_is_a_product_not_a_hand_written_number() -> None:
    """生成件与判据必须同源：册子里的数就是这一次测量重算出来的数。"""
    _need_ruff()
    raw = json.loads(BASELINE.read_text(encoding="utf-8"))
    hits, files, problems = slr.measure(ROOT)
    assert not problems, problems
    reg = {(e["file"], e["code"]): int(e["count"]) for e in raw["entries"]}
    assert reg == dict(hits), (sorted(set(reg.items()) - set(hits.items())),
                               sorted(set(hits.items()) - set(reg.items())))
    assert sorted(raw["files"]) == files, "文件清单与语料不同源"
    assert raw["totals"]["hits"] == sum(hits.values()), raw["totals"]
