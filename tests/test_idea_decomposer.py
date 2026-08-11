"""v5.8 Commit 12 / v5.8.1 Commit 2：IdeaDecomposer Provider 抽象测试。

覆盖：
- 无 provider → CAPABILITY_UNAVAILABLE（诚实失败，不写 DB）；
- Fake provider → Structured Idea + 8 Claims 全部创建，默认 A 非 V；
- schema validation：非法输出（缺字段/坏 JSON）→ FAILED_VALIDATION 不落库；
- persist 后 audit 可查 + tenant/project scoped；
- provider 经 ProviderRegistry 注册后可路由（capability 架构对齐）；
- v5.8.1：decompose_existing 保持 Idea 身份连续性（同一 idea_id，raw_input
  保留，lifecycle → structured，claims 挂同一 idea）；
- v5.8.1：constraints_json 走 serializer（真 JSON 写入 + 旧 repr 兼容读取）。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.idea import (
    CAPABILITY_UNAVAILABLE,
    IDEA_DECOMPOSE_CAPABILITY,
    ClaimService,
    Idea,
    IdeaDecomposer,
    IdeaDecompositionProviderAdapter,
    IdeaDecompositionUnavailable,
    IdeaDecompositionValidationError,
    IdeaNotFoundError,
    IdeaService,
    StructuredCandidate,
    UnavailableProvider,
    parse_constraints,
    serialize_constraints,
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
    assert idea["lifecycle_status"] == "active"  # 对象生命状态（Commit 3）
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


# ---------------------------------------------------------------------------
# 6) v5.8.1 Commit 2：decompose_existing 保持 Idea 身份连续性（I0→I1 同一记录）
# ---------------------------------------------------------------------------
def _intake_raw_idea(db, raw_input: str = ELDERLY_REHAB_PROMPT):
    """intake：创建 raw Idea（I0）。"""
    svc = IdeaService(db)
    raw = svc.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                          title="raw", raw_input=raw_input, goal=raw_input,
                          lifecycle_status="raw"), actor="alice")
    assert raw.idea_id.startswith("IDEA-")
    return raw


def test_decompose_existing_same_idea_id(env):
    """intake 创建 raw Idea → decompose_existing → 返回同一个 idea_id，
    lifecycle 变为 structured，claims 挂在该 idea 下（不再产生第二个 Idea）。"""
    db = env
    raw = _intake_raw_idea(db)
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())

    result = d.decompose_existing(raw.idea_id, actor="alice")

    # 身份连续性：同一个 idea_id
    assert result["idea"]["idea_id"] == raw.idea_id
    assert result["idea"]["lifecycle_status"] == "active"  # 对象生命状态（Commit 3）
    assert result["idea"]["version_no"] == raw.version_no + 1
    # 只存在 1 个 Idea（不是两个）
    ideas = IdeaService(db).list("default", "P1")
    assert len(ideas) == 1
    assert ideas[0].idea_id == raw.idea_id
    # 8 claims 全部挂在同一 idea 下
    claims = ClaimService(db).list("default", "P1")
    assert len(claims) == 8
    assert all(c.idea_id == raw.idea_id for c in claims)
    assert all(c.epistemic_status in ("A", "U") and c.epistemic_status != "V"
               for c in claims)


def test_decompose_existing_preserves_raw_input(env):
    """结构化后 raw_input 必须等于用户原始输入，绝不置空。"""
    db = env
    raw = _intake_raw_idea(db, raw_input=ELDERLY_REHAB_PROMPT)
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    result = d.decompose_existing(raw.idea_id)
    assert result["idea"]["raw_input"] == ELDERLY_REHAB_PROMPT
    got = IdeaService(db).get("default", "P1", raw.idea_id)
    assert got.raw_input == ELDERLY_REHAB_PROMPT
    # created_at 不变（同一记录）
    assert got.created_at == raw.created_at


def test_decompose_existing_persist_writes_real_json_constraints(env):
    """结构化后 constraints_json 是合法 JSON（json.loads 通过），且可解析回列表。"""
    db = env
    raw = _intake_raw_idea(db)
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    d.decompose_existing(raw.idea_id)
    got = IdeaService(db).get("default", "P1", raw.idea_id)
    parsed = json.loads(got.constraints_json)  # 真 JSON，不是 repr
    assert isinstance(parsed, dict)
    assert parsed["constraints"] == ["单摄像头即可", "离线可运行", "不依赖护工在场"]
    # IdeaService 经 serializer 读取
    assert IdeaService(db).get_constraints("default", "P1", raw.idea_id) == \
        parsed["constraints"]


def test_decompose_existing_no_provider_honest(env):
    """decompose_existing 无 provider → CAPABILITY_UNAVAILABLE，不写库。"""
    db = env
    raw = _intake_raw_idea(db)
    d = _decomposer(db)  # provider=None
    with pytest.raises(IdeaDecompositionUnavailable) as ei:
        d.decompose_existing(raw.idea_id)
    assert CAPABILITY_UNAVAILABLE in str(ei.value)
    # raw idea 未被修改（仍 raw、无 claims）
    got = IdeaService(db).get("default", "P1", raw.idea_id)
    assert got.lifecycle_status == "active"  # 旧值 raw 兼容映射 active
    assert ClaimService(db).list("default", "P1") == []


def test_decompose_existing_unknown_idea_raises(env):
    """decompose_existing 对不存在的 idea → IdeaNotFoundError（scope 校验）。"""
    db = env
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    with pytest.raises(IdeaNotFoundError):
        d.decompose_existing("IDEA-999")


def test_decompose_existing_validation_failure_no_write(env):
    """decompose_existing 校验失败 → FAILED_VALIDATION，不写库。"""
    db = env
    raw = _intake_raw_idea(db)
    d = _decomposer(db, provider=BrokenFakeIdeaDecompositionProvider())
    with pytest.raises(IdeaDecompositionValidationError) as ei:
        d.decompose_existing(raw.idea_id)
    assert ei.value.errors
    got = IdeaService(db).get("default", "P1", raw.idea_id)
    assert got.lifecycle_status == "active"  # 未被结构化（对象仍 active）
    assert ClaimService(db).list("default", "P1") == []


def test_decompose_existing_is_audited(env):
    """decompose_existing 写 audit（action=idea.structure）+ idea.update。"""
    db = env
    raw = _intake_raw_idea(db)
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    d.decompose_existing(raw.idea_id, actor="alice")
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "idea.structure" in actions
    assert "idea.update" in actions
    assert "claim.create" in actions
    rec = next(r for r in db.list_audit(limit=100)
               if r["action"] == "idea.structure")
    assert rec["actor"] == "alice"
    after = json.loads(rec["after_json"])
    assert after["idea_id"] == raw.idea_id
    assert after["lifecycle_status"] == "active"


def test_decompose_existing_empty_raw_input_honest(env):
    """raw_input 为空的 idea 无法结构化 → 诚实失败（不伪造结果）。"""
    db = env
    svc = IdeaService(db)
    empty = svc.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                            title="empty", raw_input="", goal="",
                            lifecycle_status="raw"), actor="alice")
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    with pytest.raises(ValueError, match="empty raw_input"):
        d.decompose_existing(empty.idea_id)
    assert svc.get("default", "P1", empty.idea_id).lifecycle_status == "active"


def test_decompose_and_persist_still_independent_new_idea(env):
    """decompose_and_persist 仍是独立「新建」API：不依赖已存在 idea。"""
    db = env
    d = _decomposer(db, provider=FakeIdeaDecompositionProvider())
    result = d.decompose_and_persist(ELDERLY_REHAB_PROMPT, actor="alice")
    # 新建 Idea：raw_input 同样保留（v5.8.1 修复）
    assert result["idea"]["raw_input"] == ELDERLY_REHAB_PROMPT
    assert result["idea"]["lifecycle_status"] == "active"  # 对象生命状态（Commit 3）
    ideas = IdeaService(db).list("default", "P1")
    assert len(ideas) == 1
    assert ideas[0].idea_id == result["idea"]["idea_id"]


# ---------------------------------------------------------------------------
# 7) v5.8.1 Commit 2：constraints_json serializer（真 JSON + 旧 repr 兼容）
# ---------------------------------------------------------------------------
def test_constraints_json_roundtrip():
    """serialize → parse 往返一致；新写入是合法 JSON。"""
    constraints = ["单摄像头即可", "离线可运行", "不依赖护工在场"]
    s = serialize_constraints(constraints)
    # 新写入必须是真 JSON（json.loads 通过，且不是 Python repr）
    data = json.loads(s)
    assert data == {"constraints": constraints}
    assert s == '{"constraints": ["单摄像头即可", "离线可运行", "不依赖护工在场"]}'
    # 往返一致
    assert parse_constraints(s) == constraints


def test_parse_constraints_legacy_repr_compatible():
    """旧 DB 中 repr 字符串（v5.8 str({...})）parse 成功。"""
    legacy = str({"constraints": ["单摄像头即可", "离线可运行"]})
    assert legacy.startswith("{'constraints':")  # 确实是旧 repr 形态
    assert parse_constraints(legacy) == ["单摄像头即可", "离线可运行"]
    # 纯列表 / 空值 / None 均兼容
    assert parse_constraints('["a", "b"]') == ["a", "b"]
    assert parse_constraints("{}") == []
    assert parse_constraints("") == []
    assert parse_constraints(None) == []
    # 既非 JSON 也非 repr → 显式失败
    with pytest.raises(ValueError):
        parse_constraints("not-a-constraints-{{{")


def test_idea_constraints_property_parses_legacy(env):
    """Idea.constraints property + IdeaService.get_constraints 兼容旧 repr。"""
    db = env
    svc = IdeaService(db)
    idea = svc.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                           title="legacy", raw_input="x",
                           constraints_json=str({"constraints": ["a", "b"]}),
                           lifecycle_status="raw"), actor="alice")
    assert idea.constraints == ["a", "b"]
    assert svc.get_constraints("default", "P1", idea.idea_id) == ["a", "b"]
