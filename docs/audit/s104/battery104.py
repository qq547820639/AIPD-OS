#!/usr/bin/env python3
"""第 104 片变异电池：把 `scripts/changelog_commit_crosscheck.py` 逐臂改坏，看谁活下来。

用法：`python docs/audit/s104/battery104.py`（就地变异 + 还原，收尾 sha 必须与开跑前相同）。

判据形状：A0 前提（每支锚点字符串必须在场）+ 六臂。每臂**先声明"红了算哪条判决"**，
再跑三类观察面：
  · `blob` —— 两支真历史 Blob 的缺席清单（`35ef6fc`→101、`629de86`→103）；
  · `tree` —— 真仓现读的退码与缺陷数；
  · `rc-no-git` —— 指向一棵没有 `.git` 的临时树（前提塌那一档的可观察面）；
  · `self` —— `--self-test` 的退码与自报行。
红在别处不算杀掉（WRONG-REASON），不红算 SURVIVED。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "scripts" / "changelog_commit_crosscheck.py"
PY = sys.executable
BLOBS = (("35ef6fc", 101), ("629de86", 103))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([PY, "-B", str(SRC), *args], capture_output=True,
                          text=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr


def load_module(tag: str):
    spec = importlib.util.spec_from_file_location(f"ccc_{tag}", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def observables(tag: str) -> dict:
    """四个观察面一次取全；`blob` 走内存里的那份模块，其余走子进程。"""
    mod = load_module(tag)
    blob = {}
    for sha_ref, victim in BLOBS:
        text = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha_ref}:CHANGELOG.md"],
                              capture_output=True, text=True, check=True).stdout
        subjects = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%s", sha_ref],
                                  capture_output=True, text=True, check=True).stdout.splitlines()
        rep = mod.emit(mod.audit(ROOT, subjects=subjects, changelog=text))
        blob[sha_ref] = {"victim_named": victim in rep["absent"], "absent": rep["absent"]}
    tree_rc, tree_out = run([])
    with tempfile.TemporaryDirectory() as td:
        nogit_rc, _ = run(["--repo", str(Path(td) / "nope")])
    self_rc, self_out = run(["--self-test"])
    return {"blob": blob, "tree_rc": tree_rc, "tree_out": tree_out,
            "nogit_rc": nogit_rc, "self_rc": self_rc, "self_ok": "全部对上" in self_out}


ARMS = [
    ("X1 摘掉缺席判决",
     "    absent = sorted(want - have)", "    absent = []",
     lambda o: not any(v["victim_named"] for v in o["blob"].values())),
    ("X2 方向反过来（条目侧当分母）",
     "    absent = sorted(want - have)", "    absent = sorted(have - want)",
     lambda o: o["tree_rc"] == 4 and "不算原告" in o["tree_out"]
     and not all(v["victim_named"] for v in o["blob"].values())),
    ("X3 把前提塌折成退 0",
     '    if rep["premise_broken"]:\n        return 2',
     '    if rep["premise_broken"]:\n        return 0',
     lambda o: o["nogit_rc"] == 0),
    ("X4 去掉主题行的词边界",
     'SLICE_IN_SUBJECT = re.compile(r"(?<![0-9A-Za-z_.-])s(\\d{2,3})(?![0-9])")',
     'SLICE_IN_SUBJECT = re.compile(r"s(\\d{2,3})(?![0-9])")',
     lambda o: o["self_rc"] != 0 or not o["self_ok"]),
    ("X5 让「一行点名多片」恒零",
     "    n = 0\n    for line in text.splitlines():\n"
     '        if ENTRY_LINE.match(line) and len({m.group(1) for m in SLICE_REF.finditer(line)}) >= 2:\n'
     "            n += 1\n    return n",
     "    return 0",
     lambda o: o["self_rc"] != 0 or not o["self_ok"]),
    ("X6 摘掉两口径对账",
     "    diverge = sorted((want & have) - strict)", "    diverge = []",
     lambda o: o["self_rc"] != 0 or not o["self_ok"]),
]

MARKS = [arms[1] for arms in ARMS]


def main() -> int:
    orig = SRC.read_text(encoding="utf-8")
    ast.parse(orig)
    before = sha(SRC)
    base = observables("base")
    print(f"基线：tree_rc={base['tree_rc']} nogit_rc={base['nogit_rc']} "
          f"self_rc={base['self_rc']} self_ok={base['self_ok']} "
          f"blob={ {k: v['absent'] for k, v in base['blob'].items()} }")
    if base["tree_rc"] != 0 or base["self_rc"] != 0 or base["nogit_rc"] != 2:
        print("A0 前提不成立：基线本身就不干净 ⇒ 后面的读数没有意义")
        return 5
    if not all(v["victim_named"] for v in base["blob"].values()):
        print("A0 前提不成立：真历史 Blob 没被点名 ⇒ 判据本来就没牙")
        return 5
    for mk in MARKS:
        if mk not in orig:
            print(f"A0 前提不成立：锚点不在场 ⇒ 这一臂会「杀掉一个不存在的东西」\n  {mk[:60]}")
            return 5

    killed = survived = wrong = 0
    base_json = json.dumps({k: v for k, v in base.items()}, ensure_ascii=False, default=str)
    for name, old, new, fires in ARMS:
        assert orig.count(old) == 1, f"{name} 锚点命中 {orig.count(old)} 次"
        mutant = orig.replace(old, new)
        ast.parse(mutant)
        SRC.write_text(mutant, encoding="utf-8")
        after = sha(SRC)
        try:
            obs = observables(name[:2])
        finally:
            SRC.write_text(orig, encoding="utf-8")
            assert sha(SRC) == before, f"{name} 还原失败"
        # 理由门：红了但不是红在本臂声明的那条判决上 ⇒ WRONG-REASON，不算杀掉也不算存活
        obs_json = json.dumps({k: v for k, v in obs.items()}, ensure_ascii=False, default=str)
        if fires(obs):
            verdict, killed = "KILLED", killed + 1
        elif obs_json != base_json:
            verdict, wrong = "WRONG-REASON", wrong + 1
        else:
            verdict, survived = "SURVIVED", survived + 1
        print(f"{verdict:9} {name}｜tree_rc={obs['tree_rc']} nogit={obs['nogit_rc']} "
              f"self_rc={obs['self_rc']} self_ok={obs['self_ok']} "
              f"absent={ {k: v['absent'] for k, v in obs['blob'].items()} }")
    print(f"合计：KILLED {killed} / SURVIVED {survived} / WRONG-REASON {wrong} / 共 {len(ARMS)} 臂")
    print(f"收尾 sha {sha(SRC)}（开跑前 {before}）")
    return 0 if survived == 0 and wrong == 0 and killed == len(ARMS) and sha(SRC) == before else 4


if __name__ == "__main__":
    sys.exit(main())
