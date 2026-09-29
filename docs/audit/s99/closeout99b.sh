# 第 99 片收口链【第二代 b】：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由本片第一代 `closeout99.sh` 派生（派生器 `derive_closeout99b.py`，同一套锚点计数与工序哨兵），
#   只换：worktree 名（`.wt-s99b`，绝对路径、落在仓库**外**）/ 报告名（`report-s99b.json`）/
#   三个日志名的 b 后缀 / 两处提交信息 / 头部注释。
#   **`PRIOR_FLOOR` 沿用已认证的 2783（第 98 片实测 collected），不改**：第一代（2785）已作废、
#   不当下界；而第二代测的就是同一棵树的内容 ⇒ collected 只会复现 2785，若把下界也写成 2785，
#   前提判据 `collected > PRIOR_FLOOR` 会把一次合法的重跑读成"用例缩水"。派生器因此
#   **没有** PRIOR_FLOOR 这条替换锚（哨兵仍要求 `PRIOR_FLOOR=2783` 在场）。
#   第二代的原因记在本片 §认证读数与那份 VOID 报告：绑定之后又动了被哈希的面
#   （`CHANGELOG.md`）⇒ 清单与树不同源，绕不过（绑定前预检正是为此而立），只能重锚后重跑一遍。
#   --expect-test 仍点三条：`tests/test_forensic_scripts_root.py`（.sh 面 12 条）、
#   `tests/test_ci_surface_census.py`（行钉进自测 + 条数两格同源，15 条）、
#   `tests/test_forensic_scripts_parse.py`（本轮新增取证脚本与收口件的语法读者）。
#   （第 99 片的原告：`tests/test_forensic_scripts_root.py` 那 12 条（新尺的 .sh 面）、
#    `tests/test_ci_surface_census.py` 那 15 条（行钉两条判决进自测 + 条数两格同源）、
#    `tests/test_forensic_scripts_parse.py`（本轮新增取证脚本 `docs/audit/s99/battery99.py`
#    与改过的 `docs/audit/s96/build_forensic_root_register.py` 的唯一语法读者）。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s99b
X=/Volumes/Extra/CodeProj/AI全链路自研/.s88-outside
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
PRIOR_FLOOR=2783
mkdir -p "$X" "$R/docs/audit/s99"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要、collected 高于上代 ----
"$PY" - "$WT/report-s99b.json" "$SHA" "$PRIOR_FLOOR" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
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
MIN_TESTS=$("$PY" -c "import json;print(json.load(open('$WT/report-s99b.json'))['summary']['collected'])")
echo "MIN_TESTS=$MIN_TESTS （上一代下界 $PRIOR_FLOOR）"

# ---- 0b. 跳过面必须与上一代逐条相同（FAIL=0 不等于同一覆盖面）----
"$PY" - "$WT/report-s99b.json" "$R/docs/audit/pytest-report-v5.6.0.json" <<'PY' || { echo "SKIP 面变了"; exit 2; }
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
cp "$WT/report-s99b.json" docs/audit/pytest-report.json
cp "$WT/report-s99b.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json \
    > "$X/bind99b.log" 2>&1
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; tail -5 "$X/bind99b.log"; exit 2; }

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
chore(s99b): 绑定第 99 片第二代的 attestation 报告（第一代作废）

一次绑定、两个旗子同时给。判定内容与第一代完全相同（`.sh` 面进分母 + 两条行钉判决进 CI 自测
+ 自测条数两格同源），换的只有清单：第一代那一跑之后又改了被哈希的 `CHANGELOG.md`
（补 92 个脚本 / 名册 70 条那组现读），`source_manifest_zero_diff` 判红、逐条对磁盘复算确认
漂移只有那 1 条（692 条仍一致）⇒ 重锚清单后重跑一遍干净签出。第一代报告按惯例留档
`docs/audit/s99/report-s99-VOID-tree-51023121-fp-21085171c58e.json`。
上一代（第 98 片，collected 2783）仍是下界——第一代（2785）已作废，不拿来当自己的界，
否则同一份内容重跑一遍就会被 `collected > 下界` 读成用例缩水。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（stdout 落树外，否则 workspace_clean 永不可能绿）----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out docs/audit/s99/gate.json > "$X/gate99b.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - <<'PY'
import json
d = json.load(open("docs/audit/s99/gate.json"))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PY

# ---- 3. 先把门的读数与日志入库，再跑收尾验签（未跟踪也算脏）----
cp "$X/bind99b.log" "$X/gate99b.log" docs/audit/s99/
git add docs/audit/s99/gate.json docs/audit/repository_snapshot.json
git add -f docs/audit/s99/gate99b.log docs/audit/s99/bind99b.log
git commit -q -m "chore(s99b): 收下发布门读数（第二代，清树后复跑）"
echo "GATE_COMMIT_RC=$?"

"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_forensic_scripts_root.py \
    --expect-test tests/test_ci_surface_census.py \
    --expect-test tests/test_forensic_scripts_parse.py \
    --min-tests "$MIN_TESTS" --json docs/audit/s99/closeout.json > "$X/closeout99b.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout99b.log" docs/audit/s99/
tail -14 docs/audit/s99/closeout99b.log

git add docs/audit/s99/closeout.json
git add -f docs/audit/s99/closeout99b.log
git commit -q -m "chore(s99b): 收尾验签读数入库（第二代）"
echo "FINAL_COMMIT_RC=$?"
echo "=== 第 99 片第二代收口结束：BIND=$BIND_RC GATE=$GATE_RC CV=$CV_RC MIN_TESTS=$MIN_TESTS ==="
