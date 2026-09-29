#!/usr/bin/env python3
"""CHANGELOG 条目 ↔ 提交历史：这一片的账到底落没落地（F-CHANGELOG-ENTRY-CROSSCHECK 第 104 片）。

为什么要有这根轴（本轮真实来由）：`tests/test_changelog_integrity.py` 那两把尺都是**自洽型**的
——一把问"同样的连续行有没有出现两次"，一把问"记号三元组在全文件唯一"。条目**整条缺席**时
记号数与口径数一起往下走，两边照样相等、照样唯一 ⇒ 门永绿。2026-09-29 一天之内撞两次：
第 102 片插 v5.63 时锚在 v5.62 标题行上却没重贴标题（正文留下、标题被吃），第 103 片那条
v5.64 **整条从没写进去**（`grep '5.64'` 与 `第 103 片` 各自 0 命中），两次四道文档门全绿，
最后是靠 `git show --stat` 读出一笔 feat 提交对 `CHANGELOG.md` 只有 1 行增才现形的。

判据不看文档自己，看另一张独立名册：**提交历史的主题行**。

- `absent`：主题里以 `s<NN>` 出现过的片号，CHANGELOG 必须有一行 `- **v…` 条目带着 `第 <NN> 片`。
- 反向不算：条目侧比提交侧多出来的片号一律不是原告——今天条目侧 102 个、提交侧 52 个，
  差的 50 个是 `sNN` 主题约定之前的轮次，反向判据会把它们全部误伤。
- `caliber-diverge`：宽松口径（只认 `第 NN 片`）与严格口径（要求同时带 `F-` 号）在
  **提交侧那些片号**上读数不一致 ⇒ 判红并点名。落笔取宽松是因为它少一种假红形状；
  这条对账保证"将来出现只被宽松认到的写法"当场可见，而不是悄悄少认。
- 只报不判：一行条目点名 ≥2 片（回指写法）单独报数。这一档是本轮量出来才降级成"报"的——
  真语料 `CHANGELOG.md` 实测有 6 行这么写（如「第 13 片：… 补第 12 片明确欠下的」），
  把它判红等于禁掉一种合法记账写法；但逐行必须取**全部** `第 NN 片` 而不是只取首枚，
  否则第二枚会从所有下游读数里静默消失。

三态：git 读不到、或提交侧一个片号都没读到、或 CHANGELOG 读不到 ⇒ **前提塌**（退 2），
绝不折成"0 缺席 = 干净"（无 `.git` 的树外副本里跑就落在这一档）。
退出码：0 干净 / 4 有缺陷 / 2 前提不成立（读数没有依据）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# 主题行里的片号：`feat(s104):`、`chore(s104):`、`重跑 s99 的电池` 都认；
# 左边排除 `.`/`-`/`_`/字母数字，于是 `.wt-s103`、`v5.1s104` 这类路径与拼接串不造假片号；
# 右边禁数字，于是 `s1034` 这种长串整枚不认（宁可少认，也不给出一个错片号）。
# 左边再排除 `/`：第 105 片本尺被这一格判红过一次——提交主题里写 `docs/audit/s106/` 是「一个路径」，
# 不是「这一片开账了」。路径段住在主题行里同样会造片号，所以位置不表态，只有 scope 与正文提法表态。
# 只取两位以上：今天没有 `s9` 这种单档写法，真出现了要新开一档而不是默认吸收。
SLICE_IN_SUBJECT = re.compile(r"(?<![0-9A-Za-z_.\-/])s(\d{2,3})(?![0-9])")
ENTRY_LINE = re.compile(r"^- \*\*v")
SLICE_REF = re.compile(r"第 (\d+) 片")
F_TOKEN = re.compile(r"\bF-[A-Za-z0-9-]+")

DEFECT_KINDS = ("absent", "caliber-diverge")


def slices_from_subjects(subjects: list[str]) -> set[int]:
    """提交侧片号集合（同一主题里出现多次只算一个）。"""
    return {int(m.group(1)) for s in subjects for m in SLICE_IN_SUBJECT.finditer(s)}


def slices_from_changelog(text: str, strict: bool = False) -> set[int]:
    """条目侧片号集合。

    逐行取 `第 NN 片` 的**全部**出现，不只取首枚——一行里点名两片是真写法（本轮实测 6 行，
    如「第 13 片：… 补第 12 片明确欠下的」，那是一种回指），只取首枚会让第二枚从所有下游
    读数里一起消失。`strict=True` 只数同时带 `F-` 号的那些行。
    """
    out: set[int] = set()
    for line in text.splitlines():
        if not ENTRY_LINE.match(line):
            continue
        if strict and not F_TOKEN.search(line):
            continue
        out.update(int(m.group(1)) for m in SLICE_REF.finditer(line))
    return out


def entry_line_count(text: str) -> int:
    """条目行（`- **v` 起头）的行数——独立分母，用来量"一行点名多片"那一档。"""
    return sum(1 for line in text.splitlines() if ENTRY_LINE.match(line))


def multi_slice_line_count(text: str) -> int:
    """一行条目里点名 ≥2 片的行数（本轮实测真语料 6 行，是回指写法，只报不判）。"""
    n = 0
    for line in text.splitlines():
        if ENTRY_LINE.match(line) and len({m.group(1) for m in SLICE_REF.finditer(line)}) >= 2:
            n += 1
    return n


def git_subjects(root: Path) -> tuple[list[str], str]:
    """现读提交主题；git 不可用/不是仓库都返回 (空, 原因)，由调用方判前提塌。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%s"],
            capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"git log 起不来：{exc}"
    if proc.returncode != 0:
        return [], f"git log 退 {proc.returncode}：{proc.stderr.strip()[:120]}"
    return proc.stdout.splitlines(), ""


