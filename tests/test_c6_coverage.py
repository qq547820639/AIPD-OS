"""C6 交付物覆盖度普查的常驻用例（`scripts/c6_coverage.py`）。

这张表回答的是「C6 那 15 项里，哪几项有生产者、哪几项只有校验方、哪几项压根没做」，
用途是**决定下一片做什么**——不然会一直在图纸上精雕，而 ICD / 装配维护 / ECR-ECO 零实现。

三件事必须常驻钉住：
1. **分母从契约文件现算**：改了 `references/production-cad-deliverables.md` 的那一行，
   本表必须红（要么映射缺项、要么留了旧项），不许悄悄停在旧口径。
2. **判据自己能红**：`--self-test` 的 7 条注入必须全被抓住。尺子不会红的绿不算证据。
3. **它是诊断档**：没被接进 `production_release_gate`，也不许接——普查读数今天就有 3 项
   零实现，挂成发布门禁等于让门永远红，反而没人看。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import c6_coverage as cov  # noqa: E402


def test_denominator_comes_from_the_contract_and_every_item_is_mapped():
    items = cov.c6_items(ROOT / cov.REFERENCE)
    assert items, "契约里那一行读不到东西"
    assert len(items) == len(set(items)), f"契约项重复：{items}"
    unmapped = [i for i in items if i not in cov.MAPPING]
    stale = sorted(set(cov.MAPPING) - set(items))
    assert not unmapped, f"契约要求但映射没有：{unmapped}"
    assert not stale, f"映射还在但契约已不要求：{stale}"


def test_contract_line_is_parsed_verbatim_not_retyped():
    """逐项名字必须与契约原文逐字一致——本片就被「总装/单件 STEP」多打一个空格抓过。"""
    text = (ROOT / cov.REFERENCE).read_text(encoding="utf-8")
    line = [one for one in text.splitlines() if one.startswith(cov.LINE_PREFIX)]
    assert len(line) == 1, line
    body = line[0][len(cov.LINE_PREFIX):].rstrip("。")
    for item in cov.MAPPING:
        assert item in body.split("、"), f"{item!r} 不是契约里的原文写法"


def test_census_is_self_consistent_today():
    report = cov.audit(ROOT)
    assert report["problems"] == [], report["problems"]
    assert report["ok"] is True


def test_verdict_rack_is_pinned_so_moves_are_deliberate():
    """档位数字是**棘轮**：想改动必须先说清哪一项进了哪一档（或退出）。

    2026-09-25 第 18 片后实测（由 `cov.audit` 现算，不是手抄）：15 项 =
    有生产者 12 / 只有校验方 2（DFM-DFA、版本与ECR-ECO）/ 零实现 1（ICD）。
    「装配/维护」由 absent 升 producer —— 只升装配那一半，维护指引仍无生产者，
    这句话写在映射的 note 里而不是靠档位表达，所以档位动之前先读 note。
    """
    report = cov.audit(ROOT)
    assert report["item_count"] == 15, report["item_count"]
    assert report["verdict_counts"] == {"producer": 12, "checker_only": 2,
                                        "absent": 1}, report["verdict_counts"]


def test_the_absent_items_are_the_ones_we_say_they_are():
    report = cov.audit(ROOT)
    absent = {r["item"] for r in report["rows"] if r["verdict"] == "absent"}
    assert absent == {"ICD"}, absent


def test_checker_only_items_have_no_src_producer():
    """「只有校验方」这档的定义要可核：列了 src/ 下的落点就不许停在这一档。"""
    for item, entry in cov.MAPPING.items():
        if entry["verdict"] == "checker_only":
            src = [p for p in entry["producers"] if p.startswith("src/")]
            assert not src, f"{item} 已被判成只有校验方，却列出产品侧生产者 {src}"


def test_injections_all_make_the_ruler_fire():
    """7 条注入必须全被抓——这条用例就是「尺子能红」的证据本身。"""
    assert cov._self_test(ROOT) == 0, "有注入没让判据开火，普查读数不可信"


def test_declared_but_unverifiable_rows_are_surfaced():
    """两栏皆空的能力行是**不可核验的声明**，必须被点名（今天有 5 行）。"""
    diag = cov.audit(ROOT)["diagnostics"]
    empty = diag["rows_with_no_implementation_and_no_test"]
    assert "cad.assembly_constraints" in empty, empty
    assert len(empty) >= 1, empty


def test_census_is_not_wired_into_the_release_gate():
    """诊断档就留在诊断档：门禁里出现 c6_coverage 就说明有人把它挂成了阻断项。"""
    gate = (ROOT / "scripts" / "production_release_gate.py").read_text("utf-8")
    assert "c6_coverage" not in gate, "把普查挂进发布门要先想清楚：今天它有 3 项零实现"


def test_cli_exit_code_and_json_payload(tmp_path):
    out = tmp_path / "c6.json"
    rc = cov.main(["--repo", str(ROOT), "--json", str(out)])
    assert rc == 0, "普查一致性判红，看 problems"
    payload = json.loads(out.read_text("utf-8"))
    assert payload["ok"] is True and payload["item_count"] == 15
    assert set(payload["verdict_counts"]) == {"producer", "checker_only", "absent"}
