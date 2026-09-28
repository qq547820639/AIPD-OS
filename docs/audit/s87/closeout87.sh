#!/bin/bash
# 第 87 片收口链：换绑报告 → 一次绑定 → 提交 → 发布门 → 收下门读数 → 收尾验签 → 提交验签读数。
# 顺序纪律（第 86 片实测到的）：发布门的取证件必须先入库再跑验签器，
# 否则验签器自带的 worktree_clean 会把自己上一步留下的 gate.json 读成一处未提交改动。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s87
X=/Volumes/Extra/CodeProj/AI全链路自研/.s87-outside     # 工具 stdout 必须落树外：`>` 在进程启动前就截断文件，落在树里 workspace_clean 永不可能绿
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
mkdir -p "$X"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：报告 0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要 ----
"$PY" - "$WT/report-s87.json" "$SHA" <<'PYX' || { echo "PRECHECK FAILED"; exit 2; }
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import release_fingerprint as rf
rep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
s = rep["summary"]
failed = s["failed"] if "failed" in s else max(s["total"] - s["passed"] - s.get("skipped", 0), 0)
assert failed == 0 and rep.get("exitcode") == 0, f"报告不干净：{s}"
assert rep["source_commit"] == sys.argv[2], "报告锚点不是 tag SHA"
disk, err = rf.fingerprint_from_file(Path("SOURCE_MANIFEST.json"))
rec = str(rep.get("source_manifest_fingerprint") or "")
assert not err and rec == disk, f"指纹不同源：报告 {rec[:12]} vs 磁盘 {disk[:12]} {err}"
print(f"PRECHECK OK: {s['passed']} passed / {s.get('skipped', 0)} skipped / "
      f"collected {s['collected']} / {round(rep['duration'], 1)}s / fp {rec[:12]}")
PYX

# ---- 1. 换入这一跑的报告，只绑定一次 ----
cp "$WT/report-s87.json" docs/audit/pytest-report.json
cp "$WT/report-s87.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; exit 2; }

"$PY" - <<'PYX' || { echo "回读失败"; exit 2; }
import json
from pathlib import Path
sha = json.loads(Path("SOURCE_MANIFEST.json").read_text())["source_commit"]
prov = json.loads(Path("PROVENANCE.json").read_text())
assert prov["source_commit"] == sha, (prov["source_commit"], sha)
tr = prov["test_report"]
assert tr["present"] and tr["parsed"] and tr["failed"] == 0, tr
print(f"回读 OK: source_commit={sha[:12]} test_report={tr['passed']}p/{tr['failed']}f/{tr['total']}t "
      f"fp={str(tr.get('source_manifest_fingerprint'))[:12]}")
PYX

git add SOURCE_MANIFEST.json docs/audit/pytest-report.json docs/audit/pytest-report-v5.6.0.json
git commit -q -F - <<'MSG'
chore(s87): 绑定第 87 片的 attestation 报告

一次绑定、两个旗子同时给：清单同源闸（第 84 片）与锚点必填校验（第 86 片）各自签一次。
MSG
echo "COMMIT_RC=$?"; git log --oneline -1

# ---- 2. 发布门 ----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out docs/audit/s87/gate.json > "$X/gate.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - <<'PYX'
import json
d = json.load(open("docs/audit/s87/gate.json"))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PYX

# ---- 2 之后先把门读数入库，再跑收尾验签（顺序不能颠倒）----
cp "$X/gate.log" docs/audit/s87/
git add docs/audit/s87/gate.json docs/audit/repository_snapshot.json
git add -f docs/audit/s87/gate.log
git commit -q -m "chore(s87): 收下发布门读数与重算的 repository_snapshot"
echo "GATE_COMMIT_RC=$?"

# ---- 3. 收尾验签 ----
"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_doc_command_census.py \
    --min-tests 2692 --json docs/audit/s87/closeout.json > "$X/closeout.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout.log" docs/audit/s87/
tail -8 docs/audit/s87/closeout.log

git add docs/audit/s87/closeout.json
git add -f docs/audit/s87/closeout.log
git commit -q -m "chore(s87): 收下收尾验签的读数"
echo "FINAL_COMMIT_RC=$?"
echo "=== 收口链结束：GATE_RC=$GATE_RC CV_RC=$CV_RC ==="
