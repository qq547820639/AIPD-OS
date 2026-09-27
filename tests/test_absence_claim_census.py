"""登记表否定句 × 反证锚点对账的常驻牙（F-STALE-ABSENCE 第 65 片）。

这把尺子管的事：能力登记表里写「X 仍没有」，那 X 今天必须真的没有。
第 65 片开出它的理由是**实测**：第 53 片接上 BOM 版本记录的返工执行器之后，
`industrialize.quote_to_bom_cost` 那句「BOM 版本记录仍没有」在登记表里又漂了 12 片；
同一族还有「执行器只认图纸声明这一类制品」与五条 `product.*` 行的「生产 Provider 未接入」。

分组的判据（每组都问一遍"如果量具坏了，这一组会不会跟着假绿"）：
① 量具被真 spawn（孤儿门禁与没有门禁看不出差别）；
② 真仓库上内置账本全成立，且**分母非空**——84 个能力、几十句否定句都要读到；
③ 两个方向的对照都用**真语料**跑：账文脱钩（删句不删账）与反证在场（CONTRADICTED），
   不靠临时目录里自己搭的假树；
④ 锚点绑 (能力 id, 字段) 不绑全文——登记表里有五条逐字相同的「生产 Provider…」，
   只按子串找会一条改完五条假装都改完；
⑤ AST 面与文本面之分：注释里写「不做 X」不许读成「X 做了」。
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import absence_claim_census as acc  # noqa: E402

TOOL = ROOT / "scripts" / "absence_claim_census.py"

# 第 65 片从真登记表里**删掉**的三句原话。留在这里不是复古：它们是 ③ 组那两档
# 判决在真语料上的永久燃料——正文改了、账没改，就必须响。
DELETED_SENTENCES = {
    "industrialize.quote_to_bom_cost": "BOM 版本记录仍没有",
    "industrialize.physical_writeback": "执行器只认图纸声明这一类制品",
    "product.derive_insights": "生产 Provider 未接入",
}


def claim(cid: str, capability: str, anchor: str, check: dict) -> dict:
    return {"id": cid, "capability": capability, "field": "current_limitation",
            "anchor": anchor, "check": check}


def verdicts(rep: dict) -> dict[str, str]:
    """账本条目各自的判决。

    滤掉两类**语料级**行（`UNACCOUNTED:*` / `EXEMPT:*`）：它们不是某条登记的判决，
    而是"这句现状文本有没有去处"的判决，喂半份账本进来时必然会多出来。
    """
    return {str(r["id"]): str(r["verdict"]) for r in rep["rows"]
            if not str(r["id"]).startswith(("UNACCOUNTED:", "EXEMPT:"))}


# ------------------------------------------------------------------ ① 真 spawn
def test_instrument_self_test_is_actually_run_and_green() -> None:
    proc = subprocess.run([sys.executable, str(TOOL), "--self-test"],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "条合成读数全部对上" in proc.stdout, proc.stdout
    assert "✓立住" in proc.stdout, proc.stdout
    for face in ("[HOLDS]", "[CONTRADICTED]", "[CLAIM_TEXT_ABSENT]",
                "[PRECONDITION]", "[UNACCOUNTED]"):
        assert face in proc.stdout, (face, proc.stdout.splitlines()[-4:])
    assert "分档之和 == 登记条数" in proc.stdout, proc.stdout.splitlines()[-4:]


def test_exit_code_zero_on_the_real_repo_and_the_faces_are_named() -> None:
    """内置账本在真仓库上退 0；4 与 2 各由下面两条用例在真语料/合成语料上钉住。

    三档分开钉，是因为"退码能分流"这件事最容易在只写一条 all-green 用例时被忘掉。
    """
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        assert acc.main([]) == 0
    out = buf.getvalue()
    assert "判红 0 条" in out, out
    assert "[HOLDS]" in out and "[CONTRADICTED]" not in out, out


# ------------------------------------------------------------------ ② 真仓库分母
def test_real_repo_all_registered_claims_hold() -> None:
    rep = acc.audit(ROOT, acc.CLAIMS)
    assert rep["problems"] == [], rep["problems"]
    assert rep["ok"] is True, rep["judged"]
    assert all(v == acc.HOLDS for v in verdicts(rep).values()), verdicts(rep)
    c = rep["corpus"]
    # 分母下界：任何一档被静默收窄（包括登记表被换成语雀夹具）都会在这里红
    assert c["capabilities"] >= 80, c
    assert c["absence_sentences"] >= 30, c   # 第 65 片把 7 句过期话改掉后现读 37
    assert c["claims_registered"] == len(acc.CLAIMS), c
    assert c["absence_sentences_unanchored"] >= 20, \
        f"覆盖率读数本身要可见：{c}"


def test_every_claim_is_located_in_its_declared_field() -> None:
    rep = acc.audit(ROOT, acc.CLAIMS)
    for row in rep["rows"]:
        assert row["verdict"] != acc.CLAIM_TEXT_ABSENT, row
        doc, field, lineno = str(row["anchor_at"]).split(":")
        # 登记表条目落在 src/，文档条目（第 66 片的 PRODUCER-COUNT-ARCH）落在 docs/——
        # 两档都是"现状面"，但只有前者在登记表里，所以读数必须带文件名才分得开。
        assert doc.startswith(("src/", "docs/")), row
        assert field in ("current_limitation", "text"), row
        assert int(lineno) > 0, row
        assert (ROOT / doc).is_file(), row


# ------------------------------------------------------------------ ⑥ 计数叙述档（第 66 片）
def test_count_face_fires_on_the_real_corpus_with_a_mis_scoped_claim() -> None:
    """真语料上的永久开火对照：把同一句话的权威档换成 canonical，判决必须翻。

    不靠改文档造违规——数字是从**那句散文**里读的，而权威是从代码 AST 现读的，
    所以"档选错"这一件事本身就足以让判据开火；它同时也证明这个数不是我在账本里抄的。
    """
    claims = (claim("MIS-SCOPED", "product_truth.impact_propagation",
                    "血缘边的生产者今天有 8 个",
                    {"kind": "producer_count", "scope": "canonical"}),)
    rep = acc.audit(ROOT, claims)
    assert verdicts(rep) == {"MIS-SCOPED": acc.CONTRADICTED}, rep
    assert any("现读" in one for one in rep["rows"][0]["evidence"]), rep


def test_document_face_claim_is_checked_against_the_same_authority() -> None:
    """`file:` 条目（架构文档）与登记表条目吃同一个权威面，两格今天都要成立。"""
    docs = tuple(c for c in acc.CLAIMS if c.get("file"))
    assert len(docs) == 1, [c["id"] for c in docs]
    rep = acc.audit(ROOT, docs)
    assert list(verdicts(rep).values()) == [acc.HOLDS], rep["rows"]


# ------------------------------------------------------------------ ⑦ 去处台账（第 67 片）
def test_real_corpus_all_capability_absences_have_a_home() -> None:
    """真仓库上「登记 + 豁免 + 未处置 == 窄档分母」且未处置为 0。

    这条才是本片的验收：不是"我多登记了几条"，而是**没有一句能力缺失的话无人认领**。
    """
    rep = acc.audit(ROOT, acc.CLAIMS)
    c = rep["corpus"]
    assert c["narrow_unaccounted"] == 0, rep["unaccounted"]
    assert c["capability_absence_sentences"] == \
        c["narrow_registered"] + c["narrow_exempted"] + c["narrow_unaccounted"], c
    assert c["capability_absence_sentences"] >= 12, c
    # 窄档必须比宽档小：收窄本身就是交付，否则"每条都要有去处"只会逼出一堆空豁免
    assert c["capability_absence_sentences"] < c["absence_sentences"], c
    assert not [r for r in rep["rows"] if str(r["id"]).startswith("EXEMPT:")], rep["rows"]


def test_partial_ledger_makes_the_missing_home_fire() -> None:
    """真语料上的永久开火对照：抽掉一条登记 ⇒ 那句话立刻"没去处" ⇒ 退 4。

    不用改登记表文本就能开火，证明这一面不是靠造句子撑起来的。
    """
    target = next(c for c in acc.CLAIMS
                  if c.get("capability") == "cad.2d_drawings"
                  and c.get("check", {}).get("kind") == "identifier")
    partial = tuple(c for c in acc.CLAIMS if c is not target)
    rep = acc.audit(ROOT, partial)
    assert rep["corpus"]["narrow_unaccounted"] >= 1, rep["corpus"]
    un = [r for r in rep["rows"] if r["verdict"] == acc.UNACCOUNTED]
    assert any(str(target["anchor"]) in str(r["detail"]) for r in un), un
    assert rep["ok"] is False, rep
    assert rep["problems"] == [], rep["problems"]


def test_exemption_without_a_referent_is_itself_a_violation() -> None:
    """豁免台账不许留僵尸条目：语料里没这句话了就必须响（与悬空账同形）。"""
    saved = dict(acc.EXEMPTIONS)
    acc.EXEMPTIONS.clear()
    acc.EXEMPTIONS["这句在语料里根本不存在-第67片对照"] = "一条写给机器看的、足够长的理由"
    try:
        rep = acc.audit(ROOT, acc.CLAIMS)
    finally:
        acc.EXEMPTIONS.clear()
        acc.EXEMPTIONS.update(saved)
    stale = [r for r in rep["rows"] if str(r["id"]).startswith("EXEMPT:")]
    assert len(stale) == 1, stale
    assert stale[0]["verdict"] == acc.CLAIM_TEXT_ABSENT, stale
    assert rep["ok"] is False, rep


def test_count_unreadable_is_precondition_not_green(tmp_path: Path) -> None:
    """句子里读不到数量词 ⇒ 前提不成立，不许悄悄当"这句没问题"。"""
    (tmp_path / "src/aipd_os").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "src/aipd_os/m.py").write_text(
        "from aipd_os.product_truth.lineage import LineageGraph\n\n\n"
        "def f(g):\n    return g.add_edge('a', 'b')\n", encoding="utf-8")
    (tmp_path / "docs/x.md").write_text("这里没有数字的说法\n", encoding="utf-8")
    claims = ({"id": "NOCOUNT", "file": "docs/x.md", "anchor": "这里没有数字的说法",
               "check": {"kind": "producer_count", "scope": "truth"}},)
    rep = acc.audit(tmp_path, claims)
    assert verdicts(rep) == {"NOCOUNT": acc.PRECONDITION}, rep
    assert any(p.startswith("count_unreadable") for p in rep["problems"]), rep


def test_missing_authority_tree_is_precondition(tmp_path: Path) -> None:
    """权威面建不起来（没有 src/aipd_os）⇒ 退 2，绝不读成"0 个生产者、句里写 0 个就对了"。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/x.md").write_text("血缘边有**三个**生产者——a、b、c\n", encoding="utf-8")
    claims = ({"id": "NOAUTH", "file": "docs/x.md", "anchor": "血缘边有**三个**生产者",
               "check": {"kind": "producer_count", "scope": "truth"}},)
    rep = acc.audit(tmp_path, claims)
    assert verdicts(rep) == {"NOAUTH": acc.PRECONDITION}, rep
    assert any(p.startswith("authority_missing") for p in rep["problems"]), rep


