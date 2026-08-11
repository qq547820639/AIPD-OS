"""内置适配器测试：discover / validate / execute（或写外部任务包）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from aipd_os.execution.adapter import AdapterError
from aipd_os.tool_adapters.builtin import build_registry


def test_all_builtin_adapters_discover_validate_execute(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("AIPD_RESEARCH_API_KEY", raising=False)
    monkeypatch.delenv("AIPD_IMGGEN_BACKEND", raising=False)
    monkeypatch.delenv("AIPD_CAD_PROVIDER", raising=False)
    reg = build_registry()
    for adapter in reg.all():
        meta = adapter.discover()
        for key in ("id", "name", "provider", "version", "maturity_ceiling", "available"):
            assert key in meta
        assert isinstance(adapter.validate_input({}), list)
        try:
            result = adapter.execute({})
            assert isinstance(result, dict)
        except AdapterError as exc:
            assert exc.classification == "external_blocked"
            assert exc.task_package and Path(exc.task_package).is_file()


def test_maturity_ceilings():
    reg = build_registry()
    assert reg.get("cad.faceted-fallback").discover()["maturity_ceiling"] == "C1"
    assert reg.get("cad.local-brep").discover()["maturity_ceiling"] == "C2"


def test_research_unavailable_writes_task_package(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("AIPD_RESEARCH_API_KEY", raising=False)
    reg = build_registry()
    a = reg.get("research.search_papers")
    assert a.discover()["available"] is False
    with pytest.raises(AdapterError) as ei:
        a.execute({"query": "steady state"})
    assert ei.value.classification == "external_blocked"
    assert ei.value.task_package and Path(ei.value.task_package).is_file()


def test_research_available_real_sources(monkeypatch):
    """配置 key + Semantic Scholar 正常响应 → 返回真实 sources，无 simulated 标记。"""
    import json
    import urllib.request

    monkeypatch.setenv("AIPD_RESEARCH_API_KEY", "dummy")
    reg = build_registry()
    a = reg.get("research.search_papers")
    assert a.discover()["available"] is True

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"data": [
                {"title": "Real Paper", "authors": [{"name": "Alice"}],
                 "year": 2023, "url": "https://api.semanticscholar.org/paper/1",
                 "abstract": "real abstract"},
            ]}).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = a.execute({"query": "q", "n": 2})
    assert "sources" in out
    assert len(out["sources"]) == 1
    assert out["sources"][0]["title"] == "Real Paper"
    assert out["sources"][0]["authors"] == ["Alice"]
    assert "simulated" not in out["sources"][0]


def test_research_http_error_external_blocked(monkeypatch, tmp_path):
    """配置 key + HTTP 错误 → external_blocked（不抛透传异常、不伪造结果）。"""
    import urllib.error
    import urllib.request

    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("AIPD_RESEARCH_API_KEY", "dummy")
    reg = build_registry()
    a = reg.get("research.search_papers")

    def fake_urlopen(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 429, "rate limited", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(AdapterError) as ei:
        a.execute({"query": "q"})
    assert ei.value.classification == "external_blocked"
    assert ei.value.task_package and Path(ei.value.task_package).is_file()


def test_research_api_key_sent_as_header(monkeypatch):
    """配置语义 == 网络调用语义：AIPD_RESEARCH_API_KEY 真实用于 x-api-key header。"""
    import json
    import urllib.request

    monkeypatch.setenv("AIPD_RESEARCH_API_KEY", "secret-key-123")
    reg = build_registry()
    a = reg.get("research.search_papers")

    seen_headers = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"data": [
                {"title": "P", "authors": [], "year": 2023, "url": "https://x/y"},
            ]}).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        seen_headers.update(req.headers)
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = a.execute({"query": "q"})
    assert "sources" in out
    # urllib 会把 header 名归一化为 Title-Case（X-api-key）
    headers_lower = {k.lower(): v for k, v in seen_headers.items()}
    assert headers_lower.get("x-api-key") == "secret-key-123", (
        "配置的 key 必须真实出现在网络请求 header 中")


def test_research_no_key_does_not_send_x_api_key_header(monkeypatch):
    """未配置 key → 请求不带 x-api-key（且适配器保守 external_dependency）。"""
    import urllib.request

    monkeypatch.delenv("AIPD_RESEARCH_API_KEY", raising=False)
    reg = build_registry()
    a = reg.get("research.search_papers")
    assert a.discover()["available"] is False

    seen_headers = {}

    def fake_urlopen(req, timeout=0):  # 不应被调用（execute 在 available 检查即停）
        seen_headers.update(req.headers)
        raise AssertionError("execute should fail before network call")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    from aipd_os.execution.adapter import AdapterError

    with pytest.raises(AdapterError) as ei:
        a.execute({"query": "q"})
    assert ei.value.classification == "external_blocked"


def test_faceted_writes_real_step_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    a = reg.get("cad.faceted-fallback")
    out = a.execute({})
    assert out.get("path")
    assert Path(out["path"]).is_file()
    text = Path(out["path"]).read_text(encoding="ascii")
    assert text.startswith("ISO-10303-21;")
    assert "FACETED_BREP(" in text
    assert a.collect_artifacts(out) == [out["path"]]
