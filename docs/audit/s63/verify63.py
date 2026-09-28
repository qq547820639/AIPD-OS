"""第 63 片收尾验签：报告 + 树上的用例名单 + 镜像正向锚，三对照才放行。

与第 62 片同形（那份脚本随 /tmp 一起没了，这里按记忆重写并把"报告记的是钉住的发布源"
这条已修正的前提写死）：
- 手写名单一律与树上的 `def test_*` 求差，不靠抄；
- `X not in …` 的前提必须配正向读锚（文件读不到时"不含"永真）；
- 判决看报告自己的签名（exitcode / summary / 每条 outcome），不看退出码；
- 报告的 source_commit 是**钉住的 tag SHA**（门禁 test_numbers_from_report 的定义）；
  "测的是这棵树"由套件内两条清单哈希用例证，不由 commit 字符串证。
"""
from __future__ import annotations

import ast
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

WT = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s63a")
REPORT = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s63-report.json")
TEST_FILE = "tests/test_truth_history.py"
PINNED = "a66040520139405095648461f7144d4f00629924"
EXPECTED_TESTS = 12
PARITY = ["tests/test_packaging.py::test_release_manifest_hashes_match_disk",
          "tests/test_packaging.py::test_source_manifest_hashes_match_disk"]

fails: list[str] = []
oks: list[str] = []


def check(cond: bool, ok_msg: str, fail_msg: str) -> None:
    (oks if cond else fails).append(ok_msg if cond else fail_msg)


if not REPORT.is_file():
    print(f"✗ 报告不存在：{REPORT}")
    sys.exit(2)
raw = REPORT.read_text(encoding="utf-8")
check(len(raw) > 2000, f"报告非平凡（{len(raw)} 字节）", f"报告只有 {len(raw)} 字节，不可信")
rep = json.loads(raw)
summary = rep.get("summary", {})
tests = rep.get("tests", [])

check(rep.get("exitcode") == 0, "exitcode == 0", f"exitcode={rep.get('exitcode')}")
outcome = collections.Counter(str(t.get("outcome")) for t in tests)
bad = sorted(k for k in outcome if k not in ("passed", "skipped", "xfailed", "xpassed"))
check(not bad, f"outcome 只有 passed/skipped（{dict(outcome)}）",
      f"出现失败类 outcome：{{k: outcome[k] for k in bad}}")
for key in ("failed", "error", "rerun"):
    check(summary.get(key, 0) == 0 and not any(
        str(t.get("outcome")) == key for t in tests),
        f"{key} 缺席或为 0", f"{key}={summary.get(key)}")
total = sum(outcome.values())
check(total == summary.get("collected") == summary.get("total"),
      f"分项合计等于 collected/total（{total}）",
      f"分项合计 {total} vs collected={summary.get('collected')} total={summary.get('total')}")
check(str(rep.get("source_commit")) == PINNED,
      f"报告 source_commit 等于钉住的 v5.6.0（{PINNED[:8]}）",
      f"报告 source_commit={str(rep.get('source_commit'))[:12]!r} 不是钉住的那份 ⇒ 门禁会判 STALE")

head = subprocess.run(["git", "-C", str(WT), "rev-parse", "HEAD"],
                      capture_output=True, text=True).stdout.strip()
check(bool(re.fullmatch(r"[0-9a-f]{40}", head)), f"工作树 HEAD 读到（{head[:8]}）",
      "git rev-parse 没返回 SHA")
tree_clean = subprocess.run(["git", "-C", str(WT), "status", "--porcelain"],
                            capture_output=True, text=True).stdout.strip()
check(tree_clean == "", "被检出的工作树干净（没有未提交改动混进取证）",
      f"工作树不干净：{tree_clean[:120]}")
check(len(tests) == summary.get("collected"), f"tests[] 长度等于 collected（{len(tests)}）",
      f"tests[] {len(tests)} vs collected {summary.get('collected')}")

src = (WT / TEST_FILE).read_text(encoding="utf-8")
on_disk = [n.name for n in ast.parse(src).body
           if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
check(len(on_disk) >= EXPECTED_TESTS,
      f"树上的 {TEST_FILE} 读到 {len(on_disk)} 条用例（≥{EXPECTED_TESTS}）",
      f"只读到 {len(on_disk)} 条用例 ⇒ 分母本身不可信")
report_names = {t["nodeid"].split("::")[-1] for t in tests if t["nodeid"].startswith(TEST_FILE)}
check(not sorted(set(on_disk) - report_names),
      f"{TEST_FILE} 的 {len(on_disk)} 条全在报告里",
      f"报告缺这些树上的用例：{sorted(set(on_disk) - report_names)}")
check(not sorted(report_names - set(on_disk)), "报告没有凭空多出的同名用例",
      f"报告里有树上不存在的用例：{sorted(report_names - set(on_disk))}")
not_passed = sorted(t["nodeid"].split("::")[-1] for t in tests
                    if t["nodeid"].startswith(TEST_FILE) and t.get("outcome") != "passed")
check(not not_passed, "本片用例逐条 outcome == passed", f"这些用例不是 passed：{not_passed}")
by_name = {t["nodeid"]: t.get("outcome") for t in tests}
for node in PARITY:
    check(by_name.get(node) == "passed", f"内容同一性证据在场且通过：{node.split('::')[-1]}",
          f"缺 {node} ⇒ 只有 commit 字符串对得上不算证")

# 正向读锚：证明"没红"不是因为整棵树上没有这片的实现
db_src = (WT / "src/aipd_os/state/db.py").read_text(encoding="utf-8")
cmd_src = (WT / "src/aipd_os/cli/commands_truth.py").read_text(encoding="utf-8")
readme = (WT / "README.md").read_text(encoding="utf-8")
contract = (WT / "src/aipd_os/cli/command_contract.py").read_text(encoding="utf-8")
check("def audit_history(" in db_src, "state/db.py 里读到 audit_history",
      "db.py 里没有 audit_history ⇒ 检出的树不含本片实现")
check("def cmd_truth_history(" in cmd_src, "commands_truth.py 里读到 cmd_truth_history",
      "commands_truth.py 里没有 cmd_truth_history")
check('"truth history": cmd_truth_history' in (WT / "src/aipd_os/cli/commands.py").read_text(encoding="utf-8"),
      "派发表里有 truth history", "commands.py 的派发表没有该命令")
check('CommandEntry("truth history"' in contract, "契约条目在场", "契约里没有 truth history 条目")
check("aipd truth history" in readme, "README 里读到速查行", "README 里没有该行")
fn = next((n for n in ast.parse(cmd_src).body
           if isinstance(n, ast.FunctionDef) and n.name == "cmd_truth_history"), None)
check(fn is not None, "AST 里找到 cmd_truth_history 这个函数", "AST 里找不到该函数")
if fn is not None:
    body = ast.get_source_segment(cmd_src, fn) or ""
    check("add_audit" not in body,
          f"处理器函数体（{len(body.splitlines())} 行）里没有写审计的调用",
          "处理器函数体里出现 add_audit ⇒ 读面在污染审计通道")

print("=" * 62)
print("第 63 片收尾验签")
print("=" * 62)
for m in oks:
    print("  [OK] " + m)
for m in fails:
    print("  [FAIL] " + m)
print(f"读数：collected={summary.get('collected')} passed={summary.get('passed')} "
      f"skipped={summary.get('skipped')} duration={rep.get('duration')}s  HEAD={head[:8]}")
print(f"结论：{'全 [OK]' if not fails else f'{len(fails)} 条 FAIL'}")
sys.exit(0 if not fails else 1)
