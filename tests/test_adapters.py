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


def test_research_available_simulated(monkeypatch):
    monkeypatch.setenv("AIPD_RESEARCH_API_KEY", "dummy")
    reg = build_registry()
    a = reg.get("research.search_papers")
    assert a.discover()["available"] is True
    out = a.execute({"query": "q", "n": 2})
    assert "sources" in out
    assert len(out["sources"]) == 2


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
