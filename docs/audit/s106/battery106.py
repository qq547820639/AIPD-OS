#!/usr/bin/env python3
"""第 106 片变异电池：把异常卫生门的四条判据逐臂改坏，看谁活下来。

用法：`python docs/audit/s106/battery106.py`（就地变异 `tests/test_exception_hygiene.py`
与 `scripts/audit_repo.py` 并还原；收尾 sha 必须与开跑前相同）。**别在认证全量跑着的
时候跑它**——每臂都要 spawn 一次常驻用例。

观察面：`pytest tests/test_exception_hygiene.py` 的 **FAILED 用例集合**（不是单个退码——
每臂都要点名"该红的是哪几支"，红在别处记 WRONG-REASON）。A0 先证明基线 14/14 干净
且每个锚点字符串在场，否则整轮判"注入无效"退 5。
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "tests" / "test_exception_hygiene.py"
SRC2 = ROOT / "scripts" / "audit_repo.py"
SPEC = "tests/test_exception_hygiene.py"
PY = sys.executable
ENV = {"PYTHONDONTWRITEBYTECODE": "1"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def run_spec() -> set[str]:
    env = {**dict(os.environ), **ENV}
    proc = subprocess.run([PY, "-B", "-m", "pytest", "-q", "--tb=no", "-rf",
                           "-p", "no:cacheprovider", SPEC],
                          cwd=str(ROOT), capture_output=True, text=True, check=False, env=env)
    failed = set()
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.startswith("FAILED "):
            failed.add(line.split("::", 1)[1].split(" - ")[0].strip())
    return failed


# (名字, 目标文件, 锚点, 变异, 该红用例的判定)
ARMS = [
    ("X1 记号窗口整面放行", SRC,
     '    window = lines[max(lineno - 2, 0):lineno + 1]\n    return any(MARKER in line for line in window)',
     '    return True',
     lambda f: {"test_control_unmarked_except_pass_fires",
                "test_control_unmarked_suppress_fires"} <= f),
    ("X2 旧记号判据致盲（收回臂假死）", SRC,
     'def _old_marker_lines(parsed):\n    hits = []',
     'def _old_marker_lines(parsed):\n    return []\n    hits = []',
     lambda f: "test_control_old_marker_fires_retraction_arm" in f),
    ("X3 suppress 形态看不见（裸导入也放行）", SRC,
     '        name = getattr(func, "id", None) or getattr(func, "attr", None)\n        if name == "suppress":\n            return True\n    return False',
     '        return False\n    return False',
     lambda f: {"test_control_unmarked_suppress_fires",
                "test_control_bare_suppress_import_shape_also_fires"} <= f),
    ("X4 旧记号真回到代码面（收回臂真开火）", SRC2,
     '        # aipd: empty-except - 目录统计尽力而为：权限/IO 失败不阻断审计',
     '        # noqa: EMPTY_EXCEPT - 目录统计尽力而为：权限/IO 失败不阻断审计',
     lambda f: {"test_old_marker_fully_retracted", "test_no_unmarked_swallow"} <= f),
    ("X5 解析不了静默跳过（第三态回潮）", SRC,
     '            unparseable.append(Path(f"{f} (解析不了: {exc})"))',
     '            pass  # X5 静默跳过',
     lambda f: "test_control_unparseable_file_is_reported_not_skipped" in f),
    ("X6 扫描面塌到只剩一个目录", SRC,
     'SCAN_DIRS = [\n    ROOT / "src" / "aipd_os",\n    ROOT / "scripts",\n    ROOT / "state_service",\n]',
     'SCAN_DIRS = [\n    ROOT / "state_service",\n]',
     lambda f: "test_scan_directories_present" in f),
]


def main() -> int:
    orig = SRC.read_text(encoding="utf-8")
    orig2 = SRC2.read_text(encoding="utf-8")
    ast.parse(orig)
    ast.parse(orig2)
    start, start2 = sha(SRC), sha(SRC2)
    base = run_spec()
    print(f"基线：FAILED={len(base)}（期望 0）")
    if base:
        print("A0 前提不成立：基线本身红 ⇒ 后面的读数没有意义")
        return 5
    for _name, target, old, _new, _fires in ARMS:
        text = orig if target == SRC else orig2
        if text.count(old) != 1:
            print(f"A0 前提不成立：锚点命中 {text.count(old)} 次（要恰好 1）\n  {old[:70]}")
            return 5
    killed = survived = wrong = 0
    for name, target, old, new, fires in ARMS:
        text = orig if target == SRC else orig2
        path = target
        start_sha = start if target == SRC else start2
        mutant = text.replace(old, new)
        ast.parse(mutant)
        path.write_text(mutant, encoding="utf-8")
        assert sha(path) != start_sha, f"{name} 变异没落地（sha 未变）"
        try:
            failed = run_spec()
        finally:
            path.write_text(text, encoding="utf-8")
            assert sha(path) == start_sha, f"{name} 还原失败"
        if fires(failed):
            verdict, killed = "KILLED", killed + 1
        elif not failed:
            verdict, survived = "SURVIVED", survived + 1
        else:
            verdict, wrong = "WRONG-REASON", wrong + 1
        print(f"{verdict:13} {name}｜红 {len(failed)} 支: {sorted(failed)[:3]}")
    end, end2 = sha(SRC), sha(SRC2)
    print(f"合计 KILLED {killed} / SURVIVED {survived} / WRONG-REASON {wrong} / 共 {len(ARMS)} 臂")
    print(f"收尾 sha {end}/{end2}（开跑前 {start}/{start2}）")
    ok = (killed == len(ARMS) and survived == 0 and wrong == 0
          and end == start and end2 == start2)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
