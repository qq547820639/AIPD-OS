"""第 66 片新分支的变异电池（计数档 + file 锚点档）。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TARGET = ROOT / "scripts/absence_claim_census.py"
PY = str(ROOT / ".venv/bin/python")

ARMS: list[dict] = [
    {
        "id": "B1-count-folds-empty-authority-into-violation",
        "note": "去掉「权威面空/有盲区就不判」那一支 ⇒ 把看不见折成句里写错（第 66 片的真错）",
        "old": '        if blind or not authority:\n'
               '            return (False, [], (blind or '
               '[f"authority_empty: {scope} 档一个位点都没读到"]))',
        "new": '        if False:\n            return (False, [], ["x"])',
        "probes": ["self-test", "pytest:missing_authority"],
    },
    {
        "id": "B2-markdown-not-stripped",
        "note": "不剥 `*` ⇒ 文档面永远读不到数，计数档在唯一需要它的面上静默不开火",
        "old": '    text = text.replace("*", "")',
        "new": '    text = text + ""',
        "probes": ["self-test", "pytest:document_face"],
    },
    {
        "id": "B3-count-taken-from-whole-field",
        "note": "不切句，拿整段文本取第一个数量词 ⇒ 数会读到别的小句头上",
        "old": '            root, dict(claim.get("check", {})), slice_sentence(text, anchor))',
        "new": '            root, dict(claim.get("check", {})), text)',
        "probes": ["self-test"],
    },
    {
        "id": "B4-file-anchor-branch-removed",
        "note": "账本不吃文档条目（只吃登记表）⇒ 文档那格变悬空账，第 66 片的两个面少一个",
        "old": '    if rel:\n        path = root / rel',
        "new": '    if False:\n        path = root / rel',
        "probes": ["self-test", "pytest:document_face"],
    },
    {
        "id": "B5-authority-ignores-which-graph",
        "note": "不分 truth / canonical，凡 add_edge 位点都算 truth"
                " ⇒ 权威数从 8 变 12（含 SQL 入口则更多）",
        "old": '        elif "LineageGraph" in text:',
        "new": '        elif True or "LineageGraph" in text:',
        "probes": ["self-test", "pytest:count_face"],
    },
    {
        "id": "B6-only-arabic-digits",
        "note": "数词表清空（正则只吃阿拉伯数字）⇒ 中文写法的计数句一律读不到",
        "old": 'r"(?:有|共|为)\\s*(\\d+|[一二三四五六七八九十两])\\s*个"',
        "new": 'r"(?:有|共|为)\\s*(\\d+)\\s*个"',
        "probes": ["self-test"],
    },
]


def sha() -> str:
    return hashlib.sha256(TARGET.read_bytes()).hexdigest()[:12]


def run_probe(probe: str) -> tuple[str, int, str]:
    if probe == "self-test":
        cmd = [PY, str(TARGET), "--self-test"]
    else:
        cmd = [PY, "-m", "pytest", "tests/test_absence_claim_census.py",
               "-k", probe.split(":", 1)[1], "-q", "--no-header", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    out = proc.stdout + proc.stderr
    tail = [ln for ln in out.splitlines()
            if "passed" in ln or "failed" in ln or "AssertionError" in ln
            or "SyntaxError" in ln or "全部对上" in ln][-2:]
    return probe, proc.returncode, " | ".join(t[:110] for t in tail)


def main() -> int:
    base = sha()
    src = TARGET.read_text(encoding="utf-8")
    rows = []
    for arm in ARMS:
        old, new = arm["old"], arm["new"]
        if src.count(old) != 1:
            rows.append((arm["id"], "BAD-ANCHOR", f"old 命中 {src.count(old)} 次"))
            continue
        if new in src:
            rows.append((arm["id"], "BAD-ANCHOR", "new 文本原本已在树上"))
            continue
        mutated = src.replace(old, new, 1)
        compile_ok = True
        try:
            compile(mutated, str(TARGET), "exec")
        except SyntaxError as exc:
            compile_ok = False
            rows.append((arm["id"], "BAD-MUTATION", f"注入后语法不过：{exc}"))
        if compile_ok:
            TARGET.write_text(mutated, encoding="utf-8")
            try:
                assert sha() != base, "落地失败：sha 未变"
                readings = [run_probe(p) for p in arm["probes"]]
            finally:
                TARGET.write_text(src, encoding="utf-8")
                assert sha() == base, "还原失败"
            killed = any(rc != 0 for _p, rc, _t in readings)
            rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                         " ;; ".join(f"{p}→rc={rc} {t}" for p, rc, t in readings)))
    print("=" * 72)
    print(f"基线 sha={base}（每臂还原后校验同值）")
    for rid, verdict, detail in rows:
        print(f"[{verdict:11}] {rid}\n    {detail}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    s = sum(1 for _r, v, _d in rows if v == "SURVIVED")
    b = len(rows) - k - s
    print(f"合计 KILLED {k} / SURVIVED {s} / 电池自身问题 {b}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
