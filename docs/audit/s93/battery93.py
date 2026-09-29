r"""第 93 片变异电池：依赖许可证门禁**正文面**的每个口径选择，各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| Y0 | 不改任何字节（对照臂）⇒ 必须全绿，否则电池前提不成立 |
| Y1 | 断言窗口退回全文（只认头 8 行 → 全部行） |
| Y2 | 正文严重度按「断言∪提及」算，而不是只按断言 |
| Y3 | 标题判据从行首退回子串 |
| Y4 | 撤掉 LGPL 正文引用 GPL 的豁免 |
| Y5 | 「没有正文」折算成已核对 |
| Y6 | 「正文认不出」折算成合规 |
| Y7 | 无断言时不再算提及档（把提前 return 放回去） |
| Y8 | 重复记录按 id 面判「两种说法」 |
| Y9 | 重复记录取第一份而不是最严那份 |
| Y10 | 重复对账只在闭包内跑 |
| Y11 | ids 不再清洗成标识符 |
| Y12 | 台账比对退回逐字相等（丢掉粗名覆盖） |
| Y13 | 包树里的许可证也算本包正文 |
| Y14 | 「正文与元数据打架」不开火 |

用例简名（`self` 那条是 spawn `--self-test` 的常驻用例，其余是正文面的常驻牙）：
`real` = `test_real_corpus_body_face_is_populated_and_has_no_false_red`
`bundled` = `test_body_stricter_than_metadata_fires_but_a_bundled_list_does_not`
`lgpl` = `test_lgpl_body_text_does_not_escalate_to_gpl`
`three` = `test_body_states_are_three_not_two`
`dup` = `test_duplicate_metadata_records_take_the_stricter_saying`
`away` = `test_outside_closure_duplicate_records_still_reconcile`
`wheel` = `test_bodies_are_read_from_a_real_wheel_not_only_from_injection`
`coarse` = `test_ledger_can_adjudicate_a_package_whose_metadata_gives_only_a_coarse_name`
`self` = `test_instrument_self_test_is_actually_spawned_and_green`

实测翻红（一支臂一条，冒号后是被抓住的用例数与简名）：
Y1:1 real（多开 1 笔打架：numpy）· Y2:1 real（多开 5 笔：ocp/librt/mypy/numpy/pathspec）·
Y3:2 bundled self · Y4:2 lgpl self · Y5:3 three real self · Y6:3 three bundled self ·
Y7:2 bundled self · Y8:2 dup self · Y9:2 dup self · Y10:2 away real（`self` 抓不到）·
Y11:2 coarse self · Y12:2 coarse self · Y13:2 wheel real · Y14:4 bundled lgpl wheel self

形状说明：Y5/Y6/Y9/Y10/Y14 撤的是**判决**（少红，或把"看不见/认不出"这第三态折成绿）；
Y1/Y2/Y3/Y4/Y13 撤的是**正文口径**，危险方向是"把 vendored 或 quoted 的第三方许可证
读成本包给自己选的许可证"，于是把 BSD/Apache 的包误判成 AGPL；Y8/Y11/Y12 撤的是
**比对口径**，方向是把同族两种写法、整段全文、粗名 classifier 都读成"两种说法/裁不动"。
Y1/Y2/Y10/Y13 各有一条**只活在真语料**里的原告（合成夹具的正文都在 8 行内、也没有
quoted 全文，而它唯一的重复名字 `b-dualrec` 从声明根走得到），所以 `self` 那一格对
Y10 是空的：闭包外那一圈压根没被合成语料覆盖，只有 `real` 与 `away` 看得见它。

跑法：`python docs/audit/s93/battery93.py`。开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TOOL = REPO / "scripts" / "dependency_license_gate.py"
TESTS = ["tests/test_dependency_license_gate.py"]

ARMS = [
    ("Y0-control-no-change", "对照：原样必须全绿", None, None),
    ("Y1-window-back-to-full", "断言窗口退回全文",
     'head = lines[:8]',
     'head = lines'),
    ("Y2-severity-from-mentions", "严重度按提及算而不是断言",
     'for f in asserted],',
     'for f in set(asserted) | set(mentioned)],'),
    ("Y3-title-substring-not-prefix", "标题判据从行首退回子串",
     'on_line = any(ln.startswith(t) for ln in head for t in titles)',
     'on_line = any(t in ln for ln in head for t in titles)'),
    ("Y4-drop-lgpl-gpl-carveout", "撤掉 LGPL 引用 GPL 的豁免（循环体置 pass）",
     '        parent = COPYLEFT_PARENT.get(fam)\n'
     '        if parent:\n'
     '            mentioned.discard(parent)\n'
     '            asserted.discard(parent)\n',
     '        pass\n'),
    ("Y5-missing-counts-as-checked", "没有正文折算成已核对",
     'out["state"] = "missing"',
     'out["state"] = "checked"'),
    ("Y6-unrecognized-counts-as-checked", "正文不识别折算成合规",
     'out["state"] = "unrecognized"',
     'out["state"] = "checked"'),
    ("Y7-no-asserted-early-return", "无断言时不再算提及档（把提前 return 放回去）",
     '        out["state"] = "unrecognized"\n'
     '    if meta_rank not in SEVERITY:',
     '        out["state"] = "unrecognized"\n'
     '        return out\n'
     '    if meta_rank not in SEVERITY:'),
    ("Y8-conflict-by-id-face", "重复记录按 id 面判不一致",
     'conflict = len({p[0] for p in per}) > 1',
     'conflict = len({tuple(sorted(p[2])) for p in per}) > 1'),
    ("Y9-take-first-not-strictest", "重复记录取第一份而不是最严",
     'for p in per[1:]:',
     'for p in per[1:0]:'),
    # 两笔编辑合起来才让"闭包外那一圈"整段变死：桶计数只数闭包内 + 循环体不再遍历 dupes。
    ("Y10-dupes-only-in-closure", "重复对账只在闭包内跑",
     [('buckets["duplicate-records"] = len(dupes)',
       'buckets["duplicate-records"] = sum(1 for n in dupes if n in seen)'),
      ('for name in dupes:', 'for name in []:')], None),
    ("Y11-ids-not-tokenised", "ids 不再清洗成标识符",
     'return [i for i in ids if len(i) <= 40 and re.fullmatch(r"[A-Za-z0-9.+:_()/-]+", i)]',
     'return list(ids)'),
    ("Y12-ledger-verbatim-equality", "台账比对退回逐字相等",
     'return all(x in expanded for x in led_ids)',
     'return set(led_ids) == set(ids)'),
    ("Y13-tree-files-count-as-bodies", "包树里的许可证也算正文",
     'if not any(".dist-info" in x for x in parts):',
     'if False:'),
    ("Y14-body-fight-does-not-fire", "正文打架不开火（append 的守卫改成 False）",
     '    if body_sev > meta_sev:',
     '    if False:'),
]


def pairs(arm):
    """一支臂的编辑归一成 [(旧, 新), …]（`new is None` 时 `old` 本身就是成对清单）。"""
    old, new = arm[2], arm[3]
    if old is None:
        return []
    if new is None:
        return list(old)
    return [(old, new)]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home()),
                               "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def _drop_cache() -> None:
    """删掉靶文件在 pycache_prefix / __pycache__ 里的两份缓存（防陈旧字节码遮蔽还原后的源）。"""
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__" / (TOOL.stem + f".{sys.implementation.cache_tag}.pyc"))):
        with contextlib.suppress(OSError):
            os.remove(cand)


def main() -> int:
    _drop_cache()
    original = TOOL.read_bytes()
    print(f"原文件 sha={sha(original)}")
    text = original.decode("utf-8")
    stale = [(arm[0], text.count(o)) for arm in ARMS
             for o, _n in pairs(arm) if text.count(o) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if pairs(a))} 支臂、"
          f"{sum(len(pairs(a)) for a in ARMS)} 处编辑各命中 1 次")
    rc, out = run_tests()
    if rc != 0:
        print("Y0 对照臂不绿，电池前提不成立：", out[-900:])
        return 5
    print("[CONTROL OK] Y0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for arm in ARMS:
        edits = pairs(arm)
        if not edits:
            continue
        mutated = text
        for o, n in edits:
            mutated = mutated.replace(o, n, 1)
        TOOL.write_text(mutated, encoding="utf-8")
        if sha(TOOL.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {arm[0]} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        # 语法门用进程内 ast.parse：外部字节码编译会往 `sys.pycache_prefix` 落缓存，
        # 而缓存有效性只看 (源 mtime 整秒, 字节数) ⇒ 同长度变异＋同秒还原会遮蔽还原后的源。
        try:
            ast.parse(TOOL.read_text(encoding="utf-8"))
            chk_rc, chk_err = 0, ""
        except SyntaxError as exc:
            chk_rc, chk_err = 1, str(exc)
        if chk_rc != 0:
            print(f"[BAD-ANCHOR] {arm[0]} 变异体语法不过：{chk_err[:200]}")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        rc, out = run_tests()
        TOOL.write_bytes(original)
        _drop_cache()
        if sha(TOOL.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {arm[0]}")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {arm[0]}（{arm[1]}）撤掉之后用例照绿 ⇒ 这一格其实没被看见")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {arm[0]}（{arm[1]}）被抓住 {len(killed)} 条："
                  f"{'; '.join(killed)[:520]}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if pairs(a))
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {sha(original)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
