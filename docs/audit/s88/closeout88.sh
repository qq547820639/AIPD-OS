#!/bin/bash
# 第 88 片收口链：换绑报告 → 一次绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 每一步退码由该步自己那一步读出（不接管道）；任一硬前提不过就停下并保留现场。
# 与第 86/87 片的差别：
#   · 报告来自已经跑完的干净签出（.wt-s88/report-s88.json），本脚本不重跑全量；
#   · `--expect-test` 点名两条**都加了用例**的文件（+3 与 +3）；
#   · `--min-tests` 由本轮报告现读，并硬断它严格大于上一轮的下界（2692），
#     这样"本片新增用例根本没跑到"仍会红，而不是被自己算出来的数放过去。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s88
X=/Volumes/Extra/CodeProj/AI全链路自研/.s88-outside     # 工具 stdout 必须落树外
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
PRIOR_FLOOR=2692
mkdir -p "$X" "$R/docs/audit/s88"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：报告 0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要 ----
"$PY" - "$WT/report-s88.json" "$SHA" "$PRIOR_FLOOR" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import release_fingerprint as rf
rep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
s = rep["summary"]
# `failed` 键在 0 failed 时缺席（与生产侧 `_parse_pytest_report` 同口径推导）。
failed = s["failed"] if "failed" in s else max(s["total"] - s["passed"] - s.get("skipped", 0), 0)
assert failed == 0 and rep.get("exitcode") == 0, f"报告不干净：{s}"
assert rep["source_commit"] == sys.argv[2], "报告锚点不是 tag SHA"
disk, err = rf.fingerprint_from_file(Path("SOURCE_MANIFEST.json"))
rec = str(rep.get("source_manifest_fingerprint") or "")
assert not err and rec == disk, f"指纹不同源：报告 {rec[:12]} vs 磁盘 {disk[:12]} {err}"
prior = int(sys.argv[3])
assert s["collected"] > prior, f"本轮 collected={s['collected']} 不高于上一轮下界 {prior}"
print(f"PRECHECK OK: {s['passed']} passed / {s.get('skipped', 0)} skipped / "
      f"collected {s['collected']} / {round(rep['duration'], 1)}s / fp {rec[:12]}")
PY
MIN_TESTS=$("$PY" -c "import json;print(json.load(open('$WT/report-s88.json'))['summary']['collected'])")
echo "MIN_TESTS=$MIN_TESTS （上一轮下界 $PRIOR_FLOOR）"

# ---- 1. 换入这一跑的报告，只绑定一次（两个旗子同时给）----
cp "$WT/report-s88.json" docs/audit/pytest-report.json
cp "$WT/report-s88.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json \
    > "$X/bind.log" 2>&1
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; tail -5 "$X/bind.log"; exit 2; }

"$PY" - <<'PY' || { echo "回读失败"; exit 2; }
import json
from pathlib import Path
sha = json.loads(Path("SOURCE_MANIFEST.json").read_text())["source_commit"]
prov = json.loads(Path("PROVENANCE.json").read_text())
assert prov["source_commit"] == sha, (prov["source_commit"], sha)
tr = prov["test_report"]
assert tr["present"] and tr["parsed"] and tr["failed"] == 0, tr
print(f"回读 OK: source_commit={sha[:12]} test_report={tr['passed']}p/{tr['failed']}f/{tr['total']}t "
      f"fp={str(tr.get('source_manifest_fingerprint'))[:12]}")
PY

git add SOURCE_MANIFEST.json PROVENANCE.json \
        docs/audit/pytest-report.json docs/audit/pytest-report-v5.6.0.json
git commit -q -F - <<'MSG'
chore(s88): 绑定第 88 片的 attestation 报告

一次绑定、两个旗子同时给。放行同时签着两道判据：第 84 片的清单同源闸，
与第 86/88 片那对锚点必填校验（操作员入口与 write_evidence() 的 API 各一半）。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（stdout 落树外，否则 workspace_clean 永不可能绿）----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out docs/audit/s88/gate.json > "$X/gate.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - <<'PY'
import json
d = json.load(open("docs/audit/s88/gate.json"))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]     # 门这份是列表，键叫 check
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PY

# ---- 3. 先把门的读数入库，再跑收尾验签（验签判的是 git status --porcelain，未跟踪也算脏）----
cp "$X/bind.log" "$X/gate.log" docs/audit/s88/
git add docs/audit/s88/gate.json docs/audit/repository_snapshot.json
git add -f docs/audit/s88/gate.log docs/audit/s88/bind.log
git commit -q -m "chore(s88): 收下发布门读数（取证件先入库，再谈验签）"
echo "GATE_COMMIT_RC=$?"

"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_release_evidence_preflight.py \
    --expect-test tests/test_doc_command_census.py \
    --min-tests "$MIN_TESTS" --json docs/audit/s88/closeout.json > "$X/closeout.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout.log" docs/audit/s88/
tail -12 docs/audit/s88/closeout.log

git add docs/audit/s88/closeout.json
git add -f docs/audit/s88/closeout.log
git commit -q -m "chore(s88): 收尾验签读数入库"
echo "FINAL_COMMIT_RC=$?"
echo "=== 收口链结束：BIND=$BIND_RC GATE=$GATE_RC CV=$CV_RC MIN_TESTS=$MIN_TESTS ==="
