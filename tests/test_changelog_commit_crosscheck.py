"""条目↔提交对账的常驻门禁（F-CHANGELOG-ENTRY-CROSSCHECK 第 104 片）。

这把尺回答一句 CHANGELOG 自己答不出的话：**这一片的账，落地了吗？**
`tests/test_changelog_integrity.py` 那两把尺都是自洽型的（重复块 / 记号唯一），
条目整条缺席时记号数与口径数一起少，两边照样相等 ⇒ 永绿。2026-09-29 一天之内撞两次
（v5.62 标题被吃、v5.64 整条没写），两次四道文档门全绿，最后是 `git show --stat` 读出来的。
所以第四源取仓库历史的主题行，而不是文档自身。

这里必须钉住的四格：

1. **真树 0 缺席**（判红档）：主题里点名过的片号都要有条目。
2. **牙口**：两支真历史 Blob 必须被点名——事故现场当夹具，不靠合成语料自证。
3. **反向不误伤**：条目侧比提交侧多出来的那些片（`sNN` 主题约定之前的轮次）不是原告。
4. **尺子自己能红**：`--self-test` 由子进程真 spawn，只被文本提到不算跑过。

分母一律现算，且只钉下界与"这一档看得见非零对象"，不抄绝对数（抄了就会漂）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "changelog_commit_crosscheck.py"
sys.path.insert(0, str(ROOT / "scripts"))

import changelog_commit_crosscheck as rcc  # noqa: E402


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        pytest.skip(f"git {args[0]} 读不到（{proc.stderr.strip()[:60]}）⇒ 本用例未覆盖，不是通过")
    return proc.stdout


def test_real_tree_has_no_absent_entry() -> None:
    """现读：提交历史点名的每一片，CHANGELOG 都要有条目行。"""
    rep = rcc.emit(rcc.audit(ROOT))
    assert rep["premise_broken"] is False, f"前提塌：{rep['problems']}"
    assert rep["absent"] == [], f"这些片有提交、没条目：{rep['defects']}"
    assert rep["caliber_diverge"] == [], f"这些条目不带 F- 号：{rep['caliber_diverge']}"


@pytest.mark.parametrize("blob, victim", [
    ("35ef6fc", 101),   # 第 102 片：插 v5.63 时锚在 v5.62 标题上，标题被吃
    ("629de86", 103),   # 第 103 片：v5.64 整条从没写进去
])
def test_two_real_incidents_are_named_by_the_ruler(blob: str, victim: int) -> None:
    """开火控制用真历史 Blob，不用编出来的夹具。

    这两支是「判据有牙」的唯一硬证据：同一段代码喂今天的树判 0 缺席，喂当时那一份
    `CHANGELOG.md` 必须点名victim 那一片。缺一支，就说明这把尺在真事故上不开火。
    """
    text = _git("show", f"{blob}:CHANGELOG.md")
    assert text.startswith("# Changelog"), "Blob 读到的不是 CHANGELOG 正文"
    subjects = _git("log", "--format=%s", blob).splitlines()
    rep = rcc.emit(rcc.audit(ROOT, subjects=subjects, changelog=text))
    assert victim in rep["absent"], f"{blob} 上第 {victim} 片没被抓到：{rep}"


def test_direction_is_one_way_only() -> None:
    """条目侧多出来的片号不是原告（`sNN` 主题约定之前的轮次全在这一档里）。"""
    rep = rcc.emit(rcc.audit(ROOT))
    assert rep["counts"]["extra"] > 0, "反向那一档一个对象都没有 ⇒ 这条判决是空的"
    assert rep["counts"]["commit"] >= 53, f"提交侧分母塌了：{rep['counts']}"
    assert rep["counts"]["entry"] >= 101, f"条目侧分母塌了：{rep['counts']}"


def test_multi_slice_back_reference_is_seen_not_judged() -> None:
    """回指写法（一行点名两片）必须数得出来，但不能因此判红。

    只报不判是量出来才这么定的：真语料实测 6 行这么写。若哪天数到 0，
    说明逐行取片号退回了"只取首枚"，第二枚就会从所有下游读数里静默消失。
    """
    rep = rcc.emit(rcc.audit(ROOT))
    assert rep["counts"]["multi_slice_lines"] >= 1, "一行点名多片这一档看不见对象了"
    assert rep["ok"] is True, f"只报不判的档把结论带红了：{rep['defects']}"


def test_self_test_is_actually_run() -> None:
    """`--self-test` 必须真被 spawn，且自报条数与实读标记数一致。"""
    proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--self-test"],
                          capture_output=True, text=True, check=False)
    out = proc.stdout
    assert proc.returncode == 0, f"合成语料没全立住：{out}{proc.stderr[-400:]}"
    stated = [line for line in out.splitlines() if "判据读数" in line]
    assert len(stated) == 1, f"自报行应当恰好一条，实得 {stated}"
    assert "全部对上" in stated[0]
    assert out.count("✓立住") == int(stated[0].split("上")[1].split("条")[0]), out
