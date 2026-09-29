#!/usr/bin/env python3
r"""由第 96 片的收口脚本派生第 97 片那一支（根路径由 `__file__` 推，不写死仓库内绝对路径）。

换的六类锚（每处由脚本现数命中次数，任一为 0 就整支不写）：
① `s96`→`s97`；② 签出名（第 96 片用掉 `.wt-s96b` ⇒ 本片第一签出直接叫 `.wt-s97`）；
③ `PRIOR_FLOOR`（上一代实测 collected 2772）；④ 头部派生说明与原告清单；
⑤ `--expect-test` 的两行（第 97 片动了 `scripts/release_evidence.py` ⇒ 既点新增那支文件，
   也点既有的绑定前预检那支——后者是"改了工具却没测到旧口径"的探测器）；
⑥ 绑定提交正文。

派生完必做三件：残留 `s96` 归零、工序哨兵逐条仍在、`bash -n` 过。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "docs/audit/s96/closeout96.sh"
DST = ROOT / "docs/audit/s97/closeout97.sh"

SUBS = [
    ("s96", "s97"),
    # 第二代签出带 b：第一代 `.wt-s97`（被自家卫生门拦下那一跑）的名字要留给它的 VOID 读数。
    ("/.wt-s97b", "/.wt-s97b"),
    ("# 由上一片（第 95 片）逐行派生", "# 由上一片（第 96 片）逐行派生"),
    ("#   PRIOR_FLOOR=上一代实测 collected(2761)", "#   PRIOR_FLOOR=上一代实测 collected(2772)"),
    ("PRIOR_FLOOR=2761", "PRIOR_FLOOR=2772"),
    ("#   （第 96 片的原告在两个文件里：`tests/test_forensic_scripts_root.py` 那 10 条\n"
     "#    与 `tests/test_closeout_verifier.py` 补的 C5 读数标签那一极；只点一条就会让\n"
     "#    \"另一半没跑到\"读成通过）。",
     "#   （第 97 片的原告在两个文件里：`tests/test_release_evidence_environment.py` 那 8 条\n"
     "#    与既有的 `tests/test_release_evidence_preflight.py`——后者是\"改了工具却没测到\n"
     "#    旧口径\"的探测器：本片动了同一支 `scripts/release_evidence.py` 的版本号来源。）"),
    ("    --expect-test tests/test_closeout_verifier.py \\\n",
     "    --expect-test tests/test_release_evidence_preflight.py \\\n"),
    ("    --expect-test tests/test_forensic_scripts_root.py \\\n",
     "    --expect-test tests/test_release_evidence_environment.py \\\n"),
    # 日志**基名**里的数字前面是 `out`/`bind`/`gate` 而不是 `s`，所以 `s95`→`s96` 这类替换
    # 从第 95 片起一直在漏它们：第 96 片跑完，docs/audit/s96/ 里躺着的是
    # bind95.log / gate95.log / closeout95.log（内容是真读数，名字是上一轮的）。
    ("bind95.log", "bind97.log"),
    ("gate95.log", "gate97.log"),
    ("closeout95.log", "closeout97.log"),
    ("# 第 96 片收口链", "# 第 97 片收口链"),
    ("绑定第 96 片的 attestation 报告", "绑定第 97 片的 attestation 报告"),
    ("=== 第 96 片收口结束", "=== 第 97 片收口结束"),
    ("一次绑定、两个旗子同时给。本轮动的是两处读数面：`scripts/closeout_verifier.py` 的 C5 说明串\n"
     "不再被 `[:8]` 截半（标签与\"弱一档\"那句都要出现，常驻用例直读那个字符串），以及\n"
     "`docs/audit/s97/build_forensic_root_register.py` 这把新尺——取证脚本把仓库内绝对路径写死时\n"
     "必须被唯一一条写明理由的豁免接住，否则判红（名册是生成物，重新生成洗不出更宽的豁免）。\n"
     "上一代（第 95 片，collected 2761）只作下界对比。",
     "一次绑定、两个旗子同时给。本轮动的是发布工具的**写入内容来源**：`_pkg_version()` 先问\n"
     "`importlib.metadata.version()`，查不到才回退 `mod.__version__`（本机现跑读 jsonschema 4.25.1\n"
     "的属性已在吐 DeprecationWarning，将来移除后那一格会静默变 `unknown`）；并给\n"
     "`_build_environment`/`_dependency_lock`/`generate_bundle_manifest`/`--bundle` 四段补上常驻牙——\n"
     "这四段此前在 `tests/` 里逐个名字零命中。切换前后三格版本号现读逐字相同 ⇒ 只换来源不换数。\n"
     "上一代（第 96 片，collected 2772）只作下界对比。"),
]

SENTINELS = ["GATE_RC=$?", "CV_RC=$?", "FINAL_COMMIT_RC=$?", "MIN_TESTS=", "SKIP 面逐条相同",
             "PRECHECK FAILED", "bind97.log", "gate97.log", "closeout97.log"]


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    for old, new in SUBS:
        n = text.count(old)
        assert n >= 1, f"锚点读不到 ⇒ 一支都不写：{old[:60]!r} 命中 {n}"
        text = text.replace(old, new)
    assert "s96" not in text, "还有 s96 残留"
    assert "95.log" not in text, "日志基名还带着上上轮的数字（`sNN` 替换管不到 `bind95.log` 这种写法）"
    for s in SENTINELS:
        assert s in text, f"派生件丢了工序哨兵：{s}"
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(text, encoding="utf-8")
    chk = subprocess.run(["bash", "-n", str(DST)], capture_output=True, text=True)
    print(f"写出 {DST.relative_to(ROOT)}：{text.count(chr(10))} 行、{len(SUBS)} 处替换各命中 ≥1、"
          f"bash -n rc={chk.returncode} {chk.stderr[:200]}")
    return 0 if chk.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
