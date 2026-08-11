"""v5.8 Commit 10：Claim Domain 测试。

覆盖：
- CRUD + scope 隔离（tenant/project/idea 三重）；
- 默认 epistemic_status 为 A（Assumption）或 U，绝不默认 V；
- 非法 claim_type / 非法 epistemic_status 拒绝；
- audit + version 乐观锁；
- tenantA 不能改 tenantB 的 claim；
- 创建 Claim 时校验 idea 存在且同 scope。
"""
from __future__ import annotations

import pytest

from aipd_os.idea import (
    Claim,
    ClaimNotFoundError,
    ClaimOptimisticLockError,
    ClaimScopeError,
    ClaimService,
    Idea,
    IdeaService,
)
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    ideas = IdeaService(db)
    idea = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                             title="Idea 1", raw_input="raw"))
    return db, ClaimService(db), idea


def _claim(idea, **kw):
    defaults = dict(
        claim_id="", idea_id=idea.idea_id, claim_type="problem",
        statement="老年人希望独立行走更久",
        epistemic_status="A", confidence=0.6, source="user-interview",
    )
    defaults.update(kw)
    return Claim(tenant_id="default", project_id="P1", **defaults)


# ---------------------------------------------------------------------------
# 1) CRUD
# ---------------------------------------------------------------------------
def test_claim_crud(env):
    db, svc, idea = env
    claim = svc.create(_claim(idea))
    assert claim.claim_id.startswith("CLM-")
    assert claim.epistemic_status == "A"  # Candidate Claim = Assumption

    got = svc.get("default", "P1", claim.claim_id)
    assert got.statement == "老年人希望独立行走更久"
    assert got.idea_id == idea.idea_id

    updated = svc.update("default", "P1", claim.claim_id, expected_version=1,
                         epistemic_status="E", confidence=0.8)
    assert updated.version_no == 2
    assert updated.epistemic_status == "E"

    claims = svc.list("default", "P1")
    assert [c.claim_id for c in claims] == [claim.claim_id]
    assert [c.claim_id for c in svc.list("default", "P1", idea_id=idea.idea_id)] == [claim.claim_id]


# ---------------------------------------------------------------------------
# 2) scope 隔离（tenant/project/idea 三重）
# ---------------------------------------------------------------------------
def test_claim_tenant_scope_isolation(env):
    db, svc, idea = env
    db.ensure_default_tenant("tenantB")
    db.init_project("tenantB", "PB", "PB", "g")
    claim = svc.create(_claim(idea))
    with pytest.raises((ClaimNotFoundError, KeyError)):
        svc.get("tenantB", "PB", claim.claim_id)
    with pytest.raises((ClaimNotFoundError, KeyError)):
        svc.update("tenantB", "PB", claim.claim_id, expected_version=1,
                   statement="hacked")
    assert svc.list("tenantB", "PB") == []


def test_claim_project_scope_isolation(env):
    db, svc, idea = env
    db.init_project("default", "P2", "P2", "g")
    claim = svc.create(_claim(idea))  # project P1
    with pytest.raises((ClaimNotFoundError, KeyError)):
        svc.get("default", "P2", claim.claim_id)
    assert svc.list("default", "P2") == []


def test_claim_rejects_idea_from_other_project(env):
    db, svc, idea = env
    db.init_project("default", "P2", "P2", "g")
    other_idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P2", title="other"))
    # 在 P1 创建指向 P2 idea 的 claim → 拒绝（同 scope 校验）
    with pytest.raises(ClaimScopeError):
        svc.create(_claim(idea, idea_id=other_idea.idea_id))


# ---------------------------------------------------------------------------
# 3) 默认认知状态：A 或 U，绝不默认 V；非法值拒绝
# ---------------------------------------------------------------------------
def test_claim_default_epistemic_status_not_verified(env):
    _, svc, idea = env
    claim = svc.create(_claim(idea))
    assert claim.epistemic_status in ("A", "U")
    assert claim.epistemic_status != "V"
    # 显式 U 也合法（unknown）
    c2 = svc.create(_claim(idea, epistemic_status="U"))
    assert c2.epistemic_status == "U"


def test_claim_invalid_claim_type_rejected(env):
    _, svc, idea = env
    with pytest.raises(ValueError, match="claim_type"):
        svc.create(_claim(idea, claim_type="bogus"))


def test_claim_invalid_epistemic_status_rejected(env):
    _, svc, idea = env
    with pytest.raises(ValueError, match="epistemic_status"):
        svc.create(_claim(idea, epistemic_status="X"))
    claim = svc.create(_claim(idea))
    with pytest.raises(ValueError, match="epistemic_status"):
        svc.update("default", "P1", claim.claim_id, expected_version=1,
                   epistemic_status="Z")


# ---------------------------------------------------------------------------
# 4) audit + 乐观锁
# ---------------------------------------------------------------------------
def test_claim_writes_are_audited_and_locked(env):
    db, svc, idea = env
    claim = svc.create(_claim(idea), actor="alice")
    svc.update("default", "P1", claim.claim_id, expected_version=1,
               statement="updated", actor="bob")
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "claim.create" in actions and "claim.update" in actions
    with pytest.raises(ClaimOptimisticLockError):
        svc.update("default", "P1", claim.claim_id, expected_version=1,
                   statement="stale")
