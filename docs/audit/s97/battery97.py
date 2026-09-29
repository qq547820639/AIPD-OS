r"""第 97 片变异电池：`release_evidence.py` 那四支"原先没人调"的分支，每个口径各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| W0 | 不改任何字节（对照臂）⇒ 必须全绿，否则电池前提不成立 |
| W1 | 版本号退回**属性优先**（`mod.__version__` 赢过打包元数据） |
| W2 | `not-installed` 折成 `unknown`（"没装"与"给不出版本"读成同一种形状） |
| W3 | `pip freeze` 不再看退码（失败时把垃圾 stdout 记进证件） |
| W4 | freeze 失败时把整段锁文件一起带走（"一次尽力而为失败 ⇒ 全段空"） |
| W5 | `bundle_path` 写成绝对路径（这个字段的全部意义就是可重定位） |
| W6 | 非 zip 不再退化成"整包自身"一条（退化成静默 0 条＝空清单看着像合规） |
| W7 | zip 每条的 sha 用整包 sha 顶替（逐条对账失效，条目数照样对） |
| W8 | 条目不再按 path 排序 |
| W9 | 环境段的 `packages` 循环不跑（那一格从证件里静默消失） |

用例简名：`host` = `test_build_environment_header_fields_are_the_host_truth`；
`poles` = `test_metadata_wins_and_the_two_missing_shapes_stay_distinct`；
`lock` = `test_dependency_lock_keeps_lockfiles_when_pip_freeze_fails_or_lies`；
`zip` = `test_zip_bundle_lists_every_member_with_independently_recomputed_sha`；
`nonzip` = `test_non_zip_bundle_degrades_to_exactly_one_self_entry`；
`relpath` = `test_bundle_path_is_relative_and_not_tied_to_the_dev_machine`；
`cli` = `test_bundle_cli_flag_writes_the_bundle_manifest_and_omission_does_not`；
`disk` = `test_provenance_on_disk_carries_a_populated_build_environment`（生产侧，
读的是已入库那份 `PROVENANCE.json` ⇒ 它**不会**因变异而红，这是它的用途而不是失败）。

跑法：`python -B docs/audit/s97/battery97.py`。开局先数锚点：任一锚点命中 ≠ 1 就一支都不跑（退 7）。

两处硬化的形状是第 96 片付过账才写进来的：语法检查一律 `ast.parse`（`py_compile` 会把
**变异体**的字节码落进 `sys.pycache_prefix`，而"同长度变异 + 同秒还原"会让缓存被判定仍然有效，
之后每次 import 跑的都是变异体）；跑测试的子进程带 `-B` 与 `PYTHONDONTWRITEBYTECODE=1`，
且开局/每臂复位后各清一次缓存路径。
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
TOOL = REPO / "scripts" / "release_evidence.py"
TESTS = ["tests/test_release_evidence_environment.py"]

ARMS = [
    ("W0-control-no-change", "对照：原样必须全绿", None, None),
    ("W1-attribute-first-version", "版本号退回属性优先",
     '    try:\n'
     '        return importlib.metadata.version(pkg)\n'
     '    except importlib.metadata.PackageNotFoundError:\n'
     '        pass\n',
     '    try:\n'
     '        return getattr(__import__(pkg), "__version__", "unknown")\n'
     '    except Exception:\n'
     '        return "not-installed"\n'),
    ("W2-not-installed-folds-to-unknown", "没装折成给不出版本",
     '        return "not-installed"',
     '        return "unknown"'),
    ("W3-freeze-return-code-ignored", "freeze 不看退码",
     '        if freeze.returncode == 0:',
     '        if True:'),
    ("W4-lockfiles-die-with-freeze", "freeze 失败带走整段锁文件",
     '    for name in LOCKFILES:',
     '    for name in (LOCKFILES if lock["pip_freeze"] is not None else []):'),
    ("W5-bundle-path-absolute", "bundle_path 写成绝对路径",
     '    bundle_path = os.path.relpath(str(bundle.resolve()), str(base))',
     '    bundle_path = str(bundle.resolve())'),
    ("W6-nonzip-degrades-to-nothing", "非 zip 不再退化成一条",
     '        entries.append({"path": bundle.name, "size": bundle.stat().st_size,\n'
     '                        "sha256": bundle_sha})',
     '        pass'),
    ("W7-entry-sha-is-bundle-sha", "每条 sha 用整包顶替",
     '                    "sha256": _sha256_bytes(data),',
     '                    "sha256": bundle_sha,'),
    ("W8-entries-unsorted", "条目不再排序",
     '    entries.sort(key=lambda e: e["path"])',
     '    pass'),
    ("W9-packages-loop-dropped", "环境段的 packages 不跑",
     '    for pkg in ("cryptography", "aipd_os", "jsonschema"):',
     '    for pkg in ():'),
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


def drop_cache() -> None:
    """清掉本文件的两份字节码缓存：`sys.pycache_prefix`（macOS 默认在 ~/Library/Caches）与 `__pycache__`。"""
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__" / (TOOL.stem + f".{sys.implementation.cache_tag}.pyc"))):
        with contextlib.suppress(OSError):
            os.remove(cand)


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    drop_cache()
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
        print("W0 对照臂不绿，电池前提不成立：", out[-1200:])
        return 5
    print("[CONTROL OK] W0 原样全绿")
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
        try:
            ast.parse(TOOL.read_text(encoding="utf-8"))
            chk_err = ""
        except SyntaxError as exc:
            chk_err = str(exc)
        if chk_err:
            print(f"[BAD-ANCHOR] {arm[0]} 变异体语法不过：{chk_err[:200]}")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        rc, out = run_tests()
        TOOL.write_bytes(original)
        drop_cache()
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
