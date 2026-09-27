"""第 65 片收尾读数：从**原件现跑**生成《八、终局读数》，不手抄。

纪律（记忆 anchor-scripted-doc-patch / ledger-splice-hygiene）：
① 锚点吃掉整块占位（标题 + 占位句），不留重复标题；
② 断言在**写盘之前**对内存里算好的文本判，标题按行首数不按子串数；
③ 任何一格取不到读数 ⇒ 整轮拒写（不许落 `?`）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TMP = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s65")
DOC = REPO / "docs/audit/ABSENCE_CLAIM_CENSUS_F-STALE-ABSENCE_2026-09-27.md"
REPORT = TMP / "checkout/report-s65.json"
PY = str(REPO / ".venv/bin/python")

PLACEHOLDER = "## 八、终局读数（占位）"


def sh(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True,
                          cwd=str(cwd or REPO), timeout=900)
    return proc.returncode, proc.stdout + proc.stderr


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True).stdout.strip()


def main() -> int:
    rows: list[str] = []
    fails: list[str] = []

    # 1) 签出那一跑的原件读数
    if not REPORT.is_file():
        fails.append(f"report 不存在：{REPORT}")
    else:
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        s = rep.get("summary", {})
        terminal = {k: v for k, v in s.items() if k not in ("passed", "collected", "total")}
        env_sha = str(rep.get("source_commit", ""))
        rows.append(
            f"- **签出那一跑的原件**（`tmp/s65/checkout`，HEAD `{git('rev-parse','--short','HEAD')}`）："
            f"`exitcode={rep.get('exitcode')}`、`collected={s.get('collected')}`、"
            f"`passed={s.get('passed')}`、`skipped={s.get('skipped')}`、"
            f"其余终态 `{terminal}`、用时 `{rep.get('duration', 0):.1f}s`、"
            f"`root={rep.get('root')}`、`source_commit={env_sha[:12]}`")
        env_sha = str(rep.get("source_commit", ""))
        if not env_sha:
            fails.append("报告里没有顶层 source_commit（conftest 注入的是顶层键，不是 environment）")
        tagsha = (TMP / "tagsha.txt").read_text(encoding="utf-8").strip()
        if env_sha != tagsha:
            fails.append(f"报告 source_commit {env_sha[:12]} != tag {tagsha[:12]}")
        if rep.get("exitcode") != 0:
            fails.append(f"全量 exitcode={rep.get('exitcode')}")

    # 2) 本片主角：量具在真仓库上
    rc, out = sh([PY, "scripts/absence_claim_census.py"])
    if rc != 0:
        fails.append(f"census rc={rc}")
    head = [ln for ln in out.splitlines() if ln.startswith("语料：") or "判红 0 条" in ln]
    rows.append("- **收尾量具自证**：`scripts/absence_claim_census.py` → "
                f"`rc={rc}`；" + "；".join(h.strip() for h in head))
    rc2, out2 = sh([PY, "scripts/absence_claim_census.py", "--self-test"])
    n_mark = out2.count("✓立住")
    if rc2 != 0 or n_mark == 0:
        fails.append(f"--self-test rc={rc2} marks={n_mark}")
    rows.append(f"- **`--self-test`**：`rc={rc2}`，**{n_mark} 条**合成读数全对上")
    rc3, out3 = sh([PY, "-m", "pytest", "tests/test_absence_claim_census.py", "-q"])
    tail3 = [ln for ln in out3.splitlines() if "passed" in ln or "failed" in ln][-1:]
    if rc3 != 0:
        fails.append(f"常驻用例 rc={rc3} {tail3}")
    rows.append(f"- **常驻用例**：`pytest tests/test_absence_claim_census.py -q` → `{tail3[0] if tail3 else '?'}`（rc={rc3}）")

    # 3) 账本同步：删了句不删账必须响（外部账本 = 开尺那三句）
    rc4, out4 = sh([PY, "scripts/absence_claim_census.py",
                    "--claims", str(TMP / "before_claims.json")])
    kinds = {}
    for ln in out4.splitlines():
        for k in ("CLAIM_TEXT_ABSENT", "CONTRADICTED"):
            if f"[{k}]" in ln:
                kinds[k] = kinds.get(k, 0) + 1
    if rc4 != 4:
        fails.append(f"外部账本 rc={rc4}（应为 4）")
    rows.append("- **账文同步那一档在真仓库上的读数**：`--claims before_claims.json` → "
                f"`rc={rc4}`，`{kinds}`（三句已删 ⇒ 三条悬空账）")

    # 4) 收尾验签**先跑**，门禁**后跑**（第 64 片的纪律：gate 会写 repository_snapshot.json，
    #    先跑 gate 会让 closeout_verifier 的 C7 worktree_clean 读到自造的脏）
    tagsha = (TMP / "tagsha.txt").read_text(encoding="utf-8").strip()
    rc6, out6 = sh([PY, "scripts/closeout_verifier.py", "--tag", "v5.6.0",
                    "--expect-test", "tests/test_absence_claim_census.py",
                    "--min-tests", "2500"])
    if rc6 != 0:
        fails.append(f"closeout_verifier rc={rc6}")
    key = [ln.strip() for ln in out6.splitlines()
           if "报告" in ln or "格绿" in ln or "✗" in ln or "锚点" in ln][:4]
    rows.append("- **第 64 片那台收尾验签在本片树上**：`rc={}`；{}".format(
        rc6, "；".join(key) if key else out6[-300:]))
    rc5, out5 = sh([PY, "scripts/production_release_gate.py", "--release-ready", "--tag", "v5.6.0"])
    okn = out5.count('"passed": true')
    if rc5 != 0:
        fails.append(f"gate rc={rc5}")
    ready = "true" if '"release_ready": true' in out5 else "false"
    rows.append(f"- **发布门禁**：`production_release_gate --release-ready --tag v5.6.0` → `rc={rc5}`、"
                f"`\"passed\": true` 计 {okn} 条、`release_ready` {ready}")
    rc7, out7 = sh([PY, "scripts/audit_repo.py", "--strict"])
    bad = [ln for ln in out7.splitlines() if ln.strip().startswith("✗")]
    if rc7 == 0 or len(bad) != 1 or "Provenance source commit" not in bad[0]:
        fails.append(f"audit_repo --strict rc={rc7} ✗ 数={len(bad)} {bad[:2]}")
    rows.append(f"- **`audit_repo --strict`**：`rc={rc7}`，恰 **{len(bad)}** 条 ✗"
                f"（`{bad[0].strip()[:80] if bad else '—'}`）——这条按设计不修：发布锚点不许重锚到 HEAD")
    rows.append(f"- **锚点核对**：`SOURCE_MANIFEST.source_commit` = "
                f"`{json.loads((REPO / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['source_commit'][:12]}`"
                f" == tag `{tagsha[:12]}`；被哈希文件数 "
                f"`{len(json.loads((REPO / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))['files'])}`")
    dirty = git("status", "--porcelain")
    rows.append(f"- **工作树**：`git status --porcelain` 输出 {len(dirty.splitlines())} 行"
                + ("（gate 之后落 snapshot 属常态）" if dirty else ""))

    if fails:
        print("REFUSE-WRITE，取不到/不成立的读数：")
        for one in fails:
            print("  -", one)
        return 2

    body = ["## 八、终局读数（由 `tmp/s65/terminal65.py` 从原件现跑生成，不手抄）", ""]
    body += rows
    merged_block = "\n".join(body)

    text = DOC.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        print("占位锚点不在文档里，拒写（不追加第二份标题）")
        return 2
    merged = text.replace(PLACEHOLDER, merged_block, 1)
    n_titles = sum(1 for ln in merged.splitlines() if ln.startswith("## 八、"))
    assert n_titles == 1, f"§八 标题按行首数={n_titles}，必须恰好 1"
    assert "?" not in merged_block, "读数里不许有占位符（取不到就整轮拒写，不许落 ?）"
    assert "None" not in merged_block, [ln for ln in merged_block.splitlines() if "None" in ln]
    DOC.write_text(merged, encoding="utf-8")
    print("WROTE §八，行数 +%d" % (len(merged.splitlines()) - len(text.splitlines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
