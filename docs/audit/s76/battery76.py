# ruff: noqa: E501   # 长字面量是逐字锚点，不拆行改值

"""第 76 片（全文获取那一步）的变异电池。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
FT = ROOT / "scripts/research/fetch_fulltexts.py"
AC = ROOT / "scripts/absence_claim_census.py"
PY_BIN = str(ROOT / ".venv/bin/python")
TESTS = ["tests/test_research_fulltext_step.py", "tests/test_absence_claim_census.py"]

ARMS = [
    {"id": "T1-arxiv-derivation-dropped", "file": FT,
     "note": "不再按 arxiv_id 推官方 PDF 直链 ⇒ arXiv 那批永远「没开放副本」",
     "old": '    if source == "arxiv" and arxiv_id:',
     "new": '    if source == "__never__" and arxiv_id:'},
    {"id": "T2-falls-back-to-publisher-page", "file": FT,
     "note": "没标开放就退回 url 去取 ⇒ 越过版权/robots 边界，正是库里明令禁止的",
     "old": '    return {"url": "", "license": None,\n            "reason": f"{source or \'未知来源\'} 没返回开放副本，不去 scrape 出版商页面"}',
     "new": '    return {"url": str(item.get("url") or ""), "license": None,\n            "reason": "退回条目自带 url（电池臂）"}'},
    {"id": "T3-download-error-swallowed", "file": FT,
     "note": "下载抛错不计数也不点名 ⇒ 整步看起来「只是没拿到」",
     "old": '            counts["error"] += 1\n'
            '            skipped.append({"title": title, "reason": f"下载抛错：{type(exc).__name__}: {exc}"})',
     "new": '            pass\n            skipped.append({"title": title, "reason": "拿不到"})'},
    {"id": "T4-offline-still-downloads", "file": FT,
     "note": "`--offline` 也照下 ⇒ 那条「不下载也不伪造」的承诺落空",
     "old": '    getter = None if args.offline else http_getter()',
     "new": '    getter = http_getter()'},
    {"id": "T5-duplicate-claim-guard-removed", "file": AC,
     "note": "去掉重复 id 守卫 ⇒ 第 76 片我自己复制四块登记那种事会静默通过",
     "old": '    if dupes:\n        # 第 76 片我自己踩出来的：一次 index 切片替换写反了区间，',
     "new": '    if False and dupes:\n        # 第 76 片我自己踩出来的：一次 index 切片替换写反了区间，'},
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def run_tests():
    proc = subprocess.run([PY_BIN, "-m", "pytest", *TESTS, "-q", "--no-header",
                           "-p", "no:cacheprovider"], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=1200)
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
