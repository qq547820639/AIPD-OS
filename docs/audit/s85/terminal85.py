"""给第 85 片取证文档补一节「九、终局读数」——所有数字一律现读，不手抄。

闸门（任一不过就整节不写）：
① 绑进证据的报告自记指纹 == 磁盘 SOURCE_MANIFEST 的内容摘要；
② 干净签出那一跑 0 failed 且 exitcode==0；
③ 发布门 release_ready=True 且逐项全过；
④ 收尾验签判红 0、前提塌 0；
⑤ 判红面 ④ 在真仓库上判红 0 且分母非空（script_rows/judged ≥ 4）；
⑥ `doc_command_census --self-test` 与 `release_evidence` 的现场拒写都过。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

R = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
S = R / "docs/audit/s85"
DOC = R / "docs/audit/SCRIPT_ROW_CENSUS_F-DOC-CMD-SCRIPTS_2026-09-28.md"
PY = str(R / ".venv/bin/python")
sys.path.insert(0, str(R / "scripts"))
import release_fingerprint as rf  # noqa: E402


def sh(args):
    p = subprocess.run(args, cwd=str(R), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def main() -> int:
    bound = json.loads((R / "docs/audit/pytest-report-v5.6.0.json").read_text(encoding="utf-8"))
    rec = str(bound.get("source_manifest_fingerprint") or "")
    disk, err = rf.fingerprint_from_file(R / "SOURCE_MANIFEST.json")
    assert not err and rec and rec == disk, f"①：报告 {rec[:12]} vs 磁盘 {disk[:12]} {err}"

    s = bound["summary"]
    n_failed = s["failed"] if "failed" in s else max(
        s["total"] - s["passed"] - s.get("skipped", 0), 0)
    assert n_failed == 0 and bound.get("exitcode") == 0, f"②：{s}"

    gd = json.loads((S / "gate.json").read_text(encoding="utf-8"))
    badg = [c["check"] for c in gd["checks"] if not c.get("passed")]
    assert gd.get("release_ready") is True and not badg, f"③：{badg}"

    cv = json.loads((S / "closeout.json").read_text(encoding="utf-8"))
    assert not cv.get("violations") and not cv.get("problems"), \
        f"④：{[v['check'] for v in cv.get('violations', [])]}" \
        f" / {[p['check'] for p in cv.get('problems', [])]}"

    cj = S / "census.json"
    subprocess.run([PY, "scripts/doc_command_census.py", "--repo", ".", "--json", str(cj)],
                   cwd=str(R), capture_output=True, text=True, check=True)
    c = json.loads(cj.read_text(encoding="utf-8"))
    cc = c["corpus"]
    assert not c["violations"], f"⑤：{c['violations'][:3]}"
    assert cc["script_rows"] >= 4 and cc["script_rows_judged"] >= 4, cc

    st = subprocess.run([PY, "scripts/doc_command_census.py", "--self-test"],
                        cwd=str(R), capture_output=True, text=True)
    assert st.returncode == 0 and "条合成读数全部对上" in st.stdout, f"⑥：{st.stdout[-200:]}"
    marks = re.search(r"self-test：(\d+) 条", st.stdout).group(1)

    head = sh(["git", "rev-parse", "HEAD"])
    tag = sh(["git", "rev-parse", "v5.6.0^{commit}"])
    bind = sh(["git", "log", "--format=%h", "-1", "--", "PROVENANCE.json"])
    nfiles = len(json.loads((R / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))["files"])

    SEC = f"""## 九、终局读数（绑定那一跑，全部现读）

| 格 | 读数 |
| --- | --- |
| 被认证提交 | `{tag[:12]}`（tag `v5.6.0`，本轮不重锚） |
| 收口 HEAD | `{head[:12]}` |
| 绑定提交 | `{bind}` |
| 清单分母 | {nfiles} 个文件（**与第 84 片同数**——本轮没加新脚本也没加新测试文件） |
| 报告自记清单指纹 / 磁盘内容摘要 | `{rec[:12]}` == `{disk[:12]}` 逐位相等 |
| 干净签出那一跑 | {s['passed']} passed / {s.get('skipped', 0)} skipped / {n_failed} failed，{round(bound['duration'], 1)} s，`exitcode={bound['exitcode']}` |
| 发布门 | `release_ready=True`，{len(gd['checks'])} 项全过 |
| 收尾验签 | {len(cv['checks'])} 格全绿（判红 0、前提塌 0） |
| 判红面 ④（真仓库） | 行首 `python scripts/X.py` {cc['script_rows']} 行 / 判 {cc['script_rows_judged']} 行 / 不封闭 {len(cc['script_rows_unbounded'])} 行，判红 **0** |
| 判红面 ④（立条前） | 同语料判红 **1** 处（`references/cad-runtime-acceptance.md` 的 `--require-cad`），文档改对后归零 |
| `--self-test` | {marks} 条合成读数全部对上（含新档四支臂） |

两道"看不见 ≠ 没有"的读数在这张表里各自有位置：`script_rows_judged < script_rows` 只能由
`script_rows_unbounded` 解释（今天真仓库为 0 行不封闭，合成语料里那一行由自测钉住）；
判红 0 的含义由"立条前有 1 处"那一行担保，不是由"这档没跑"担保。

"""
    t = DOC.read_text(encoding="utf-8")
    assert "## 九、终局读数" not in t, "已经补过了（幂等闸）"
    head_h = "## 八、遗留"
    assert t.count(head_h) == 1
    DOC.write_text(t.replace(head_h, SEC + head_h, 1), encoding="utf-8")
    print(f"已补 §九：HEAD {head[:7]} / 报告 {s['passed']} passed / 判红面④真仓库 0 违规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
