r"""第 92 片变异电池：依赖许可证门禁的每道判决/每个信号选择，各配一支撤销臂。

| 臂 | 撤掉的东西 | 谁必须翻红 |
| --- | --- | --- |
| B0 | 不改任何字节（对照） | ——必须全绿，否则电池前提不成立 |
| B1 | `forbidden`（强 copyleft）不再判红 | `test_forbidden_family_cannot_be_waived_by_the_ledger` + 自测 |
| B2 | 只看 `License-Expression`，丢掉 `License` 字段与 classifier | **真语料原告**：casadi 会从「未裁定」退成看不见/未标注；`test_casadi_stays_red…`、`test_generic_classifier_alone…` 都红 |
| B3 | `OR`/`AND` 结构拍平（任一候选可用即放行） | `test_or_branch_is_usable_but_and_pair_is_not` + 自测（`MIT AND LGPL-2.1` 会因含 MIT 变绿） |
| B4 | `needs-review` 也算放行 | `test_casadi_stays_red…` + 台账两极用例 + 自测 |
| B5 | 台账对强 copyleft 的「越权放行」这一笔 | `test_forbidden_family…` + 自测 |
| B6 | 「声明了却没装」必须有理由（改成全部已登记） | `test_declared_but_uninstalled_needs_a_written_reason` + 自测 |
| B7 | 没装的传递依赖折成"合规"而不是只报 | 自测的 `unresolved` 那一格（真仓库不红 ⇒ 这臂证明"只报"不是"白报"） |

形状说明：B1/B4/B5/B6 撤的是**判决**（少红），B2/B3/B7 撤的是**信号与口径**——
它们的危险方向都是"把不确定的读成合规"，正是这类门最常见的假绿。
B2 是唯一有**真仓库原告**的一臂：本面立起的原因就是那一条 casadi。

跑法：`python docs/audit/s92/battery92.py`。开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。
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
    ("B0-control-no-change", "对照：原样必须全绿", None, None),
    ("B1-forbidden-not-red", "强 copyleft 不再判红",
     '        elif rank == "forbidden":',
     "        elif False:"),
    ("B2-drop-license-field", "只看 License-Expression，丢掉 License 字段（与 classifier 那一支）",
     '    for f in rec.get("license_fields") or []:',
     "    for f in []:"),
    ("B3-flatten-or-and", "`OR`/`AND` 拍平成候选集合（任一可用即放行）",
     '        if all(LICENSE_FAMILY[i] == "allowed" for i in b):',
     '        if any(LICENSE_FAMILY[i] == "allowed" for i in b):'),
    ("B4-needs-review-clears", "台账挂上条目就放行（不再要求 accepted）",
     '                if ent["decision"] != "accepted":',
     "                if False:"),
    ("B5-ledger-can-waive-forbidden", "去掉「台账越权放行」这一笔",
     "            if ent:",
     "            if False:"),
    ("B6-declared-missing-needs-no-reason", "声明了却没装 ⇒ 全部当已登记",
     "        if name in reasons:",
     "        if True:"),
    ("B7-unresolved-counts-as-clean", "把没装的传递依赖折成 allowed 而不是只报",
     '            buckets["unresolved"] += 1',
     '            buckets["allowed"] += 1'),
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
        print("B0 对照臂不绿，电池前提不成立：", out[-900:])
        return 5
    print("[CONTROL OK] B0 原样全绿")
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
