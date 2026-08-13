"""v5.8.1 Commit 12：CLI status 动态 capability probe 测试。

覆盖：
- probe_research_capabilities：AdapterRegistry 无 research adapter → 全部
  UNAVAILABLE；注册 provider 后 → AVAILABLE；
- cmd_status 输出 capabilities 分 AVAILABLE/UNAVAILABLE；blocked 列
  UNAVAILABLE（不再硬编码 RESEARCH_CAPABILITIES）。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from aipd_os.cli.commands import cmd_status, probe_research_capabilities
from aipd_os.execution.research_integration import ResearchToolAdapter
from aipd_os.idea import Idea, IdeaService
from aipd_os.state.db import AIPDStateDB
from aipd_os.tool_adapters.builtin import build_registry
from tests.fixtures.idea.research_fixtures import FakeResearchProvider


def _env(tmp_path):
    db_path = str(tmp_path / "state.db")
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="I", raw_input="r"), actor="alice")
    return db_path


# ---------------------------------------------------------------------------
# 1) probe_research_capabilities 动态
# ---------------------------------------------------------------------------
def test_probe_unavailable_when_no_adapter(tmp_path):
    """无 research adapter → 全部 UNAVAILABLE（诚实，不硬编码也非伪造）。"""
    registry = build_registry()
    probe = probe_research_capabilities(registry)
    assert probe["available"] == []
    assert "research.academic_search" in probe["unavailable"]
    assert "research.novelty_check" in probe["unavailable"]


def test_probe_available_after_registration(tmp_path):
    """注册 research provider → 对应 capability 变 AVAILABLE。"""
    registry = build_registry()
    registry.register(ResearchToolAdapter(FakeResearchProvider(
        capability_id="research.academic_search",
        result={"sources": [], "provider": "fake"})))
    probe = probe_research_capabilities(registry)
    assert "research.academic_search" in probe["available"]
    assert "research.academic_search" not in probe["unavailable"]
    # 未注册的仍 UNAVAILABLE
    assert "research.novelty_check" in probe["unavailable"]


# ---------------------------------------------------------------------------
# 2) cmd_status 输出（真实 CLI service 层）
# ---------------------------------------------------------------------------
def test_status_capabilities_dynamic(tmp_path, capsys):
    """注册 provider 前 status 显示 UNAVAILABLE；注册后显示 AVAILABLE。"""
    db_path = _env(tmp_path)

    # 未注册 → blocked = UNAVAILABLE
    args = SimpleNamespace(db=db_path, project="P1", json=True,
                           markdown=False, capability_registry=build_registry())
    cmd_status(args)
    data = json.loads(capsys.readouterr().out)
    cap = data["idea"]["capabilities"]
    assert "research.academic_search" in cap["unavailable"]
    assert "research.academic_search" not in cap["available"]
    assert data["idea"]["blocked_capabilities"] == cap["unavailable"]
    assert data["idea"]["note"] == "CAPABILITY_UNAVAILABLE"

    # 注册 provider 后 → AVAILABLE，blocked 减少
    reg = build_registry()
    reg.register(ResearchToolAdapter(FakeResearchProvider(
        capability_id="research.academic_search",
        result={"sources": [], "provider": "fake"})))
    args2 = SimpleNamespace(db=db_path, project="P1", json=True,
                            markdown=False, capability_registry=reg)
    cmd_status(args2)
    data2 = json.loads(capsys.readouterr().out)
    cap2 = data2["idea"]["capabilities"]
    assert "research.academic_search" in cap2["available"]
    assert "research.academic_search" not in data2["idea"]["blocked_capabilities"]
