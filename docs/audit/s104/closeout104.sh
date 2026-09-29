# 第 104 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由 `docs/audit/s103/closeout103.sh` 派生，服务于第 104 片（同一套工序，只换片号专有的字面量）。
# 由 `docs/audit/s101/closeout101.sh` 派生（同一套工序，见其头部那条第 99 片教训：所有被哈希的面
#   都在"生成清单 → 干净全量 → 绑定"这条链开始之前定稿，链跑完只动 `docs/audit/`）。
#   只换：worktree 名（`.wt-s104`，绝对路径且落在仓库**外**——`git -C 仓库 worktree add 相对路径`
#   会按 `-C` 的目标解析，第 99 片实测把签出建到仓库里过一次）/ 报告名 / 四个日志名 /
#   产物目录（`docs/audit/s104/`）/ PRIOR_FLOOR=上一片实测 collected(2803) / 绑定提交信息 /
#   --expect-test 三条（本片原告 = `tests/test_changelog_commit_crosscheck.py` 的新尺（第四源缺席判决：
#   凡 `git log --format=%s` 主题行里以 `s<NN>` 出现过的片号，CHANGELOG 必须有一行 `- **v…第 NN 片` 条目
#   接住；方向只有这一边，条目侧多出的一律不算原告，词边界只认主题行不读正文，提交侧读不到片号判前提塌）、
#   `tests/test_changelog_integrity.py` 守的 CHANGELOG 形状面（重复块/重复条目头，自洽型、看不见整条缺席）、
#   `tests/test_unreachable_code.py` 的不可达代码尺）。
#   两条已记录的卫生规矩照抄：门的 JSON/stdout 与验签的 JSON 一律**落树外**再 cp 入库
#   （第 91/100 片两次实测：写进被检查的树 ⇒ `workspace_clean`/`worktree_clean` 必自红）；
#   取证件先 commit 再跑验签（未跟踪也算脏）。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s104
X=/Volumes/Extra/CodeProj/AI全链路自研/.s88-outside
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
PRIOR_FLOOR=2803
mkdir -p "$X" "$R/docs/audit/s104"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要、collected 高于上代 ----
"$PY" - "$WT/report-s104.json" "$SHA" "$PRIOR_FLOOR" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
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
assert s["collected"] > prior, f"collected={s['collected']} 不高于上一代下界 {prior}"
print(f"PRECHECK OK: {s['passed']} passed / {s.get('skipped', 0)} skipped / "
      f"collected {s['collected']} / {round(rep['duration'], 1)}s / fp {rec[:12]}")
PY
MIN_TESTS=$("$PY" -c "import json;print(json.load(open('$WT/report-s104.json'))['summary']['collected'])")
echo "MIN_TESTS=$MIN_TESTS （上一代下界 $PRIOR_FLOOR）"

# ---- 0b. 跳过面必须与上一代逐条相同（FAIL=0 不等于同一覆盖面）----
"$PY" - "$WT/report-s104.json" "$R/docs/audit/pytest-report-v5.6.0.json" <<'PY' || { echo "SKIP 面变了"; exit 2; }
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
cp "$WT/report-s104.json" docs/audit/pytest-report.json
cp "$WT/report-s104.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json \
    > "$X/bind104.log" 2>&1
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; tail -5 "$X/bind104.log"; exit 2; }

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
chore(s104): 绑定第 104 片的 attestation 报告

一次绑定、两个旗子同时给。本片给 CHANGELOG 补上第四源：`tests/test_changelog_integrity.py`
那两道判决（重复块、重复条目头）都是自洽型的——条目整条缺席时记号数与口径数一起往下走，
两边仍然相等、仍然唯一，结构上看不见缺席；撞过两次（一次留下正文丢了标题、一次 v5.64 整条没写），
两次四道门禁全绿，直到准备认证时才被 `git show --stat` 读出来。新常驻尺因此不看 CHANGELOG 自己，
而看另一张独立名册——仓库历史的主题行：凡 `git log --format=%s` 里以 `s<NN>` 出现过的片号，
CHANGELOG 必须有一行 `- **v…第 NN 片` 条目接住。方向只有这一边，条目侧比提交侧多出来的一律不算原告
（条目侧片号远多于提交侧，反向判据会把 `sNN` 主题约定之前的那些轮次全部误伤）。
片号只在词边界上认、只读主题行不读正文——worktree 名这类路径串住在正文里，读正文会造出假片号；
`git` 读不到、或提交侧一个片号都没读到，一律判前提塌（退 2），绝不把"看不见"折成"没漂"。
上一片（第 103 片，collected 2803）作下界；本轮新增这把常驻尺连同它的两支历史 Blob 控制 ⇒ collected 只会更多。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（JSON 与 stdout 都落树外）----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out "$X/gate104.json" > "$X/gate104.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - "$X/gate104.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PY

# ---- 3. 先把门的读数与日志入库，再跑收尾验签（未跟踪也算脏）----
cp "$X/bind104.log" "$X/gate104.log" docs/audit/s104/
cp "$X/gate104.json" docs/audit/s104/gate.json
git add docs/audit/s104/gate.json
git add -f docs/audit/s104/gate104.log docs/audit/s104/bind104.log
git commit -q -m "chore(s104): 收下发布门读数（取证件先入库，再谈验签）"
echo "GATE_COMMIT_RC=$?"

"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_changelog_commit_crosscheck.py \
    --expect-test tests/test_changelog_integrity.py \
    --expect-test tests/test_unreachable_code.py \
    --min-tests "$MIN_TESTS" --json "$X/closeout104.json" > "$X/closeout104.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout104.json" "$X/closeout104.log" docs/audit/s104/
tail -14 docs/audit/s104/closeout104.log

git add docs/audit/s104/closeout104.json
git add -f docs/audit/s104/closeout104.log
git commit -q -m "chore(s104): 收尾验签读数入库"
echo "FINAL_COMMIT_RC=$?"
echo "=== 第 104 片收口结束：BIND=$BIND_RC GATE=$GATE_RC CV=$CV_RC MIN_TESTS=$MIN_TESTS ==="