def audit(root: Path, subjects: list[str] | None = None,
          changelog: str | None = None) -> dict[str, Any]:
    """三方读数：提交侧片号、条目侧片号（两口径）、缺席与口径分叉两张判红清单。

    `subjects` / `changelog` 是给自测与常驻用例注进去的语料；两者都不给时才现读磁盘与 git。
    """
    rep: dict[str, Any] = {"ok": False, "premise_broken": False, "problems": [],
                           "defects": [], "commit_slices": [], "entry_slices": [],
                           "counts": {"commit": 0, "entry": 0, "extra": 0,
                                      "entry_lines": 0, "multi_slice_lines": 0},
                           "source": {}}
    if subjects is None:
        subjects, err = git_subjects(root)
        if err:
            rep["problems"].append(f"提交侧读不到：{err}")
            rep["premise_broken"] = True
            return rep
        rep["source"]["subjects"] = "git log --format=%s（现读）"
    else:
        rep["source"]["subjects"] = "注入语料"
    if changelog is None:
        path = root / "CHANGELOG.md"
        if not path.is_file():
            rep["problems"].append(f"条目侧读不到：{path.name} 不在盘上")
            rep["premise_broken"] = True
            return rep
        changelog = path.read_text(encoding="utf-8", errors="replace")
        rep["source"]["changelog"] = path.name
    else:
        rep["source"]["changelog"] = "注入语料"

    want = slices_from_subjects(subjects)
    if not want:
        rep["problems"].append("提交侧一个片号都没读到，读数没有依据（不折成『无缺席』）")
        rep["premise_broken"] = True
        return rep

    have = slices_from_changelog(changelog)
    strict = slices_from_changelog(changelog, strict=True)
    entry_lines = entry_line_count(changelog)

    absent = sorted(want - have)
    diverge = sorted((want & have) - strict)
    rep["commit_slices"] = sorted(want)
    rep["entry_slices"] = sorted(have)
    rep["counts"] = {"commit": len(want), "entry": len(have),
                     "extra": len(have - want), "entry_lines": entry_lines,
                     "multi_slice_lines": multi_slice_line_count(changelog)}
    for n in absent:
        rep["defects"].append({"kind": "absent", "slice": n,
                               "detail": f"提交历史里有 s{n}，CHANGELOG 没有第 {n} 片条目"})
    for n in diverge:
        rep["defects"].append({"kind": "caliber-diverge", "slice": n,
                               "detail": f"第 {n} 片条目只被宽松口径认到（缺 F- 号）"})
    kinds = {d["kind"] for d in rep["defects"]}
    if kinds - set(DEFECT_KINDS):
        rep["problems"].append(f"出现未登记的缺陷类型：{sorted(kinds - set(DEFECT_KINDS))}")
        return rep
    rep["ok"] = not (absent or diverge)
    return rep


