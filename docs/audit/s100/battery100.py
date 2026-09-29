r"""第 100 片变异电池：`scripts/scripts_lint_ratchet.py` 的六处口径，各配一支撤销臂。

| 臂 | 撤掉的东西 |
| --- | --- |
| A0 | 不改任何字节（对照臂）⇒ 必须全绿 |
| A1 | 棘轮那一判的阈值抬到不可达（`today > want + 999`）⇒ 涨了也读成持平 |
| A2 | "新规则码没登记"那一判 ⇒ 缺条目被当成登记值 0 的普通格 |
| A3 | "已偿待撤"那一判 ⇒ 清单只涨不消，谁也不知道哪格该摘 |
| A4 | 直连清单对账的比较式自反化（`face == face`）⇒ 接面这件事不再有人核 |
| A5 | `corpus_empty` 这个**标记名**改掉 ⇒ 下游（用例与 README 的复算入口）认不出这条前提 |
| A6 | `--emit` 挡空语料之后的那道 `return 2`（换成 `pass`）⇒ 生成侧照样写出空册 |

**为什么每一支都长这样而不是 `if False and …`**：靶文件自己就在被量的面上（`scripts/` 里的
脚本会被 ruff 数），`False and x` 这种常量条件会被判成 **SIM223**，于是基线凭空多一格
"未登记"——臂"被抓住"了，却是**因为夹具变了而不是因为判据变了**。第一版就是这么被本电池的
债中性门挡下来的（4 支 BAD-ANCHOR，0 支误判 KILLED）。现在每支臂落笔前后各数一次靶文件命中，
不等就记 BAD-ANCHOR 而不是 KILLED。
A5 钉的是**标记名本身**：`corpus_empty` / `baseline_missing` 这些前缀是量具、常驻用例与
文档复算入口三方共用契约，改名等于把"前提塌"降级成"没人认得的第三条状态"。

跑法：`python -B docs/audit/s100/battery100.py`。锚点先数：任一命中 ≠ 1 就一支都不跑。
语法门用 `ast.parse`（`py_compile` 会把变异体的字节码落进 `sys.pycache_prefix`，
同长度变异 + 同秒还原会遮蔽还原后的源——第 96 片实测），子进程带 `-B`，每臂复位后清缓存。
"""
from __future__ import annotations

import ast
import collections
import contextlib
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TOOL = REPO / "scripts" / "scripts_lint_ratchet.py"
TESTS = ["tests/test_scripts_lint_ratchet.py"]

ARMS = [
    ("A0-control-no-change", "对照：原样必须全绿", None, None),
    ("A1-ratchet-never-fires", "涨了也读成持平（阈值抬到不可达）",
     '        elif today > want:',
     '        elif today > want + 999:'),
    ("A2-unregistered-never-fires", "新规则码不再要求记账",
     '        if want == 0 and today > 0:',
     '        if want < 0 and today > 0:'),
    ("A3-paid-never-fires", "已偿的格不再要求摘掉",
     '        elif want > 0 and today == 0:',
     '        elif want > 0 and today < 0:'),
    ("A4-face-check-self-reflexive", "ci.yml 直连清单不再与 0 债集合对账",
     '    face_ok = face == zero or (zero == sorted(files) and RUFF_ARG in face)',
     '    face_ok = face == face or (zero == sorted(files) and RUFF_ARG in face)'),
    ("A5-premise-tag-renamed", "前提标记名改掉 ⇒ 下游认不出这条前提",
     '        problems.append(f"corpus_empty',
     '        problems.append(f"corpusXXXX'),
    ("A6-emit-still-writes-on-empty", "--emit 挡不住空语料（照样写出空册）",
     '        print("前提不成立 ⇒ 整批不落盘：" + "；".join(problems))\n        return 2',
     '        print("前提不成立 ⇒ 整批不落盘：" + "；".join(problems))\n        pass'),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def _drop_cache() -> None:
    for cand in (importlib.util.cache_from_source(str(TOOL)),
                 str(TOOL.parent / "__pycache__"
                     / f"{TOOL.stem}.{sys.implementation.cache_tag}.pyc")):
        with contextlib.suppress(OSError):
            os.remove(cand)


def target_debt() -> collections.Counter:
    """靶文件当前的 ruff 命中表（(行, 码) 计数）——债中性别靠肉眼，靠它。"""
    proc = subprocess.run([str(REPO / ".venv/bin/ruff"), "check", "--no-cache",
                           "--output-format", "concise", str(TOOL.relative_to(REPO))],
                          cwd=REPO, capture_output=True, text=True)
    return collections.Counter(ln.split(":")[3].strip().split()[0]
                               for ln in proc.stdout.splitlines() if ln.startswith("scripts/"))


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-B", "-m", "pytest", "-q",
                           "--no-header", "-p", "no:cacheprovider", *TESTS],
                          cwd=REPO, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                               "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    _drop_cache()
    original = TOOL.read_bytes()
    text = original.decode("utf-8")
    print(f"原文件 sha={sha(original)} 靶文件债={dict(target_debt()) or '无'}")
    stale = [(arm[0], text.count(arm[2])) for arm in ARMS if arm[2] is not None
             and text.count(arm[2]) != 1]
    if stale:
        for n, h in stale:
            print(f"[BAD-ANCHOR] {n} 锚点命中 {h} 次（要 1）")
        print("锚点普查不过 ⇒ 一支臂都不跑。")
        return 7
    print(f"[ANCHORS OK] {sum(1 for a in ARMS if a[2])} 支臂各命中 1 次")
    base_debt = target_debt()
    rc, out = run_tests()
    if rc != 0:
        print("A0 对照臂不绿，电池前提不成立：", out[-1500:])
        return 5
    print("[CONTROL OK] A0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, old, new in ARMS:
        if old is None:
            continue
        TOOL.write_text(text.replace(old, new, 1), encoding="utf-8")
        if sha(TOOL.read_bytes()) == sha(original):
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        try:
            ast.parse(TOOL.read_text(encoding="utf-8"))
            err = ""
        except SyntaxError as exc:
            err = str(exc)
        if err:
            print(f"[BAD-ANCHOR] {name} 变异体语法不过：{err[:200]}")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            continue
        debt = target_debt()
        if debt != base_debt:
            print(f"[BAD-ANCHOR] {name} 不债中性：靶文件命中从 {dict(base_debt)} 变成 {dict(debt)}"
                  f" ⇒ 抓住它的是夹具变了，不是判据变了")
            marks["BAD-ANCHOR"] += 1
            TOOL.write_bytes(original)
            _drop_cache()
            continue
        rc, out = run_tests()
        TOOL.write_bytes(original)
        _drop_cache()
        if sha(TOOL.read_bytes()) != sha(original):
            print(f"[!] 复位失败 {name}")
            return 6
        killed = [ln.split(" - ")[0].replace("FAILED ", "")
                  for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {name}（{what}）撤掉之后用例照绿 ⇒ 这一格其实没被看见")
            marks["SURVIVED"] += 1
        else:
            print(f"[KILLED]   {name}（{what}）被抓住 {len(killed)} 条：{'; '.join(killed)[:520]}")
            marks["KILLED"] += 1
    total = sum(1 for a in ARMS if a[2])
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    print(f"收尾复算 sha={sha(TOOL.read_bytes())}（应等于 {sha(original)}）"
          f"；靶文件债={dict(target_debt()) or '无'}")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