# ------------------------------------------------------------------ ④b 两份登记表一面
def test_real_repo_two_registry_files_agree_on_every_shared_id() -> None:
    """`product.*` 七行的权威在 `scripts/product_capabilities_extra.py`，
    `registry_data.py` 是生成物 ⇒ 两份对同一 id 同一字段不许各说各话。
    """
    corpus, problems = acc.registry_strings(ROOT)
    assert problems == [], problems
    shared = [cid for cid, f in corpus.items()
              if len({rel for rows in f.values() for rel, _l, _t in rows}) > 1]
    assert len(shared) >= 5, f"前提：两文件确有重叠的 id，实读 {shared}"
    rep = acc.audit(ROOT, acc.CLAIMS)
    assert rep["divergence"] == [], rep["divergence"]


def test_divergent_duplicate_is_judged_on_its_own(tmp_path: Path, monkeypatch) -> None:
    """两份各说各话要**自己**退 4：不靠别的判红凑出来，也不许读成"其中一份没被消费所以没事"。"""
    monkeypatch.setattr(acc, "REGISTRY_FILES",
                        ("src/aipd_os/registry_data.py", "scripts/extra.py"))
    (tmp_path / "src/aipd_os").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    row = ('{"id": "cap.a", "name": "%s", '
           '"current_limitation": "跨币种折算未实现"}')
    (tmp_path / "src/aipd_os/registry_data.py").write_text(
        "CAPABILITIES = [" + (row % "同一个名字") + "]\n", encoding="utf-8")
    (tmp_path / "scripts/extra.py").write_text(
        "PRODUCT_CAPABILITIES = [" + (row % "另一个名字") + "]\n", encoding="utf-8")
    claims = (claim("QUIET", "cap.a", "跨币种折算未实现",
                    {"kind": "identifier", "paths": ["src"],
                     "symbols": ["zzz-not-a-symbol"]}),)
    rep = acc.audit(tmp_path, claims)
    assert list(verdicts(rep).values()) == [acc.HOLDS], rep["rows"]
    assert len(rep["divergence"]) == 1, rep["divergence"]
    assert rep["ok"] is False and rep["problems"] == [], rep
    with contextlib.redirect_stdout(io.StringIO()):
        assert acc.main(["--repo", str(tmp_path)]) == 4


