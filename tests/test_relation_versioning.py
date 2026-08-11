"""v5.8.1 Commit 7：EvidenceRelation versioning + 并发安全 ID 测试。

覆盖：
- add 不再 INSERT OR REPLACE：同 (claim_id, evidence_id, relation_type) 重复
  add → EvidenceRelationConflictError（不删旧行、created_at 不变、version 不重置）；
- get_or_create 幂等语义：重复 → 返回现有 relation（created=False）；
- update 走 expected_version 递增 version_no + audit；created_at 不变；
- 并发安全 ID：多线程生成 idea/claim/relation id 无重复（id_sequences 原子分配）。
"""
from __future__ import annotations

import threading

import pytest

from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceRelation,
    EvidenceRelationConflictError,
    EvidenceRelationOptimisticLockError,
    EvidenceRelationService,
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
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="P1",
              idea_id=idea.idea_id, claim_type="problem",
              statement="s", epistemic_status="A"))
    relations = EvidenceRelationService(db)
    return {"db": db, "idea": idea, "claim": claim, "relations": relations}


def _ev(db, title="t"):
    return db.add_evidence("default", "P1", kind="paper", title=title,
                           url=f"https://example.invalid/{title}")


def _rel(claim, evidence, rtype="supports", **kw):
    return EvidenceRelation(relation_id="", tenant_id="default", project_id="P1",
                            claim_id=claim.claim_id, evidence_id=evidence,
                            relation_type=rtype, **kw)


# ---------------------------------------------------------------------------
# 1) add 不再 INSERT OR REPLACE
# ---------------------------------------------------------------------------
def test_evidence_add_not_replace_relation(env):
    """同 key 重复 add → conflict；旧 row 不被删除、created_at 不变、version 不重置。"""
    db = env["db"]
    claim = env["claim"]
    relations = env["relations"]
    ev = _ev(db)
    rel = relations.add(_rel(claim, ev, "supports"), actor="alice")
    created_at = rel.created_at
    # 同 (claim, evidence, relation_type) 再次 add → typed conflict
    with pytest.raises(EvidenceRelationConflictError) as ei:
        relations.add(_rel(claim, ev, "supports"), actor="bob")
    assert "already exists" in str(ei.value)
    # 旧 row 未被删除：仍可查到，created_at 不变，version_no 仍为 1
    got = relations.get("default", "P1", rel.relation_id)
    assert got.created_at == created_at
    assert got.version_no == 1
    assert got.review_status == "pending"
    assert len(relations.list_for_claim("default", "P1", claim.claim_id)) == 1
    # 不同 relation_type 可共存（不冲突）
    rel2 = relations.add(_rel(claim, ev, "contradicts"), actor="alice")
    assert rel2.relation_id != rel.relation_id
    assert len(relations.list_for_claim("default", "P1", claim.claim_id)) == 2


def test_duplicate_add_returns_existing_or_conflict(env):
    """get_or_create 幂等：重复 → 返回现有 relation（created=False）。"""
    db = env["db"]
    claim = env["claim"]
    relations = env["relations"]
    ev = _ev(db)
    created, is_new = relations.get_or_create(_rel(claim, ev, "supports"), actor="alice")
    assert is_new is True
    existing, is_new2 = relations.get_or_create(_rel(claim, ev, "supports"), actor="bob")
    assert is_new2 is False
    assert existing.relation_id == created.relation_id
    # created_at 保持首次值
    assert existing.created_at == created.created_at
    # 仅一次 audit（evidence_relation.add 只有一次）
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert actions.count("evidence_relation.add") == 1


# ---------------------------------------------------------------------------
# 2) version history：update 走乐观锁 + audit；created_at 不变
# ---------------------------------------------------------------------------
def test_relation_version_history(env):
    """update 用 expected_version 递增 version_no + audit；created_at 不变。"""
    db = env["db"]
    claim = env["claim"]
    relations = env["relations"]
    ev = _ev(db)
    rel = relations.add(_rel(claim, ev, "supports"), actor="alice")
    created_at = rel.created_at

    updated = relations.update("default", "P1", rel.relation_id,
                               expected_version=1, actor="bob",
                               review_status="reviewed")
    assert updated.version_no == 2
    assert updated.review_status == "reviewed"
    assert updated.created_at == created_at  # created_at 不变
    # 乐观锁：旧版本号冲突
    with pytest.raises(EvidenceRelationOptimisticLockError):
        relations.update("default", "P1", rel.relation_id,
                         expected_version=1, review_status="rejected")
    # audit
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert actions.count("evidence_relation.update") == 1


# ---------------------------------------------------------------------------
# 3) 并发安全 ID（id_sequences 原子分配，替代 scan-max）
# ---------------------------------------------------------------------------
def test_concurrent_id_generation_no_duplicate(tmp_path):
    """多线程并发 create → 无重复 ID（sequence table 串行化分配）。"""
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    ideas = IdeaService(db)
    results: list[str] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            idea = ideas.create(Idea(idea_id="", tenant_id="default",
                                     project_id="P1", title="t", raw_input="r"),
                                actor="t")
            with lock:
                results.append(idea.idea_id)
        except Exception as exc:  # pragma: no cover - 记录并发失败
            with lock:
                errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"并发 create 失败: {errors}"
    assert len(results) == 8
    assert len(set(results)) == 8  # 无重复 ID
    assert len(ideas.list("default", "P1")) == 8
    # 继续串行创建 → ID 不回落
    extra = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                              title="t", raw_input="r"), actor="t").idea_id
    assert extra not in set(results)


def test_sequence_resumes_after_legacy_data(tmp_path):
    """已有存量 id（IDEA-001..00N）的库：新 id 从 max+1 继续（migration v5 seed）。"""
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    svc = IdeaService(db)
    # 预置存量数据（模拟 v5 之前的库）
    with db.connect() as c:
        for i in range(1, 4):
            c.execute(
                "INSERT INTO ideas(idea_id,project_id,tenant_id,title,raw_input,"
                "goal,problem,target_user,desired_outcome,constraints_json,source,"
                "lifecycle_status,version_no,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"IDEA-00{i}", "P1", "default", f"t{i}", "r", "", "", "", "",
                 "{}", "", "active", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))
    # 对齐 migration v5 seed 语义（next_val = 现有最大编号）
    with db.connect() as c:
        c.execute("UPDATE id_sequences SET next_val = 3 WHERE name = 'idea'")
    new_idea = svc.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                               title="new", raw_input="r"), actor="t")
    assert new_idea.idea_id == "IDEA-004"
