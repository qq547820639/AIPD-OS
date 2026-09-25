"""文档代码引用普查的常驻门禁（F-DOC-REF 第 41 片）。

`scripts/doc_reference_census.py` 回答一句很小的话：**文档里写出来的
`path/to/file.py[:123]`，今天还指得回盘上的东西吗？** 它抓到的第一条真缺陷
是我自己上一轮写进 CHANGELOG 的一个不存在的文件名，所以这条轴值得常驻，
而不是一次性普查。

三件事必须钉住：

1. **现状面为 0**：README / SKILL / docs 架构面 / references 里的代码引用必须解析得到。
   这是判红档。
2. **历史面不能被拿来藏现状缺陷**：`CHANGELOG.md` 与 `docs/audit/**` 记的是当时的事实，
   只报不判、不改写；但"哪些文档算历史"这件事本身要被核——
   把 README 挪进历史名单就等于把门禁关掉（注入反证 D3 打的正是这一格）。
3. **尺子自己能红**：`--self-test` 的 20 条合成读数必须全立住，且由本文件**子进程真 spawn**
   （只被文本提到不算跑过）。

分母不手抄：引用总数、分类 Σ、文档份数一律现算，Σ 对不上就判「读数不可信」。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import doc_reference_census as census  # noqa: E402


@pytest.fixture(scope="module")
def report() -> dict:
    rep: dict = census.audit(ROOT)
    return rep


def test_live_docs_have_no_dead_code_references(report) -> None:
    """现状面：文档写出的代码引用必须全部解析得到（行号还得在文件行数内）。"""
    assert report["live_defects"] == [], f"指不回事实的引用：{report['live_defects']}"
    assert report["ok"] is True, report["problems"]


def test_reading_is_not_vacuous(report) -> None:
    """判据得真读到语料；空循环不算绿（分母全部现算）。"""
    assert report["docs"] > 100, f"只读了 {report['docs']} 份文档"
    assert report["denominator"] > 2000, f"只解析出 {report['denominator']} 处引用"
    assert sum(report["buckets"].values()) == report["denominator"]
    assert report["buckets"].get("resolved", 0) > 2000, "几乎没解析成功 ⇒ 判据在空转"


def test_history_face_cannot_swallow_the_live_face(report) -> None:
    """豁免名单是门禁的一部分：现状面文档绝不允许被划成历史。"""
    for doc in ("README.md", "SKILL.md", "docs/architecture/state_inventory.md",
                "references/state-model.md"):
        assert not census._is_history(doc), f"{doc} 被划进历史面 ⇒ 现状判红形同关闭"
    for doc in ("CHANGELOG.md", "docs/audit/x.md"):
        assert census._is_history(doc), f"{doc} 应当按历史面处理（只报不判）"
    live = {d[0] for d in map(tuple, report["live_defects"])}
    assert not any(census._is_history(d) for d in live), "历史面缺陷混进了现状判红清单"


def test_history_face_is_reported_not_silently_zero(report) -> None:
    """历史面确有读数在流动（今天 >100 条）；把它静默清零等于把这一面关掉。"""
    assert len(report["history_defects"]) > 100, len(report["history_defects"])
    assert report["buckets"].get("missing", 0) >= len(report["history_defects"])


def test_instrument_self_test_runs_and_is_green() -> None:
    """尺子自己必须能红：子进程真跑 --self-test，并核它报的是"全部立住"。"""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "doc_reference_census.py"), "--self-test"],
        capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条合成读数全部对上" in proc.stdout, proc.stdout
    assert "✗" not in proc.stdout, proc.stdout


def test_json_artifact_matches_in_process_reading(tmp_path, report) -> None:
    """落盘读数与内存读数同源（产物路径本身就是判据的一部分）。"""
    out = tmp_path / "docrefs.json"
    assert census.main(["--repo", str(ROOT), "--json", str(out)]) in (0, 4)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["live_defects"] == report["live_defects"]
    assert on_disk["denominator"] == report["denominator"]
    assert on_disk["buckets"] == report["buckets"]


def test_multi_and_missing_are_kept_apart(report) -> None:
    """简写歧义只报不判，真指不回才判红——两档混了就等于要么误伤要么放过。"""
    assert report["buckets"].get("multi", 0) > 100, "multi 档读空 ⇒ 简写全被判红了？"
    for doc, target, line in (tuple(x) for x in report["live_defects"]):
        assert target, (doc, line)
