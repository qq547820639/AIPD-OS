#!/usr/bin/env python3
"""第 87 片面 ⑤ 的变异电池：每一档判决都要有一支"撤掉它就必红"的对照臂。

分类：KILLED（该臂的判据红了）/ SURVIVED（撤掉判决没人发现＝没牙）/
BAD-ANCHOR（锚点没落到预期位置，臂作废，读数不进合计）。
对照臂 X0 不改任何字节，必须先证明"原样是绿的"，否则后面的红不能归因给变异。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TOOL = REPO / "scripts" / "doc_command_census.py"
TESTS = "tests/test_doc_command_census.py"

# 每支臂：(名字, 期望被哪些用例抓住, old, new)。old 必须在文件里恰好命中一次。
ARMS = [
    ("X0-control-no-change", "对照：原样必须全绿", None, None),
    ("X1-absolute-not-dead", "绝对路径不再算死链",
     '                if path.startswith("/"):\n                    rows.append((rel, no, path, "dead"))\n                    continue\n',
     ''),
    ("X2-register-not-consumed", "登记册不再被消费（豁免成空转）",
     '            if path in ereg:\n                e_counts["dead_registered"] += 1\n                continue\n',
     ''),
    ("X3-no-stale-register-check", "登记册单向：撤掉「该撤」那一半",
     '    for path, why in reg_stale:\n        key = ("登记册该撤", ENTRY_REGISTER_REL, 0, path)\n        judged.append(key)\n        extra[key] = why\n',
     ''),
    ("X4-placeholder-check-dropped", "模板形态不再免判",
     '                if ENTRY_PLACEHOLDER_RE.search(path):\n                    rows.append((rel, no, path, "placeholder"))\n                    continue\n',
     ''),
    ("X5-untracked-not-judged", "「没入库」这一档被撤（本轮我自己犯的错无人守）",
     '            key = ("入口未入库", rel, no, path)\n            judged.append(key)\n',
     ''),
    ("X6-git-unknown-becomes-guilty", "git 读不出时折成违规（不知道当_HAVE_没入库）",
     '                if tracked is None:\n                    rows.append((rel, no, path, "tracked"))\n                    continue\n',
     '                if tracked is None:\n                    rows.append((rel, no, path, "untracked"))\n                    continue\n'),
    ("X7-scripts-delegated-dropped", "`scripts/…` 又回到两处各记一笔红",
     '                if path.startswith("scripts/"):\n',
     '                if False:\n'),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def run_tests() -> tuple[int, str]:
    p = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "pytest", "-q",
                        "--no-header", "-p", "no:cacheprovider", TESTS],
                       cwd=REPO, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                            "HOME": str(Path.home())})
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    orig = TOOL.read_bytes()
    orig_sha = sha(orig)
    print(f"原文件 sha={orig_sha}")
    rc, out = run_tests()
    if rc != 0:
        print("X0 对照臂不绿，电池前提不成立：", out[-600:])
        return 5
    print("[CONTROL OK] X0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, old, new in ARMS:
        if name.startswith("X0"):
            continue                      # 对照臂不参与牙的合计（上面已证它不红）
        text = orig.decode("utf-8")
        hits = text.count(old)
        if hits != 1:
            print(f"[BAD-ANCHOR] {name}（{what}）锚点命中 {hits} 次 ⇒ 臂作废")
            marks["BAD-ANCHOR"] += 1
            continue
        mutated = text.replace(old, new, 1)
        TOOL.write_text(mutated, encoding="utf-8")
        if sha(TOOL.read_bytes()) == orig_sha:            # 落地证明：字节必须变
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(orig)
            continue
        rc, out = run_tests()
        TOOL.write_bytes(orig)
        if sha(TOOL.read_bytes()) != orig_sha:
            print(f"[!] 复位失败 {name}")
            return 6
        # 归因要落到"哪条用例抓住的"，不是 pytest 的任意一行输出
        killed_by = [ln.split(" - ")[0].replace("FAILED ", "")
                     for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {name}（{what}）撤掉这档判决，用例照绿 ⇒ 没牙")
            marks["SURVIVED"] += 1
        else:
            who = "; ".join(killed_by) if killed_by else "(没解析出 FAILED 行，见日志)"
            print(f"[KILLED]   {name}（{what}）被抓住：{who[:150]}")
            marks["KILLED"] += 1
    total = len(ARMS) - 1
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k not in ('KILLED',) and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {orig_sha}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
