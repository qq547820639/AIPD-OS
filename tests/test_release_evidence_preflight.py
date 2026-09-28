"""绑定前那道闸的常驻牙（F-BIND-PREFLIGHT 第 84 片）。

`release_evidence.py` 现在带 `--test-report` 时，必须在**第一个字节落盘之前**核对
"报告自记的清单指纹 == 即将写出的这份清单的内容摘要"，不符就退 2 且不写任何文件。
这一片的存在理由：第 83 片把 C10 从判红改成前提塌（判红会自锁），于是"缺字段"这一判
在验签侧只剩下"挡配方"的分量——真正的拦截必须回到写入侧，否则守的还是"我记得跑那一步"。

两极都要钉：坏形状按形状逐档（没字段 / 内容不同源 / 报告读不出），
合规侧要证"只换 `generated_at` 照样能绑"（否则每轮正常收尾都被自己拒掉），
还要证**拒写不半写**（树里已经躺着的证据不许被动过一半）。
"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

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


def test_refuses_a_report_without_the_fingerprint_and_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    out = tmp_path / "out"
    rc, text = _bind(tmp_path, repo, out, _report(tmp_path, None))
    assert rc == 2, (rc, text)
    assert "source_manifest_fingerprint" in text, text
    assert not (out / "SOURCE_MANIFEST.json").exists(), "拒写必须在一个字节落盘之前"
    assert not (out / "PROVENANCE.json").exists()


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
    assert len(guard) == 1, ast.dump(fn.test if hasattr(fn, "test") else guard[0].test)[:200]
    body_src = "\n".join(ast.unparse(s) for s in guard[0].body)
    assert "preflight_report_vs_source" in body_src, body_src[:300]
    writes = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr == "write_text"]
    assert writes, "write_evidence 里没有写盘调用，这条接线断言是空的"
    first_write = min(n.lineno for n in writes)
    needle = "preflight_report_vs_source"
    call = next(n for n in ast.walk(guard[0]) if isinstance(n, ast.Call)
                and needle in {getattr(n.func, "id", ""), getattr(n.func, "attr", "")})
    assert call.lineno < first_write, (call.lineno, first_write)
