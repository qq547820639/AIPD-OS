"""依赖许可证门禁的常驻牙（F-DEP-LICENSE 第 92 片）。

分五组：① 量具必须被真的 spawn；② 真仓库上分母非空且**退码由判据自己决定**；
③ 注入的两极（看得见但不合规 ⇒ 红；裁对了 ⇒ 绿）；④ 两处信号阶梯的形状，
其中"只有泛化 classifier + 具体 License 字段"那一格就是本面立起的真原因（casadi）；
⑤ 第 93 片加的**正文面**与重复记录对账（`body_face` / `package_license` / `bodies_of`），
其中"同一份 AGPL 文字在标题位判红、在键值行只记档"那一极是本面的形状关键。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dependency_license_gate as dlg  # noqa: E402

TOOL = ROOT / "scripts" / "dependency_license_gate.py"


def _spawn(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)


def _tree(tmp: Path, deps: list[str]) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "pyproject.toml").write_text(
        "[project]\ndependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]\n",
        encoding="utf-8")
    return tmp


def _rec(name: str, expr: str = "", fields: list[str] | None = None,
         cls: list[str] | None = None, requires: list[str] | None = None) -> dict[str, Any]:
    """`scripts/` 不在 mypy 的 `files` 里 ⇒ 导入进来的构造器是无类型的，落一次注解。"""
    rec: dict[str, Any] = dlg._rec(name, expr=expr, fields=fields, cls=cls, requires=requires)
    return rec


def test_instrument_self_test_is_actually_spawned_and_green() -> None:
    """没有这一条，`--self-test` 与"没有自测"在读数上不可区分（第 60 片的孤儿门禁）。"""
    proc = _spawn("--self-test")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条合成读数全部对上" in proc.stdout, proc.stdout


def test_real_repo_face_is_live_and_return_code_follows_the_verdict() -> None:
    rep = dlg.audit(ROOT)
    c = rep["corpus"]
    assert not rep["problems"], rep["problems"]
    assert c["declared_roots"] >= 10, c
    assert c["closure"] >= 40, c
    assert c["inspected"] >= 35, c
    assert rep["buckets"]["allowed"] >= 30, rep["buckets"]
    # 退码不许钉成绝对数：钉"退码 == 判据自己的结论"，覆盖面变化时它仍成立
    rc = _spawn("--repo", str(ROOT)).returncode
    assert rc == (0 if rep["ok"] else 4), (rc, rep["ok"], rep["violations"])
    assert rep["corpus"]["skipped_optional_requires"] > 100, rep["corpus"]


def test_casadi_stays_red_until_a_human_adjudicates_it() -> None:
    """真仓库的**活原告**：`cadquery ← casadi`，上游自述 LGPL-3.0-or-later。

    这条用例钉的是"它今天还没被拍板"，不是"它永远不合规"。
    要让它转绿：把 `docs/audit/DEPENDENCY_LICENSE_LEDGER.json` 里那条 `decision`
    改成 `accepted`，并按 `docs/security/dependency-license-review.md` §二 补齐三条分发义务
    ——届时这条用例**必须被改**（改成断言"已 accepted 且台账理由非空"），
    不许用放宽判据的方式糊过去。
    """
    rep = dlg.audit(ROOT)
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证未裁定", "casadi") in fired, (fired, rep["buckets"])
    row = next(r for r in rep["rows"] if r["package"] == "casadi")
    assert row["licenses"] == ["lgpl-3.0-or-later"], row
    assert row["via"] == "cadquery", row
    assert dlg.main(["--repo", str(ROOT)]) == 4, fired


def test_generic_classifier_alone_is_invisible_not_compliant(tmp_path: Path) -> None:
    """`License :: OSI Approved`（泛化）不算已标注；同一包的 `License` 字段才是答案。

    两极：只给泛化 classifier ⇒ 判「看不见」；补上具体的 `License` 字段 ⇒ 按字段判档。
    少了第一极，"信号阶梯"会退化成"classifier 优先"，casadi 那一格就会被读成未标注而放过。
    """
    tree = _tree(tmp_path / "t1", ["zzz-only-osi"])
    idx = {"zzz-only-osi": [_rec("zzz-only-osi", cls=["OSI Approved"])]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    assert ("依赖许可证看不见", "zzz-only-osi") in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]

    idx2 = {"zzz-only-osi": [_rec("zzz-only-osi", cls=["OSI Approved"],
                                  fields=["GNU Lesser General Public License v3 or later "
                                          "(LGPLv3+)"])]}
    rep2 = dlg.audit(tree, idx=idx2, declared_not_installed={})
    got2 = {(v["field"], v["doc"]) for v in rep2["violations"]}
    assert ("依赖许可证看不见", "zzz-only-osi") not in got2, got2
    assert ("依赖许可证未裁定", "zzz-only-osi") in got2, got2
    assert dlg._canon("Zzz_Only-OSI") == "zzz-only-osi"


def test_ledger_can_clear_a_review_package_only_with_a_matching_license(tmp_path: Path) -> None:
    """台账要**逐字对上现读的许可证串**且 `decision=accepted` 才放行；差一个字就判「该撤」。"""
    tree = _tree(tmp_path / "t2", ["zzz-lgpl"])
    led = tree / dlg.POLICY_REL
    led.parent.mkdir(parents=True)
    rec = {"zzz-lgpl": [_rec("zzz-lgpl", fields=["GNU Lesser General Public License v3 or later "
                                                 "(LGPLv3+)"])]}

    def write(lic: str, decision: str) -> None:
        led.write_text(json.dumps({"entries": [{"package": "zzz-lgpl", "license": lic,
                                                "decision": decision, "why": "合成裁决"}]},
                                  ensure_ascii=False), encoding="utf-8")

    write("LGPL-3.0-or-later", "accepted")
    rep = dlg.audit(tree, idx=rec, declared_not_installed={})
    assert not rep["violations"], rep["violations"]
    assert rep["buckets"]["adjudicated"] == 1, rep["buckets"]

    write("LGPL-2.1", "accepted")             # 上游换许可证 / 抄错 ⇒ 该撤
    rep2 = dlg.audit(tree, idx=rec, declared_not_installed={})
    assert ("台账该撤", "zzz-lgpl") in {(v["field"], v["doc"]) for v in rep2["violations"]}, \
        rep2["violations"]

    write("LGPL-3.0-or-later", "needs-review")
    rep3 = dlg.audit(tree, idx=rec, declared_not_installed={})
    assert ("依赖许可证未裁定", "zzz-lgpl") in {
        (v["field"], v["doc"]) for v in rep3["violations"]}, rep3["violations"]
    assert rep3["corpus"]["ledger_size"] == 1, rep3["corpus"]


def test_or_branch_is_usable_but_and_pair_is_not(tmp_path: Path) -> None:
    """`A OR B` 任一分支可用即放行；`A AND B` 里有不可用的就要人拍板。

    这是把"许可证集合"与"许可证表达式"分开的唯一反证：拍平之后
    `MIT AND LGPL-2.1` 会因为含 MIT 而变绿——那正是这类门最常见的假绿方向。
    """
    tree = _tree(tmp_path / "t4", ["zzz-dual", "zzz-pair"])
    idx = {"zzz-dual": [_rec("zzz-dual", expr="Apache-2.0 OR BSD-3-Clause")],
           "zzz-pair": [_rec("zzz-pair", expr="MIT AND LGPL-2.1")]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证未裁定", "zzz-pair") in fired, fired
    assert rep["buckets"]["allowed"] == 1, rep["buckets"]
    assert rep["buckets"]["review-required"] == 1, rep["buckets"]


def test_declared_but_uninstalled_needs_a_written_reason(tmp_path: Path) -> None:
    """我们自己声明、这个环境装不上的依赖：没理由就判红（覆盖面缺口要签字）。"""
    tree = _tree(tmp_path / "t5", ["zzz-missing"])
    idx = {"zzz-here": [_rec("zzz-here", expr="MIT")]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    assert ("声明的依赖没查过", "zzz-missing") in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]
    assert dlg.main(["--repo", str(tree)]) == 4, rep["violations"]

    rep2 = dlg.audit(tree, idx=idx, declared_not_installed={"zzz-missing": "合成：不装它的理由"})
    assert not rep2["violations"], rep2["violations"]
    assert rep2["buckets"]["declared-missing"] == 1, rep2["buckets"]


def test_forbidden_family_cannot_be_waived_by_the_ledger(tmp_path: Path) -> None:
    """强 copyleft 不由台账静默吞掉：裁了也要红（两笔：禁用 + 越权放行）。"""
    tree = _tree(tmp_path / "t6", ["zzz-agpl"])
    idx = {"zzz-agpl": [_rec("zzz-agpl", expr="AGPL-3.0-or-later")]}
    led = tree / dlg.POLICY_REL
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps({"entries": [
        {"package": "zzz-agpl", "license": "AGPL-3.0-or-later", "decision": "accepted",
         "why": "想放行"}]}, ensure_ascii=False), encoding="utf-8")
    rep = dlg.audit(tree, idx=idx, declared_not_installed={})
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("依赖许可证禁用", "zzz-agpl") in fired, fired
    assert ("台账越权放行", "zzz-agpl") in fired, fired


def test_premise_missing_pyproject_is_not_zero_risk(tmp_path: Path) -> None:
    """读不到声明面 ⇒ 退 2（前提不成立），不许读成"一个依赖都没有所以零风险"。"""
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert dlg.main(["--repo", str(empty)]) == 2
    rep = dlg.audit(empty)
    assert rep["ok"] is False and any(p.startswith("pyproject_missing") for p in rep["problems"]), \
        rep["problems"]


# ---- 第 93 片：许可证**正文**与元数据对账 ----

AGPL_BODY = ("GNU AFFERO GENERAL PUBLIC LICENSE\n"
             "Version 3, 19 November 2007\n\n"
             "Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>\n"
             "Everyone is permitted to copy and distribute verbatim copies\n")
MIT_BODY = ("MIT License\n\nCopyright (c) 2020 someone\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files.\n")
LGPL_BODY = ("GNU LESSER GENERAL PUBLIC LICENSE\n"
             "Version 3, 29 June 2007\n\n"
             "This version of the GNU Lesser General Public License incorporates\n"
             "the terms and conditions of version 3 of the GNU General Public License,\n"
             "supplemented by the additional permissions listed below.\n")
# bundled 声明文件的真实形状（实测 cadquery-ocp 的 `LICENSES_bundled`）：
# 许可证名只出现在 `license:` 这种**键值行**里，不在标题位。
BUNDLED_BODY = ("This wheel distribution bundles a number of libraries\n"
                "that are compatibly licensed. We list them here.\n\n"
                "name: someothersub\nfiles: pkg/_vendor/*\n"
                "license: GNU AFFERO GENERAL PUBLIC LICENSE\n")


def test_body_stricter_than_metadata_fires_but_a_bundled_list_does_not(
        tmp_path: Path) -> None:
    """正文面三极：同一份 AGPL 文字，**位置**决定判决。

    标题行 ⇒ 判红（元数据低报）；MIT 正文 ⇒ 不红；`license: AGPL…` 键值行 ⇒ 只记档。
    少了第三极，本仓 BSD/Apache 的包只要附带一份 vendored 第三方声明就会被判红
    （实测 cadquery-ocp 的 `LICENSES_bundled` 里真有 AGPL/GPL/LGPL 三个更严的名字）。
    """
    tree = _tree(tmp_path / "b1", ["zzz-body"])
    idx = {"zzz-body": [_rec("zzz-body", expr="MIT")]}

    def rep_with(text: str):
        return dlg.audit(tree, idx=idx, declared_not_installed={},
                         bodies={"zzz-body": [("zzz_body-1.0.dist-info/licenses/LICENSE",
                                              text)]})

    fired = {(v["field"], v["doc"]) for v in rep_with(AGPL_BODY)["violations"]}
    assert ("许可证正文与元数据打架", "zzz-body") in fired, fired
    assert rep_with(AGPL_BODY)["corpus"]["inspected"] == 1, rep_with(AGPL_BODY)["corpus"]
    assert not rep_with(MIT_BODY)["violations"], rep_with(MIT_BODY)["violations"]
    bundled = rep_with(BUNDLED_BODY)
    assert ("许可证正文与元数据打架", "zzz-body") not in {
        (v["field"], v["doc"]) for v in bundled["violations"]}, bundled["violations"]
    assert bundled["buckets"]["body-severe-mention"] == 1, bundled["buckets"]
    assert bundled["buckets"]["body-unrecognized"] == 1, bundled["buckets"]


def test_lgpl_body_text_does_not_escalate_to_gpl(tmp_path: Path) -> None:
    """LGPL 正文按 FSF 写法必然逐字引用 GPL ⇒ 断言只算 lgpl，GPL 连"提及"都不算。

    少了这条豁免，一条 LGPL 依赖会因为自己的正文引用了 GPL 而**二次误红**
    （把"禁用"的帽子扣到弱 copyleft 上）。反向对照：纯 GPL 正文配 MIT 元数据必须开火。
    """
    tree = _tree(tmp_path / "b2", ["zzz-lgpl"])
    rep = dlg.audit(tree, idx={"zzz-lgpl": [_rec("zzz-lgpl", expr="LGPL-3.0-or-later")]},
                    declared_not_installed={},
                    bodies={"zzz-lgpl": [("x.dist-info/licenses/LICENSE", LGPL_BODY)]})
    row = next(r for r in rep["rows"] if r["package"] == "zzz-lgpl")
    assert row["body"]["asserted"] == ["lgpl-3.0-or-later"], row["body"]
    assert "gpl-3.0-or-later" not in row["body"]["mentioned"], row["body"]
    assert ("许可证正文与元数据打架", "zzz-lgpl") not in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]
    gpl = dlg.audit(tree, idx={"zzz-lgpl": [_rec("zzz-lgpl", expr="MIT")]},
                    declared_not_installed={},
                    bodies={"zzz-lgpl": [("x.dist-info/licenses/LICENSE",
                                          "GNU GENERAL PUBLIC LICENSE\nVersion 3\n")]})
    assert ("许可证正文与元数据打架", "zzz-lgpl") in {
        (v["field"], v["doc"]) for v in gpl["violations"]}, gpl["violations"]


def test_body_states_are_three_not_two(tmp_path: Path) -> None:
    """「没有正文」「正文认不出」都不许折算成合规，也不许折算成违规——它们是第三态。"""
    tree = _tree(tmp_path / "b3", ["zzz-none", "zzz-odd"])
    idx = {"zzz-none": [_rec("zzz-none", expr="MIT")],
           "zzz-odd": [_rec("zzz-odd", expr="MIT")]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={},
                    bodies={"zzz-odd": [("y.dist-info/LICENSE",
                                         "Proprietary notice. All rights reserved.\n")]})
    b = rep["buckets"]
    assert b["body-missing"] == 1 and b["body-unrecognized"] == 1 and b["body-checked"] == 0, b
    assert not rep["violations"], rep["violations"]
    states = {r["package"]: r["body"]["state"] for r in rep["rows"]}
    assert states == {"zzz-none": "missing", "zzz-odd": "unrecognized"}, states


def test_duplicate_metadata_records_take_the_stricter_saying(tmp_path: Path) -> None:
    """同名多份记录：档位不同 ⇒ 判红并取**最严**那份；同族两种写法 ⇒ 不算两种说法。

    真读到的形状：本环境里 `aipd-os` 有 wheel 的 `.dist-info` 与遗留
    `src/aipd_os.egg-info` 两份记录。按"取第一份"判＝拿排在前面那份当结论。
    """
    tree = _tree(tmp_path / "b4", ["zzz-dup"])
    conflict = {"zzz-dup": [_rec("zzz-dup", expr="MIT"),
                            _rec("zzz-dup", expr="AGPL-3.0-or-later")]}
    rep = dlg.audit(tree, idx=conflict, declared_not_installed={}, bodies={})
    fired = {(v["field"], v["doc"]) for v in rep["violations"]}
    assert ("同名多份元数据不一致", "zzz-dup") in fired, fired
    assert ("依赖许可证禁用", "zzz-dup") in fired, fired        # 取最严那份，不是取第一份
    assert rep["corpus"]["inspected"] == 1, rep["corpus"]      # 分母按名字计一次
    assert rep["corpus"]["duplicate_conflicts"] == ["zzz-dup"], rep["corpus"]

    samefam = {"zzz-dup": [_rec("zzz-dup", cls=["BSD License"]),
                           _rec("zzz-dup", expr="BSD-3-Clause")]}
    rep2 = dlg.audit(tree, idx=samefam, declared_not_installed={}, bodies={})
    assert ("同名多份元数据不一致", "zzz-dup") not in {
        (v["field"], v["doc"]) for v in rep2["violations"]}, rep2["violations"]
    assert rep2["corpus"]["duplicate_conflicts"] == [], rep2["corpus"]


def test_outside_closure_duplicate_records_still_reconcile(tmp_path: Path) -> None:
    """重复记录的对账不许只在闭包内跑：本仓唯一真原告 `aipd-os` 就在闭包外。

    这一格是"覆盖面自己漏了自己"的形状——判据遍历声明根，而项目自身走不到，
    于是 `同名多份：['aipd-os']` 出现在名册上却一个桶都不进（读成 0 个）。
    """
    tree = _tree(tmp_path / "b4x", ["zzz-seen"])
    idx = {"zzz-seen": [_rec("zzz-seen", expr="MIT")],
           "zzz-away": [_rec("zzz-away", expr="MIT"), _rec("zzz-away", expr="AGPL-3.0")]}
    rep = dlg.audit(tree, idx=idx, declared_not_installed={}, bodies={})
    assert rep["buckets"]["duplicate-records"] == 1, rep["buckets"]
    assert rep["buckets"]["duplicate-conflict"] == 1, rep["buckets"]
    assert ("同名多份元数据不一致", "zzz-away") in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]


def test_bodies_are_read_from_a_real_wheel_not_only_from_injection(
        tmp_path: Path) -> None:
    """生产读文件这条路自己也要被走到：造一个**真** dist-info，让量具自己去读。

    注入的 `bodies=` 只证明判决逻辑；`RECORD + locate()` 这条路走不通的话，
    真仓库那一跑会安静地读到一个空名册（"没有正文"被读成"没有风险"）。
    """
    import importlib.metadata as md

    site = tmp_path / "site"
    dist = site / "zzzreal-1.0.dist-info"
    (dist / "licenses").mkdir(parents=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: zzzreal\n"
                                   "Version: 1.0\nLicense-Expression: MIT\n",
                                   encoding="utf-8")
    (dist / "licenses" / "LICENSE").write_text(AGPL_BODY, encoding="utf-8")
    (dist / "RECORD").write_text("zzzreal-1.0.dist-info/METADATA,,\n"
                                 "zzzreal-1.0.dist-info/licenses/LICENSE,,\n",
                                 encoding="utf-8")
    got = dlg.bodies_of(md.Distribution.at(dist))
    assert [n for n, _t in got] == ["zzzreal-1.0.dist-info/licenses/LICENSE"], got
    assert AGPL_BODY.splitlines()[0] in got[0][1], got
    # 包树里的 vendored 许可证不算它自己的正文（实测 casadi 有 58 个、numpy 3 个）
    (site / "zzzreal").mkdir()
    (site / "zzzreal" / "LICENSE").write_text(MIT_BODY, encoding="utf-8")
    (dist / "RECORD").write_text("zzzreal-1.0.dist-info/METADATA,,\n"
                                 "zzzreal-1.0.dist-info/licenses/LICENSE,,\n"
                                 "zzzreal/LICENSE,,\n", encoding="utf-8")
    assert [n for n, _t in dlg.bodies_of(md.Distribution.at(dist))] == [
        "zzzreal-1.0.dist-info/licenses/LICENSE"], dlg.bodies_of(md.Distribution.at(dist))
    rep = dlg.audit(_tree(tmp_path / "b5", ["zzzreal"]),
                    idx={"zzzreal": [_rec("zzzreal", expr="MIT")]},
                    declared_not_installed={}, bodies={"zzzreal": got})
    assert ("许可证正文与元数据打架", "zzzreal") in {
        (v["field"], v["doc"]) for v in rep["violations"]}, rep["violations"]


def test_ledger_can_adjudicate_a_package_whose_metadata_gives_only_a_coarse_name(
        tmp_path: Path) -> None:
    """整段许可证全文写在元数据里（实测 numpy / multimethod / reportlab / cadquery 四家）
    ⇒ ids 只留标识符；classifier 只给粗名 `BSD License` 时，台账裁 `BSD-3-Clause` 要能对上。
    两条都没有的话，这类包挂上裁定条目也永远红——那是闸门自己把出口拦死了。
    """
    tree = _tree(tmp_path / "b6", ["zzz-para"])
    para = ("Copyright (c) 2005-2024, somebody. All rights reserved.\n"
            "Redistribution and use in source and binary forms, with or without\n"
            "modification, are permitted provided that the following conditions\n")
    idx = {"zzz-para": [_rec("zzz-para", cls=["BSD License"], fields=[para])]}
    led = tree / dlg.POLICY_REL
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps({"entries": [{"package": "zzz-para", "license": "BSD-3-Clause",
                                            "decision": "accepted", "why": "合成"}]},
                              ensure_ascii=False), encoding="utf-8")
    rep = dlg.audit(tree, idx=idx, declared_not_installed={}, bodies={})
    row = [r for r in rep["rows"] if r["package"] == "zzz-para"][0]
    assert row["licenses"] == ["bsd"], row
    assert not rep["violations"], rep["violations"]          # 粗名覆盖细串 ⇒ 不判「该撤」
    led.write_text(json.dumps({"entries": [{"package": "zzz-para", "license": "MIT",
                                            "decision": "accepted", "why": "真换族"}]},
                              ensure_ascii=False), encoding="utf-8")
    rep2 = dlg.audit(tree, idx=idx, declared_not_installed={}, bodies={})
    assert ("台账该撤", "zzz-para") in {(v["field"], v["doc"]) for v in rep2["violations"]}, \
        rep2["violations"]


def test_real_corpus_body_face_is_populated_and_has_no_false_red() -> None:
    """真仓库那一跑：正文面必须有分母，且已知误报形状都不开火。

    钉的是**关系**不是绝对数（覆盖面会变）：断言可比的名词数压得住"认不出"，
    casadi 落"无正文"，而本仓今天没有任何一格判红是正文面报的。
    """
    rep = dlg.audit(ROOT)
    b, c = rep["buckets"], rep["corpus"]
    assert c["body_files"] >= 40, c
    assert b["body-checked"] >= 30 and b["body-checked"] > b["body-unrecognized"], b
    assert b["body-severe-mention"] >= 5, b        # 真语料里 bundled 声明是常态，不是异常
    missing = {r["package"] for r in rep["rows"] if r["body"]["state"] == "missing"}
    assert missing == {"casadi"}, (missing, b)
    fired = {v["field"] for v in rep["violations"]}
    assert "许可证正文与元数据打架" not in fired, rep["violations"]
    assert "同名多份元数据不一致" not in fired, rep["violations"]
    # 已知误报名单逐个点名不许开火（它们就是"窗口判据"会红的那几格）
    rows = {r["package"]: r for r in rep["rows"]}
    for pkg in ("typing-extensions", "numpy", "cadquery-ocp", "mypy", "pillow", "nlopt",
                "pathspec", "librt"):
        body = rows[pkg]["body"]
        assert "gpl-3.0-or-later" not in body["asserted"], (pkg, body)
        assert "agpl-3.0-or-later" not in body["asserted"], (pkg, body)
    assert c["duplicated_names"] == ["aipd-os"], c
    assert b["duplicate-records"] == 1 and b["duplicate-conflict"] == 0, b
