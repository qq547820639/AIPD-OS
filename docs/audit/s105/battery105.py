#!/usr/bin/env python3
"""第 105 片变异电池：把符号支路的同名候选遍历逐臂改坏，看谁活下来。

用法：`python docs/audit/s105/battery105.py`（就地变异 `scripts/doc_reference_census.py` 并还原；
收尾 sha 必须与开跑前相同）。**别在认证全量跑着的时候跑它**——每臂都要 spawn 一次常驻用例。

三类观察面（每臂都取全，缺一就没有"红在别处"的判别力）：
  · `self`   —— 量具自己的 `--self-test`（合成两极）；
  · `buckets`—— 真语料的 `symbol-missing` / `symbol-resolved` 计数（现读，不抄常数）；
  · `spec`   —— 常驻用例 `tests/test_doc_reference_census.py` 的退码（真仓两极在那儿）。
A0 先证明基线干净（三者都在预期位）且每个锚点字符串在场，否则整轮判"注入无效"退 5。
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "scripts" / "doc_reference_census.py"
SPEC = "tests/test_doc_reference_census.py"
PY = sys.executable
ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def spawn(args: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    proc = subprocess.run([PY, "-B", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=False, env={**dict(__import__("os").environ), **ENV})
    return proc.returncode, proc.stdout + proc.stderr


def observables() -> dict:
    """三观察面一次取全；`buckets` 直接 import 量具读真语料，不走文案解析。"""
    self_rc, self_out = spawn([str(SRC), "--self-test"])
    spec_rc, _ = spawn(["-m", "pytest", "-q", "-p", "no:cacheprovider", SPEC])
    sys.path.insert(0, str(ROOT / "scripts"))
    for mod in ("doc_reference_census",):
        sys.modules.pop(mod, None)
    import doc_reference_census as census
    buckets = census.audit(census.ROOT)["buckets"]
    return {"self_rc": self_rc, "self_ok": "全部对上" in self_out,
            "spec_rc": spec_rc,
            "missing": buckets.get("symbol-missing", 0),
            "resolved": buckets.get("symbol-resolved", 0)}


ARMS = [
    ("X1 关掉整条同名遍历",
     "        cands = same_name_paths(target, root)", "        cands = []",
     lambda o: o["missing"] > o["_base_missing"] or o["spec_rc"] != 0 or o["self_rc"] != 0),
    ("X2 候选清单被截窄成永不命中",
     '    return [root / q for q in _index(root) if q.endswith(needle) or q == rel]',
     "    return []",
     lambda o: o["missing"] > o["_base_missing"] or o["spec_rc"] != 0),
    ("X3 一份都没有也判 resolved",
     '        r.klass = "symbol-missing"\n        r.detail = (f"{p.relative_to(root)} 里找不到符号 {symbol!r}"',
     '        r.klass = "symbol-resolved"\n        r.detail = (f"{p.relative_to(root)} 里找不到符号 {symbol!r}"',
     lambda o: o["missing"] < o["_base_missing"] or o["spec_rc"] != 0 or o["self_rc"] != 0),
    ("X4 detail 报的是首选那份（假出处）",
     '                r.detail = (f"{q.relative_to(root)}:{alt[0]}-{alt[1]} ← {symbol}"',
     '                r.detail = (f"{p.relative_to(root)}:{alt[0]}-{alt[1]} ← {symbol}"',
     lambda o: o["spec_rc"] != 0),
]

MARKS = [arm[1] for arm in ARMS]


def main() -> int:
    orig = SRC.read_text(encoding="utf-8")
    ast.parse(orig)
    start = sha(SRC)
    base = observables()
    print(f"基线：self_rc={base['self_rc']} self_ok={base['self_ok']} spec_rc={base['spec_rc']} "
          f"missing={base['missing']} resolved={base['resolved']}")
    if base["self_rc"] != 0 or not base["self_ok"] or base["spec_rc"] != 0 or base["missing"] < 1:
        print("A0 前提不成立：基线本身不干净或符号档为空 ⇒ 后面的读数没有意义")
        return 5
    for mk in MARKS:
        if mk not in orig:
            print(f"A0 前提不成立：锚点不在场，这一臂会杀掉一个不存在的东西\n  {mk[:70]}")
            return 5
    killed = survived = wrong = 0
    for name, old, new, fires in ARMS:
        assert orig.count(old) == 1, f"{name} 锚点命中 {orig.count(old)} 次"
        mutant = orig.replace(old, new)
        ast.parse(mutant)
        SRC.write_text(mutant, encoding="utf-8")
        assert sha(SRC) != start, f"{name} 变异没落地（sha 未变）"
        try:
            obs = observables()
            obs["_base_missing"] = base["missing"]
        finally:
            SRC.write_text(orig, encoding="utf-8")
            assert sha(SRC) == start, f"{name} 还原失败"
        same = json.dumps({k: v for k, v in obs.items() if k != "_base_missing"},
                          sort_keys=True) == json.dumps(base, sort_keys=True)
        if fires(obs):
            verdict, killed = "KILLED", killed + 1
        elif same:
            verdict, survived = "SURVIVED", survived + 1
        else:
            verdict, wrong = "WRONG-REASON", wrong + 1
        print(f"{verdict:13} {name}｜self={obs['self_rc']} spec={obs['spec_rc']} "
              f"missing={obs['missing']}(基线 {base['missing']}) resolved={obs['resolved']}")
    end = sha(SRC)
    print(f"合计 KILLED {killed} / SURVIVED {survived} / WRONG-REASON {wrong} / 共 {len(ARMS)} 臂")
    print(f"收尾 sha {end}（开跑前 {start}）")
    return 0 if (killed == len(ARMS) and survived == 0 and wrong == 0 and end == start) else 4


if __name__ == "__main__":
    sys.exit(main())
