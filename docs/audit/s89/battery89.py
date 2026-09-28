#!/usr/bin/env python3
"""第 89 片变异电池：面 ⑤ 这十五处"自己造红 / 自己免判 / 读数与判决打架"的形状，各配一支撤销臂。

| 臂 | 撤掉的判决 | 谁必须翻红 |
| --- | --- | --- |
| Y1 | `git ls-tree -r HEAD` 退回 `git ls-files`（读索引） | staged-but-uncommitted 那条用例 + `--self-test` |
| Y2 | `audit()` 不再把面 ④ 的行集交给面 ⑤ ⇒ 谁都免责不了 | 面 ④/⑤ 分工那两条 + 自测的 `delegated == 1` |
| Y3 | 让渡回到**无条件**（`scripts/` 一律免责，第 87 片原样） | "取证文档那条必须判红"的两条用例 + 自测 |
| Y4 | 去掉"git 读不出时不判「该撤」"的抑制 ⇒ 降级自己造红 | 新写的降级两极用例 + 自测 |
| Y5 | 去掉"git 读不出 ⇒ 存在即合规"的降级 ⇒ 不知道被折成违规 | 未入库那档的 git_unknown 用例 + 自测 |
| Y6 | 撤掉 `core.quotePath=false` ⇒ 非 ASCII 路径被转义 | 按名读非 ASCII 入口那条用例 |
| Y7 | `emit_register` 不再自算面 ④ 行集 ⇒ 草案与判决两套说法 | 新写的"草案死链集 == 判决 dead 集"那条 |
| Y8 | 让渡行不再判"在不在 HEAD"（整行让给只看磁盘的面 ④） | 新写的让渡行 untracked 两极 + 自测 |
| Y15 | 让渡行连"磁盘上有没有"都不看 ⇒ 缺脚本被改口成未入库 | 自测那条"同一行只记一笔"（面 ④/⑤ 双记） |
| Y9 | `violations` 不去重（一处缺陷记两笔红） | 新写的"同行两处引用记一笔"那条 + 自测 |
| Y10 | `citations` 恒为 1（去重把引用次数丢掉） | 同上那条的 `citations == 2` 半支 |
| Y11 | 「该撤」只看状态名 ⇒ 被面 ④ 收着的在册入口永远撤不掉 | 新写的"面 ④ 手里的登记仍可撤"正极 |
| Y12 | 把 `delegated` 一律当成跑得动 ⇒ 磁盘上没有的也被判「该撤」 | 同一条用例的反极（该留的没留） |
| Y13 | 面 ⑤ 读到 0 处也照跑反向臂 ⇒ "没读到"折成"没人引用" | 新写的 entry_face_empty 两极 |
| Y14 | 语料读不全时草案照落盘 | 新写的"拒绝时不许动目标文件"那条 |

Y4 与 Y5 是同一条例外（"不知道 ≠ 违规"）的两个方向：一个防**漏判**、一个防**多判**，
所以两臂都必须红，缺一半都说明那条纪律只是单边洁癖。
Y9 与 Y10 也成对：一支证"清单不重复记"，一支证"引用次数没被顺手抹掉"——
只写 Y9 的话，"去重"可以退化成"少报"而没人判。
对照臂 Y0 不改任何字节，必须先证明"原样是绿的"。

改判据所在的代码行，会把**以那一行为锚的老控制**一起挪掉：本电池的 Y3 就先后被
第 88、89 片各挪一次（`0` 命中而不是"臂作废"里没写的那种红）。跑电池之前先数锚点，
比跑完再读"BAD-ANCHOR 6/10"便宜。

跑法：`python docs/audit/s89/battery89.py`（每臂只跑 census 一个用例文件，约 30 秒一臂）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
CEN = REPO / "scripts" / "doc_command_census.py"
TESTS = ["tests/test_doc_command_census.py"]

ARMS = [
    ("Y0-control-no-change", "对照：原样必须全绿", None, None),
    ("Y1-tracked-face-becomes-index", "跟踪面退回读索引（`git add` 未 commit 被当成已入库）",
     '''        proc = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false",
                               "ls-tree", "-r", "--name-only", "HEAD"],''',
     '''        proc = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false",
                               "ls-files"],'''),
    ("Y6-quote-path-flag-dropped", "撤掉 `core.quotePath=false` ⇒ 非 ASCII 路径被转义成八进制串",
     '''        proc = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false",
                               "ls-tree", "-r", "--name-only", "HEAD"],''',
     '''        proc = subprocess.run(["git", "-C", str(root),
                               "ls-tree", "-r", "--name-only", "HEAD"],'''),
    ("Y2-handoff-map-not-passed", "面 ⑤ 拿不到面 ④ 的行集（让渡变成「谁都不免责」）",
     "    erows, egit_unknown, p7 = entry_points(root, face4=face4_map)",
     "    erows, egit_unknown, p7 = entry_points(root)"),
    ("Y3-delegation-unconditional", "回到第 87 片那版：`scripts/` 一律免责",
     '''                if path.startswith("scripts/"):
                    if stem4 is not None and path == f"scripts/{stem4}.py":''',
     '''                if path.startswith("scripts/"):
                    if stem4 is None or True:      # 撤掉"面 ④ 真收了这一行"这个条件'''),
    ("Y7-emit-draft-drops-hand-off", "`emit_register` 不再自算面 ④ 行集：草案把 delegated 当死链",
     '''    srows, _sunbounded, sp = script_rows(root)
    face4_map = {(rel, no): stem for rel, no, stem, _used in srows}''',
     '''    srows, _sunbounded, sp = script_rows(root)
    face4_map = {}     # 草案与判决对同一条入口各说一套'''),
    ("Y8-delegated-row-skips-head-check", "让渡行不再判"
     "「磁盘上有、HEAD 里没有」（整行让给只看磁盘的面 ④）",
     '''                        if tracked is not None and (root / path).is_file() \\
                                and path not in tracked:''',
     '''                        if False:'''),
    ("Y15-delegated-row-ignores-disk", "让渡行连「磁盘上有没有」都不看 ⇒ 缺脚本被改口成未入库",
     '''                        if tracked is not None and (root / path).is_file() \\
                                and path not in tracked:''',
     '''                        if tracked is not None and path not in tracked:'''),
    ("Y9-violations-not-deduplicated", "缺陷清单不去重：同一缺陷按引用次数记多笔红",
     "    for key in order:",
     "    for key in judged:"),
    ("Y10-citation-count-pinned-to-one", "`citations` 恒为 1：去重顺手把引用次数抹掉",
     "        cite = count[key]",
     "        cite = 1"),
    ("Y11-reverse-arm-reads-state-names", "「该撤」只看状态名 ⇒ 被面 ④ 收着的在册入口永远撤不掉",
     '''        resolved = all(s == "tracked" or (s == "delegated" and (root / path).is_file())
                       for s in states)''',
     '''        resolved = all(s == "tracked" for s in states)'''),
    ("Y12-reverse-arm-trusts-delegated", "把 `delegated` 一律当成跑得动 ⇒ 缺脚本也被判「该撤」",
     '''        resolved = all(s == "tracked" or (s == "delegated" and (root / path).is_file())
                       for s in states)''',
     '''        resolved = all(s in ("tracked", "delegated") for s in states)'''),
    ("Y13-empty-entry-face-still-reverses", "面 ⑤ 读到 0 处也照跑反向臂 ⇒ 「没读到」折成「没人引用」",
     "    for path, _note in ([] if (ereg and not erows) else sorted(ereg.items())):",
     "    for path, _note in sorted(ereg.items()):"),
    ("Y14-emit-writes-on-unreadable-corpus", "语料读不全时草案照落盘（会删掉仍在被引用的登记）",
     '''    problems = list(sp) + list(p7)
    if problems:''',
     '''    problems = list(sp) + list(p7)
    if False:'''),
    ("Y4-stale-fire-on-unknown-git", "降级自己造红：git 读不出也照判「登记册该撤」",
     '''        if egit_unknown:
            # 这棵树 git 读不出''',
     '''        if False:
            # 这棵树 git 读不出'''),
    ("Y5-no-existence-grace-on-unknown-git", "把「不知道」折成违规：git 读不出也判未入库",
     '''                if tracked is None:
                    rows.append((rel, no, path, "tracked"))
                    continue
''',
     '''                if tracked is None and False:
                    rows.append((rel, no, path, "tracked"))
                    continue
'''),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home())})
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    original = CEN.read_bytes()
    print(f"原文件 sha={sha(original)}")
    text = original.decode("utf-8")
    stale = [(n, text.count(o)) for n, _w, o, _n2 in ARMS
             if o is not None and text.count(o) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。跑完再读「N 臂作废」比先数一遍贵一个数量级。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if a[2] is not None)} 支臂各命中 1 次")
    rc, out = run_tests()
    if rc != 0:
        print("Y0 对照臂不绿，电池前提不成立：", out[-800:])
        return 5
    print("[CONTROL OK] Y0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, old, new in ARMS:
        if old is None:
            continue
        text = original.decode("utf-8")
        hits = text.count(old)
        if hits != 1:
            print(f"[BAD-ANCHOR] {name}（{what}）锚点命中 {hits} 次 ⇒ 臂作废")
            marks["BAD-ANCHOR"] += 1
            continue
        CEN.write_text(text.replace(old, new, 1), encoding="utf-8")
        if sha(CEN.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            CEN.write_bytes(original)
            continue
        chk = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "py_compile",
                              str(CEN)], capture_output=True, text=True)
        if chk.returncode != 0:
            # 语法塌的臂答的是"我的替换不合法"，不是"这条判决有牙"——单列，不混进 KILLED
            print(f"[BAD-ANCHOR] {name} 变异体编译不过：{chk.stderr[-160:]}")
            marks["BAD-ANCHOR"] += 1
            CEN.write_bytes(original)
            continue
        rc, out = run_tests()
        CEN.write_bytes(original)
        if sha(CEN.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {name}")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {name}（{what}）撤掉这档判决，用例照绿 ⇒ 没牙")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {name}（{what}）被抓住："
                  f"{'; '.join(killed) or '(无 FAILED 行，见日志)'[:600]}")
            marks["KILLED"] += 1
    total = len(ARMS) - 1
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(CEN.read_bytes())}（应等于 {sha(original)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
