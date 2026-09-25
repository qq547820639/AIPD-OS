"""上一版交付物基线（第 28 片）：语义摘要必须「省得掉时间戳、省不掉结论」。

这一格要答的是第 27 片答不了的另一半：手里没有上一版清单时，
「没有变更单提到这个文件」既可能是**没改过**，也可能是**改了没提单**——
两者字节层面同形，所以只能记 `undetermined`。有了基线才能把它们分开。

比对不能直接用原始 sha256：本仓实测过（`docs/audit/ECO_RELEASE_COVERAGE_F-C6-ECO_2026-09-25.md`
§七第 7 条），同一份金样品连跑两次 DFM，报告体字节确定，**侧车不确定**——
它带一个 `generated_at`。按原始字节比就会把「又跑了一遍」报成工程变更。

所以有了「易变字段」这层，而**这层正是最容易造假绿的地方**：
一个能吞掉任意键的 ignore 列表 = 关掉判据的开关。本文件的用例两向都钉：
省时间戳 ⇒ 摘要不变；改一个真结论 ⇒ 摘要必须变；没声明过的键 ⇒ 一律算变。
"""
from __future__ import annotations

import json

from aipd_os.delivery_baseline import (
    BASELINE_KIND,
    artefact_index,
    diff_since_baseline,
    load_baseline_semantics,
    semantic_digest,
    write_baseline,
)


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


class TestSemanticDigest:
    def test_a_newer_timestamp_alone_is_not_a_change(self, tmp_path):
        """实测事实：侧车每次重新生成都会换 `generated_at` ⇒ 原始哈希必变。"""
        first = _write_json(tmp_path / "a.json", {"generated_at": "2026-09-25T07:13:29+00:00",
                                                 "ok": True})
        second = _write_json(tmp_path / "b.json", {"generated_at": "2026-09-26T09:00:00+00:00",
                                                   "ok": True})
        a, b = semantic_digest(first), semantic_digest(second)
        assert a["sha256"] != b["sha256"], "前提不成立就不是在测这件事"
        assert a["semantic_sha256"] == b["semantic_sha256"]
        assert a["volatile_dropped"] == ["/generated_at"]

    def test_changing_a_real_conclusion_moves_the_semantic_digest(self, tmp_path):
        """反证：易变字段只能省时间戳，省不掉结论。

        没有这一条，「易变」二字就是关掉判据的开关——随便改什么都能洗成没变。
        """
        first = _write_json(tmp_path / "a.json", {"generated_at": "t1",
                                                 "findings": [{"rule": "壁厚", "measured": 2.0}]})
        second = _write_json(tmp_path / "b.json", {"generated_at": "t2",
                                                  "findings": [{"rule": "壁厚",
                                                                "measured": 1.1}]})
        assert (semantic_digest(first)["semantic_sha256"]
                != semantic_digest(second)["semantic_sha256"])

    def test_key_order_does_not_count_as_a_change(self, tmp_path):
        first = _write_json(tmp_path / "a.json", {"x": 1, "y": 2})
        second = _write_json(tmp_path / "b.json", {"y": 2, "x": 1})
        assert (semantic_digest(first)["semantic_sha256"]
                == semantic_digest(second)["semantic_sha256"]), "键序不是内容"

    def test_nested_and_list_positions_are_reported_by_name(self, tmp_path):
        """剔了什么必须交出去：只报「省了两处」不够，得说省在哪。"""
        path = _write_json(tmp_path / "a.json", {"document": {"generated_at": "t"},
                                                 "runs": [{"accessed": "d1"}, {"x": 1}]})
        assert semantic_digest(path)["volatile_dropped"] == ["/document/generated_at",
                                                             "/runs[0]/accessed"]

    def test_an_undeclared_similar_key_is_never_dropped(self, tmp_path):
        """白名单按**整名**匹配：`created` / `generated_at_utc_x` 这种近似名一律算内容。"""
        first = _write_json(tmp_path / "a.json", {"created": "t1", "generated_at_utc_x": 1})
        second = _write_json(tmp_path / "b.json", {"created": "t2", "generated_at_utc_x": 2})
        a, b = semantic_digest(first), semantic_digest(second)
        assert a["volatile_dropped"] == []
        assert a["semantic_sha256"] != b["semantic_sha256"]

    def test_a_text_artifact_gets_no_ignores_at_all(self, tmp_path):
        """报告体（Markdown）没有可声明的字段名 ⇒ 语义摘要 = 原始哈希，不假装能省什么。"""
        path = tmp_path / "r.md"
        path.write_text("# 报告\n\n- 最小壁厚 2mm\n", encoding="utf-8")
        digest = semantic_digest(path)
        assert digest["sha256"] == digest["semantic_sha256"]
        assert digest["volatile_dropped"] == []
        other = tmp_path / "r2.md"
        other.write_text(path.read_text(encoding="utf-8") + "\n补一句\n", encoding="utf-8")
        assert semantic_digest(other)["semantic_sha256"] != digest["semantic_sha256"]


