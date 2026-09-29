#!/usr/bin/env python3
r"""由第 97 片的收口脚本派生第 98 片那一支（根路径由 `__file__` 推，不写死仓库内绝对路径）。

换的锚（每处由脚本现数命中次数，任一为 0 就整支不写）：
① `s97`→`s98`；② 签出名 `.wt-s98`；③ `PRIOR_FLOOR`（上一代实测 collected 2780）；
④ 头部派生说明与原告清单；⑤ `--expect-test` 两行（第 98 片动了 `scripts/ci_surface_census.py`
   与它的常驻文件，另加 `tests/test_forensic_scripts_parse.py`——它才是本轮新增
   `docs/audit/s98/battery98.py` 的读者，语法塌只有它看得见）；⑥ 绑定提交正文与三处日志基名。

派生完必做三件：残留 `s97`/`97.log` 归零、工序哨兵逐条仍在、`bash -n` 过。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "docs/audit/s97/closeout97.sh"
DST = ROOT / "docs/audit/s98/closeout98.sh"

SUBS = [
    ("s97", "s98"),
    ("# 由上一片（第 96 片）逐行派生", "# 由上一片（第 97 片）逐行派生"),
    ("#   PRIOR_FLOOR=上一代实测 collected(2772)", "#   PRIOR_FLOOR=上一代实测 collected(2780)"),
    ("PRIOR_FLOOR=2772", "PRIOR_FLOOR=2780"),
    ("bind97.log", "bind98.log"),
    ("gate97.log", "gate98.log"),
    ("closeout97.log", "closeout98.log"),
    ("# 第 97 片收口链", "# 第 98 片收口链"),
    ("绑定第 97 片的 attestation 报告", "绑定第 98 片的 attestation 报告"),
    ("=== 第 97 片收口结束", "=== 第 98 片收口结束"),
    ("#   （第 97 片的原告在两个文件里：`tests/test_release_evidence_environment.py` 那 8 条\n"
     "#    与既有的 `tests/test_release_evidence_preflight.py`——后者是\"改了工具却没测到\n"
     "#    旧口径\"的探测器：本片动了同一支 `scripts/release_evidence.py` 的版本号来源。）",
     "#   （第 98 片的原告在两个文件里：`tests/test_ci_surface_census.py` 那 15 条\n"
     "#    与 `tests/test_forensic_scripts_parse.py`——后者是本轮新增取证脚本\n"
     "#    `docs/audit/s98/battery98.py` 的唯一读者，它语法塌只有这一条看得见。）"),
    ("    --expect-test tests/test_release_evidence_preflight.py \\\n",
     "    --expect-test tests/test_ci_surface_census.py \\\n"),
    ("    --expect-test tests/test_release_evidence_environment.py \\\n",
     "    --expect-test tests/test_forensic_scripts_parse.py \\\n"),
    ("一次绑定、两个旗子同时给。本轮动的是发布工具的**写入内容来源**：`_pkg_version()` 先问\n"
     "`importlib.metadata.version()`，查不到才回退 `mod.__version__`（本机现跑读 jsonschema 4.25.1\n"
     "的属性已在吐 DeprecationWarning，将来移除后那一格会静默变 `unknown`）；并给\n"
     "`_build_environment`/`_dependency_lock`/`generate_bundle_manifest`/`--bundle` 四段补上常驻牙——\n"
     "这四段此前在 `tests/` 里逐个名字零命中。切换前后三格版本号现读逐字相同 ⇒ 只换来源不换数。\n"
     "上一代（第 96 片，collected 2772）只作下界对比。",
     "一次绑定、两个旗子同时给。本轮动的是 CI 对账尺的**行钉维度**：`ci_commands()` 按命令文本去重，\n"
     "所以 `line` 一直是「排序后第一个跑这条命令的 job」那一行，而 `job` 列是一串名字——现读 3 条\n"
     "跨 job 命令共 23 处执行点只钉住 3 个。现在逐 (job, 行) 记账（`occurrences`/`lines_total`，\n"
     "定不到行号的 job 也以空列表露头），并加两条判决 `CI面行钉不穷举` / `CI面行钉指错行`；\n"
     "第二查做成纯函数 `line_pin_defects(cmds, file_lines)`，否则正常解析下天然自洽、够不到那一档。\n"
     "上一代（第 97 片，collected 2780）只作下界对比。"),
]

SENTINELS = ["GATE_RC=$?", "CV_RC=$?", "FINAL_COMMIT_RC=$?", "MIN_TESTS=", "SKIP 面逐条相同",
             "PRECHECK FAILED", "bind98.log", "gate98.log", "closeout98.log"]


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    for old, new in SUBS:
        n = text.count(old)
        assert n >= 1, f"锚点读不到 ⇒ 一支都不写：{old[:60]!r} 命中 {n}"
        text = text.replace(old, new)
    assert "s97" not in text, "还有 s97 残留"
    assert "97.log" not in text, "日志基名还带着上一轮的数字"
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
