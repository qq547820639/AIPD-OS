"""P1-4 全文与文本类型测试：文本类型区分、全文获取/缓存/去重、版权边界、
结论绑定来源/段落/时间/过期策略、可替换 Provider。

诚实护栏：受版权/robots 限制的全文标记为 restricted 且不越权获取；
未配置 Provider 时保持 external_dependency（诚实等待，不伪造结果）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aipd_os.research.fulltext import (
    ACCESS_BLOCKED,
    ACCESS_OPEN,
    ACCESS_RESTRICTED,
    TEXT_TYPE_ABSTRACT,
    TEXT_TYPE_FULL_TEXT,
    TEXT_TYPE_METADATA,
    TEXT_TYPE_OCR_TEXT,
    TEXT_TYPE_QUOTED_SNIPPET,
    Conclusion,
    ExternalProvider,
    FullTextCache,
    TextRecord,
    classify_access,
    classify_text,
    competitor_provider,
    deduplicate_texts,
    default_expires_at,
    fetch_fulltext,
    patent_provider,
    refetch_strategy,
    regulation_provider,
    standard_provider,
    tag_text,
)


# ---------------------------------------------------------------- 文本类型区分
def test_classify_text_distinguishes_five_types():
    assert classify_text({"text_type": "metadata"}) == TEXT_TYPE_METADATA
    assert classify_text({"abstract": "..."}) == TEXT_TYPE_ABSTRACT
    assert classify_text({"full_text": "body"}) == TEXT_TYPE_FULL_TEXT
    assert classify_text({"body": "body"}) == TEXT_TYPE_FULL_TEXT
    assert classify_text({"is_ocr": True}) == TEXT_TYPE_OCR_TEXT
    assert classify_text({"ocr": True}) == TEXT_TYPE_OCR_TEXT
    assert classify_text({"quoted_snippet": "quote"}) == TEXT_TYPE_QUOTED_SNIPPET
    assert classify_text({"quote": "q"}) == TEXT_TYPE_QUOTED_SNIPPET
    # 无任何内容字段 -> metadata
    assert classify_text({}) == TEXT_TYPE_METADATA


def test_tag_text_adds_explicit_type():
    tagged = tag_text({"abstract": "snippet"})
    assert tagged["text_type"] == TEXT_TYPE_ABSTRACT
    # 不修改入参
    src = {"abstract": "snippet"}
    tag_text(src)
    assert "text_type" not in src


def test_text_record_sha256_and_defaults():
    rec = TextRecord(text_type=TEXT_TYPE_FULL_TEXT, text="hello")
    assert rec.access == ACCESS_OPEN
    assert rec.sha256  # 自动计算
    assert rec.retrieved_at


# ---------------------------------------------------------------- 全文获取/缓存/去重
def test_fetch_fulltext_open_access_with_getter_caches():
    url = "https://arxiv.org/abs/2401.12345"
    calls = []
    cache = FullTextCache()

    def getter(u):
        calls.append(u)
        return b"real full text body"

    r1 = fetch_fulltext(url, source="arxiv", cache=cache, getter=getter)
    assert r1.access == ACCESS_OPEN
    assert r1.text == "real full text body"
    assert r1.sha256
    assert r1.retrieved_at

    # 第二次命中缓存，不再调用下载器
    r2 = fetch_fulltext(url, source="arxiv", cache=cache, getter=getter)
    assert r2.text == r1.text
    assert len(calls) == 1


def test_fetch_fulltext_cache_file_backed(tmp_path):
    url = "https://arxiv.org/abs/2401.99999"
    cache = FullTextCache(cache_dir=str(tmp_path / "cache"))
    r = fetch_fulltext(url, source="arxiv", cache=cache, getter=lambda u: b"persisted text")
    assert r.access == ACCESS_OPEN
    # 新实例从磁盘命中
    cache2 = FullTextCache(cache_dir=str(tmp_path / "cache"))
    cached = cache2.get(url)
    assert cached is not None
    assert cached.text == "persisted text"


def test_dedup_by_content_sha256():
    recs = [
        TextRecord(text_type=TEXT_TYPE_FULL_TEXT, text="duplicate", source="a"),
        TextRecord(text_type=TEXT_TYPE_FULL_TEXT, text="duplicate", source="b"),
        TextRecord(text_type=TEXT_TYPE_FULL_TEXT, text="unique", source="c"),
    ]
    out = deduplicate_texts(recs)
    assert len(out) == 2
    assert {r.source for r in out} == {"a", "c"}  # 保留首次出现


def test_fetch_open_without_getter_honest_restricted():
    url = "https://arxiv.org/abs/2401.00001"
    rec = fetch_fulltext(url, source="arxiv")
    # 开放来源但无下载器：诚实标记受限，不伪造全文
    assert rec.access == ACCESS_RESTRICTED
    assert rec.text == ""


def test_fetch_fulltext_binary_body_not_faked_as_text():
    """回归：二进制（PDF）下载体不得被 decode 成乱码当全文。"""
    url = "https://arxiv.org/abs/2401.00002"
    binary = b"%PDF-1.7\n" + bytes(range(256))
    rec = fetch_fulltext(url, source="arxiv", getter=lambda u: binary)
    assert rec.access == ACCESS_RESTRICTED
    assert rec.text == ""
    assert rec.sha256  # 仍记录内容哈希，便于溯源


def test_fetch_fulltext_utf8_text_still_works():
    url = "https://arxiv.org/abs/2401.00003"
    rec = fetch_fulltext(url, source="arxiv", getter=lambda u: "纯文本全文".encode())
    assert rec.access == ACCESS_OPEN
    assert rec.text == "纯文本全文"


def test_default_expires_at_is_parseable_aware_iso():
    """回归：default_expires_at 曾产出 '...+00:00Z' 双时区后缀导致解析失败、
    过期时间静默失效。"""
    from aipd_os.research.fulltext import _parse_iso
    exp = default_expires_at(days=1)
    assert not exp.endswith("Z")
    parsed = _parse_iso(exp)
    assert parsed is not None
    assert parsed > datetime.now(timezone.utc)


# ---------------------------------------------------------------- 版权/访问边界
def test_classify_access_boundaries():
    # 开放许可
    assert classify_access("https://x.example/f", license="CC-BY") == ACCESS_OPEN
    assert classify_access("https://x.example/f", license="cc0") == ACCESS_OPEN
    # 已知开放访问域名
    assert classify_access("https://arxiv.org/abs/1") == ACCESS_OPEN
    # 受版权全文（无开放许可，非开放域名）-> restricted：不越权获取
    assert classify_access("https://paywall.example/secured.pdf") == ACCESS_RESTRICTED
    # robots 禁止 -> blocked
    assert (
        classify_access("https://arxiv.org/abs/1", robots_disallowed=True)
        == ACCESS_BLOCKED
    )


def test_restricted_and_blocked_fulltext_not_fetched():
    url = "https://paywall.example/secured.pdf"
    r = fetch_fulltext(url, source="paywall", getter=lambda u: b"should never fetch")
    assert r.access == ACCESS_RESTRICTED
    assert r.text == ""  # 不越权获取受版权保护全文

    r2 = fetch_fulltext(
        "https://arxiv.org/abs/1", robots_disallowed=True, getter=lambda u: b"x"
    )
    assert r2.access == ACCESS_BLOCKED
    assert r2.text == ""


# ---------------------------------------------------------------- 结论绑定
def test_conclusion_binds_source_locator_paragraph_time_scope_expires():
    c = Conclusion(
        source="arxiv.org",
        locator="sec.3.2 ¶2",
        paragraph="The agent uses a faceted B-Rep model.",
        scope="full_text",
        expires_at=default_expires_at(days=180),
        binding="https://arxiv.org/abs/2401.12345",
    )
    d = c.to_dict()
    assert d["source"] == "arxiv.org"
    assert d["locator"] == "sec.3.2 ¶2"
    assert d["paragraph"].endswith("model.")
    assert d["retrieved_at"]
    assert d["scope"] == "full_text"
    assert d["expires_at"]
    assert d["binding"] == "https://arxiv.org/abs/2401.12345"
    # 可写
    c.locator = "sec.4"
    assert c.to_dict()["locator"] == "sec.4"


def test_conclusion_expiry_and_refetch_policy():
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=1)).isoformat()
    future = (now + timedelta(days=30)).isoformat()

    expired = Conclusion(source="s", expires_at=past)
    assert expired.is_expired(now=now) is True
    assert expired.refetch_due(now=now) is True
    assert refetch_strategy(past, now=now) == "sync"

    fresh = Conclusion(source="s", expires_at=future)
    assert fresh.is_expired(now=now) is False
    assert fresh.refetch_due(now=now) is False
    assert refetch_strategy(future, now=now) == "none"

    never = Conclusion(source="s")
    assert never.is_expired() is False
    assert never.refetch_due() is False
    assert refetch_strategy(None) == "none"


# ---------------------------------------------------------------- 可替换 Provider
def test_providers_default_to_external_dependency():
    for prov in (standard_provider(), regulation_provider(), patent_provider(), competitor_provider()):  # noqa: E501
        assert prov.available() is False  # 未配置 -> external_dependency
        assert prov.provide("anything") == []  # 诚实等待，不伪造结果
        assert prov.kind in {"standard", "regulation", "patent", "competitor"}


def test_provider_with_injected_impl_delegates():
    class FakeImpl(ExternalProvider):
        def __init__(self, kind):
            super().__init__(kind)

        def available(self):
            return True

        def provide(self, query):
            return [{"key": query, "value": "x"}]

    p = patent_provider(FakeImpl("patent"))
    assert p.available() is True
    assert p.provide("q") == [{"key": "q", "value": "x"}]
