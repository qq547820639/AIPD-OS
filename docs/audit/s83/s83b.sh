#!/bin/bash
# 第 83 片收尾（第二次全量）：干净签出全量 → 前提核对 → 绑定 → 门两轮 → 验签十一格 → 门第二轮。
# 第 1 步（刷清单）已在 7acaced 完成，3d5e0f6 只换了 docs/audit/ 里那份未绑定的报告（不参与哈希）。
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # 第 99 片：仓库根由脚本自身位置推，不再写死
T=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s83
W=$T/final2
PY=$R/.venv/bin/python
REPORT=docs/audit/pytest-report-v5.6.0.json
export PATH="$R/.venv/bin:$PATH"
cd "$R" || exit 9
TAGSHA=$(git rev-parse 'v5.6.0^{commit}')

echo "===== 1/5 干净签出全量（第二跑）====="
HEADSHA=$(git rev-parse HEAD)
git worktree remove --force "$W" 2>/dev/null
git worktree add --detach "$W" "$HEADSHA" || exit 9
echo "[full] worktree=$W HEAD=$HEADSHA tagSHA=$TAGSHA"
cd "$W" || exit 9
PYTHONPATH="$W/src:$W/scripts" $PY -c "import aipd_os; print('[full] aipd_os 来自', aipd_os.__file__)"
PYTHONPATH="$W/src:$W/scripts" AIPD_SOURCE_COMMIT="$TAGSHA" timeout 1800 $PY -m pytest tests -q \
  --no-header -p no:cacheprovider --json-report --json-report-file="$T/report2.json" -rf 2>&1 | tail -8
echo "[full] pytest_rc=${PIPESTATUS[0]}"
PYTHONPATH="$W/src:$W/scripts" $PY - <<PY
import json
d = json.load(open("$T/report2.json"))
print("[full] summary =", d["summary"])
print("[full] failed =", [x["nodeid"] for x in d["tests"] if x["outcome"] in ("failed", "error")] or "0 条")
print("[full] duration =", round(d["duration"], 1), "s")
print("[full] source_manifest_fingerprint =", d.get("source_manifest_fingerprint"))
PY
cd "$R" || exit 9

echo; echo "===== 2/5 前提核对 + 绑定 + 提交 ====="
$PY - "$R" <<'PY' || exit 8
import json, subprocess, sys
from pathlib import Path
T = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s83")
R = Path(sys.argv[1])          # 由外层 shell 传进来（heredoc 是带引号的，不会自己展开）
sys.path.insert(0, str(R / "scripts"))
import release_fingerprint as rf  # noqa: E402

d = json.loads((T / "report2.json").read_text(encoding="utf-8"))
s = d["summary"]
bad = [x["nodeid"] for x in d["tests"] if x["outcome"] in ("failed", "error")]
ph = [x["nodeid"] for x in d["tests"] for k in ("setup", "teardown")
      if x.get(k, {}).get("outcome") in ("failed", "error")]
tag = subprocess.run(["git", "-C", str(R), "rev-parse", "v5.6.0^{commit}"],
                     capture_output=True, text=True).stdout.strip()
head = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"],
                      capture_output=True, text=True).stdout.strip()
rec = str(d.get("source_manifest_fingerprint") or "")
disk, err = rf.fingerprint_from_file(R / "SOURCE_MANIFEST.json")
reasons = []
if d["exitcode"] != 0:
    reasons.append(f"exitcode={d['exitcode']}")
if bad:
    reasons.append(f"终态坏 {bad[:5]}")
if ph:
    reasons.append(f"相位坏 {ph[:3]}")
if d["source_commit"] != tag:
    reasons.append(f"source_commit={str(d['source_commit'])[:12]} != tag {tag[:12]}")
if not rec:
    reasons.append("报告没带 source_manifest_fingerprint")
elif rec != disk:
    reasons.append(f"报告指纹 {rec[:12]} != 磁盘清单 {disk[:12] or err}")
if reasons:
    print("REFUSE-BIND：" + "；".join(reasons))
    sys.exit(8)
