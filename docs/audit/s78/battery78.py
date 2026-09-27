# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 78 片（真文本源优先 + 策略前移）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
FT = ROOT / "scripts/research/fetch_fulltexts.py"
LB = ROOT / "src/aipd_os/research/fulltext.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_research_fulltext_step.py"]

ARMS = [
    {"id": "V1-pmc-no-longer-preferred", "file": FT,
     "note": "PMC 优先级摘掉 ⇒ 同一篇文章又退回 PDF，白等一个抽取器",
     "old": '    if pmcid:', "new": '    if pmcid and False:'},
    {"id": "V2-xml-sniff-removed", "file": FT,
     "note": "不认 JATS ⇒ XML 掉进 undecodable/纯文本分支，正文计数说谎",
     "old": '    if head.startswith(b"<?xml") or b"<article" in head or b"<jats:" in head:',
     "new": '    if False:'},
    {"id": "V3-policy-checked-after-download", "file": FT,
     "note": "策略判定挪回下载之后 ⇒ 不开放的也发请求，且 outcome 与 access 再次互相打脸",
     "old": '        pre = classify_access(url, license=target["license"])',
     "new": '        pre = ACCESS_OPEN'},
    {"id": "V4-outcome-not-tied-to-access", "file": FT,
     "note": "去掉 not_open_* 派生 ⇒ 抽到字面文本就自称 extracted_*，与 access=restricted 并存",
     "old": ("        if rec.access != ACCESS_OPEN:\n"
             '            outcome = f"not_open_{rec.access}"'),
     "new": ("        if False:\n"
             '            outcome = f"not_open_{rec.access}"')},
    {"id": "V5-landing-page-guard-gone", "file": FT,
     "note": "全文长度下界归零 ⇒ 摘要落地页当正文（与第 77 片同一形状）",
     "old": '        if text and len(text) < MIN_FULL_TEXT_CHARS:',
     "new": '        if False:'},
    {"id": "V6-host-allowlist-widened", "file": LB,
     "note": "白名单顺手放进别的站 ⇒ 主机边界的用例必须红",
     "old": '    "zenodo.org",', "new": '    "zenodo.org",\n    "researchgate.net",'},
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=900)
    out = proc.stdout + proc.stderr
    keep = [ln for ln in out.splitlines() if "passed" in ln or "failed" in ln][-1:]
    return proc.returncode, keep[0][:80] if keep else ""


def main():
    srcs = {a["file"]: a["file"].read_text(encoding="utf-8") for a in ARMS}
    bases = {k: sha(k) for k in srcs}
    rows = []
    for arm in ARMS:
        tgt, old, new = arm["file"], arm["old"], arm["new"]
        src = srcs[tgt]
        if src.count(old) != 1:
            rows.append((arm["id"], "BAD-ANCHOR", f"old 命中 {src.count(old)} 次"))
            continue
        if new in src:
            rows.append((arm["id"], "BAD-ANCHOR", "new 已在树上"))
            continue
        mutated = src.replace(old, new, 1)
        try:
            compile(mutated, str(tgt), "exec")
        except SyntaxError as exc:
            rows.append((arm["id"], "BAD-MUTATION", str(exc)))
            continue
        tgt.write_text(mutated, encoding="utf-8")
        try:
            assert sha(tgt) != bases[tgt], "落地失败"
            rc, line = run_tests()
        finally:
            tgt.write_text(src, encoding="utf-8")
            assert sha(tgt) == bases[tgt], "还原失败"
        rows.append((arm["id"], "KILLED" if rc != 0 else "SURVIVED", line))
    for k, v in bases.items():
        print(f"基线 {k.name} sha={v}")
    for rid, v, d in rows:
        print(f"[{v:11}] {rid}  {d[:110]}")
    killed = sum(1 for _r, v, _d in rows if v == "KILLED")
    print(f"合计 KILLED {killed} / 其余 {len(rows) - killed}")
    return 0 if killed == len(ARMS) else 1


if __name__ == "__main__":
    sys.exit(main())