def emit(rep: dict[str, Any]) -> dict[str, Any]:
    """把读数写成机器可消费的形状（常驻用例只吃这个，不吃文案）。"""
    return {"ok": rep["ok"], "premise_broken": rep["premise_broken"],
            "problems": rep["problems"], "defects": rep["defects"],
            "counts": rep["counts"], "commit_slices": rep["commit_slices"],
            "entry_slices": rep["entry_slices"],
            "absent": [d["slice"] for d in rep["defects"] if d["kind"] == "absent"],
            "caliber_diverge": [d["slice"] for d in rep["defects"]
                                if d["kind"] == "caliber-diverge"]}


def render(rep: dict[str, Any]) -> str:
    c = rep["counts"]
    lines = [f"提交侧片号 {c['commit']} 个 / 条目侧 {c['entry']} 个"
             f"（条目行 {c['entry_lines']} 行，只有条目没有提交 {c['extra']} 个不算原告，"
             f"一行点名多片 {c['multi_slice_lines']} 行只报不判）"]
    defects = rep["defects"]
    if defects:
        lines.append(f"缺陷 {len(defects)} 条，按类型：")
        for kind in DEFECT_KINDS:
            hits = [d for d in defects if d["kind"] == kind]
            if hits:
                lines.append(f"  {kind} {len(hits)} 条")
                lines += [f"    ! {d['detail']}" for d in hits]
    elif not rep["problems"]:
        lines.append("缺陷 0 条：提交历史点名的每一片都在 CHANGELOG 有条目")
    if rep["problems"]:
        lines.append("前提塌/读数不可信：")
        lines += [f"  ! {p}" for p in rep["problems"]]
    return "\n".join(lines)


def _cases() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """合成语料：每控制给「输入 + 期望读数」，期望写成键值而不是条数。

    片号一律取两位以上：本尺的主题口径**故意**不认单档（`s7` 那种写法今天不存在，
    真出现了要新开一档而不是默认吸收）。第一版夹具全用 `s7/s8/s9`，于是四控制以
    "提交侧一个片号都没读到" 的前提塌挡通过——判据没错、夹具是假的，这条写在这里是防复发。
    前提塌类的控制必须同时点名**是哪条问题**开的火，否则换一个原因也能通过。
    """
    ok = {"subjects": ["feat(s17): 加一把尺", "chore(s17): 取证件", "docs(s18): 补账"],
          "changelog": "- **v5.1 F-SCALE-01 第 17 片：加了尺\n"
                       "- **v5.2 F-SCALE-01 第 18 片：补了账\n"}
    absent = {"subjects": ["feat(s17): 加一把尺", "feat(s19): 又加一把"],
              "changelog": "- **v5.1 F-SCALE-01 第 17 片：加了尺\n"}
    only_entry = {"subjects": ["feat(s17): 加一把尺"],
                  "changelog": "- **v5.1 F-SCALE-01 第 17 片：加了尺\n"
                               "- **v5.0 F-OLD-01 第 13 片：约定之前的轮次\n"}
    no_subjects = {"subjects": ["chore: 没有片号的提交", "回收 .wt-s103 签出"],
                   "changelog": "- **v5.1 F-SCALE-01 第 17 片：加了尺\n"}
    diverge = {"subjects": ["feat(s12): 一条不带 F 号的账"],
               "changelog": "- **v5.70 第 12 片：条目写得像账，但没挂缺陷号\n"}
    eaten = {"subjects": ["feat(s17): 加一把尺", "feat(s18): 第二把尺"],
             "changelog": "- **v5.1 F-SCALE-01 第 17 片：加了尺\n"
                          "  第 18 片的正文留下了，标题行被上一笔插入吃掉\n"}
    pathy = {"subjects": ["chore(s12): 那次判红的红因是并发子代理建的 `docs/audit/s106/`"],
             "changelog": "- **v5.9 F-A-01 第 12 片：本体有账\n"}
    merged = {"subjects": ["feat(s17): 加一把尺", "feat(s18): 第二把尺"],
              "changelog": "- **v5.1 F-SCALE-01 第 17 片与第 18 片：两片刻在一行里\n"}
    return [
        ("齐备不开火（提交侧两片都在条目里有记号）", ok,
         {"absent": [], "caliber_diverge": [], "ok": True, "premise_broken": False}),
        ("缺席开火（有 s19 提交、无第 19 片条目）", absent,
         {"absent": [19], "caliber_diverge": [], "ok": False, "premise_broken": False}),
        ("只有条目没有提交不算原告（反向不误伤）", only_entry,
         {"absent": [], "extra": 1, "ok": True}),
        ("提交侧一个片号都没读到 ⇒ 前提塌（不折成干净）", no_subjects,
         {"premise_broken": True, "ok": False, "problem": "提交侧一个片号都没读到"}),
        ("主题里的路径段不算开账（本尺自己的真实假原告）", pathy,
         {"absent": [], "ok": True, "premise_broken": False}),
        ("标题被吃也算缺席（正文留下不救条目）", eaten,
         {"absent": [18], "ok": False, "premise_broken": False}),
        ("两口径只在提交侧片号上对账（不带 F 号 ⇒ 判红）", diverge,
         {"absent": [], "caliber_diverge": [12], "ok": False}),
        ("一行点名多片：两片都算有账，那一档只报数不塌前提", merged,
         {"absent": [], "ok": True, "premise_broken": False, "multi_slice": 1}),
    ]