(T / "s83bind2.txt").write_text(f"""chore(s83): 绑定第 83 片的 attestation 报告（{s['passed']} passed / {s['skipped']} skipped / 0 failed）

干净签出第二跑：`git worktree` 检出 {head[:12]}、`PYTHONPATH` 顶到那份 `src`/`scripts`
（日志打了真正被加载的模块路径）、`AIPD_SOURCE_COMMIT` = tag v5.6.0 的提交（现读）。
`exitcode={d['exitcode']}`、summary={s}、setup/teardown 坏 0 条；跳过的 {s.get('skipped', 0)} 条
与上一轮同一批（联网与真实邮件服务的既有用例）。

**这是头一份带清单指纹的绑定证据**：`source_manifest_fingerprint={rec[:16]}…`，
与磁盘 `SOURCE_MANIFEST.json` 的内容规范摘要逐位相等——这道核对现在写在绑定脚本里
（不等就退 8），也就是 C11 的"事前档"：不必等验签在绑定之后才发现报告和清单不同源。
第一跑（`7acaced` 那趟，2658/5 failed）之所以不能绑，是因为那棵树里被绑的报告还没有字段，
5 条红同一个因；解法见上一条提交 `3d5e0f6`，不是放宽判据。
""", encoding="utf-8")
print(f"前提全过：{s}；报告指纹 {rec[:16]} == 磁盘清单摘要；绑定信息已生成")
PY
cp "$T/report2.json" "$R/$REPORT"
timeout 300 $PY scripts/release_evidence.py --repo . --test-report "$REPORT" \
  --source-commit "$TAGSHA" 2>&1 | tail -2
echo "bind_rc=${PIPESTATUS[0]}"
timeout 600 $PY -m pytest -q --no-header -p no:cacheprovider \
  tests/test_packaging.py tests/test_closeout_verifier.py tests/test_report_manifest_fingerprint.py \
  tests/test_changelog_integrity.py tests/test_absence_claim_census.py 2>&1 | tail -4
echo "resident2_rc=${PIPESTATUS[0]}"
git status --short
git add SOURCE_MANIFEST.json PROVENANCE.json "$REPORT"
git commit -q -F "$T/s83bind2.txt" && git log --oneline -1

echo; echo "===== 3/5 发布门（逐项）====="
timeout 900 $PY scripts/production_release_gate.py --release-ready --repo . --tag v5.6.0 \
  --test-report "$REPORT" --json-out "$T/gate_s83.json" > "$T/gate_s83.txt" 2>&1
echo "gate_rc=$?"
$PY -c "
import json;d=json.load(open('$T/gate_s83.json'))
print('[gate] release_ready=',d['release_ready'])
for c in d['checks']: print('  -',c['check'],c['passed'],str(c['detail'])[:110])"

echo; echo "===== 4/5 收尾提交（门重写的快照）+ 验签十一格 ====="
git status --short
git add docs/audit/
git commit -q -F - <<'MSG' 2>/dev/null || echo "（无待提交件：门这一跑没改动快照，属正常）"
chore(s83): 收下发布门重算的 repository_snapshot

`production_release_gate` 每跑一次就重写这份快照，`workspace_clean` 没有豁免路径 ⇒
"门之后再提一次"是配方的常态形状。
MSG
echo "--- closeout_verifier（十一格，应全绿）---"
timeout 300 $PY scripts/closeout_verifier.py --tag v5.6.0 \
  --expect-test tests/test_report_manifest_fingerprint.py --min-tests 2660
echo "verifier_rc=$?"

echo; echo "===== 5/5 第二次门（确认 8/8 且树干净）---"
timeout 900 $PY scripts/production_release_gate.py --release-ready --repo . --tag v5.6.0 \
  --test-report "$REPORT" --json-out "$T/gate_s83b.json" > "$T/gate_s83b.txt" 2>&1
echo "gate2_rc=$?"
$PY -c "
import json;d=json.load(open('$T/gate_s83b.json'))
print('[gate2] release_ready=',d['release_ready'])
for c in d['checks']: print('  -',c['check'],c['passed'])"
git status --short
git log --oneline -6
echo "ALL DONE"
