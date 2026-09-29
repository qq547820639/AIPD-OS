# 第 105 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由 `docs/audit/s104/closeout104.sh` 派生，服务于第 105 片（同一套工序，只换片号专有的字面量）。
# 由 `docs/audit/s101/closeout101.sh` 派生（同一套工序，见其头部那条第 99 片教训：所有被哈希的面
#   都在"生成清单 → 干净全量 → 绑定"这条链开始之前定稿，链跑完只动 `docs/audit/`）。
#   只换：worktree 名（`.wt-s105`，绝对路径且落在仓库**外**——`git -C 仓库 worktree add 相对路径`
#   会按 `-C` 的目标解析，第 99 片实测把签出建到仓库里过一次）/ 报告名 / 四个日志名 /
#   产物目录（`docs/audit/s105/`）/ PRIOR_FLOOR=上一片实测 collected(2809) / 绑定提交信息 /
#   --expect-test 三条（本片原告 = `tests/test_doc_reference_census.py` 的符号锚新支路（简写指针
#   `path.py::symbol` 不许只查 `resolve()` 按 ROOTS 前缀先撞上的那一份，而要扫遍所有同名候选文件：
#   符号在靠后那份里 ⇒ `symbol-resolved` 且点名真载体；哪份都没有 ⇒ 仍判 `symbol-missing`，
#   不许因为"多查了几份"就被洗成有）、既有的 CHANGELOG 记账尺
#   `tests/test_changelog_commit_crosscheck.py`（提交主题行里以 `s<NN>` 出现过的片号，CHANGELOG 必须有
#   一行 `- **v…第 NN 片` 条目接住，方向只有这一边）、`tests/test_unreachable_code.py` 的不可达代码尺）。
#   两条已记录的卫生规矩照抄：门的 JSON/stdout 与验签的 JSON 一律**落树外**再 cp 入库
#   （第 91/100 片两次实测：写进被检查的树 ⇒ `workspace_clean`/`worktree_clean` 必自红）；
#   取证件先 commit 再跑验签（未跟踪也算脏）。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s105
X=/Volumes/Extra/CodeProj/AI全链路自研/.s88-outside
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
PRIOR_FLOOR=2809
mkdir -p "$X" "$R/docs/audit/s105"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要、collected 高于上代 ----
"$PY" - "$WT/report-s105.json" "$SHA" "$PRIOR_FLOOR" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
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
MIN_TESTS=$("$PY" -c "import json;print(json.load(open('$WT/report-s105.json'))['summary']['collected'])")
echo "MIN_TESTS=$MIN_TESTS （上一代下界 $PRIOR_FLOOR）"

# ---- 0b. 跳过面必须与上一代逐条相同（FAIL=0 不等于同一覆盖面）----
"$PY" - "$WT/report-s105.json" "$R/docs/audit/pytest-report-v5.6.0.json" <<'PY' || { echo "SKIP 面变了"; exit 2; }
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
cp "$WT/report-s105.json" docs/audit/pytest-report.json
cp "$WT/report-s105.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json \
    > "$X/bind105.log" 2>&1
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; tail -5 "$X/bind105.log"; exit 2; }

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
chore(s105): 绑定第 105 片的 attestation 报告

一次绑定、两个旗子同时给。本片原告是文档引用普查的符号锚支路：简写指针 `path.py::symbol`
原先只查 `resolve()` 按 ROOTS 前缀先撞上的那一份，同名文件一多，真载体在别处的引用就被判成
`symbol-missing`——把"没翻到那一份"折成了"符号不存在"。修好的支路因此扫遍所有同名候选：
符号在靠后的那份里也要认，并且要点名真正的载体文件；哪一份都没有才仍判 `symbol-missing`，
不许因为多查了几份就把它洗成有。CHANGELOG 记账尺与不可达代码尺照旧守着各自的既有面，
读到什么判什么，读不到前提一律判前提塌，绝不把"看不见"折成"没漂"。
上一片（第 104 片，collected 2809）作下界；本轮新增这条符号支路的常驻控制 ⇒ collected 只会更多。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（JSON 与 stdout 都落树外）----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out "$X/gate105.json" > "$X/gate105.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - "$X/gate105.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PY

# ---- 3. 先把门的读数与日志入库，再跑收尾验签（未跟踪也算脏）----
cp "$X/bind105.log" "$X/gate105.log" docs/audit/s105/
cp "$X/gate105.json" docs/audit/s105/gate.json
git add docs/audit/s105/gate.json
git add -f docs/audit/s105/gate105.log docs/audit/s105/bind105.log
git commit -q -m "chore(s105): 收下发布门读数（取证件先入库，再谈验签）"
echo "GATE_COMMIT_RC=$?"

"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_doc_reference_census.py \
    --expect-test tests/test_changelog_commit_crosscheck.py \
    --expect-test tests/test_unreachable_code.py \
    --min-tests "$MIN_TESTS" --json "$X/closeout105.json" > "$X/closeout105.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout105.json" "$X/closeout105.log" docs/audit/s105/
tail -14 docs/audit/s105/closeout105.log

git add docs/audit/s105/closeout105.json
git add -f docs/audit/s105/closeout105.log
git commit -q -m "chore(s105): 收尾验签读数入库"
echo "FINAL_COMMIT_RC=$?"
echo "=== 第 105 片收口结束：BIND=$BIND_RC GATE=$GATE_RC CV=$CV_RC MIN_TESTS=$MIN_TESTS ==="
