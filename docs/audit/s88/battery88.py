#!/usr/bin/env python3
"""第 88 片变异电池：每一档判决都要有一支"撤掉它就必红"的对照臂。

覆盖面三根轴（10 支臂）：
- `release_evidence.write_evidence()` 的锚点必填（X1 把默认值装回去、X2 关掉整条校验、
  X3 把"恰好 40 位"退化成"至少 7 位"——第 86 片 X3 记的那条最可能的腐化路径，这轮在 API 侧重演、
  X8 把字符类放宽回大小写通吃——只在大写那档才有牙，见 `test_api_refuses_..._before_any_write`）；
- 登记册的 `cited_by_at_emit_time` 降级（X4 让那列重新承重、X7 把 `rule` 常量改回写错归属数的那版）；
- `emit_register` 的三条新前提（X5 撤掉 note 带旧值、X6 目标读不出也照样落盘、
  X9 不再报出"有依据却被丢"的条目、X10 目标不是字典时不拒绝）。

X6 与 X10 是按复核件要求改的形状：原来那版把拒绝分支删成 `pass` 会让电池靠
`UnboundLocalError` **崩溃**而红，于是"拒绝时不许动目标文件"那条断言从没被执行过。
现在两支都在正常返回路径上翻红。

分类：KILLED（该臂被常驻用例抓住）/ SURVIVED（撤掉没人发现＝这档没牙）/
BAD-ANCHOR（锚点没落到预期位置，臂作废，读数不进合计）。
对照臂 X0 不改任何字节，必须先证明"原样是绿的"，否则后面的红不能归因给变异。

跑法：`python docs/audit/s88/battery88.py`（约 15 分钟，每臂跑三个用例文件）。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path("/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS")
EV = REPO / "scripts" / "release_evidence.py"
CEN = REPO / "scripts" / "doc_command_census.py"
TESTS = ("tests/test_release_evidence_preflight.py "
         "tests/test_doc_command_census.py tests/test_release_evidence.py").split()

API_GUARD = '    if not re.fullmatch(r"[0-9a-f]{40}", source_commit or ""):'
DROP_REPORT = '            "dropped": dropped, "refused": ""}'
NON_DICT_BRANCH = (
    '        if not isinstance(existing, dict):\n'
    '            return {"written": 0, "missing_notes": [], "dropped": [],\n'
    '                    "refused": f"目标登记册不是字典（读到 {type(existing).__name__}），"\n'
    '                               "草案不落盘以免抹掉手写依据"}')

# (名字, 撤掉的是什么, 目标文件, old, new)。old 必须在目标文件里恰好命中一次。
ARMS = [
    ("X0-control-no-change", "对照：原样必须全绿", None, None, None),
    ("X1-default-put-back", "签名默认值装回 `| None = None`（少传参数不再报错）", EV,
     '                   source_commit: str) -> dict:',
     '                   source_commit: str | None = None) -> dict:'),
    ("X2-api-guard-off", "整条锚点校验关掉（`False and` 使判据永不让步）", EV,
     API_GUARD,
     '    if False and not re.fullmatch(r"[0-9a-fA-F]{40}", source_commit or ""):'),
    ("X3-40-becomes-7", "「恰好 40 位」退化成「至少 7 位」：短 SHA 重新通过", EV,
     API_GUARD,
     '    if not re.match(r"[0-9a-fA-F]{7,}", source_commit or ""):'),
    ("X4-snapshot-column-reweighted", "把快照列接回判据（缺列的登记条目不再豁免）", CEN,
     '        out[path] = str(e.get("note") or "")',
     '        if not e.get("cited_by_at_emit_time"):\n'
     '            continue\n'
     '        out[path] = str(e.get("note") or "")'),
    ("X5-no-note-carry-forward", "刷新登记册时不再带旧 note（手写豁免依据被抹掉）", CEN,
     '                     "note": old_notes.get(k, "")} for k, v in sorted(by.items())],',
     '                     "note": ""} for k, v in sorted(by.items())],'),
    ("X6-overwrite-unparsable-register", "目标读不出时照样落盘（拒绝只剩一句话）", CEN,
     '        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:\n'
     '            return {"written": 0, "missing_notes": [], "dropped": [],\n'
     '                    "refused": f"目标登记册读不出，草案不落盘以免抹掉手写依据：{exc}"}',
     '        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:\n'
     '            existing = {}'),
    ("X7-rule-text-drift", "`rule` 常量写错归属档数（与册子各漂各的）", CEN,
     'REGISTER_RULE = (\n    "面 ⑤ 对每一条 `<解释器> 路径.py|.sh` 形态的入口判五种归属"',
     'REGISTER_RULE = (\n    "面 ⑤ 对每一条 `<解释器> 路径.py|.sh` 形态的入口判四种归属"'),
    ("X8-api-hex-class-widened", "API 侧把字符类放宽回大小写通吃", EV,
     API_GUARD,
     '    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_commit or ""):'),
    ("X9-dropped-notes-unreported", "有手写依据却被丢的条目不再报出来", CEN,
     DROP_REPORT,
     '            "dropped": [], "refused": ""}'),
    ("X10-nondict-target-not-refused", "目标不是字典时不拒绝（回去就抛 AttributeError）", CEN,
     NON_DICT_BRANCH,
     '        if not isinstance(existing, dict):\n            pass'),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def run_tests() -> tuple[int, str]:
    p = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "pytest", "-q",
                        "--no-header", "-p", "no:cacheprovider", *TESTS],
                       cwd=REPO, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src"),
                            "HOME": str(Path.home())})
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    originals = {f: f.read_bytes() for f in (EV, CEN)}
    for f, b in originals.items():
        print(f"{f.name} sha={sha(b)}")
    rc, out = run_tests()
    if rc != 0:
        print("X0 对照臂不绿，电池前提不成立：", out[-800:])
        return 5
    print("[CONTROL OK] X0 原样全绿")
    marks = {"KILLED": 0, "SURVIVED": 0, "BAD-ANCHOR": 0}
    for name, what, tool, old, new in ARMS:
        if tool is None:
            continue                      # 对照臂不参与牙的合计（上面已证它不红）
        text = tool.read_bytes().decode("utf-8")
        hits = text.count(old)
        if hits != 1:
            print(f"[BAD-ANCHOR] {name}（{what}）锚点在 {tool.name} 命中 {hits} 次 ⇒ 臂作废")
            marks["BAD-ANCHOR"] += 1
            continue
        tool.write_text(text.replace(old, new, 1), encoding="utf-8")
        if sha(tool.read_bytes()) == sha(originals[tool]):    # 落地证明：字节必须变
            print(f"[BAD-ANCHOR] {name} 改写后字节未变")
            marks["BAD-ANCHOR"] += 1
            tool.write_bytes(originals[tool])
            continue
        rc, out = run_tests()
        tool.write_bytes(originals[tool])
        if sha(tool.read_bytes()) != sha(originals[tool]):
            print(f"[!] 复位失败 {name}")
            return 6
        killed_by = [ln.split(" - ")[0].replace("FAILED ", "")
                     for ln in out.splitlines() if ln.startswith("FAILED ")]
        if rc == 0:
            print(f"[SURVIVED] {name}（{what}）撤掉这档判决，用例照绿 ⇒ 没牙")
            marks["SURVIVED"] += 1
        else:
            who = "; ".join(killed_by) if killed_by else "(没解析出 FAILED 行，见日志)"
            # 不截太短：第 88 片复核时 `[:200]` 把第三条归因切掉，读数无法核对是哪条用例抓的
            print(f"[KILLED]   {name}（{what}）被抓住：{who[:600]}")
            marks["KILLED"] += 1
    total = len(ARMS) - 1
    print(f"合计 KILLED {marks['KILLED']} / {total}；"
          f"其余按判决分类：{ {k: v for k, v in marks.items() if k != 'KILLED' and v} or '无' }")
    for f, b in originals.items():
        print(f"收尾复算 {f.name} sha={sha(f.read_bytes())}（应等于 {sha(b)}）")
    return 0 if marks["SURVIVED"] == 0 and marks["BAD-ANCHOR"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
