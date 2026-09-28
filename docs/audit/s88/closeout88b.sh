#!/bin/bash
# 第 88 片收口链·第二代：复核交回的五条动完代码之后重新认证一次。
# 与第一代（closeout88.sh，绑定提交 5ac551c）的差别只有三处：
#   · 工作树与报告换名（.wt-s88b / report-s88b.json），第一代的原件一字不动地留着；
#   · PRIOR_FLOOR 取第一代的实测 collected（2702），棘轮方向由脚本硬断；
#   · 门的读数写到 gate-b.json / closeout-b.json，两代不互换引用。
# 每一步退码由该步自己那一步读出（不接管道）；任一硬前提不过就停下并保留现场。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s88b
X=/Volumes/Extra/CodeProj/AI全链路自研/.s88-outside
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
PRIOR_FLOOR=2702
mkdir -p "$X" "$R/docs/audit/s88"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：报告 0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要 ----
"$PY" - "$WT/report-s88b.json" "$SHA" "$PRIOR_FLOOR" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
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
prior = int(sys.argv[3])
assert s["collected"] > prior, f"本轮 collected={s['collected']} 不高于上一代下界 {prior}"
print(f"PRECHECK OK: {s['passed']} passed / {s.get('skipped', 0)} skipped / "
      f"collected {s['collected']} / {round(rep['duration'], 1)}s / fp {rec[:12]}")
PY
MIN_TESTS=$("$PY" -c "import json;print(json.load(open('$WT/report-s88b.json'))['summary']['collected'])")
echo "MIN_TESTS=$MIN_TESTS （上一代下界 $PRIOR_FLOOR）"

# ---- 0b. 跳过面要与第一代逐条相同，否则"0 failed"不等于同一覆盖面 ----
"$PY" - "$WT/report-s88b.json" "$R/docs/audit/pytest-report-v5.6.0.json" <<'PY' || { echo "SKIP 面变了"; exit 2; }
import json, sys
from pathlib import Path
def sk(p):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    return {t["nodeid"] for t in d["tests"] if t["outcome"] == "skipped"}
new, old = sk(sys.argv[1]), sk(sys.argv[2])
assert not (old - new), f"上一代跳过、这一代跑了：{sorted(old - new)}"
assert not (new - old), f"这一代新增跳过（覆盖面缩了）：{sorted(new - old)}"
print(f"SKIP 面逐条相同：{len(new)} 条")
PY

# ---- 1. 换入这一跑的报告，只绑定一次（两个旗子同时给）----
cp "$WT/report-s88b.json" docs/audit/pytest-report.json
cp "$WT/report-s88b.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json \
    > "$X/bind-b.log" 2>&1
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; tail -5 "$X/bind-b.log"; exit 2; }

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
chore(s88b): 重新绑定第二代 attestation 报告

复核交回的五条（大写形状、dropped 报告、非字典拒绝、用例的两处假牙）都动了 scripts/ 与
tests/，也就是动了清单收录的哈希面 ⇒ 第一代那一跑不再描述当前树。
仍是一次绑定、两个旗子同时给；锚点还是 tag SHA，不是 HEAD。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（stdout 落树外，否则 workspace_clean 永不可能绿）----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out docs/audit/s88/gate-b.json > "$X/gate-b.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - <<'PY'
import json
d = json.load(open("docs/audit/s88/gate-b.json"))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PY

# ---- 3. 先把门的读数入库，再跑收尾验签（未跟踪也算脏）----
cp "$X/bind-b.log" "$X/gate-b.log" docs/audit/s88/
git add docs/audit/s88/gate-b.json docs/audit/repository_snapshot.json
git add -f docs/audit/s88/gate-b.log docs/audit/s88/bind-b.log
git commit -q -m "chore(s88b): 收下第二代发布门读数"
echo "GATE_COMMIT_RC=$?"

"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_release_evidence_preflight.py \
    --expect-test tests/test_doc_command_census.py \
    --min-tests "$MIN_TESTS" --json docs/audit/s88/closeout-b.json > "$X/closeout-b.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout-b.log" docs/audit/s88/
tail -14 docs/audit/s88/closeout-b.log

git add docs/audit/s88/closeout-b.json
git add -f docs/audit/s88/closeout-b.log
git commit -q -m "chore(s88b): 第二代收尾验签读数入库"
echo "FINAL_COMMIT_RC=$?"
echo "=== 第二代收口结束：BIND=$BIND_RC GATE=$GATE_RC CV=$CV_RC MIN_TESTS=$MIN_TESTS ==="
