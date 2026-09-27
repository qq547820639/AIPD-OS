"""第 65 片 `scripts/absence_claim_census.py` 的变异电池：每条新分支都要有自己的原告。

每臂：改一处 → 断言 old 恰好命中 1 次且 new 原本 0 次 → 跑指定靶 → 收 rc 与关键读数 → 还原并验 sha。
靶分两种：`self-test`（合成语料）与 `pytest -k <expr>`（常驻用例）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TARGET = ROOT / "scripts/absence_claim_census.py"
VENV_PY = str(ROOT / ".venv/bin/python")

ARMS: list[dict] = [
    {
        "id": "A1-anchor-loosened-to-fulltext",
        "note": "locate 不绑 (capability, field)，退化成全文子串 ⇒ 五条同句里改一条会被读成五条都改完",
        "old": '    for rel, lineno, text in corpus.get(capability, {}).get(field, []):\n'
               '        if anchor in text:\n'
               '            return rel, field, lineno\n'
               '    return None',
        "new": '    for fields in corpus.values():\n'
               '        for rel, lineno, text in fields.get(field, []):\n'
               '            if anchor in text:\n'
               '                return rel, field, lineno\n'
               '    return None',
        "probes": ["pytest:wrong_capability"],
    },
    {
        "id": "A2-blindspot-overrides-a-found-falsifier",
        "note": "把 present 那一支挪到 check_problems 之后（第 65 片真犯过的耦合缺陷）"
                " ⇒ 别处的盲区会推翻本条已经拿到证据的判决",
        "old": '        if present:\n            verdict = CONTRADICTED\n'
               '        elif check_problems:\n            verdict = PRECONDITION\n'
               '        else:\n            verdict = HOLDS',
        "new": '        if check_problems:\n            verdict = PRECONDITION\n'
               '        elif present:\n            verdict = CONTRADICTED\n'
               '        else:\n            verdict = HOLDS',
        "probes": ["self-test"],
    },
    {
        "id": "A3-precondition-folded-into-holds",
        "note": "解析不出来时读成「这句话是对的」⇒ 盲区被折成合规",
        "old": '        if present:\n            verdict = CONTRADICTED\n'
               '        elif check_problems:\n            verdict = PRECONDITION\n'
               '        else:\n            verdict = HOLDS',
        "new": '        if present:\n            verdict = CONTRADICTED\n'
               '        else:\n            verdict = HOLDS',
        "probes": ["self-test", "pytest:precondition"],
    },
    {
        "id": "A4-identifier-face-degrades-to-text",
        "note": "AST 面换成逐行文本子串 ⇒ 注释里写「不做 X」会被读成「X 做了」（假红方向）",
        "old": '            if named is not None and named in want:\n'
               '                hits.append(f"{rel}:{lineno}")',
        "new": '            if named is not None and named in want:\n'
               '                hits.append(f"{rel}:{lineno}")\n'
               '        for no, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):\n'
               '            if any(w in ln for w in want):\n'
               '                hits.append(f"{rel}:{no}")',
        "probes": ["pytest:comment_only"],
    },
    {
        "id": "A5-dangling-claim-skipped",
        "note": "正文里找不到锚点就跳过 ⇒ 「删句不删账」这一整档消失",
        "old": '        if where is None:\n'
               '            rows.append({"id": claim.get("id"), "verdict": CLAIM_TEXT_ABSENT,',
        "new": '        if where is None:\n'
               '            rows.append({"id": claim.get("id"), "verdict": HOLDS,',
        "probes": ["self-test", "pytest:dangling"],
    },
    {
        "id": "A6-empty-ledger-reads-as-clean",
        "note": "去掉 claims_empty 前提 ⇒ 空账本退 0，整面判据静默失效",
        "old": '    if not claims:\n        problems.append("claims_empty: 账本一条都没登记")',
        "new": '    if False:\n        problems.append("claims_empty: 账本一条都没登记")',
        "probes": ["self-test"],
    },
    {
        "id": "A7-no-one-hop-const-resolution",
        "note": "只认字面量、不解析一跳常量 ⇒ bom/bom_cost 两个执行器看不见，"
                "「BOM 版本记录仍没有」那类过期话会读成成立（漏判方向）",
        "old": '            if isinstance(value, ast.Name):',
        "new": '            if False and isinstance(value, ast.Name):',
        "probes": ["self-test", "pytest:external"],
    },
    {
        "id": "A8-only-contradicted-judged",
        "note": "judged 里去掉 CLAIM_TEXT_ABSENT ⇒ 悬空账不再改判决/退码",
        "old": '    judged = [r for r in rows if r["verdict"] in (CONTRADICTED, CLAIM_TEXT_ABSENT)]',
        "new": '    judged = [r for r in rows if r["verdict"] in (CONTRADICTED,)]',
        "probes": ["self-test", "pytest:dangling"],
    },
    {
        "id": "A9-self-reference-guard-removed",
        "note": "扫描面不再排除量具自身与它的用例 ⇒ 自测夹具里的假锚点会进真分母",
        "old": '                if set(path.parts) & SKIP_DIRS or path.stem in SELF_STEMS:',
        "new": '                if set(path.parts) & SKIP_DIRS:',
        "probes": ["pytest:instrument_and_its"],
    },
    {
        "id": "A10-divergence-face-removed",
        "note": "去掉两份登记表对同一 id 各说各话那一面 ⇒ 第 65 片的真实失效形状读成干净",
        "old": '    divergence = duplicate_divergence(corpus)',
        "new": '    divergence = []',
        "probes": ["self-test", "pytest:divergent"],
    },
    {
        "id": "A11-anchor-reading-loses-file",
        "note": "读数不带文件名 ⇒ 两份登记表里的同一行号会互相冒充",
        "old": '"anchor_at": f"{where[0]}:{where[1]}:{where[2]}",',
        "new": '"anchor_at": f"{where[1]}:{where[2]}",',
        "probes": ["pytest:every_claim"],
    },
]

SELFTEST_PROBE = "self-test"


def sha() -> str:
    return hashlib.sha256(TARGET.read_bytes()).hexdigest()[:12]


def run_probe(probe: str) -> tuple[int, str]:
    if probe == SELFTEST_PROBE:
        cmd = [VENV_PY, str(TARGET), "--self-test"]
    else:
        expr = probe.split(":", 1)[1]
        cmd = [VENV_PY, "-m", "pytest", "tests/test_absence_claim_census.py",
               "-k", expr, "-q", "--no-header", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    tail = [ln for ln in (proc.stdout + proc.stderr).splitlines()
            if ("passed" in ln or "failed" in ln or "AssertionError" in ln
                or "error" in ln.lower() and "no tests ran" not in ln)][-3:]
    return proc.returncode, " | ".join(tail)[:300]


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
        TARGET.write_text(src.replace(old, new, 1), encoding="utf-8")
        try:
            if sha() == base:
                rows.append((arm["id"], "NOT-LANDED", "改写后 sha 未变"))
                continue
            readings = [(p, *run_probe(p)) for p in arm["probes"]]
        finally:
            TARGET.write_text(src, encoding="utf-8")
            assert sha() == base, f"{arm['id']} 还原失败"
        killed = any(rc != 0 for _p, rc, _t in readings)
        rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                     " ;; ".join(f"{pr}→rc={rc} {txt}"
                                for pr, rc, txt in readings)))
    print("=" * 72)
    print(f"基线 sha={base}（终局还原校验同值）")
    for rid, verdict, detail in rows:
        print(f"[{verdict:11}] {rid}\n    {detail}")
    killed = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {killed} / SURVIVED {sum(1 for _r, v, _d in rows if v == 'SURVIVED')}"
          f" / 锚点或落地问题 {sum(1 for _r, v, _d in rows if v not in ('KILLED', 'SURVIVED'))}")
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
