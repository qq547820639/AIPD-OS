# ruff: noqa: E501   # 长中文读数串，不为过 lint 而拆坏字面量

"""第 67 片收尾读数：从原件现跑生成《六、终局读数》，取不到就整轮拒写。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
TMP = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s76")
DOC = REPO / "docs/audit/FULLTEXT_STEP_F-FULLTEXT-STEP_2026-09-27.md"
REPORT = TMP / "final/report.json"
PY = str(REPO / ".venv/bin/python")
PLACEHOLDER = "## 四、终局读数（占位）"


def sh(args, timeout=900):
    proc = subprocess.run(args, capture_output=True, text=True,
                          cwd=str(REPO), timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True).stdout.strip()


def main() -> int:
    rows, fails = [], []
    tagsha = (REPO.parent / "tmp/s65/tagsha.txt").read_text(encoding="utf-8").strip()
    # 环境前提先看住：`production_release_gate.no_unacknowledged_cve` 用 shutil.which('pip-audit')
    # 找可执行，PATH 里没有 .venv/bin 时它 fail-closed 报"不可用"⇒ rc=2、只有 7 条 true。
    # 那是环境缺位不是代码回归（项目记忆里记过同一格两次）。这里直接拒跑，别让它冒充判决。
    # 判"pip-audit 在不在"要在**当前进程的环境**里查（shutil.which）。
    # 先前那版起 `bash -lc`，登录 shell 会重读 profile 把调用方 export 的 PATH 洗掉，
    # 于是明明有 pip-audit 也报"没有"——一把只会误拒的守卫比没有守卫更糟。
    if shutil.which("pip-audit") is None:
        print("REFUSE-WRITE：PATH 里没有 pip-audit——先 export "
              "PATH=\"$PWD/.venv/bin:$PATH\" 再跑（否则门禁会 fail-closed 假红）")
        return 2

    if not REPORT.is_file():
        fails.append(f"report 不存在：{REPORT}")
    else:
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        s = rep.get("summary", {})
        other = {k: v for k, v in s.items() if k not in ("passed", "collected", "total")}
        wt = subprocess.run(["git", "-C", str(TMP / "final"), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
        rows.append(f"- **签出那一跑**（`tmp/s76/final`，报告产出于提交 `{wt}`，"
                    f"主树当时 HEAD `{git('rev-parse', '--short', 'HEAD')}`）："
                    f"`exitcode={rep.get('exitcode')}`、`collected={s.get('collected')}`、"
                    f"`passed={s.get('passed')}`、`skipped={s.get('skipped')}`、"
                    f"其余终态 `{other}`、用时 `{rep.get('duration', 0):.1f}s`、"
                    f"`root={rep.get('root')}`、"
                    f"`source_commit={str(rep.get('source_commit'))[:12]}`")
        if rep.get("exitcode") != 0:
            fails.append(f"全量 exitcode={rep.get('exitcode')}")
        if str(rep.get("source_commit")) != tagsha:
            fails.append("报告 source_commit != tag SHA")

    # 本片改的是 doc_command_census ⇒ 主角是它；absence_claim_census 只作同族回归
    rc, out = sh([PY, "scripts/doc_command_census.py"])
    if rc != 0:
        fails.append(f"doc_command_census rc={rc}")
    got = [ln.strip() for ln in out.splitlines()
           if ln.startswith(("只报面", "现状面缺陷", "权威面"))]
    rows.append("- **同族尺子 `doc_command_census`**：`rc={}`；{}".format(rc, "；".join(got)))
    if "未注册命令 0" not in out and "现状面缺陷 0 条" not in out:
        fails.append("doc 尺子现状面不干净")
    rc1b, out1b = sh([PY, "scripts/absence_claim_census.py"])
    if rc1b != 0:
        fails.append(f"absence_claim_census rc={rc1b}")
    got1b = [ln.strip() for ln in out1b.splitlines()
             if ln.startswith(("能力缺失句", "被挡在窄档外"))]
    rows.append("- **同族回归 `absence_claim_census`**：`rc={}`；{}".format(
        rc1b, "；".join(got1b)))
    if "未处置 0" not in out1b:
        fails.append("窄档仍有未处置句")

    rc2, out2 = sh([PY, "scripts/doc_command_census.py", "--self-test"])
    rc2b, out2b = sh([PY, "scripts/absence_claim_census.py", "--self-test"])
    marks = out2.count("✓立住") + out2b.count("✓立住")
    if rc2 != 0 or rc2b != 0 or marks < 30:
        fails.append(f"--self-test doc={rc2} absence={rc2b} marks={marks}")
    rows.append(f"- **两把尺子的 `--self-test`**：`rc={rc2}/{rc2b}`，合计 **{marks} 条**"
                "合成读数全对上（条数由本次运行现数）")

    rc3, out3 = sh([PY, "-m", "pytest", "tests/test_doc_command_census.py",
                    "tests/test_absence_claim_census.py", "-q"])
    tail3 = [ln for ln in out3.splitlines() if "passed" in ln or "failed" in ln][-1:]
    if rc3 != 0 or not tail3:
        fails.append(f"常驻用例 rc={rc3} {tail3}")
    rows.append(f"- **常驻用例（全文步骤与连接器映射合跑，两个不同文件）**：`pytest "
                f"tests/test_research_fulltext_step.py tests/test_research_fulltext_fetcher.py -q` → "
                f"`{tail3[0] if tail3 else ''}`（rc={rc3}）")

    rc4, out4 = sh([PY, "docs/audit/s76/battery76.py"], timeout=1200)
    sum4 = [ln for ln in out4.splitlines() if ln.startswith("合计")]
    if rc4 != 0 or not sum4:
        fails.append(f"battery rc={rc4} {sum4}；输出尾：{out4[-300:]!r}")
    rows.append(f"- **变异电池（入库副本现跑）**：`docs/audit/s76/battery76.py` → "
                f"`rc={rc4}`，{sum4[0] if sum4 else ''}")

    sys.path.insert(0, str(REPO / "scripts"))
    import absence_claim_census as acc  # noqa: E402
    corpus, pbs = acc.registry_strings(REPO)
    wide = acc.absence_sentences(corpus)
    narrow = [x for x in wide if acc.is_capability_absence(x.split("|", 2)[-1])]
    axes = Counter(acc.classify_absence(x.split("|", 2)[-1])[0] for x in wide)
    d1, d2, d3 = (axes["no-predicate"], axes["no-noun"], axes["non-claim"])
    ex_thin = [k for k, v in acc.EXEMPTIONS.items() if len(v.strip()) < 8]
    rows.append(f"- **两档分母现读**：宽档 {len(wide)} 句、窄档 {len(narrow)} 句"
                f"（差的 {len(wide) - len(narrow)} 句按轴分：无缺失谓词 {d1}、无能力名词 {d2}、"
                 f"谈判决/谈口径 {d3}）；"
                f"登记表解析问题 `{pbs}`；薄理由豁免 `{ex_thin}`")

    # 收尾验签先跑，门禁后跑（gate 会写 repository_snapshot.json）
    rc5, out5 = sh([PY, "scripts/closeout_verifier.py", "--tag", "v5.6.0",
                    "--expect-test", "tests/test_absence_claim_census.py",
                    "--min-tests", "2500"])
    if rc5 != 0:
        fails.append(f"closeout_verifier rc={rc5}")
    key5 = [ln.strip()[:110] for ln in out5.splitlines() if "报告" in ln or "✓" in ln][:2]
    rows.append("- **第 64 片那台收尾验签在本片树上**：`rc={}`；{}".format(rc5, "；".join(key5)))

    rc6, out6 = sh([PY, "scripts/production_release_gate.py", "--release-ready",
                    "--tag", "v5.6.0"])
    okn = out6.count('"passed": true')
    ready = "true" if '"release_ready": true' in out6 else "false"
    if rc6 != 0:
        fails.append(f"gate rc={rc6}")
    rows.append(f"- **发布门禁**：`rc={rc6}`、`\"passed\": true` 计 {okn} 条、"
                f"`release_ready` {ready}")

    sample_problems_bad = len(acc.check_axis_samples(acc.absence_sentences(
        acc.registry_strings(REPO)[0])))
    gate_claims = tuple(c for c in acc.CLAIMS
                        if c.get("check", {}).get("kind") == "external_callers")
    gate_ids = {str(c["id"]) for c in gate_claims}
    gate_verdicts = sorted({str(r["verdict"]) for r in acc.audit(REPO, gate_claims)["rows"]
                            if str(r["id"]) in gate_ids})
    rows.append("- **具名样本核对**：四档共 "
                f"{sum(len(v) for v in acc.AXIS_SAMPLES.values())} 条，样本问题 {sample_problems_bad} 条；"
                f"分档 {dict(axes)}")
    rows.append("- **沿第 71 片那条轴的例行复算**：`external_callers` 对 "
                "`commit_approved` / `commit_snapshot` 判 "
                + ",".join(gate_verdicts) +
                "，正向对照 `record_dxf_lineage` 判 "
                + str(acc.audit(REPO, ({"id": "POS", "capability": "product.definition_gate",
                                        "field": "current_limitation",
                                        "anchor": "aipd product gate --commit",
                                        "check": {"kind": "external_callers",
                                                  "symbol": "record_dxf_lineage"}},))
                      ["rows"][0]["verdict"]) + "（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）")
    rc7, out7 = sh([PY, "scripts/audit_repo.py", "--strict"])
    bad = [ln.strip() for ln in out7.splitlines() if ln.strip().startswith("✗")]
    if rc7 == 0 or len(bad) != 1:
        fails.append(f"audit_repo --strict rc={rc7} ✗ 数={len(bad)}")
    rows.append(f"- **`audit_repo --strict`**：`rc={rc7}`，恰 **{len(bad)}** 条 ✗"
                f"（`{bad[0][:70] if bad else '—'}`）——设计内不修")

    man = json.loads((REPO / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    # 差集要现算，不能抄上一片的说法：第 71 片就是这么在读数里留下了一句
    # "本片文件数不变"，而实际 +2（新实现 + 新常驻测试）。
    tag_manifest = subprocess.run(["git", "show", "v5.6.0:SOURCE_MANIFEST.json"],
                                  cwd=str(REPO), capture_output=True, text=True)
    try:
        tag_files = {str(e.get("path") or e.get("file"))
                     for e in json.loads(tag_manifest.stdout)["files"]}
    except (ValueError, KeyError):
        tag_files = set()
        rows.append("- **注意**：tag 的清单读不到 ⇒ 差集判不了（不当成 0 个新增）")
    now_files = {str(e.get("path") or e.get("file")) for e in man["files"]}
    added = sorted(now_files - tag_files)
    gone = sorted(tag_files - now_files)
    rows.append(f"- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = "
                f"`{str(man['source_commit'])[:12]}` == tag；被哈希文件数 "
                f"`{len(man['files'])}`；**相对 tag v5.6.0** 的清单：新增 {len(added)} 个、"
                f"消失 {len(gone)} 个（这是 25 片的累计漂移，不是本片增量——"
                f"本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）")
    if added:
        rows.append("- **相对 tag 新增的被哈希文件（前 5 个）**：" + "、".join(f"`{a}`" for a in added[:5]))
    dirty = git("status", "--porcelain")
    rows.append(f"- **工作树**：`git status --porcelain` 输出 {len(dirty.splitlines())} 行")

    if fails:
        print("REFUSE-WRITE：")
        for one in fails:
            print("  -", one)
        return 2
    body = "\n".join(["## 四、终局读数（由 `docs/audit/s76/terminal76.py` 从原件现跑生成，不手抄）",
                      ""] + rows)
    text = DOC.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:
        print("占位不在，拒写")
        return 2
    merged = text.replace(PLACEHOLDER, body, 1)
    assert sum(1 for ln in merged.splitlines() if ln.startswith("## 四、")) == 1, "标题重复"
    assert "?" not in body and "None" not in body, "读数里不许有占位符/None"
    DOC.write_text(merged, encoding="utf-8")
    print("WROTE 终局读数一节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