# ------------------------------------------------------------------ ③ 真语料两向对照
def test_dangling_ledger_fires_on_the_real_repo() -> None:
    """删了句、没删账 ⇒ 判红。用的是第 65 片真删掉的三句原话。

    这一条不许改成"随便编一句话"：它要求**这句话曾经在登记表里**、今天不在了，
    否则它测的就不是账文同步，而是子串找不到。
    """
    corpus, problems = acc.registry_strings(ROOT)
    assert problems == [], problems
    for cap, sentence in DELETED_SENTENCES.items():
        assert acc.locate(corpus, cap, "current_limitation", sentence) is None, \
            f"{cap} 里又出现了 {sentence!r}：前提变了，本用例与登记表要一起重开"
    claims = tuple(claim(f"DELETED-{k}", k, v, {"kind": "identifier",
                                                "paths": ["src/aipd_os/cad"],
                                                "symbols": ["LineageGraph"]})
                   for k, v in sorted(DELETED_SENTENCES.items()))
    rep = acc.audit(ROOT, claims)
    assert len([r for r in rep["rows"] if not str(r["id"]).startswith(
        ("UNACCOUNTED:", "EXEMPT:"))]) == len(claims), rep["rows"]
    assert all(r["verdict"] == acc.CLAIM_TEXT_ABSENT for r in rep["rows"]
               if str(r["id"]) in {c["id"] for c in claims}), rep["rows"]
    assert len([r for r in rep["judged"] if not str(r["id"]).startswith(
        ("UNACCOUNTED:", "EXEMPT:"))]) == 3, rep["judged"]


