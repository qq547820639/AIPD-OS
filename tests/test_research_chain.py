"""研究链（P1-2）测试：摄入净化、摘要/全文区分、全文解析、引用一致、
可信度/冲突、回写 Product Truth / Evidence Register、过期传播、失败保持 not_verified。

诚实护栏贯穿全程：在线检索/下载为 external_dependency，绝不伪造成功在线结果。
"""

from __future__ import annotations

import pytest

from aipd_os.research import (
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    Abstract,
    AttachmentTooLarge,
    Citation,
    CompetitorRetriever,
    ContractFetcher,
    DisallowedExtension,
    Document,
    FullText,
    HttpDocumentFetcher,
    PatentRetriever,
    ResearchBackend,
    ResearchFinding,
    StandardsRetriever,
    ingest_attachment,
    mark_evidence_expired,
    network_competitors,
    network_patents,
    network_standards,
    resolve_conflicts,
    run_research_chain,
    sanitize_text,
    sha256_of,
    source_metadata,
    timeliness,
)
from aipd_os.state.db import AIPDStateDB
from tests.fixtures.research.retriever_fixtures import (
    competitors_test_retriever,
    patents_test_retriever,
    standards_test_retriever,
)


@pytest.fixture
def db(tmp_path):
    d = AIPDStateDB(str(tmp_path / "state.db"), encryption_key="test-key")
    d.ensure_default_tenant()
    d.init_project("default", "p1", "P1", "goal")
    return d


