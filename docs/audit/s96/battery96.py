r"""第 96 片变异电池：取证脚本根路径门禁**每个判决与每个口径选择**，各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| Z0 | 不改任何字节（对照臂）⇒ 必须全绿，否则电池前提不成立 |
| Z1 | 「根路径未点名」折成"按 __file__ 推根"（未归类静默算合规） |
| Z2 | 该撤判据的谓词取反（名册挂着已经不写死的条目 ⇒ 永不该撤） |
| Z3 | 「点名规则不唯一」不再开火（两条规则抢文件时靠顺序挑第一条） |
| Z4 | 「名册缺条目」不再开火（规则接住了但没落到纸面也算豁免） |
| Z5 | 「名册规则过期」不再开火（名册与规则表不同源也放行） |
| Z6 | 「豁免理由空缺」不再开火（空理由换免跑） |
| Z7 | 磁盘上已不存在的登记条目不再判该撤 |
| Z8 | 名册里同一路径登记两遍不再算前提问题 |
| Z9 | `repo_inside` 恒真（仓库外路径也被当成本仓原告） |
| Z10 | 识别面退回 **ASCII 白名单**字符类（本仓根含中文 ⇒ 真语料零命中） |
| Z11 | `HOST_RE` 放宽成 `^/`（URL 路由混进"仓库外路径"读数） |
| Z12 | `--emit` 的归属唯一闸只拦 ≥2 条，命中 0 条的静默不进册 |
| Z13 | 名册读不到不再算前提塌（退码从 2 掉到 0） |
| Z14 | 分母与档位求和不再同源（`derived` 少计一档） |
| Z15 | 「仓库内」退回只按**当前这次签出**的目录前缀判（在 worktree 里跑就一片假红） |

用例简名：`self` = `test_instrument_self_test_is_actually_spawned_and_green`（spawn
`--self-test`，读的是**变异后的盘上文件**，所以量具自己的 15 支臂也算一层牙）；
`worktree` = `test_a_worktree_checkout_of_the_same_repo_still_counts_as_repo_inside`（Z15 的原告）；
`live` = `test_real_repo_face_is_live_and_return_code_follows_the_verdict`；
`nonascii` = `test_the_abs_probe_reaches_a_non_ascii_repo_path`；
`poles` = `test_an_unlisted_script_fires_and_the_listed_one_does_not`；
`report` = `test_outside_repo_literals_are_reported_but_never_judge`；
`shape` = `test_a_name_shape_rule_can_mis_bucket_a_file`；
`premise` = `test_premise_missing_register_is_not_zero_risk`；
`regen` = `test_register_on_disk_matches_the_rules_table`。

跑法：`python docs/audit/s96/battery96.py`。开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。
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
TOOL = REPO / "docs" / "audit" / "s96" / "build_forensic_root_register.py"
TESTS = ["tests/test_forensic_scripts_root.py"]

ARMS = [
    ("Z0-control-no-change", "对照：原样必须全绿", None, None),
    ("Z1-unclassified-folds-to-derived", "未归类静默算合规",
     '        if not r["rules"]:\n            buckets["unwatched"] += 1',
     '        if not r["rules"]:\n            buckets["derived"] += 1\n            continue\n'
     '            buckets["unwatched"] += 1'),
    ("Z2-stale-listing-never-fires", "该撤判据谓词取反",
     '            if r["path"] in reg:\n                violations.append({\n'
     '                    "field": "名册该撤"',
     '            if r["path"] not in reg:\n                violations.append({\n'
     '                    "field": "名册该撤"'),
    ("Z3-overlap-not-judged", "规则不唯一不开火",
     '        if len(r["rules"]) > 1:\n            buckets["unwatched"] += 1',
     '        if len(r["rules"]) > 1:\n            buckets["exempt"] += 1\n            continue\n'
     '            buckets["unwatched"] += 1'),
    ("Z4-missing-listing-not-judged", "缺条目不开火",
     '        if ent is None:\n            buckets["unwatched"] += 1',
     '        if ent is None:\n            buckets["exempt"] += 1\n            continue\n'
     '            buckets["unwatched"] += 1'),
    ("Z5-rule-drift-not-judged", "规则过期不开火",
     '        if ent.get("rule") != r["rules"][0]:\n            buckets["unwatched"] += 1',
     '        if ent.get("rule") == r["rules"][0]:\n            buckets["unwatched"] += 1'),
    ("Z6-empty-reason-passes", "空理由换免跑",
     '        if not str(ent.get("reason") or "").strip():\n            buckets["unwatched"] += 1',
     '        if not str(ent.get("reason") or "").strip():\n            buckets["exempt"] += 1\n'
     '            continue\n            buckets["unwatched"] += 1'),
    ("Z7-gone-entry-kept", "已不存在的登记不再判该撤",
     '    for rel in sorted(set(reg) - set(by_path)):',
     '    for rel in sorted([]):'),
    ("Z8-duplicate-listing-quiet", "同一路径登记两遍不再算前提问题",
     '        if e["path"] in reg:\n            problems.append(',
     '        if False and e["path"] in reg:\n            problems.append('),
    ("Z9-inside-is-absolute", "repo_inside 恒真",
     '    return resolved == root or root in resolved.parents',
     '    return bool(resolved)'),
    ("Z10-ascii-only-charset", "识别面退回 ASCII 白名单",
     'ABS_RE = re.compile(r"""["\'](/[^\\s"\'`\\\\]{3,})["\']""")',
     'ABS_RE = re.compile(r"""["\'](/[A-Za-z0-9_.+~/:-]{3,})["\']""")'),
    ("Z11-host-prefix-loosened", "HOST_RE 放宽成任何绝对路径",
     'HOST_RE = re.compile(r"^/(?:Volumes|Users|home|tmp|private/tmp|mnt|opt)/")',
     'HOST_RE = re.compile(r"^/")'),
    ("Z12-emit-drops-unclassified", "--emit 把没归类的静默跳过",
     '    bad = [r["path"] for r in rows if len(r["rules"]) != 1]',
     '    bad = [r["path"] for r in rows if len(r["rules"]) > 1]\n'
     '    rows = [r for r in rows if r["rules"]]'),
    ("Z13-missing-register-not-premise", "读不到名册不再算前提塌",
     '        return {}, [f"register_missing: 读不到 {REL}"]',
     '        return {}, []'),
    ("Z15-prefix-only-inside", "「仓库内」退回只按当前签出的目录前缀判",
     '        inside = [(ln, lit) for ln, lit in lits if any(repo_inside(r, lit) for r in roots)]',
     '        inside = [(ln, lit) for ln, lit in lits if repo_inside(root, lit)]'),
    ("Z14-bucket-denominator-split", "档位少计一档",
     '                buckets["derived"] += 1\n            continue',
     '                buckets["derived"] += 0\n            continue'),
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
    """删掉本文件在 pycache_prefix / __pycache__ 里的两份缓存（防陈旧字节码遮蔽还原后的源）。"""
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__" / (TOOL.stem + ".cpython-39.pyc"))):
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
        print("Z0 对照臂不绿，电池前提不成立：", out[-1200:])
        return 5
    print("[CONTROL OK] Z0 原样全绿")
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
        # 语法检查一律用 ast.parse：`py_compile` 会往 `sys.pycache_prefix`（本机
        # `~/Library/Caches/com.apple.python`）落字节码。缓存有效性只看 (源 mtime 整秒, 字节数)，
        # 而 Z14 那支臂把 `+= 1` 改成 `+= 0`——**长度不变**、还原又落在同一秒 ⇒
        # 电池跑完之后每一次 import 该文件读到的都是那个变异体（本轮实测：derived 恒 0）。
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