def test_present_falsifier_contradicts_on_the_real_corpus() -> None:
    """CONTRADICTED 那一档也要在**真语料**上有永久对照。

    锚点选登记表里今天仍成立的一句（「跨币种折算未实现」），反证锚点故意选一个
    真在 `src/aipd_os/cad` 里被引用的名字——于是"这句话被证伪"是机器读出来的，
    不是我在临时目录里搭出来的。
    """
    claims = (claim("FIRED-ON-REAL", "industrialize.quote_to_bom_cost",
                    "跨币种折算未实现",
                    {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                     "symbols": ["LineageGraph"]}),)
    rep = acc.audit(ROOT, claims)
    assert verdicts(rep) == {"FIRED-ON-REAL": acc.CONTRADICTED}, rep
    assert rep["rows"][0]["evidence"], "判红必须带位点"
    assert any(p.startswith("src/aipd_os/cad/") for p in rep["rows"][0]["evidence"]), \
        rep["rows"][0]["evidence"]


def test_external_claims_ledger_is_a_real_code_path(tmp_path: Path) -> None:
    """`--claims` 不是装饰：常驻用例靠它在真仓库上做出退 4 的那一跑。"""
    ledger = tmp_path / "claims.json"
    ledger.write_text(json.dumps([{
        "id": "EXT", "capability": "industrialize.quote_to_bom_cost",
        "field": "current_limitation", "anchor": "跨币种折算未实现",
        "check": {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                  "symbols": ["LineageGraph"]}}], ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(TOOL), "--claims", str(ledger)],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "[CONTRADICTED]" in proc.stdout, proc.stdout


# ------------------------------------------------------------------ ④ 锚点绑定
def test_anchor_bound_to_the_wrong_capability_does_not_pass() -> None:
    """同句在别的能力行里出现，不算这一行"已登记"。

    锚点必须用**逐字取自另一行**的原话：第 65 片第一版这里写的是
    「这句话只属于别的行：生产 Provider…」——加了前缀之后，把判据放宽成全文子串找
    也照样读成 `CLAIM_TEXT_ABSENT`，于是那一臂变异当场存活（电池实测 SURVIVED）。
    """
    corpus, problems = acc.registry_strings(ROOT)
    assert problems == [], problems
    anchor = "跨币种折算未实现"
    home = "industrialize.quote_to_bom_cost"
    assert acc.locate(corpus, home, "current_limitation", anchor) is not None, "前提：原话在这一行"
    assert acc.locate(corpus, "supervisor.fact_writeback", "current_limitation", anchor) is None
    wrong = claim("MISBOUND", "supervisor.fact_writeback", anchor,
                  {"kind": "identifier", "paths": ["src/aipd_os/cad"],
                   "symbols": ["LineageGraph"]})
    rep = acc.audit(ROOT, (wrong,))
    assert verdicts(rep) == {"MISBOUND": acc.CLAIM_TEXT_ABSENT}, rep
    # 反证：把同一锚点绑回它真正所在的那一行，判决就变成"由位点说话"的两档之一
    right = claim("BOUND", home, anchor, wrong["check"])
    assert verdicts(acc.audit(ROOT, (right,))) == {"BOUND": acc.CONTRADICTED}, rep


def test_five_rows_share_the_sentence_and_are_each_checked() -> None:
    """五条 `product.*` 行今天都写了同一句真话——逐行登记才逐行有据。"""
    corpus, problems = acc.registry_strings(ROOT)
    assert problems == [], problems
    sentence = "生产 Provider 今天只有 LLM 这一家"
    rows = [cid for cid, fields in corpus.items()
            if any(sentence in text
                   for _f, _ln, text in fields.get("current_limitation", []))]
    assert len(rows) == 5, rows


# ------------------------------------------------------------------ ⑤ AST 面
def test_comment_only_mention_is_not_a_hit(tmp_path: Path) -> None:
    """注释与 docstring 里写「不做 LineageGraph」不算引用了它（文本面会假红）。"""
    pkg = tmp_path / "src/aipd_os/x"
    pkg.mkdir(parents=True)
    (pkg / "m.py").write_text(
        '"""这里**不写** truth_lineage 边, 也不建 LineageGraph。"""\n'
        '# LineageGraph 出现在注释里也不算\n', encoding="utf-8")
    assert acc.identifier_hits(tmp_path, ["src/aipd_os/x"], ["LineageGraph"]) == []
    (pkg / "n.py").write_text(
        'from aipd_os.product_truth.lineage import LineageGraph\n\n\n'
        'def f(store):\n    return LineageGraph(store)\n', encoding="utf-8")
    hits = acc.identifier_hits(tmp_path, ["src/aipd_os/x"], ["LineageGraph"])
    assert hits == ["src/aipd_os/x/n.py:1", "src/aipd_os/x/n.py:5"], hits


def test_unresolvable_anchor_is_precondition_not_hold(tmp_path: Path) -> None:
    """一跳解析不到的常量 ⇒ 退 2，绝不折算成"这个执行器不存在"。"""
    (tmp_path / "src/aipd_os/bom").mkdir(parents=True)
    (tmp_path / "src/aipd_os/bom/ghost.py").write_text(
        'from aipd_os.nowhere import ARTIFACT_GHOST\nSUPPORTED_ARTIFACT = ARTIFACT_GHOST\n',
        encoding="utf-8")
    (tmp_path / "src/aipd_os/registry_data.py").write_text(
        'CAPABILITIES = [{"id": "cap.a", "current_limitation": "ghost 这一类仍没有执行器"}]\n',
        encoding="utf-8")
    claims = (claim("PRE", "cap.a", "仍没有执行器",
                    {"kind": "artifact_executor", "artifact": "anything"}),)
    rep = acc.audit(tmp_path, claims)
    assert verdicts(rep) == {"PRE": acc.PRECONDITION}, rep
    assert any(p.startswith("anchor_unresolvable") for p in rep["problems"]), rep


def test_instrument_and_its_tests_are_out_of_the_scanned_faces() -> None:
    """量具自己的文件里必须写着假锚点才能证明判据会开火 ⇒ 不许进任何分母。"""
    scanned = {p.stem for p in acc._iter_py(ROOT, ["scripts"])}
    assert "absence_claim_census" not in scanned, sorted(scanned)[:5]
    assert "test_absence_claim_census" not in scanned
    corpus, problems = acc.registry_strings(ROOT)
    assert problems == [], problems
    assert "absence_claim_census" not in json.dumps(list(corpus), ensure_ascii=False)


def test_readme_carries_a_runnable_line_for_the_instrument() -> None:
    """README 里的可执行入口要与量具同名（第 60 片同款镜像，行首那一条）。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python scripts/absence_claim_census.py" in readme, \
        "改README这一行时同批改这里"


# ------------------------------------------------------------------ ⑧ 外部调用点档（第 68 片）
def test_gate_commit_has_no_production_caller_yet() -> None:
    """产品定义门禁的 commit 这一步：生产面 0 处外部调用点 ⇒ 这句登记今天成立。"""
    claims = tuple(c for c in acc.CLAIMS
                   if c.get("check", {}).get("kind") == "external_callers")
    assert len(claims) == 2, [c["id"] for c in claims]
    rep = acc.audit(ROOT, claims)
    assert set(verdicts(rep).values()) == {acc.HOLDS}, rep["rows"]
    ids = {str(c["id"]) for c in claims}
    for row in rep["rows"]:
        if str(row["id"]) not in ids:
            continue   # 喂半份账本必然多出语料级的"未处置"行，它们的 evidence 就是空的
        assert "外部调用点 = 0 处" in row["evidence"][0], row["evidence"]


def test_external_callers_probe_can_fire_positive_on_the_real_corpus() -> None:
    """探针必须会开火：拿一个真有外部调用点的名字，同一档必须判成过期。

    没有这一条，"0 处调用点"这个读数与"探针对任何名字都报 0"在输出上完全同形
    （记忆里那条"探针恒零的形状"在这里的对偶）。
    """
    probe = ({"id": "POS", "capability": "product.definition_gate",
              "field": "current_limitation", "anchor": "今天没有生产入口",
              "check": {"kind": "external_callers", "symbol": "record_dxf_lineage"}},)
    rep = acc.audit(ROOT, probe)
    assert verdicts(rep) == {"POS": acc.CONTRADICTED}, rep["rows"]
    ev = rep["rows"][0]["evidence"]
    assert any("外部调用点 = 1 处" in one for one in ev), ev
    assert any("commands_drawing.py" in str(one) for one in ev), ev


def test_external_callers_counts_are_memoized_and_stable() -> None:
    """同一 symbol 两次判决必须同一读数（缓存命中不能改变结果，也不能改变盲区）。"""
    claims = tuple(c for c in acc.CLAIMS
                   if c.get("check", {}).get("kind") == "external_callers")
    a1 = acc.external_callers(ROOT, "commit_snapshot")
    a2 = acc.external_callers(ROOT, "commit_snapshot")
    assert a1 == a2, (a1, a2)
    rep = acc.audit(ROOT, claims)
    assert list(verdicts(rep).values()) == [acc.HOLDS] * len(claims), rep["rows"]


def test_external_callers_without_production_tree_is_precondition(tmp_path: Path) -> None:
    """生产面除登记表自己没有别的代码时，"0 处调用点"是盲区，不是证据。"""
    (tmp_path / "src/aipd_os").mkdir(parents=True)
    (tmp_path / "src/aipd_os/registry_data.py").write_text(
        'CAPABILITIES = [{"id": "cap.a", "current_limitation": "X 今天没有生产入口"}]\n',
        encoding="utf-8")
    claims = ({"id": "NOAUTH", "capability": "cap.a", "field": "current_limitation",
               "anchor": "今天没有生产入口",
               "check": {"kind": "external_callers", "symbol": "zzz_nope"}},)
    rep = acc.audit(tmp_path, claims)
    assert verdicts(rep) == {"NOAUTH": acc.PRECONDITION}, rep["rows"]
    assert any(str(p).startswith("authority_thin") for p in rep["problems"]), rep["problems"]
