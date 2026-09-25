"""DFM/DFA 分析生产者（capability ``cad.dfm_dfa``）。

这里钉的是三件事，每件都能机器核：

1. **事实是内核实测的**：壁厚、孔径/孔深、内圆角、同轴孔系、包络与体积——用例拿
   *已知形状*（0.6mm 板、Ø6 通孔、R2 圆角）去比对物理真值，不是比对快照。
2. **阈值必须带来处**：每条规则自带 `source`（URL + 访问日期 + 来处是哪一类 + 一句限定）。
   本仓口径的判据 `url` 留空且 `basis == "own_measure"`，绝不自称标准；把厂商给**甲特征**
   的数用到**乙特征**上，必须走 `borrowed_out_of_scope` 并指回甲那条（用例机器核对链路）。
3. **测不出来就说测不出来**：前提不成立记 `blind`，不折算成 pass；
   一次都没测出来的分析，读起来必须一眼看出是盲区。
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from aipd_os.cad.dfm import (
    RULES,
    analyze,
    generate_dfm_report,
    geometry_facts,
    material_is_plastic,
    measure_min_wall_thickness,
    rule_by_id,
)
from aipd_os.release_manifest import build_release_manifest

TENANT = "t"
PROJECT = "p"


def _plate(thickness=0.6, size=12.0, hole_diameter=2.0):
    import cadquery as cq

    wp = cq.Workplane("XY").box(size, size, thickness)
    if hole_diameter:
        wp = wp.faces(">Z").workplane().hole(hole_diameter)
    return wp.val().wrapped


def _block_with_hole():
    """20×20×10 板 + Ø6 通孔：孔壁到外侧面 7mm，是这片的最小「壁」。"""
    import cadquery as cq

    return cq.Workplane("XY").box(20, 20, 10).faces(">Z").workplane().hole(6).val().wrapped


def _filleted():
    """20×20×10 板 + 四条 R2 圆角（部分回转圆柱面），没有整孔。"""
    import cadquery as cq

    return cq.Workplane("XY").box(20, 20, 10).edges("|Y").fillet(2.0).val().wrapped


def _coaxial_blind_holes():
    """同一根 Z 轴上两个盲孔：顶面 Ø6 深 5（比值 0.83）、底面 Ø3 深 8（比值 2.67）。

    本机实测：这两个圆柱面的轴向分别是 +Z 与 -Z（取决于建模顺序），所以同轴判据
    必须按**无向直线**比，夹具就是照这一点挑的。
    """
    import cadquery as cq

    wp = cq.Workplane("XY").box(20, 20, 20).faces(">Z").workplane().circle(3.0).cutBlind(-5)
    wp = wp.faces("<Z").workplane().circle(1.5).cutBlind(-8)
    return wp.val().wrapped


class TestGeometryFactsAreMeasured:
    def test_through_hole_gives_radius_depth_and_ratio(self):
        facts = geometry_facts(_block_with_hole())
        hole = facts["holes"][0]
        assert hole["diameter_mm"] == pytest.approx(6.0, abs=1e-6)
        assert hole["depth_mm"] == pytest.approx(10.0, abs=1e-6)
        assert hole["depth_over_diameter"] == pytest.approx(10.0 / 6.0, abs=1e-6)

    def test_fillet_is_not_counted_as_a_hole(self):
        """圆角也是圆柱面。整孔的判据是**角向张角满一周**，不是「它是个圆柱」。"""
        facts = geometry_facts(_filleted())
        assert facts["holes"] == []
        assert facts["inside_radius_mm"] == pytest.approx(2.0, abs=1e-6)
        assert facts["partial_cylinder_count"] == 4

    def test_min_wall_thickness_of_a_thin_plate_is_the_plate(self):
        measured = measure_min_wall_thickness(_plate(thickness=0.6, size=12.0))
        assert measured["min_mm"] == pytest.approx(0.6, abs=1e-6)

    def test_min_wall_thickness_of_a_drilled_block_is_the_hole_to_face_wall(self):
        """Ø6 孔在 20 宽板里 ⇒ 孔壁到外侧面 20/2-3 = 7mm，不是 10mm（板厚）。"""
        measured = measure_min_wall_thickness(_block_with_hole())
        assert measured["min_mm"] == pytest.approx(7.0, abs=1e-3)

    def test_a_shell_without_thickness_blinds_the_wall_rule_instead_of_reporting_zero(self):
        """只有一个平面的壳量不出壁厚：`min_mm` 必须是 None，不是 0.0 也不是「合格」。

        这条同时钉住 odd_hit_rays 的含义——每条射线只命中一次（进不出），
        配对失败就是没量到，而不是量到 0。
        """
        import cadquery as cq

        sheet = cq.Workplane("XY").box(10, 10, 1).faces(">Z").val().wrapped
        measured = measure_min_wall_thickness(sheet)
        assert measured["min_mm"] is None
        assert measured["rays_with_hits"] > 0 and measured["odd_hit_rays"] > 0
        report = analyze(sheet, material="6061-T6")
        reasons = {b["rule"]: b["reason"] for b in report["blind"]}
        assert reasons.get("wall_thickness_metal") == "no_probeable_planar_face", reasons

    def test_ray_sampling_reports_how_much_it_saw(self):
        """只报最小值不报采样数，读者就没法判断这个最小值是测出来的还是漏出来的。"""
        measured = measure_min_wall_thickness(_plate(thickness=0.6, size=12.0))
        assert measured["rays_with_hits"] > 0
        assert measured["spacing_mm"] == pytest.approx(0.5)
        assert measured["odd_hit_rays"] >= 0          # 切线/相切命中如实计数

    def test_coaxial_holes_group_by_axis_not_by_name(self):
        facts = geometry_facts(_coaxial_blind_holes())
        assert len(facts["holes"]) == 2
        assert sorted(h["diameter_mm"] for h in facts["holes"]) == [3.0, 6.0]
        groups = facts["coaxial_groups"]
        assert len(groups) == 1 and groups[0]["hole_count"] == 2
        assert groups[0]["axis"] == pytest.approx([0.0, 0.0, 1.0], abs=1e-6)

    def test_envelope_and_volume_are_real_numbers(self):
        facts = geometry_facts(_block_with_hole())
        assert facts["envelope_mm"] == pytest.approx([20.0, 20.0, 10.0], abs=1e-6)
        # 20*20*10 - π*3²*10 = 4000 - 282.7433
        assert facts["volume_mm3"] == pytest.approx(4000 - math.pi * 9 * 10, abs=1e-3)

    def test_an_empty_shape_is_refused_not_reported_as_zero_facts(self):
        """空 compound 读不出面：抛错，而不是交出一份「孔 0 个、壁厚无」的分析。"""
        from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound

        empty = TopoDS_Compound()
        TopoDS_Builder().MakeCompound(empty)
        with pytest.raises(ValueError):
            geometry_facts(empty)


class TestRulebookCarriesItsSources:
    def test_every_rule_declares_where_its_number_came_from(self):
        for rule in RULES:
            src = rule["source"]
            assert set(src) == ({"url", "accessed", "kind", "note"}
                                | ({"stated_for"}
                                   if rule["basis"] == "borrowed_out_of_scope" else set())), \
                rule["id"]
            assert src["kind"] == rule["basis"], rule["id"]
            if rule["basis"] == "own_measure":
                assert src["url"] == "", f"{rule['id']}：本仓口径不许挂 URL"
                assert "本仓口径" in src["note"], rule["id"]
            else:
                assert src["url"].startswith("https://"), rule["id"]
                assert src["accessed"] == "2026-09-25", rule["id"]

    def test_a_borrowed_number_points_back_at_the_rule_it_was_stated_for(self):
        """「挂个 URL 就有出处」不算出处：借来的数必须指回表内真被页撑着的那条。

        链路四格全核：被借的那条自己是厂商页的数、limit 一字不差、同一页，
        而且这条必须自认是外推（note 里写着）并只判 advisory ——外推不能阻断发布。
        """
        borrowed = [r for r in RULES if r["basis"] == "borrowed_out_of_scope"]
        assert borrowed, "表里已没有借数规则：要么删了它（连带删这条用例），要么改口径"
        for rule in borrowed:
            donor = rule_by_id(rule["source"]["stated_for"])
            assert donor["id"] != rule["id"], f"{rule['id']}：自己借自己不叫来处"
            assert donor["basis"] == "vendor_capability", rule["id"]
            assert donor["limit"] == rule["limit"], rule["id"]
            assert donor["source"]["url"] == rule["source"]["url"], rule["id"]
            assert "外推" in rule["source"]["note"], rule["id"]
            assert rule["severity"] == "advisory", rule["id"]

    def test_sourced_thresholds_are_the_pages_own_numbers(self):
        """阈值不是可以随手改的：改数就得同时改来处，否则这条红。"""
        limits = {r["id"]: r.get("limit") for r in RULES}
        assert limits["wall_thickness_metal"] == 0.8      # HLH Rapid（Xometry 独立给 0.794）
        assert limits["wall_thickness_plastic"] == 1.5    # HLH Rapid / Xometry 同值
        assert limits["hole_depth_to_diameter"] == 4.0    # Xometry（保守侧，上限 10 另列）
        assert limits["gun_drill_required"] == 10.0       # Xometry
        assert limits["tolerance_below_achievable"] == 0.025  # Xometry 标称可达
        # 内圆角**没有**可引用的绝对阈值来处（厂商给的是「≥ 腔深 1/3」这个比值），
        # 所以那条只报事实、不设 limit —— 有 limit 就是编数。
        assert limits["inside_radius_reported"] is None
        # 孔周留肉同理：本轮检索（HLH Rapid / Xometry / 3ERP 转述的 ISO 2768）都没有
        # 机加件的孔边距规则。这两格钉的是「借的是壁厚那条数」，改数=改借的来处。
        assert limits["hole_land_reported"] is None
        assert limits["hole_land_metal"] == limits["wall_thickness_metal"]
        assert limits["hole_land_plastic"] == limits["wall_thickness_plastic"]

    def test_rule_id_set_is_a_ratchet(self):
        assert {r["id"] for r in RULES} == {
            "wall_thickness_metal", "wall_thickness_plastic", "hole_depth_to_diameter",
            "gun_drill_required", "inside_radius_reported",
            "tolerance_below_achievable", "same_axis_hole_count",
            "hole_land_reported", "hole_land_metal", "hole_land_plastic"}

    def test_a_borrowed_rule_is_refused_for_each_way_its_link_can_be_wrong(self):
        """运行时逐格拦，且**每种坏法各有一句话**：只要求「抛 ValueError」会让
        一道检查被另一道顶替而无人察觉（实测：删掉 donor 检查后仍被 limit 检查拦住，
        用例照样绿）。"""
        shape = _plate(thickness=2.0, size=12.0, hole_diameter=2.0)
        borrower = next(r for r in RULES if r["basis"] == "borrowed_out_of_scope")
        source = borrower["source"]
        cases = [
            ({k: v for k, v in source.items() if k != "stated_for"}, "stated_for"),
            (dict(source, stated_for="inside_radius_reported"), "不是页子上的数"),
            (dict(source, url="https://xometry.hk/en/industry-standards-in-cnc-machining/"),
             "不是同一页"),
        ]
        for bad_source, message in cases:
            with pytest.raises(ValueError, match=message):
                analyze(shape, material="6061-T6",
                        rules=[dict(borrower, source=bad_source)])
        for bad_limit in (0.3, 0.81):
            with pytest.raises(ValueError, match="limit 却写成"):
                analyze(shape, material="6061-T6", rules=[dict(borrower, limit=bad_limit)])

    def test_a_rule_calling_itself_own_measure_can_not_carry_a_url(self):
        """自称「本仓口径」却挂着厂商页：那是拿别人的页给自己造的数撑腰，运行时拒。"""
        shape = _plate(thickness=2.0, size=12.0, hole_diameter=2.0)
        liar = dict(rule_by_id("hole_land_reported"),
                    source=dict(rule_by_id("hole_land_reported")["source"],
                                url="https://hlhrapid.com/knowledge/design-guide-cnc-machining/"))
        with pytest.raises(ValueError, match="URL"):
            analyze(shape, material="6061-T6", rules=[liar])

    def test_hole_to_face_wall_is_measured_not_the_plate_thickness(self):
        """这条是判据的物理正确性：孔壁到外侧面 7mm，比板厚 10mm 更该被 DFM 关心。"""
        report = analyze(_block_with_hole(), material="6061-T6")
        assert report["facts"]["min_wall_thickness_mm"] == pytest.approx(7.0, abs=1e-3)
        verdicts = {f["rule"]: f["verdict"] for f in report["findings"]}
        assert verdicts["wall_thickness_metal"] == "pass"

    def test_a_rule_can_not_be_added_without_a_source(self):
        with pytest.raises(ValueError, match="source"):
            analyze(_block_with_hole(), rules=[{"id": "ad_hoc", "measure": "facts.holes",
                                                "op": ">", "limit": 999.0, "unit": "个"}])

    def test_a_rule_whose_basis_disagrees_with_its_source_is_refused(self):
        """挂厂商的数却自称标准（或反过来）——两处不一致必须当场拒。"""
        bad = dict(RULES[0], basis="standard_paraphrase")
        with pytest.raises(ValueError, match="kind"):
            analyze(_block_with_hole(), rules=[bad])


class TestFindingsAndBlindSpots:
    def test_metal_thin_wall_fires_advisory(self):
        report = analyze(_plate(thickness=0.4, size=12.0, hole_diameter=0),
                         material="6061-T6")
        fired = [f for f in report["findings"] if f["rule"] == "wall_thickness_metal"]
        assert fired and fired[0]["verdict"] == "flag"
        assert fired[0]["value"] == pytest.approx(0.4, abs=1e-6)
        assert fired[0]["severity"] == "advisory"

    def test_plastic_rule_uses_the_plastic_line_not_the_metal_one(self):
        """1.0mm 壁厚：按金属线（0.8）是合格，按塑料线（1.5）是问题——两档不许互相顶。"""
        plastic = analyze(_plate(thickness=1.0, size=12.0, hole_diameter=0), material="ABS")
        by_rule = {f["rule"]: f["verdict"] for f in plastic["findings"]}
        assert by_rule["wall_thickness_plastic"] == "flag"
        assert "wall_thickness_metal" not in by_rule, "材料是塑料，金属那条不该参与判定"

    def test_unknown_material_blinds_both_wall_rules(self):
        report = analyze(_plate(thickness=1.0, size=12.0, hole_diameter=0),
                         material="未登记合金-7")
        blind = {b["rule"] for b in report["blind"]}
        assert {"wall_thickness_metal", "wall_thickness_plastic"} <= blind
        assert all(b["reason"] == "material_class_unknown" for b in report["blind"]
                   if b["rule"].startswith("wall_thickness"))
        verdicts = {f["rule"] for f in report["findings"]}
        assert "wall_thickness_metal" not in verdicts

    def test_deep_hole_ratio_and_gun_drill_hold(self):
        import cadquery as cq

        wp = cq.Workplane("XY").box(20, 20, 25).faces(">Z").workplane() \
            .circle(1.0).cutBlind(-24)                       # Ø2 深 24 ⇒ 比值 12
        report = analyze(wp.val().wrapped, material="6061-T6")
        hits = {f["rule"]: f for f in report["findings"]}
        assert hits["gun_drill_required"]["verdict"] == "hold"
        assert hits["hole_depth_to_diameter"]["verdict"] == "flag"
        # 实测比值要跟着结论走：读者能复核「12 倍」这个数是量出来的不是抄的
        assert hits["hole_depth_to_diameter"]["value"] == pytest.approx(12.0, abs=0.01)
        assert hits["hole_depth_to_diameter"]["measured"] == "hole \u00d82 \u00d7 深 24"

    def test_declared_tolerance_tighter_than_achievable_holds(self):
        report = analyze(_block_with_hole(), material="6061-T6",
                         spec={"features": [{"feature": "TOP.hole_0",
                                             "tolerance": {"upper": 0.01, "lower": -0.01}}]})
        hit = [f for f in report["findings"] if f["rule"] == "tolerance_below_achievable"]
        assert hit and hit[0]["verdict"] == "hold"
        assert hit[0]["measured"] == "TOP.hole_0"

    def test_loose_declared_tolerance_passes_and_absence_blinds(self):
        loose = analyze(_block_with_hole(), spec={"features": [
            {"feature": "TOP.hole_0", "tolerance": {"upper": 0.1, "lower": -0.1}}]})
        assert [f["verdict"] for f in loose["findings"]
                if f["rule"] == "tolerance_below_achievable"] == ["pass"]
        none = analyze(_block_with_hole())
        blind = {b["rule"] for b in none["blind"]}
        assert "tolerance_below_achievable" in blind

    def test_no_holes_blinds_the_hole_rules_instead_of_passing_them(self):
        report = analyze(_filleted(), material="6061-T6")
        blind = {b["rule"] for b in report["blind"]}
        assert {"hole_depth_to_diameter", "gun_drill_required", "same_axis_hole_count"} <= blind
        assert not [f for f in report["findings"] if f["rule"] == "hole_depth_to_diameter"]

    def test_inside_radius_is_reported_not_judged(self):
        """厂商给的圆角建议是「≥ 腔深 1/3」这个**比值**，本仓量不出可比的腔深，
        所以那条只报实测半径、不判红——编一个绝对阈值就是假装标准。"""
        report = analyze(_filleted(), material="6061-T6")
        hit = [f for f in report["findings"] if f["rule"] == "inside_radius_reported"]
        assert hit and hit[0]["verdict"] == "info" and hit[0]["limit"] is None
        assert hit[0]["value"] == pytest.approx(2.0, abs=1e-6)
        assert hit[0]["basis"] == "own_measure"

    def test_analysis_exposes_what_it_did_not_look_at(self):
        report = analyze(_block_with_hole(), material="6061-T6")
        assert report["not_covered"] == [
            "DFA 装配力与紧固顺序", "模具侧抽芯与脱模方向", "铸造圆角与收缩率",
            "热变形/振动的 CAE 仿真", "工序工时与加工成本"]


class TestMaterialClassification:
    def test_common_names(self):
        assert material_is_plastic("ABS") is True
        assert material_is_plastic("6061-T6") is False
        assert material_is_plastic("阳极氧化铝") is False
        assert material_is_plastic("尼龙 PA66") is True

    def test_empty_or_unknown_is_not_silently_a_class(self):
        for value in (None, "", "   ", "碳纤维预浸料"):
            assert material_is_plastic(value) is None, value


class TestCliSurface:
    def test_cli_writes_report_and_sidecar(self, tmp_path):
        from aipd_os.cli.main import main

        step = tmp_path / "bracket.step"
        import cadquery as cq

        cq.exporters.export(cq.Workplane("XY").box(20, 20, 10).faces(">Z")
                            .workplane().hole(6), str(step))
        out = tmp_path / "dfm.md"
        rc = main(["drawing", "dfm", "--step", str(step), "--part", "BR-1",
                   "--out", str(out), "--material", "6061-T6"])
        assert rc == 0, rc
        assert out.is_file()
        side = json.loads((tmp_path / "dfm.md.evidence.json").read_text(encoding="utf-8"))
        assert side["document"] == "dfm_report"
        assert side["facts"]["min_wall_thickness_mm"] == pytest.approx(7.0, abs=1e-3)

    def test_cli_missing_step_is_rc2(self, tmp_path):
        from aipd_os.cli.main import main

        rc = main(["drawing", "dfm", "--step", str(tmp_path / "nope.step"),
                   "--part", "BR-1", "--out", str(tmp_path / "d.md")])
        assert rc == 2

    def test_cli_exit4_when_a_hold_finding_exists(self, tmp_path):
        import cadquery as cq

        from aipd_os.cli.main import main

        step = tmp_path / "deep.step"
        cq.exporters.export(cq.Workplane("XY").box(20, 20, 25).faces(">Z")
                            .workplane().circle(1.0).cutBlind(-24), str(step))
        rc = main(["drawing", "dfm", "--step", str(step), "--part", "DP-1",
                   "--out", str(tmp_path / "d.md"), "--material", "6061-T6"])
        assert rc == 4, rc


class TestReleaseManifestSeesTheAnalysis:
    def _report(self, tmp_path, shape_builder=_block_with_hole):
        from aipd_os.cad.dfm import generate_dfm_report

        return generate_dfm_report(tmp_path / "dfm.md", model=shape_builder(),
                                    part_name="BR-1", material="6061-T6")

    def _db(self, tmp_path):
        from aipd_os.product_truth.store import ProductTruthStore

        db = tmp_path / "state.db"
        ProductTruthStore(str(db), tenant_id=TENANT, project_id=PROJECT)
        return db

    def _doc(self, tmp_path, report_path, db):
        out = tmp_path / "release.json"
        build_release_manifest(db_path=db, tenant_id=TENANT, project_id=PROJECT,
                               dfm_doc=report_path, out_path=out)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_key_present_with_hash(self, tmp_path):
        report = self._report(tmp_path)
        doc = self._doc(tmp_path, Path(report["document_path"]), self._db(tmp_path))
        ref = doc["dfm_dfa"]
        assert ref["sha256"] == hashlib.sha256(
            Path(report["document_path"]).read_bytes()).hexdigest()
        assert doc["dfm_summary"]["hold_count"] == 0
        assert doc["dfm_summary"]["blind_rule_count"] >= 1

    def test_hold_findings_block_readiness(self, tmp_path):
        import cadquery as cq

        deep = cq.Workplane("XY").box(20, 20, 25).faces(">Z").workplane() \
            .circle(1.0).cutBlind(-24).val().wrapped
        report = self._report(tmp_path, lambda: deep)
        doc = self._doc(tmp_path, Path(report["document_path"]), self._db(tmp_path))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "dfm_hold_findings" in kinds, kinds
        one = [i for i in doc["issues"] if i["kind"] == "dfm_hold_findings"][0]
        assert one["blocking"] is True and "gun_drill_required" in one["detail"]

    def test_missing_sidecar_is_blocking(self, tmp_path):
        report = self._report(tmp_path)
        (tmp_path / "dfm.md.evidence.json").unlink()
        doc = self._doc(tmp_path, Path(report["document_path"]), self._db(tmp_path))
        assert "dfm_evidence_missing" in [i["kind"] for i in doc["issues"]]

    def test_advisory_findings_are_reported_but_do_not_block(self, tmp_path):
        thin = _plate(thickness=0.4, size=12.0, hole_diameter=0)
        report = self._report(tmp_path, lambda: thin)
        doc = self._doc(tmp_path, Path(report["document_path"]), self._db(tmp_path))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "dfm_advisory_findings" in kinds
        assert all(not i["blocking"] for i in doc["issues"]
                   if i["kind"] == "dfm_advisory_findings")

    def test_no_analysis_writes_no_key(self, tmp_path):
        doc = self._doc(tmp_path, None, self._db(tmp_path))
        assert "dfm_dfa" not in doc and "dfm_summary" not in doc

    def test_an_all_blind_analysis_is_visible_not_a_green_pass(self, tmp_path):
        """一条都没判成：不阻断就绪（没证过的事不冤枉人），但必须看得见是盲区。"""
        plain = _plate(thickness=2.0, size=12.0, hole_diameter=0)
        report = generate_dfm_report(tmp_path / "blind.md", model=plain,
                                     part_name="PL-1", material=None)
        assert report["counts"]["measured"] == 0 and report["counts"]["blind"] >= 5
        doc = self._doc(tmp_path, Path(report["document_path"]), self._db(tmp_path))
        one = [i for i in doc["issues"] if i["kind"] == "dfm_unmeasured"]
        assert one and one[0]["blocking"] is False, [i["kind"] for i in doc["issues"]]
        assert doc["dfm_summary"]["measured_rule_count"] == 0
