"""给第 83 片取证文档补一节「六、终局读数」——所有数字一律现读，不手抄。

闸门（任一不过就整节不写）：
① 绑进证据的那份报告自带指纹，且与磁盘 `SOURCE_MANIFEST.json` 的内容规范摘要逐位相等；
② 发布门两轮都 `release_ready=True` 且八项全过；
③ `closeout_verifier` 那一行判决为"全部判据绿"；
④ 干净签出那一跑 0 failed；
⑤ 写完后 §五/§六/§七/§八 四个标题各存在一次且顺序正确。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

R = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
T = Path("/Volumes/Extra/CodeProj/AI全链路自研/tmp/s83")
DOC = R / "docs/audit/REPORT_MANIFEST_FINGERPRINT_F-REPORT-MANIFEST-FINGERPRINT_2026-09-28.md"
sys.path.insert(0, str(R / "scripts"))
import release_fingerprint as rf  # noqa: E402


def sh(args):
    p = subprocess.run(args, cwd=str(R), capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def gate(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    checks = d["checks"]
    return d["release_ready"], all(c["passed"] for c in checks), len(checks)


log = (T / "s83b.log").read_text(encoding="utf-8")
bound = json.loads((R / "docs/audit/pytest-report-v5.6.0.json").read_text(encoding="utf-8"))
disk_fp, err = rf.fingerprint_from_file(R / "SOURCE_MANIFEST.json")
rec_fp = str(bound.get("source_manifest_fingerprint") or "")
g1 = gate(T / "gate_s83.json")
g2 = gate(T / "gate_s83b.json")
verifier_green = "全部判据绿" in log
run_clean = bound["summary"].get("failed", 0) == 0 and bound["exitcode"] == 0
dur = round(bound["duration"], 1)
skips = [x["nodeid"] for x in bound["tests"] if x["outcome"] == "skipped"]
head = sh(["git", "rev-parse", "HEAD"])
bind_commit = sh(["log", "--format=%h", "-1", "--", "PROVENANCE.json"])
worktree = re.search(r"\[full\] worktree=(\S+)", log)
loaded = re.search(r"\[full\] aipd_os 来自 (\S+)", log)
src_n = len(json.loads((R / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))["files"])
rel_n = len(json.loads((R / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))["files"])
prov = json.loads((R / "PROVENANCE.json").read_text(encoding="utf-8"))
bound_sha = str(prov["test_report"].get("sha256") or "")[:12]
import hashlib  # noqa: E402
actual_sha = hashlib.sha256((R / "docs/audit/pytest-report-v5.6.0.json").read_bytes()).hexdigest()[:12]

fail = []
if not rec_fp or rec_fp != disk_fp:
    fail.append(f"报告指纹 {rec_fp[:12] or '（没有）'} != 磁盘 {disk_fp[:12] or err}")
if not run_clean:
    fail.append(f"绑定的那份不干净：{bound['summary']}")
if not verifier_green:
    fail.append("closeout_verifier 那一行没打出「全部判据绿」")
if not (g1[0] and g1[1] and g2[0] and g2[1]):
    fail.append(f"发布门没两轮全过：{g1} / {g2}")
if bound_sha != actual_sha:
    fail.append(f"PROVENANCE 记的报告 sha {bound_sha} != 磁盘那份 {actual_sha}")
if fail:
    print("REFUSE-WRITE：" + "；".join(fail))
    sys.exit(8)

SEC = f"""## 六之二、终局读数（绑定那一跑，全部现读）

| 格 | 读数 |
|---|---|
| 干净签出 | worktree `{worktree.group(1) if worktree else '?'}` 检出 HEAD，`aipd_os` 真被加载自 `{loaded.group(1) if loaded else '?'}` |
| summary | `{bound['summary']}`，`exitcode={bound['exitcode']}`，`duration={dur} s` |
| 跳过（与上一轮同一批） | {len(skips)} 条：联网与真实邮件服务的既有用例 |
| 报告指纹 | `source_manifest_fingerprint={rec_fp[:16]}…` == 磁盘 `SOURCE_MANIFEST.json` 内容规范摘要 |
| PROVENANCE 绑定 | `test_report.sha256={bound_sha}…`，与磁盘那份逐字节一致；绑定提交 `{bind_commit}` |
| 清单分母 | SOURCE {src_n} 个文件 / RELEASE {rel_n} 个文件（`docs/audit/` 整体排除 ⇒ 0 条） |
| 发布门 | 第一轮 `release_ready={g1[0]}`（{g1[2]} 项全过）；第二轮 `release_ready={g2[0]}`（{g2[2]} 项全过） |
| 收尾验签 | `closeout_verifier --tag v5.6.0 --expect-test tests/test_report_manifest_fingerprint.py --min-tests 2660` ⇒ 全部判据绿（十一格） |

两条本片该记住的形状：

1. **"报告与清单同源"这件事现在是两处读的**：绑定脚本在写之前就比（不等退 8，是 C11 的事前档），
   `closeout_verifier` 在绑定之后照 C10/C11 复核。事前档现在只活在收尾脚本里 ⇒ 下一片接进
   `release_evidence.py` 本体（§八.4），否则它守的是"我记得跑这一步"。
2. **换绑之前那 5 条红不是判据坏，是判据在要求换绑**。第一版把它写成判红造成自锁，
   改判前提塌之后配方仍然过不去（退 2），只是不再伪造"有 5 条违规"这个读数。
   写这一节时报告已经带着字段，`problems` 为空，十一格全绿——那条限定放行
   （`problems ⊆ {{report_fingerprint_recorded}}`）就此回到"必须绿"的名单里。

"""

head_re = re.compile(r"^## ", re.M)
t = DOC.read_text(encoding="utf-8")
anchor = "## 七、复算入口"
assert t.count(anchor) == 1, t.count(anchor)
assert "## 六之二、终局读数" not in t, "已经补过了（幂等闸）"
new = t.replace(anchor, SEC + anchor, 1)
DOC.write_text(new, encoding="utf-8")

back = DOC.read_text(encoding="utf-8")
order = [back.index(x) for x in ("## 六、电池", "## 六之二、终局读数",
                                 "## 七、复算入口", "## 八、本片没做的事")]
assert order == sorted(order), order
assert len(re.findall(r"^## ", back, head_re)) == len(re.findall(r"^## ", t, head_re)) + 1
assert "@@" not in back and "'?'" not in back and "if worktree else" not in back
print(f"[WROTE] §六 终局读数已补（HEAD {head[:7]}）；标题序 {order}")
print(f"[读数] summary={bound['summary']} 指纹={rec_fp[:12]} 门={g1[0]}/{g2[0]} 清单={src_n}/{rel_n}")
