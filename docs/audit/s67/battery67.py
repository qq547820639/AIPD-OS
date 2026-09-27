"""第 67 片新分支的变异电池（窄档、去处台账、豁免陈旧、table_ddl、_norm 剥号）。"""
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
        "id": "C1-coverage-comparison-does-not-strip-asterisks",
        "note": "比较锚点时不剥 markdown 的 * ⇒ 已登记的句子被读成没登记（假未处置）",
        "old": '    anchored = {_norm(str(c.get("anchor"))) for c in claims if c.get("anchor")}',
        "new": '    anchored = {str(c.get("anchor")) for c in claims if c.get("anchor")}',
        "probes": ["pytest:real_corpus_all", "self-test"],
    },
    {
        "id": "C2-narrowing-dropped",
        "note": "不做收窄，宽档直接当判据面 ⇒ 每条行为描述都被逼着登记或豁免",
        "old": '    narrow = [s for s in sentences if is_capability_absence(s.split("|", 2)[-1])]',
        "new": '    narrow = list(sentences)',
        "probes": ["self-test", "pytest:partial_ledger"],
    },
    {
        "id": "C3-non-claim-exclusions-emptied",
        "note": "清空「谈判决/谈口径」的排除表 ⇒ 那类句子重新掉进判据面",
        "old": 'NON_CLAIM_PATTERNS = ("不算收口", "不写任何公差", "即判未收口", "记成盲区",\n'
               '                      "不会被伪装成", "不能用来放行", "读者不会把")',
        "new": 'NON_CLAIM_PATTERNS = ()',
        "probes": ["self-test", "pytest:real_corpus_all", "pytest:partial_ledger"],
    },
    {
        "id": "C4-unaccounted-not-judged",
        "note": "只数不判：未处置不再产出行 ⇒ 账没结清也照样绿",
        "old": '    for s in unaccounted:\n'
               '        rows.append({"id": f"UNACCOUNTED:{s.split(\'|\', 1)[0]}",\n'
               '                     "verdict": UNACCOUNTED, "evidence": [], "problems": [],\n'
               '                     "detail": s.split("|", 2)[-1][:90]})',
        "new": '    for s in unaccounted:\n        pass',
        "probes": ["self-test", "pytest:partial_ledger"],
    },
    {
        "id": "C5-stale-exemption-not-judged",
        "note": "豁免台账漂了不响 ⇒ 僵尸豁免可以永远躺在账上",
        "old": '        if not any(_norm(key) in _norm(s.split("|", 2)[-1]) for s in sentences):\n'
               '            rows.append({"id": f"EXEMPT:{key[:24]}", "verdict": CLAIM_TEXT_ABSENT,',
        "new": '        if False:\n'
               '            rows.append({"id": f"EXEMPT:{key[:24]}", "verdict": CLAIM_TEXT_ABSENT,',
        "probes": ["self-test", "pytest:exemption_without"],
    },
    {
        "id": "C6-thin-exemption-reason-accepted",
        "note": "空/短理由的豁免照收 ⇒ 「豁免」变成一条不需要成本的后门",
        "old": '        if len(reason.strip()) < 8:',
        "new": '        if False:',
        "probes": ["self-test"],
    },
    {
        "id": "C7-table-ddl-kind-removed",
        "note": "去掉 table_ddl 那一支 ⇒ 「没建 operations 表」这句退回无人认领",
        "old": '    if kind == "table_ddl":\n'
               '        name = str(check.get("table", ""))',
        "new": '    if kind == "table_ddl_disabled":\n'
               '        name = str(check.get("table", ""))',
        "probes": ["pytest:real_corpus_all", "self-test"],
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
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines()
            if "passed" in ln or "failed" in ln or "AssertionError" in ln
            or "SyntaxError" in ln or "Error" in ln][-2:]
    return probe, proc.returncode, " | ".join(k[:90] for k in keep)


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
        try:
            compile(mutated, str(TARGET), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", f"注入后语法不过：{exc}"))
            continue
        TARGET.write_text(mutated, encoding="utf-8")
        try:
            assert sha() != base, "落地失败：sha 未变"
            readings = [run_probe(p) for p in arm["probes"]]
        finally:
            TARGET.write_text(src, encoding="utf-8")
            assert sha() == base, "还原失败"
        killed = any(rc != 0 for _p, rc, _t in readings)
        rows.append((arm["id"], "KILLED" if killed else "SURVIVED",
                     " ;; ".join(f"{pr}→rc={rc} {t}" for pr, rc, t in readings)))
    print("=" * 72)
    print(f"基线 sha={base}（每臂还原后校验同值）")
    for rid, verdict, detail in rows:
        print(f"[{verdict:11}] {rid}\n    {detail}")
    k = sum(1 for _r, v, _d in rows if v == "KILLED")
    s = sum(1 for _r, v, _d in rows if v == "SURVIVED")
    print(f"合计 KILLED {k} / SURVIVED {s} / 电池自身问题 {len(rows) - k - s}")
    return 0 if k == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
