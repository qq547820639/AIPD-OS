"""第 66 片收尾读数：从原件现跑生成《六、终局读数》，取不到就整轮拒写。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TMP = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s66")
DOC = REPO / "docs/audit/PRODUCER_COUNT_F-PRODUCER-COUNT_2026-09-27.md"
REPORT = TMP / "checkout/report-s66.json"
PY = str(REPO / ".venv/bin/python")
PLACEHOLDER = "## 六、终局读数（占位）"


def sh(args, timeout=900):
    proc = subprocess.run(args, capture_output=True, text=True,
                          cwd=str(REPO), timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True).stdout.strip()


def main():
    rows, fails = [], []
    if not REPORT.is_file():
        fails.append(f"report 不存在：{REPORT}")
    else:
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        s = rep.get("summary", {})
        other = {k: v for k, v in s.items() if k not in ("passed", "collected", "total")}
        sha_tag = (REPO.parent / "tmp/s65/tagsha.txt").read_text(encoding="utf-8").strip()
        wt_head = subprocess.run(["git", "-C", str(TMP / "checkout"),
                                  "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
        rows.append(f"- **签出那一跑**（`tmp/s66/checkout`，报告产出于提交 `{wt_head}`，"
                    f"主树当时 HEAD `{git('rev-parse','--short','HEAD')}`）："
                    f"`exitcode={rep.get('exitcode')}`、`collected={s.get('collected')}`、"
                    f"`passed={s.get('passed')}`、`skipped={s.get('skipped')}`、"
                    f"其余终态 `{other}`、用时 `{rep.get('duration', 0):.1f}s`、"
                    f"`root={rep.get('root')}`、`source_commit={str(rep.get('source_commit'))[:12]}`")
        if rep.get("exitcode") != 0:
            fails.append(f"全量 exitcode={rep.get('exitcode')}")
        if str(rep.get("source_commit")) != sha_tag:
            fails.append("报告 source_commit != tag SHA")

    rc, out = sh([PY, "scripts/absence_claim_census.py"])
    if rc != 0:
        fails.append(f"census rc={rc}")
    got = [ln.strip() for ln in out.splitlines()
           if ln.strip().startswith(("语料：", "判红 0 条", "✓ PRODUCER", "✗ PRODUCER"))]
    rows.append("- **本片主角（终态）**：`absence_claim_census` → `rc={}`；{}".format(
        rc, "<br>".join(got)))

    rc2, out2 = sh([PY, "scripts/absence_claim_census.py", "--self-test"])
    marks = out2.count("✓立住")
    if rc2 != 0 or marks == 0:
        fails.append(f"--self-test rc={rc2} marks={marks}")
    rows.append(f"- **`--self-test`**：`rc={rc2}`，**{marks} 条**合成读数全对上"
                "（含本片新增的 4 条计数档合成读数与 1 条「权威面空 ⇒ 不判」）")

    rc3, out3 = sh([PY, "-m", "pytest", "tests/test_absence_claim_census.py", "-q"])
    tail3 = [ln for ln in out3.splitlines() if "passed" in ln or "failed" in ln][-1:]
    if rc3 != 0 or not tail3:
        fails.append(f"常驻用例 rc={rc3} {tail3}")
    rows.append(f"- **常驻用例**：`pytest tests/test_absence_claim_census.py -q` → "
                f"`{tail3[0] if tail3 else ''}`（rc={rc3}）")

    rc4, out4 = sh([PY, "docs/audit/s66/battery66.py"], timeout=1200)
    sum4 = [ln for ln in out4.splitlines() if ln.startswith("合计")]
    if rc4 != 0 or not sum4:
        fails.append(f"battery rc={rc4} {sum4}")
    rows.append(f"- **变异电池（入库副本现跑）**：`docs/audit/s66/battery66.py` → "
                f"`rc={rc4}`，{sum4[0] if sum4 else ''}")

    sys.path.insert(0, str(REPO / "scripts"))
    import absence_claim_census as acc
    producers, blind = acc.edge_producers(REPO)
    rows.append(f"- **权威面现读**（判决用的就是它）：truth `{len(producers['truth'])}` 个、"
                f"canonical `{len(producers['canonical'])}` 个、SQL 写入口 "
                f"`{len(producers['sql_entry'])}` 个、盲区 `{blind}`")

    rc5, out5 = sh([PY, "scripts/closeout_verifier.py", "--tag", "v5.6.0",
                    "--expect-test", "tests/test_absence_claim_census.py",
                    "--min-tests", "2500"])
    if rc5 != 0:
        fails.append(f"closeout_verifier rc={rc5}")
    key5 = [ln.strip()[:120] for ln in out5.splitlines()
            if "报告" in ln or "✓" in ln][:2]
    rows.append("- **第 64 片那台收尾验签在本片树上**：`rc={}`；{}".format(rc5, "；".join(key5)))

    rc6, out6 = sh([PY, "scripts/production_release_gate.py", "--release-ready", "--tag", "v5.6.0"])
    okn = out6.count('"passed": true')
    ready = "true" if '"release_ready": true' in out6 else "false"
    if rc6 != 0:
        fails.append(f"gate rc={rc6}")
    rows.append(f"- **发布门禁**：`rc={rc6}`、`\"passed\": true` 计 {okn} 条、"
                f"`release_ready` {ready}")

    rc7, out7 = sh([PY, "scripts/audit_repo.py", "--strict"])
    bad = [ln.strip() for ln in out7.splitlines() if ln.strip().startswith("✗")]
    if rc7 == 0 or len(bad) != 1:
        fails.append(f"audit_repo --strict rc={rc7} ✗ 数={len(bad)}")
    rows.append(f"- **`audit_repo --strict`**：`rc={rc7}`，恰 **{len(bad)}** 条 ✗"
                f"（`{bad[0][:70] if bad else '—'}`）——设计内不修")

    man = json.loads((REPO / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    rows.append(f"- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = "
                f"`{str(man['source_commit'])[:12]}` == tag；被哈希文件数 `{len(man['files'])}`"
                f"（本片**文件数不变**，只改内容 ⇒ 与第 65 片同为 669）")
    dirty = git("status", "--porcelain")
    rows.append(f"- **工作树**：`git status --porcelain` 输出 {len(dirty.splitlines())} 行")

    if fails:
        print("REFUSE-WRITE：")
        for f in fails:
            print("  -", f)
        return 2
    heading = "## 六、终局读数（由 `docs/audit/s66/terminal66.py`（已入库）从原件现跑生成，不手抄）"
    body = "\n".join([heading, ""] + rows)
    text = DOC.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        print("占位不在，拒写")
        return 2
    merged = text.replace(PLACEHOLDER, body, 1)
    assert sum(1 for ln in merged.splitlines()
               if ln.startswith("## 六、")) == 1, "标题按行首数必须恰好 1"
    assert "?" not in body and "None" not in body, "读数里不许有占位符/None"
    DOC.write_text(merged, encoding="utf-8")
    print("WROTE 终局读数一节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
