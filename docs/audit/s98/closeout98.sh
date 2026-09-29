# 第 98 片收口链：绑定 → 提交 → 发布门 → 提交门的读数 → 收尾验签。
# 由上一片（第 97 片）逐行派生，只换：报告名 / worktree 名 / 产物目录名 /
#   PRIOR_FLOOR=上一代实测 collected(2780) / 绑定提交信息 / --expect-test 点两条
#   （第 98 片的原告在两个文件里：`tests/test_ci_surface_census.py` 那 15 条
#    与 `tests/test_forensic_scripts_parse.py`——后者是本轮新增取证脚本
#    `docs/audit/s98/battery98.py` 的唯一读者，它语法塌只有这一条看得见。）
# 派生完做两件事：grep 残留 s94 归零（$X 的 .s88-outside 除外）、bash -n 过一遍。
set -u
R=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
WT=/Volumes/Extra/CodeProj/AI全链路自研/.wt-s98b
X=/Volumes/Extra/CodeProj/AI全链路自研/.s88-outside
PY="$R/.venv/bin/python"
export PATH="$R/.venv/bin:$PATH"
PRIOR_FLOOR=2780
mkdir -p "$X" "$R/docs/audit/s98"
cd "$R" || exit 9

SHA=$(git rev-parse 'v5.6.0^{commit}')
echo "tag SHA = $SHA"

# ---- 0. 硬前提：0 failed、锚点 == tag、自记指纹 == 磁盘清单内容摘要、collected 高于上代 ----
"$PY" - "$WT/report-s98.json" "$SHA" "$PRIOR_FLOOR" <<'PY' || { echo "PRECHECK FAILED"; exit 2; }
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
MIN_TESTS=$("$PY" -c "import json;print(json.load(open('$WT/report-s98.json'))['summary']['collected'])")
echo "MIN_TESTS=$MIN_TESTS （上一代下界 $PRIOR_FLOOR）"

# ---- 0b. 跳过面必须与上一代逐条相同（FAIL=0 不等于同一覆盖面）----
"$PY" - "$WT/report-s98.json" "$R/docs/audit/pytest-report-v5.6.0.json" <<'PY' || { echo "SKIP 面变了"; exit 2; }
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
cp "$WT/report-s98.json" docs/audit/pytest-report.json
cp "$WT/report-s98.json" docs/audit/pytest-report-v5.6.0.json
"$PY" scripts/release_evidence.py --repo . --out . --version 5.6.0 \
    --source-commit "$SHA" --test-report docs/audit/pytest-report-v5.6.0.json \
    > "$X/bind98.log" 2>&1
BIND_RC=$?
echo "BIND_RC=$BIND_RC"
[ "$BIND_RC" = 0 ] || { echo "绑定被拒——清单在跑完之后又动过，回去重跑而不是绕闸"; tail -5 "$X/bind98.log"; exit 2; }

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
chore(s98): 绑定第 98 片的 attestation 报告

一次绑定、两个旗子同时给。本轮动的是 CI 对账尺的**行钉维度**：`ci_commands()` 按命令文本去重，
所以 `line` 一直是「排序后第一个跑这条命令的 job」那一行，而 `job` 列是一串名字——现读 3 条
跨 job 命令共 23 处执行点只钉住 3 个。现在逐 (job, 行) 记账（`occurrences`/`lines_total`，
定不到行号的 job 也以空列表露头），并加两条判决 `CI面行钉不穷举` / `CI面行钉指错行`；
第二查做成纯函数 `line_pin_defects(cmds, file_lines)`，否则正常解析下天然自洽、够不到那一档。
上一代（第 97 片，collected 2780）只作下界对比。
许可证门禁仍对 casadi/LGPL 判红是有意的（台账 needs-review 等属主拍板），发布门不消费它的退码。
MSG
echo "COMMIT_RC=$?"
git log --oneline -1

# ---- 2. 发布门（stdout 落树外，否则 workspace_clean 永不可能绿）----
"$PY" scripts/production_release_gate.py --release-ready --tag v5.6.0 \
    --test-report docs/audit/pytest-report-v5.6.0.json \
    --json-out docs/audit/s98/gate.json > "$X/gate98.log" 2>&1
GATE_RC=$?
echo "GATE_RC=$GATE_RC"
"$PY" - <<'PY'
import json
d = json.load(open("docs/audit/s98/gate.json"))
bad = [c["check"] for c in d["checks"] if not c.get("passed")]
print("release_ready:", d.get("release_ready"), "| 未过:", bad or "无", "| 项数:", len(d["checks"]))
PY

# ---- 3. 先把门的读数与日志入库，再跑收尾验签（未跟踪也算脏）----
cp "$X/bind98.log" "$X/gate98.log" docs/audit/s98/
git add docs/audit/s98/gate.json docs/audit/repository_snapshot.json
git add -f docs/audit/s98/gate98.log docs/audit/s98/bind98.log
git commit -q -m "chore(s98): 收下发布门读数（取证件先入库，再谈验签）"
echo "GATE_COMMIT_RC=$?"

"$PY" scripts/closeout_verifier.py --tag v5.6.0 \
    --expect-test tests/test_ci_surface_census.py \
    --expect-test tests/test_forensic_scripts_parse.py \
    --min-tests "$MIN_TESTS" --json docs/audit/s98/closeout.json > "$X/closeout98.log" 2>&1
CV_RC=$?
echo "CV_RC=$CV_RC  （0 全绿 / 4 判红 / 2 前提塌）"
cp "$X/closeout98.log" docs/audit/s98/
tail -14 docs/audit/s98/closeout98.log

git add docs/audit/s98/closeout.json
git add -f docs/audit/s98/closeout98.log
git commit -q -m "chore(s98): 收尾验签读数入库"
echo "FINAL_COMMIT_RC=$?"
echo "=== 第 98 片收口结束：BIND=$BIND_RC GATE=$GATE_RC CV=$CV_RC MIN_TESTS=$MIN_TESTS ==="