class TestDiff:
    def test_the_four_buckets_are_disjoint_and_total(self):
        current = {"a": "1", "b": "2", "c": "3", "d": "4"}
        baseline = {"a": "1", "b": "9", "d": "4", "e": "5"}
        since = diff_since_baseline(current, baseline)
        assert since["added"] == ["c"] and since["removed"] == ["e"]
        assert since["modified"] == ["b"] and since["unchanged"] == ["a", "d"]
        assert (len(since["added"]) + len(since["removed"]) + len(since["modified"])
                + len(since["unchanged"]) == len(set(current) | set(baseline))), \
            "四桶必须不重不漏，否则一条改动可以掉在两个桶之外"

    def test_an_unreadable_artifact_reads_as_changed_not_missing(self, tmp_path):
        """磁盘上读不到的交付物：语义摘要给空串 ⇒ 与基线不等 ⇒ 判「变了」。

        记成「看不见」会被读成「没变」，那是最坏的失效方向。
        """
        index = artefact_index({"gone.md": "a" * 64}, tmp_path)
        assert index["gone.md"]["unreadable"] is True
        assert index["gone.md"]["semantic_sha256"] == ""
        assert diff_since_baseline({"gone.md": index["gone.md"]["semantic_sha256"]},
                                   {"gone.md": "b" * 64})["modified"] == ["gone.md"]


class TestFileRoundTrip:
    def test_write_then_load_says_everything_is_unchanged(self, tmp_path):
        doc = tmp_path / "part.json"
        _write_json(doc, {"generated_at": "t1", "ok": True})
        md = tmp_path / "part.md"
        md.write_text("# 报告\n", encoding="utf-8")
        raw = {"part.json": semantic_digest(doc)["sha256"],
               "part.md": semantic_digest(md)["sha256"]}
        write_baseline(tmp_path / "base.json", raw, tmp_path, release="v1",
                       source_commit="abc")
        loaded = load_baseline_semantics(tmp_path / "base.json")
        again = {p: e["semantic_sha256"] for p, e in artefact_index(raw, tmp_path).items()}
        since = diff_since_baseline(again, loaded)
        assert since["unchanged"] == ["part.json", "part.md"]
        assert not (since["added"] or since["removed"] or since["modified"])

    def test_a_file_that_is_not_a_baseline_is_refused(self, tmp_path):
        """拿别的 JSON（比如 SOURCE_MANIFEST）当基线 ⇒ 拒，不静默读出空差集。"""
        path = _write_json(tmp_path / "wrong.json", {"files": []})
        try:
            load_baseline_semantics(path)
        except ValueError as exc:
            assert BASELINE_KIND in str(exc)
        else:
            raise AssertionError("kind 不对的 JSON 被当成基线用了")

    def test_a_missing_baseline_is_empty_not_an_error(self, tmp_path):
        assert load_baseline_semantics(tmp_path / "nope.json") == {}
