#!/usr/bin/env python3
"""第 89 片变异电池：面 ⑤ 这四处"自己造红/自己免判"的形状，各配一支撤销臂。

| 臂 | 撤掉的判决 | 谁必须翻红 |
| --- | --- | --- |
| Y1 | `git ls-tree -r HEAD` 退回 `git ls-files`（读索引） | staged-but-uncommitted 那条用例 + `--self-test` |
| Y2 | `audit()` 不再把面 ④ 的行集交给面 ⑤ ⇒ 谁都免责不了 | 面 ④/⑤ 分工那两条 + 自测的 `delegated == 1` |
| Y3 | 让渡回到**无条件**（`scripts/` 一律免责，第 87 片原样） | "取证文档那条必须判红"的两条用例 + 自测 |
| Y4 | 去掉"git 读不出时不判「该撤」"的抑制 ⇒ 降级自己造红 | 新写的降级两极用例 + 自测 |
| Y5 | 去掉"git 读不出 ⇒ 存在即合规"的降级 ⇒ 不知道被折成违规 | 未入库那档的 git_unknown 用例 + 自测 |

Y4 与 Y5 是同一条例外（"不知道 ≠ 违规"）的两个方向：一个防**漏判**、一个防**多判**，
所以两臂都必须红，缺一半都说明那条纪律只是单边洁癖。
对照臂 Y0 不改任何字节，必须先证明"原样是绿的"。

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
     '''                if path.startswith("scripts/") and stem4 is not None \\
                        and path == f"scripts/{stem4}.py":''',
     '''                if path.startswith("scripts/"):
                    rows.append((rel, no, path, "delegated"))
                    continue
                if False:'''),
    ("Y4-stale-fire-on-unknown-git", "降级自己造红：git 读不出也照判「登记册该撤」",
     "            if egit_unknown:",
     "            if False:"),
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