def _self_test(tmp: Path) -> int:
    """合成语料：该红的必须红，该不红的必须不红；开不了的火要当场说出来。"""
    root = tmp / "repo"
    root.mkdir(parents=True)
    failed: list[str] = []

    def _mark(name: str, cond: bool, note: str = "") -> None:
        print(("✓立住 " if cond else "✗没立住 ") + name + (f"｜{note}" if note else ""))
        if not cond:
            failed.append(name)

    for name, inp, want in _cases():
        rep = emit(audit(root, subjects=inp["subjects"], changelog=inp["changelog"]))
        bad: list[str] = []
        for key, exp in want.items():
            if key == "problem":
                # 理由门：前提塌必须是**这一条**原因塌的，换一个原因通过不算立住。
                if not any(exp in p for p in rep["problems"]):
                    bad.append(f"问题原因没出现（期望 {exp}，实得 {rep['problems']}）")
                continue
            if key == "multi_slice":
                got = rep["counts"]["multi_slice_lines"]
            elif key == "extra":
                got = rep["counts"]["extra"]
            else:
                got = rep.get(key)
            if got != exp:
                bad.append(f"{key} 期望 {exp}，实得 {got}")
        _mark(name, not bad, "；".join(bad))

    rep = audit(tmp / "nope", subjects=["feat(s7): x"])
    _mark("条目侧读不到 ⇒ 前提塌（不折成无缺陷）",
          rep["premise_broken"] and not rep["ok"]
          and any("条目侧读不到" in p for p in rep["problems"]), str(rep["problems"]))

    a = slices_from_subjects(["chore: 回收 .wt-s103 签出"])
    b = slices_from_subjects(["chore(s103): 绑定报告", "重跑 s99 的电池", "s1034 与 s10"])
    _mark("词边界三端都真（路径不算、scope 与正文提法算、长串整枚不认）",
          a == set() and b == {103, 99, 10}, f"实得 {sorted(b)} 与 {sorted(a)}")

    _mark("数得出「一行点名多片」这一档（回指行开火、单枚行不开火）",
          multi_slice_line_count("- **v5.1 F-A-01 第 17 片与第 18 片：回指\n") == 1
          and multi_slice_line_count("- **v5.1 F-A-01 第 17 片：单枚\n") == 0
          and multi_slice_line_count("  第 17 片与第 18 片写在正文里\n") == 0)

    subj, err = git_subjects(ROOT)
    _mark("真 git 有对象（主题行数远大于片号数）",
          not err and len(subj) > 500 and slices_from_subjects(subj) != set(),
          f"主题 {len(subj)} 行 err={err!r}")

    print(f"合成语料上 {len(_cases()) + 4} 条判据读数"
          + (f"有 {len(failed)} 条没立住：{failed}" if failed else "全部对上"))
    return 4 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(ROOT), help="仓库根（默认本脚本上一层）")
    ap.add_argument("--subjects-file", default="",
                    help="调试接缝：每行一条提交主题，替代现读 git log")
    ap.add_argument("--json", default="", help="把读数写成 JSON")
    ap.add_argument("--self-test", action="store_true", help="跑合成语料")
    args = ap.parse_args(argv)
    root = Path(args.repo).resolve()
    if args.self_test:
        with tempfile.TemporaryDirectory() as td:
            return _self_test(Path(td))
    subjects = None
    if args.subjects_file:
        subjects = Path(args.subjects_file).read_text(encoding="utf-8").splitlines()
    full = audit(root, subjects=subjects)
    rep = emit(full)
    print(render(full))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    if rep["premise_broken"]:
        return 2
    return 4 if rep["defects"] else 0


if __name__ == "__main__":
    sys.exit(main())
