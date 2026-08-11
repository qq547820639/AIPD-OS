"""v5.8 Commit 12：IdeaDecomposer Provider 抽象测试。

覆盖：
- 无 provider → CAPABILITY_UNAVAILABLE（诚实失败，不写 DB）；
- Fake provider → Structured Idea + 8 Claims 全部创建，默认 A 非 V；
- schema validation：非法输出（缺字段/坏 JSON）→ FAILED_VALIDATION 不落库；
- persist 后 audit 可查 + tenant/project scoped；
- provider 经 ProviderRegistry 注册后可路由（capability 架构对齐）。
"""
from __future__ import annotations

import pytest

from aipd_os.idea import (
    CAPABILITY_UNAVAILABLE,
    IDEA_DECOMPOSE_CAPABILITY,
    ClaimService,
    IdeaDecomposer,
    IdeaDecompositionProviderAdapter,
    IdeaDecompositionUnavailable,
    IdeaDecompositionValidationError,
    IdeaService,
    StructuredCandidate,
    UnavailableProvider,
)
from aipd_os.providers.sdk import ProviderRegistry
from aipd_os.state.db import AIPDStateDB
from tests.fixtures.idea.decomposer_fixtures import (
    ELDERLY_REHAB_PROMPT,
    BrokenFakeIdeaDecompositionProvider,
    FakeIdeaDecompositionProvider,
)


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    return db


def _decomposer(db, provider=None):
    return IdeaDecomposer(db, provider=provider, tenant_id="default", project_id="P1")


# ---------------------------------------------------------------------------
# 1) 无 provider → CAPABILITY_UNAVAILABLE（诚实失败，不写 DB）
# ---------------------------------------------------------------------------
def test_no_provider_raises_capability_unavailable(env):
    db = env
    d = _decomposer(db)  # provider=None
    with pytest.raises(IdeaDecompositionUnavailable) as ei:
        d.decompose_and_persist(ELDERLY_REHAB_PROMPT)
    assert CAPABILITY_UNAVAILABLE in str(ei.value)
    # 不写 DB：无 idea、无 claims
    assert IdeaService(db).list("default", "P1") == []
    assert ClaimService(db).list("default", "P1") == []


def test_unavailable_provider_honest(env):
    d = _decomposer(env, provider=UnavailableProvider())
    assert d._provider.available() is False
    with pytest.raises(IdeaDecompositionUnavailable):
        d.decompose_and_persist(ELDERLY_REHAB_PROMPT)


# ---------------------------------------------------------------------------
# 2) Fake provider → Structured Idea + Claims 全创建，默认 A/U 非 V
# ---------------------------------------------------------------------------
def test_fake_provider_persists_idea_and_claims(env):
    db = env
    provider = FakeIdeaDecompositionProvider()
    d = _decomposer(db, provider=provider)
    result = d.decompose_and_persist(ELDERLY_REHAB_PROMPT, actor="alice")

    idea = result["idea"]
    assert idea["idea_id"].startswith("IDEA-")
    assert idea["lifecycle_status"] == "structured"
    assert idea["tenant_id"] == "default" and idea["project_id"] == "P1"
    assert len(result["claims"]) == 8  # fixture 8 claims
    # 默认 A，绝不 V
    for c in result["claims"]:
        assert c["epistemic_status"] in ("A", "U")
        assert c["epistemic_status"] != "V"

    # DB 层确认
    ideas = IdeaService(db).list("default", "P1")
    assert len(ideas) == 1
    claims = ClaimService(db).list("default", "P1")
    assert len(claims) == 8
    assert all(c.idea_id == idea["idea_id"] for c in claims)


# ---------------------------------------------------------------------------
# 3) schema validation：非法输出 → FAILED_VALIDATION 不落库
# ---------------------------------------------------------------------------
def test_invalid_candidate_fails_validation_no_db_write(env):
    db = env
    d = _decomposer(db, provider=BrokenFakeIdeaDecompositionProvider())
    with pytest.raises(IdeaDecompositionValidationError) as ei:
        d.decompose_and_persist(ELDERLY_REHAB_PROMPT)
    assert ei.value.errors  # 校验错误非空
    # 不落库
    assert IdeaService(db).list("default", "P1") == []
    assert ClaimService(db).list("default", "P1") == []


def test_validate_detects_missing_fields():
    bad = StructuredCandidate(title="", goal="g", problem="p", target_user="u",
                              desired_outcome="o", constraints=[], claims=[])
    errors = IdeaDecomposer.validate(bad)
    assert errors  # title empty / claims empty → 校验失败
    good = FakeIdeaDecompositionProvider().decompose("x")
    assert IdeaDecomposer.validate(good) == []


# ---------------------------------------------------------------------------
# 4) audit 可查 + tenant/project scoped
# ---------------------------------------------------------------------------
def test_persist_is_audited_and_scoped(env):
    db = env
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    d.decompose_and_persist(ELDERLY_REHAB_PROMPT, actor="alice")
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "idea.decompose" in actions
    assert "idea.create" in actions
    assert "claim.create" in actions
    dec = next(r for r in db.list_audit(limit=100)
               if r["action"] == "idea.decompose")
    assert dec["actor"] == "alice"
    assert dec["tenant_id"] == "default" and dec["project_id"] == "P1"
    # 其他 project 不可见
    assert IdeaService(db).list("default", "P2") == []
    assert ClaimService(db).list("default", "P2") == []


# ---------------------------------------------------------------------------
# 5) ProviderRegistry 注册后可路由（capability 架构对齐）
# ---------------------------------------------------------------------------
def test_provider_registered_in_provider_registry(env):
    registry = ProviderRegistry()
    adapter = IdeaDecompositionProviderAdapter(FakeIdeaDecompositionProvider())
    registry.register(adapter)
    assert IDEA_DECOMPOSE_CAPABILITY in registry.capability_ids()
    prov = registry.get_by_capability(IDEA_DECOMPOSE_CAPABILITY)
    assert prov is not None
    # probe 可用
    assert prov.probe().available is True
    # run 返回 candidate
    out = prov.run({"raw_input": ELDERLY_REHAB_PROMPT})
    assert out["candidate"]["title"]
    assert len(out["candidate"]["claims"]) == 8
    # 不可用 provider 注册后 probe 诚实
    registry2 = ProviderRegistry()
    registry2.register(IdeaDecompositionProviderAdapter(UnavailableProvider()))
    assert registry2.get_by_capability(IDEA_DECOMPOSE_CAPABILITY).probe().available is False
