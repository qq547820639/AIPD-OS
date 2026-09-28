"""绑定前那道闸的常驻牙（F-BIND-PREFLIGHT 第 84 片）。

`release_evidence.py` 现在带 `--test-report` 时，必须在**任何落盘动作之前**核对
"报告自记的清单指纹 == 即将写出的这份清单的内容摘要"，不符就退 2 且不写任何文件。
这一片的存在理由：第 83 片把 C10 从判红改成前提塌（判红会自锁），于是"缺字段"这一判
在验签侧只剩下"挡配方"的分量——真正的拦截必须回到写入侧，否则守的还是"我记得跑那一步"。

两极都要钉：坏形状按形状逐档（路径不在 / 报告读不出 / 没字段 / 内容不同源），
其中前两档是 `_parse_pytest_report` 的两种返回、文案必须逐字不同（把"路径不存在"说成
"present 但 parsed=false"就是把操作员最容易犯的那件事说错了）；
合规侧要证"只换 `generated_at` 照样能绑"（否则每轮正常收尾都被自己拒掉），
还要证**拒写不半写**（树里已经躺着的证据不许被动过一半）。

本文件后来成为"绑定前拒绝"这一族的落点：第 86 片把 `--source-commit` 提成操作员必填、
第 88 片把同一半闸推到 `write_evidence()` 的 API 侧，两族各带自己的合规侧（见下面分节）。
"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence as ev  # noqa: E402
import release_fingerprint as rf  # noqa: E402

TOOL = ROOT / "scripts" / "release_evidence.py"
ANCHOR = "a" * 40


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text('[project]\nname = "aipd-os"\nversion = "5.6.0"\n',
                                         encoding="utf-8")
    for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-q", "-m", "seed"]):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return repo


def _report(tmp_path: Path, fingerprint: str | None) -> Path:
    payload = {"exitcode": 0, "source_commit": ANCHOR, "package_version": "5.6.0",
               "summary": {"passed": 3, "total": 3, "collected": 3},
               "tests": [{"nodeid": "tests/test_x.py::test_a", "outcome": "passed"}]}
    if fingerprint:
        payload["source_manifest_fingerprint"] = fingerprint
    out = tmp_path / "report.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _want(repo: Path) -> str:
    doc = ev.generate_source_manifest(repo, ANCHOR)
    doc["version"] = "5.6.0"
    return rf.fingerprint_of_document(doc)


def _bind(tmp_path: Path, repo: Path, out_dir: Path, report: Path | None):
    """跑 main() 并把 stdout 收回来（不用 capsys：main 走的是同一进程的 print）。"""
    import io
    saved = sys.stdout
    buffer = io.StringIO()
    sys.stdout = buffer
    try:
        rc = ev.main(["--repo", str(repo), "--out", str(out_dir),
                      "--source-commit", ANCHOR]
                     + (["--test-report", str(report)] if report is not None else []))
    finally:
        sys.stdout = saved
    return rc, buffer.getvalue()


def _verdict(text: str) -> str:
    """取回 main() 打印的那句判决本身（剥掉公共前缀），好逐字比两档文案。

    前缀只含一个全角冒号，所以 `split("：", 1)[1]` 拿到的就是异常消息（含换行）。
    前缀没命中时这条 helper 会响亮地失败，而不是把整行吐回去冒充"判决"。
    """
    assert "拒绝写入证据" in text, text
    return text.split("：", 1)[1].strip()


def test_refuses_a_report_without_the_fingerprint_and_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, _report(tmp_path, None))
    assert rc == 2, (rc, text)
    assert "source_manifest_fingerprint" in text, text
    assert not (out / "SOURCE_MANIFEST.json").exists(), "拒写必须发生在任何落盘动作之前"
    assert not (out / "PROVENANCE.json").exists()
    assert not out.exists(), "被拒之后连输出目录都不该建（mkdir 已挪到闸之后）"


def test_refuses_when_the_manifest_content_moved_after_the_run(tmp_path: Path) -> None:
    """跑完之后改了参与哈希的内容 ⇒ 报告测的是旧那份，这份证据不许绑上去。"""
    repo = _repo(tmp_path)
    want = _want(repo)
    (repo / "src" / "late.py").write_text("late = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "内容动了"],
                   capture_output=True, check=True)
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, _report(tmp_path, want))
    assert rc == 2, (rc, text)
    assert "!= 即将写出的这份清单" in text, text
    assert not (out / "SOURCE_MANIFEST.json").exists()


def test_refuses_an_unparsable_report(tmp_path: Path) -> None:
    """present 但 parsed=false：没有可比对象也只能拒，不能把"读不出"写成一条通过的证据。"""
    repo = _repo(tmp_path)
    junk = tmp_path / "junk.json"
    junk.write_text("{ not json", encoding="utf-8")
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, junk)
    assert rc == 2, (rc, text)
    assert "读不出" in text, text
    assert not (out / "PROVENANCE.json").exists()


def test_refuses_a_report_path_that_is_not_a_file_and_names_it(tmp_path: Path) -> None:
    """`--test-report` 打错一个字母是操作员最容易犯的一档：这一档必须点名路径。"""
    repo = _repo(tmp_path)
    missing = tmp_path / "no-such-report.json"
    assert not missing.exists(), "夹具前提：这一条测的就是路径不存在"
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, missing)
    assert rc == 2, (rc, text)
    # main() 先把旗子值 resolve() 再交给 `_parse_pytest_report`，
    # 所以断的是解析后的全路径（macOS 上 tmp_path 会把 /var 解成 /private/var）。
    assert str(missing.resolve()) in text, text
    assert "不是可读文件" in text, text
    assert "parsed=false" not in text, text
    assert not (out / "SOURCE_MANIFEST.json").exists(), "拒写必须发生在任何落盘动作之前"
    assert not (out / "PROVENANCE.json").exists()
    assert not out.exists(), "被拒之后连输出目录都不该建（mkdir 已挪到闸之后）"


def test_missing_path_and_unparsable_report_get_different_verdicts(tmp_path: Path) -> None:
    """本轮改的就是这一格：两档形状共用一句文案时，其中一句必然是错的。"""
    repo = _repo(tmp_path)
    junk = tmp_path / "junk.json"
    junk.write_text("{ not json", encoding="utf-8")
    missing = tmp_path / "no-such-report.json"
    rc_junk, text_junk = _bind(tmp_path, repo, tmp_path / "out-junk", junk)
    rc_miss, text_miss = _bind(tmp_path, repo, tmp_path / "out-miss", missing)
    assert (rc_junk, rc_miss) == (2, 2), (rc_junk, rc_miss)
    unparsable, not_found = _verdict(text_junk), _verdict(text_miss)
    assert unparsable != not_found, (unparsable, not_found)
    # 文件在、JSON 坏：说"读不出/parsed=false"是准确的，但不得谎报文件不在
    assert "读不出" in unparsable and "parsed=false" in unparsable, unparsable
    assert "不是可读文件" not in unparsable, unparsable
    # 路径不在：得点名是哪个路径，且不得谎报成解析失败
    assert "不是可读文件" in not_found, not_found
    assert str(missing.resolve()) in not_found, not_found
    assert "parsed=false" not in not_found and "解析" not in not_found, not_found


def test_binds_and_records_the_fingerprint_when_it_matches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    want = _want(repo)
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, _report(tmp_path, want))
    assert rc == 0, (rc, text)
    prov = json.loads((out / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert prov["test_report"]["source_manifest_fingerprint"] == want, prov["test_report"]
    disk, err = rf.fingerprint_from_file(out / "SOURCE_MANIFEST.json")
    assert err == "" and disk == want, (disk, err)


def test_only_generated_at_moving_still_binds(tmp_path: Path) -> None:
    """假红控制：清单每次重生都换 `generated_at`，那种"变化"不许拒掉正常流程。"""
    repo = _repo(tmp_path)
    doc = ev.generate_source_manifest(repo, ANCHOR)
    doc["version"] = "5.6.0"
    stale = copy.deepcopy(doc)
    stale["generated_at"] = "2001-01-01T00:00:00+00:00"
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, _report(tmp_path, rf.fingerprint_of_document(stale)))
    assert rc == 0, (rc, text)
    assert (out / "PROVENANCE.json").is_file()


def test_refusal_does_not_touch_evidence_already_on_disk(tmp_path: Path) -> None:
    """拒写必须"整批不写"：先合法绑一次，再拿一份坏报告去绑，树上的字节一个不许动。"""
    repo = _repo(tmp_path)
    out = tmp_path / "out"
    want = _want(repo)
    assert _bind(tmp_path, repo, out, _report(tmp_path, want))[0] == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    # 分母不许是空集：`after == before` 在两边都空时恒真，那等于什么都没判
    assert len(before) >= 2, f"夹具前提：合规那一跑至少要落下东西，实得 {sorted(before)}"
    assert "SOURCE_MANIFEST.json" in before and "PROVENANCE.json" in before, sorted(before)
    (repo / "src" / "more.py").write_text("more = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "又动了"],
                   capture_output=True, check=True)
    rc, _text = _bind(tmp_path, repo, out, _report(tmp_path, want))
    assert rc == 2, rc
    after = {p.name: p.read_bytes() for p in out.iterdir()}
    assert after == before, "拒写之后磁盘上的证据必须与拒写前逐字节相同（不许半写）"


def test_path_without_test_report_is_not_gated(tmp_path: Path) -> None:
    """配方第一步"刷清单不带报告"必须照走：那道闸只吃带 `--test-report` 的那一步。"""
    repo = _repo(tmp_path)
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, None)
    assert rc == 0, (rc, text)
    assert (out / "SOURCE_MANIFEST.json").is_file()


def test_gate_is_wired_into_write_evidence_before_any_write() -> None:
    """接线断言：`write_evidence` 里那个 `if test_report is not None:` 的体内必须调 preflight，
    而且这个 if 节点必须排在第一个 `.write_text(` 之前——否则"闸在文件里"是句空话。"""
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "write_evidence")
    guard = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and "test_report is not None" in ast.unparse(n.test)]
    assert len(guard) == 1, (f"闸的 if 节点应当恰好一个，实得 {len(guard)}；"
                             f"函数体首行：{ast.unparse(fn.body[0])[:120]}")
    body_src = "\n".join(ast.unparse(s) for s in guard[0].body)
    assert "preflight_report_vs_source" in body_src, body_src[:300]
    # 只盯 `write_text` 会漏掉别的落盘面（`write_bytes` / `open(...,'w')` / `mkdir`）：
    # 闸排在这些之前同样是半写。`mkdir` 不是比喻——它一度真的是第一处副作用。
    SINKS = {"write_text", "write_bytes", "mkdir", "mkdirat", "open"}
    writes = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
              and (getattr(n.func, "attr", None) in SINKS or getattr(n.func, "id", None) in SINKS)]
    assert writes, "write_evidence 里没有任何落盘动作，这条接线断言是空的"
    first_write = min(n.lineno for n in writes)
    needle = "preflight_report_vs_source"
    call = next(n for n in ast.walk(guard[0]) if isinstance(n, ast.Call)
                and needle in {getattr(n.func, "id", ""), getattr(n.func, "attr", "")})
    assert call.lineno < first_write, (call.lineno, first_write)


# ---------------------------------------------------------------------------
# 第 86 片：锚点不许默认成 HEAD。
# 第 52 片与第 62 片两次实测记录的是同一件事——少给 `--source-commit` 不报错，
# 只把 `SOURCE_MANIFEST.source_commit` 写成当时的 HEAD；下一轮绑定才读成"清单被改过"。
# 第 84 片的指纹闸顺带拦住了**带报告**那一支，**不带报告的配方第一步**仍是静默通道。


def test_refuses_without_source_commit_on_both_paths(tmp_path: Path) -> None:
    """两条入口都要拒：带报告那一支（今天靠指纹闸恰好也拦）与不带报告那一支（此前静默）。"""
    repo = _repo(tmp_path)
    for extra in ([], ["--test-report", str(_report(tmp_path, _want(repo)))]):
        out = tmp_path / f"out{len(extra)}"
        import io
        buf, saved = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = ev.main(["--repo", str(repo), "--out", str(out), "--version", "5.6.0"] + extra)
        finally:
            sys.stdout = saved
        assert rc == 2, (extra, buf.getvalue())
        assert "必须显式给出" in buf.getvalue(), buf.getvalue()
        assert not out.exists(), "被拒时连输出目录都不该建（锚点校验也排在任何落盘之前）"


def test_refuses_a_malformed_source_commit(tmp_path: Path) -> None:
    """40 位以外的值也拒：两个读者按逐字相等判，截断 SHA 不会报错、只会永远判红。"""
    repo = _repo(tmp_path)
    for bad in ("a660405", "z" * 40, " " + "a" * 39):
        out = tmp_path / "out"
        import io
        buf, saved = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = ev.main(["--repo", str(repo), "--out", str(out), "--version", "5.6.0",
                          "--source-commit", bad])
        finally:
            sys.stdout = saved
        assert rc == 2, (bad, buf.getvalue())
        assert "不是 40 位十六进制" in buf.getvalue(), buf.getvalue()


def test_explicit_anchor_lands_verbatim_and_is_not_head(tmp_path: Path) -> None:
    """合规侧：显式锚点必须逐字落进清单，且不等于该仓库的 HEAD——否则"必填"只是仪式。"""
    repo = _repo(tmp_path)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    anchor = "b" * 40
    assert anchor != head, "夹具前提：锚点要与 HEAD 不同形，否则这条测不出"
    out = tmp_path / "out"
    import io
    buf, saved = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        rc = ev.main(["--repo", str(repo), "--out", str(out), "--version", "5.6.0",
                      "--source-commit", anchor])
    finally:
        sys.stdout = saved
    assert rc == 0, buf.getvalue()
    for name in ("SOURCE_MANIFEST.json", "PROVENANCE.json"):
        doc = json.loads((out / name).read_text(encoding="utf-8"))
        assert doc["source_commit"] == anchor, (name, doc["source_commit"])


# ---------------------------------------------------------------------------
# 第 88 片：同一半闸的 API 侧。
# 第 86 片关的是操作员入口，`write_evidence()` 的 `source_commit` 仍带 `= None` 默认，
# 而 `generate_source_manifest` / `generate_provenance` 里那句
# `source_commit or _default_source_commit(repo)` 会把它静默写成当时的 HEAD——
# 锚点是清单内容的一部分，所以这条通道不当场报错，只在下一轮绑定读成"清单被改过"。
# `generate_*` 那一层的默认值**有意保留**：`production_release_gate` 的
# `source_manifest_zero_diff` 要按"当前树"现算一份清单再比 (path, sha256)，
# 它不消费锚点；收紧到必填只会让那把尺在没有 tag 的树上无路可走。


def test_api_has_no_anchor_default(tmp_path: Path) -> None:
    """少传锚点是 `TypeError`，不是"按 HEAD 算一份"：默认值本身已被删掉。"""
    repo = _repo(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(TypeError) as exc:
        ev.write_evidence(repo, out, "5.6.0", None, None)  # type: ignore[call-arg]
    assert "source_commit" in str(exc.value), str(exc.value)
    assert not out.exists(), "签名面失败时也不该留半个目录"


@pytest.mark.parametrize("bad", [None, "", "a660405", "z" * 40, " " + "a" * 39])
def test_api_refuses_a_malformed_anchor_before_any_write(tmp_path: Path, bad) -> None:
    """显式传 `None`／空串／短 SHA／非十六进制都在任何落盘之前抛 `BindPreflightError`。

    用 `out` 目录不存在来判"排在 mkdir 之前"：本函数原来的形状正是先 `mkdir` 再算，
    第 84 片为此专门把两阶段顺序钉过一次（`test_gate_is_wired_into_write_evidence_before_any_write`）。
    """
    repo = _repo(tmp_path)
    out = tmp_path / "out"          # tmp_path 每个参数化实例都是新目录，不必再拼唯一名
    with pytest.raises(ev.BindPreflightError) as exc:
        ev.write_evidence(repo, out, "5.6.0", None, None, bad)
    assert "40 位十六进制" in str(exc.value), str(exc.value)
    assert not out.exists(), str(exc.value)


def test_api_writes_the_explicit_anchor_verbatim_and_it_is_not_head(tmp_path: Path) -> None:
    """合规侧：走 API 的显式锚点逐字落进两份清单，且不等于该仓库 HEAD。

    没有这一支，"必填"可能只是把一个错误的值传到底——本仓第 62 片就是这么红的。
    """
    repo = _repo(tmp_path)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    anchor = "c" * 40
    assert anchor != head, "夹具前提：锚点要与 HEAD 不同形，否则这条测不出"
    out = tmp_path / "out"
    got = ev.write_evidence(repo, out, "5.6.0", None, None, anchor)
    assert set(got) >= {"SOURCE_MANIFEST.json", "PROVENANCE.json"}, sorted(got)
    for name in ("SOURCE_MANIFEST.json", "PROVENANCE.json"):
        doc = json.loads((out / name).read_text(encoding="utf-8"))
        assert doc["source_commit"] == anchor, (name, doc["source_commit"])
        assert doc["source_commit"] != head, name
