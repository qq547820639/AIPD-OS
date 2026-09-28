#!/bin/bash
# 第 84 片收口链（绑定 → 提交 → 发布门 → 收尾验签）。
# 每一步的退码都由该步自己那一步读出（不接管道），任一硬前提不过就停下并保留现场。
# 前置：干净签出全量已跑完且 0 failed，报告在 $WT/run.log + $WT/report-s85.json。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s85
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"      # 少了它 pip-audit 找不到 ⇒ no_unacknowledged_cve 假红
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：报告必须 0 failed、且自记指纹与磁盘清单逐位相等（绑定前的便宜探针） ----
"$PY" - "$WT/report-s85.json" "$SHA" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
import json, sys
sys.path.insert(0, "scripts")
import release_fingerprint as rf
from pathlib import Path
rep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
s = rep["summary"]
# pytest-json-report 的 summary 在 0 failed 时**根本不带 `failed` 键**（生产侧
# `_parse_pytest_report` 就是这么推导的），所以"缺席"必须按 0 读、不能按 1 读——
# 写成 s.get("failed", 1) 会把一份干净报告判成不干净。
failed = s["failed"] if "failed" in s else max(s["total"] - s["passed"] - s.get("skipped", 0), 0)
assert failed == 0 and rep.get("exitcode") == 0, f"报告不干净：{s}"
assert rep["source_commit"] == sys.argv[2], "报告锚点不是 tag SHA"
disk, err = rf.fingerprint_from_file(Path("SOURCE_MANIFEST.json"))
rec = str(rep.get("source_manifest_fingerprint") or "")
assert not err and rec == disk, f"指纹不同源：报告 {rec[:12]} vs 磁盘 {disk[:12]} {err}"
print(f"PRECHECK OK: {s['passed']} passed / {s.get('skipped',0)} skipped / collected {s['collected']}"
      f" / {round(rep['duration'],1)}s / fp {rec[:12]}")
PY

# ---- 1. 换入这一跑的报告（两份：轮次记录 + tag 锚定那份），然后只绑定一次 ----
cp "$WT/report-s85.json" docs/audit/pytest-report.json
cp "$WT/report-s85.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——说明清单在跑完之后又动过，回去重跑而不是绕闸"; exit 2; }

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

git add SOURCE_MANIFEST.json RELEASE_MANIFEST.json PROVENANCE.json \
        docs/audit/pytest-report.json docs/audit/pytest-report-v5.6.0.json
git commit -q -F - <<'MSG'
chore(s85): 绑定第 85 片的 attestation 报告

一次绑定、两个旗子同时给（`--test-report` 与 `--source-commit`）——
少给后者会把清单锚点默认成当时的 HEAD（第 52 片实测）。
绑定这一步现在还会自己核对"报告自记的清单摘要 == 即将写出的那份清单"，
所以这份 PROVENANCE 的放行是由闸自己签的，不再依赖"我记得先刷清单再跑全量"。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（先跑，因为它会写 repository_snapshot） ----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out docs/audit/s84/gate.json > docs/audit/s84/gate.log 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" -c "
import json;d=json.load(open('docs/audit/s84/gate.json'))
bad=[c['check'] for c in d['checks'] if not c.get('passed')]   # JSON 里的键叫 check
print('release_ready=',d.get('release_ready'),' 项=',len(d['checks']),' 未过=',bad)"

# ---- 2.5 先把 gate 产物提交：验签器的 worktree_clean 看的是它开跑那一刻的 git status，
#          未跟踪的 gate.json / repository_snapshot.json 会让它作为无关连带开火。
git add docs/audit/s84/gate.json docs/audit/repository_snapshot.json
git add -f docs/audit/s84/gate.log      # 仓库 .gitignore 第 43 行 `*.log` ⇒ 取证件必须 -f
git commit -q -m "chore(s85): 收下发布门读数与重算的 repository_snapshot"
echo "GATECOMMIT_RC=$?"

# ---- 3. 收尾验签 ----
"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_doc_command_census.py --expect-test tests/test_release_evidence_preflight.py \
    --min-tests 2675 --json docs/audit/s84/closeout.json > docs/audit/s84/closeout.log 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
tail -6 docs/audit/s84/closeout.log

echo "=== 收口链结束：GATE_RC=$GATE_RC CV_RC=$CV_RC ==="