# ---------------------------------------------------------------- 摄入与净化
def test_ingest_attachment_records_sha256_and_metadata(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_bytes(b"ISO 9001 requirements text.")
    meta = ingest_attachment(f)
    assert meta["sha256"] == sha256_of(b"ISO 9001 requirements text.")
    assert meta["extension"] == ".txt"
    assert meta["original_size"] == len(b"ISO 9001 requirements text.")
    assert meta["name"] == "doc.txt"
    assert meta["sanitized_bytes"] == b"ISO 9001 requirements text."


def test_ingest_strips_dangerous_content(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_bytes(b"<script>alert(1)</script> safe <iframe src=x></iframe>")
    meta = ingest_attachment(f)
    cleaned = meta["sanitized_bytes"].decode()
    assert "<script>" not in cleaned
    assert "<iframe>" not in cleaned
    assert meta["dangerous_markers"] >= 2


def test_ingest_rejects_too_large(tmp_path):
    f = tmp_path / "big.txt"
    f.write_bytes(b"x" * 100)
    with pytest.raises(AttachmentTooLarge):
        ingest_attachment(f, max_bytes=50)


def test_ingest_rejects_disallowed_extension(tmp_path):
    f = tmp_path / "evil.exe"
    f.write_bytes(b"MZ")
    with pytest.raises(DisallowedExtension):
        ingest_attachment(f)


def test_sanitize_text_removes_event_handlers():
    out = sanitize_text('<div onclick="x()">hi</div> javascript:alert')
    assert "onclick" not in out
    assert "javascript:" not in out


# ---------------------------------------------------------------- 摘要 vs 全文
def test_abstract_not_obtainable_fulltext_obtainable():
    cite = Citation(source="official_standard", title="ISO-9001:2015")
    ab = Abstract(title="ISO-9001:2015", snippet="abstract only", citation=cite)
    ft = FullText(title="ISO-9001:2015", text="real full text", citation=cite)
    assert ab.obtainable is False
    assert ft.obtainable is True


def test_document_status_verified_only_with_fulltext():
    cite = Citation(source="official_standard", title="ISO-9001:2015")
    doc_abstract = Document(citation=cite, abstract=Abstract(title="t", snippet="s"))
    assert doc_abstract.status == STATUS_NOT_VERIFIED
    assert doc_abstract.has_full_text is False

    doc_full = Document(
        citation=cite,
        full_text=FullText(title="t", text="content"),
    )
    assert doc_full.status == STATUS_VERIFIED
    assert doc_full.has_full_text is True


# ---------------------------------------------------------------- 全文解析
def test_contract_fetcher_returns_deterministic_fulltext():
    fetcher = ContractFetcher()
    cite = Citation(source="official_standard", title="ISO-9001:2015", identifier="ISO-9001:2015")
    doc = fetcher.fetch(cite)
    assert doc.status == STATUS_VERIFIED
    assert doc.full_text is not None
    assert "quality management system" in doc.full_text.text.lower()


def test_contract_fetcher_unknown_gives_not_verified():
    fetcher = ContractFetcher()
    cite = Citation(source="official_standard", title="No Such Doc")
    doc = fetcher.fetch(cite)
    assert doc.status == STATUS_NOT_VERIFIED
    assert doc.full_text is None


def test_parse_txt_and_pdf_pluggable():
    from aipd_os.research.fetchers import parse_pdf, parse_txt

    cite = Citation(source="patent", title="P")
    ft = parse_txt(b"hello world", cite)
    assert ft.obtainable and ft.text == "hello world"
    pf = parse_pdf(b"pdf-ish bytes", cite)
    assert pf.obtainable and "pdf-ish" in pf.text


def test_http_fetcher_unavailable_marks_not_verified():
    fetcher = HttpDocumentFetcher()  # 无密钥
    assert fetcher.available() is False
    cite = Citation(source="official_standard", title="ISO-9001:2015")
    doc = fetcher.fetch(cite)
    assert doc.status == STATUS_NOT_VERIFIED
    assert doc.full_text is None


# ---------------------------------------------------------------- 引用一致
def test_citation_requires_source_and_title_and_confidence_range():
    with pytest.raises(ValueError):
        Citation(source="", title="x")
    with pytest.raises(ValueError):
        Citation(source="patent", title="")
    with pytest.raises(ValueError):
        Citation(source="patent", title="x", confidence=1.5)


def test_citation_to_dict_has_accessed_at():
    c = Citation(source="patent", title="P", confidence=0.85)
    d = c.to_dict()
    assert d["source"] == "patent"
    assert d["confidence"] == 0.85
    assert d["accessed_at"]


# ---------------------------------------------------------------- 检索
def test_standards_retriever_fixture_deterministic():
    r = standards_test_retriever()  # 显式测试夹具（Commit 7D：不再默认进生产路径）
    docs = r.search("quality management")
    assert len(docs) == 1
    assert docs[0].citation.source == "official_standard"
    assert docs[0].status == STATUS_NOT_VERIFIED  # 仅摘要，无全文


def test_patent_and_competitor_retrievers():
    assert patents_test_retriever().search("additive manufacturing")[0].citation.kind == "patent"
    assert competitors_test_retriever().search("thermal management")[0].citation.kind == "competitor"


def test_production_retrievers_default_external_dependency():
    """生产默认不再返回测试数据：available()=False，search 返回空（诚实降级）。"""

    for make in (StandardsRetriever, PatentRetriever, CompetitorRetriever):
        r = make()
        assert r.available() is False, make.__name__
        assert r.search("anything") == []
        assert r.search("quality management") == []
        assert r.search("additive manufacturing") == []


def test_network_stubs_return_not_verified_no_credentials():
    for make in (network_standards, network_patents, network_competitors):
        r = make(api_key=None)  # 无凭据
        assert r.available() is False
        assert r.search("anything") == []  # 诚实空结果，不伪造


# ---------------------------------------------------------------- 可信度/冲突
def test_source_metadata_official_and_unknown():
    assert source_metadata("official_standard")["official"] is True
    assert source_metadata("nope")["official"] is False


def test_timeliness_rating():
    assert timeliness(10)["freshness"] == "fresh"
    assert timeliness(500)["freshness"] == "aging"
    assert timeliness(2000)["freshness"] == "stale"


def test_resolve_conflicts_flags_conflict_not_silent():
    findings = [
        {"key": "thickness", "value": "1.6 mm"},
        {"key": "thickness", "value": "2.4 mm"},
    ]
    out = resolve_conflicts(findings)
    assert out["conflict"] is True
    assert out["resolved"] is False
    assert out["conflicts"][0]["key"] == "thickness"


def test_resolve_conflicts_no_conflict_resolved():
    findings = [{"key": "a", "value": "1"}, {"key": "a", "value": "1"}]
    out = resolve_conflicts(findings)
    assert out["conflict"] is False
    assert out["resolved"] is True


# ---------------------------------------------------------------- 回写
def test_write_verified_finding_creates_fact_and_evidence(db):
    backend = ResearchBackend(db, "default", "p1")
    finding = ResearchFinding(
        key="copper_thickness", value="1.6 mm", status=STATUS_VERIFIED,
        confidence=0.9,
        citations=[Citation(source="official_standard", title="IPC-H05K", confidence=0.9, kind="standard")],
    )
    fact_id = backend.write_finding(finding)
    assert fact_id is not None
    fact = db.get_fact("default", "p1", fact_id)
    assert fact["key"] == "copper_thickness"
    assert fact["value"] == "1.6 mm"
    # 保守认知状态：外部来源最多 E，绝不自动 V（retrieval verified ≠ 命题 verified）
    assert fact["status"] == "E"
    assert fact["status"] != "V"
    # Evidence Register 有记录（含 epistemic metadata）
    evs = db.list_evidence("default", "p1")
    assert len(evs) == 1
    assert evs[0]["quality"] == "full_text"
    assert evs[0]["kind"] == "standard"
    import json as _json
    ev_meta = _json.loads(evs[0]["metadata_json"] or "{}")
    assert ev_meta.get("epistemic_status") == "E"
    # 关联
    linked = db.list_evidence_for_fact("default", "p1", fact_id)
    assert len(linked) == 1


def test_write_not_verified_finding_writes_no_fact(db):
    backend = ResearchBackend(db, "default", "p1")
    finding = ResearchFinding(
        key="some_claim", value="x", status=STATUS_NOT_VERIFIED,
        citations=[Citation(source="forum", title="forum post", confidence=0.3)],
    )
    fact_id = backend.write_finding(finding)
    assert fact_id is None  # 不固化未验证结论
    assert db.list_facts("default", "p1") == []
    # 只登记证据
    eids = backend.write_evidence_only(finding)
    assert len(eids) == 1


# ---------------------------------------------------------------- 过期传播
def test_mark_evidence_expired_flags_linked_fact_stale(db):
    backend = ResearchBackend(db, "default", "p1")
    finding = ResearchFinding(
        key="voltage", value="240V", status=STATUS_VERIFIED, confidence=0.8,
        citations=[Citation(source="official_standard", title="IEC-60038", confidence=0.8)],
    )
    fact_id = backend.write_finding(finding)
    ev = db.list_evidence("default", "p1")[0]
    result = mark_evidence_expired(db, "default", "p1", ev["evidence_id"], reason="superseded")
    assert fact_id in result["stale_fact_ids"]
    assert db.get_fact("default", "p1", fact_id)["status"] == "S"
    # 过期元数据已写入 Evidence Register
    ev2 = db.list_evidence("default", "p1")[0]
    assert "expired_at" in (ev2["metadata_json"] or {})


def test_expire_evidence_list_batch(db):
    backend = ResearchBackend(db, "default", "p1")
    f = ResearchFinding(key="k", value="v", status=STATUS_VERIFIED,
                        citations=[Citation(source="patent", title="US-PAT-10404000", confidence=0.8)])
    backend.write_finding(f)
    ev = db.list_evidence("default", "p1")[0]
    out = mark_evidence_expired(db, "default", "p1", ev["evidence_id"])
    assert out["expired_at"]


# ---------------------------------------------------------------- 失败保持 not_verified
def test_run_research_chain_failure_stays_not_verified(db):
    # 使用网络检索桩（无凭据）→ 检索失败，不产生结论
    finding = ResearchFinding(
        key="thermal", value="will-not-be-written", status=STATUS_NOT_VERIFIED,
        citations=[Citation(source="industry_report", title="Comp Report", confidence=0.5)],
    )
    r = network_standards(api_key=None)
    out = run_research_chain(db, "default", "p1", finding, retriever=r)
    assert out["status"] == STATUS_NOT_VERIFIED
    assert out["fact_id"] is None
    assert db.list_facts("default", "p1") == []  # 无确定性结论被固化


def test_run_research_chain_success_writes_fact(db):
    from aipd_os.research import ContractFetcher

    finding = ResearchFinding(
        key="quality", value="requirements met", status=STATUS_NOT_VERIFIED,
        citations=[Citation(source="official_standard", title="ISO-9001:2015", confidence=0.95)],
    )
    out = run_research_chain(db, "default", "p1", finding, fetcher=ContractFetcher())
    assert out["fact_id"] is not None
    fact = db.list_facts("default", "p1")[0]
    assert fact["key"] == "quality"
    # 拿到全文（retrieval verified）≠ verified truth：写入 E 而非 V
    assert fact["status"] == "E"
