"""CLI 命令面真调棘轮（F-CLI-COV 第 39 片）。

`scripts/command_surface_census.py` 把「这条命令的 CLI 入口在常驻测试里走过没有」
从子串匹配换成 AST 读调用形态之后，读数变了样（全部可复算）：

- 旧探针报 **19 条未测**，其中 **15 条其实真调过**：`main(["drawing", "dfm", ...])`
  是两个相邻字符串常量，子串 `"drawing dfm"` 匹配不上；`eco` 四条走的是
  `main(["eco", *argv, ...])` 这种转发器，旧探针更看不见。
- 旧探针算成已测的 47 条里有 **7 条零证据**：`from ezdxf import recover` 顶了
  `recover`、dict 键 `"version"` 顶了 `version`、`test_new_commands_registered` 里那张
  名字清单顶了 `cad preflight`、`owner_dashboard`/`onboarding`/`def _reset()` 顶了
  `dashboard`/`onboard`/`reset`、`ui` 撞在 `builtin`/`build` 中间。另有 6 条**判对但理由错**
  （`cad build`/`package`/`resume`/`test` 只被别名走过、`doctor` 只被直接调处理函数走过、
  `outbox drain` 调的是共用处理函数）。两头同时错，47/66 这个总数还看着合理——
  这正是「量具读数可信度」和「代码覆盖率」被混为一谈的代价。

这里钉的是**双向棘轮**：低于 `cli` 档的集合必须与下面的登记完全相等——

- 注册了新命令却没有 argv 位用例 ⇒ 红（不许顺手把它加进基线了事）；
- 登记里的命令补上了真调用 ⇒ 也红，必须把那一格从登记里删掉（记录只减不增）；
- 档位自己变了（`none` → `handler` 这种"看着像进步"的漂移）同样红。

**第 40 片把登记清空了**：当时在册的 17 条全部补成了
`tests/test_cli_public_surface.py` 里的 `main([...])` 真调用，读数变成 cli 66 / 其余 0。
空登记不等于没有牙齿——新命令一注册就落进「未登记的缺口」那一侧；而"闭掉的那 17 条
现在还闭着"改由 `CLOSED` 这张账钉住：每条都要能指回新用例文件里的 argv 证据，
把那个文件删了或改回直接调处理函数，这里就红。

`outbox drain` / `outbox review` 停在 `handler_ambiguous`：测试直接调的是
`cmd_outbox`，而这一条处理函数被两条命令共用，分不清是哪个 verb 被走过——
按「看不见不等于通过，也不等于违规」单列一档，而不是折算进任一侧。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import command_surface_census as census  # noqa: E402

# 低于 cli 档的登记：第 40 片起为空。加命令不许进这张表，只能补真调用。
BASELINE: dict[str, str] = {}

# 第 40 片闭合的账：命令 → 必须出现在其证据里的用例文件名。
# 空 BASELINE 会留下"没有东西可断言"的空转面，这张账就是那侧的替代牙齿。
CLOSED = (
    "cad build", "cad preflight", "dashboard", "doctor", "onboard", "operate",
    "outbox drain", "outbox review", "package", "product gate", "product show",
    "recover", "reset", "resume", "test", "ui", "version",
)
CLOSURE_EVIDENCE = "test_cli_public_surface"


@pytest.fixture(scope="module")
def report() -> dict:
    rep = census.audit(ROOT)
    assert rep["ok"], f"读数不可信：{rep['problems']}"
    return rep


def test_below_cli_set_matches_the_record_exactly(report) -> None:
    """双向：漏登记（新命令没用例）与多登记（补了用例没删格）都要红。"""
    actual = {c for c, t in report["tiers"].items() if t != census.TIER_CLI}
    recorded = set(BASELINE)
    assert actual == recorded, (
        f"未登记的缺口（新注册命令没有 argv 位用例）：{sorted(actual - recorded)}；"
        f"已补真调用却没删格：{sorted(recorded - actual)}")
    assert len(recorded) == 0, (
        f"登记在册的缺口已在第 40 片清零，重新往基线里加格子等于放行新缺口：{sorted(recorded)}")


def test_each_recorded_tier_is_the_measured_one(report) -> None:
    """登记非空时逐条核档位（当前为空 ⇒ 由下一条接住这一面，别留空循环）。"""
    drifted = {c: (t, BASELINE[c]) for c, t in report["tiers"].items()
               if c in BASELINE and t != BASELINE[c]}
    assert not drifted, f"这些命令的档位与登记不符（左＝实测，右＝登记）：{drifted}"


def test_closed_register_still_points_at_real_argv_evidence(report) -> None:
    """第 40 片闭掉的 17 条必须仍指得回那批 argv 位用例。

    登记清空后，"档位漂移"这一面在 BASELINE 上是空循环；这条把它接到实据上：
    用例文件被删、或改成直接调处理函数，这里就红。
    """
    assert len(CLOSED) == 17, "闭合账本身就是分母，不许悄悄增删"
    weak = [c for c in CLOSED
            if report["tiers"].get(c) != census.TIER_CLI
            or not any(CLOSURE_EVIDENCE in e for e in report["evidence"].get(c, []))]
    assert not weak, (
        f"这些命令的 CLI 面证据又断了（应能在 {CLOSURE_EVIDENCE} 里找到 argv 位调用）：{weak}")


def test_tiers_partition_the_denominator(report) -> None:
    """Σ 档位 == 分母：每条注册命令恰好落一档，不重不漏。"""
    from aipd_os.cli.commands import COMMAND_FUNCS

    tiers = report["tiers"]
    assert set(tiers) == set(COMMAND_FUNCS)
    assert report["denominator"] == len(COMMAND_FUNCS)
    total = sum(len(v) for v in report["buckets"].values())
    # 绝对数是**漂移报警**（第 45 片加 `truth rework` 时 66 → 67，
    # 第 51 片加 `truth drift` 时 67 → 68，第 54 片加 `truth sweep` 时 68 → 69）：
    # 注册面自己变大是合法事件，被上面两行等式接住；
    # 这里钉的是"档位合计必须等于这个已知分母"。
    assert total == report["denominator"] == 69, (
        f"分母漂了：档位合计 {total}，注册 {report['denominator']}")


def test_reading_is_not_vacuous(report) -> None:
    """探针得真读到位语料，且 cli 档非空——空读数不能算绿。"""
    assert report["files_read"] > 100, f"只读了 {report['files_read']} 个测试文件"
    assert len(report["buckets"][census.TIER_CLI]) == 69, (
        f"cli 档读数漂到 {len(report['buckets'][census.TIER_CLI])}（第 40 片起为满覆盖）")
    assert report["parse_failures"] == []


def test_empty_corpus_is_reported_as_unreadable(tmp_path) -> None:
    """一册测试都没读到 ⇒ 读数不可信：既不折成通过，也不折成违规。"""
    (tmp_path / "tests").mkdir()
    rep = census.audit(tmp_path)
    assert not rep["ok"]
    assert any("empty_corpus" in p for p in rep["problems"]), rep["problems"]
    assert census.main(["--repo", str(tmp_path)]) == 4


def test_instrument_never_counts_its_own_files(report) -> None:
    """量具自身与它的用例不许当证据：按字面量反查的探针会把自己算进分母。"""
    hits = [f"{c}: {e}" for c, ev in report["evidence"].items() for e in ev
            if any(name[:-3] in e for name in census.EXCLUDE_TESTS)]
    assert not hits, f"证据里出现了量具自身：{hits}"


def test_census_self_test_runs_and_is_green() -> None:
    """常驻读者必须真的 spawn 它（只被文本提到不算跑过）。"""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "command_surface_census.py"),
         "--self-test"],
        capture_output=True, text=True, cwd=ROOT, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条注入都被抓住" in proc.stdout, proc.stdout


def test_json_artifact_agrees_with_in_process_reading(tmp_path, report) -> None:
    """写盘读数与内存读数同源：产物路径本身就是判据的一部分。"""
    out = tmp_path / "census.json"
    assert census.main(["--repo", str(ROOT), "--json", str(out)]) == 0
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["tiers"] == report["tiers"]
    assert on_disk["below_cli"] == report["below_cli"]


def test_alias_tier_comes_from_the_contract_not_a_hand_copy(report) -> None:
    """别名↔真名由 CLI 契约的 replacement 派生：抄一份就会与契约漂开。"""
    from aipd_os.cli.command_contract import CommandStatus, get_all_commands

    alias_of = {e.name: e.replacement for e in get_all_commands()
                if e.status is CommandStatus.DEPRECATED and e.replacement}
    assert alias_of, "契约里没有 deprecated→replacement，别名档就成了无源之水"
    for cmd, tier in report["tiers"].items():
        if tier == census.TIER_ALIAS:
            assert cmd in alias_of.values(), f"{cmd} 被记成别名档却无别名来源"
