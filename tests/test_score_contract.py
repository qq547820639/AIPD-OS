"""Score Contract 测试（v5.8.2 Commit 8）。

锁定：
- 新记录未评分 → DB 存 NULL（不再落 0.5 哨兵）；
- 旧库 0.5（legacy_unscored）读取时映射 None；
- migration v9 把 claims.confidence / relations.strength 改为 NULLABLE
  （v9 up/down 往返安全）；
- ID 生成：facts/decisions/deliverables/risks/evidence(get_or_create) 全部
  走 id_sequences（无 scan-max race）。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.idea.claim_service import ClaimService
from aipd_os.idea.claims import Claim
from aipd_os.idea.evidence_relations import (
    EvidenceRelation,
    EvidenceRelationService,
)
from aipd_os.state import migrations as mig
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def db(tmp_path):
    return AIPDStateDB(str(tmp_path / "state.db"))


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


# ---------------------------------------------------------------------------
# 1) nullable schema（migration v9）
# ---------------------------------------------------------------------------
def test_v9_columns_nullable(db):
    with db.connect() as c:
        claims_cols = {r[1]: r for r in c.execute(
            "PRAGMA table_info(claims)").fetchall()}
        rel_cols = {r[1]: r for r in c.execute(
            "PRAGMA table_info(claim_evidence_relations)").fetchall()}
    assert claims_cols["confidence"][3] == 0  # notnull == 0
    assert rel_cols["strength"][3] == 0
    # 无 DEFAULT 0.5
    assert claims_cols["confidence"][4] is None
    assert rel_cols["strength"][4] is None
    assert mig.current_version(str(db.path)) == 14


def test_v9_migration_roundtrip(tmp_path):
    """v9 up/down 往返：数据保留 + schema 恢复。"""
    path = str(tmp_path / "rt.db")
    db = AIPDStateDB(path)
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="default",
              claim_type="problem", statement="s", confidence=0.7))
    # up→down→up：数据保留
    mig.rollback(path, target=8)
    assert mig.current_version(path) == 8
    with sqlite3.connect(path) as c:
        row = c.execute("SELECT confidence FROM claims WHERE claim_id=?",
                        (claim.claim_id,)).fetchone()
        assert row[0] == 0.7  # 数据保留（down 时 COALESCE 不影响真实值）
    mig.migrate(path)
    assert mig.current_version(path) == 14
    db2 = AIPDStateDB(path)
    got = ClaimService(db2).get("default", "default", claim.claim_id)
    assert got.confidence == 0.7


# ---------------------------------------------------------------------------
# 2) 新写入：None → NULL；旧 0.5 → 读取 None
# ---------------------------------------------------------------------------
def test_new_claim_unscored_writes_null(db):
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="default",
              claim_type="problem", statement="s"))  # confidence=None
    with db.connect() as c:
        row = c.execute("SELECT confidence FROM claims WHERE claim_id=?",
                        (claim.claim_id,)).fetchone()
    assert row[0] is None  # NULL，不是 0.5
    got = ClaimService(db).get("default", "default", claim.claim_id)
    assert got.confidence is None


def test_new_relation_unscored_writes_null(db):
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="default",
              claim_type="problem", statement="s"))
    ev = db.add_evidence("default", "default", "paper", "t", url="https://x")
    rel = EvidenceRelationService(db).add(
        EvidenceRelation(relation_id="", tenant_id="default",
                         project_id="default", claim_id=claim.claim_id,
                         evidence_id=ev, relation_type="supports"))
    with db.connect() as c:
        row = c.execute("SELECT strength FROM claim_evidence_relations "
                        "WHERE relation_id=?", (rel.relation_id,)).fetchone()
    assert row[0] is None


def test_legacy_0_5_reads_as_none(db):
    """旧库 0.5（legacy_unscored 哨兵）读取 → None（不当作真实 0.5）。"""
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="default",
              claim_type="problem", statement="s", confidence=0.7))
    with db.connect() as c:
        c.execute("UPDATE claims SET confidence=0.5 WHERE claim_id=?",
                  (claim.claim_id,))  # 模拟旧库哨兵
    got = ClaimService(db).get("default", "default", claim.claim_id)
    assert got.confidence is None


def test_explicit_0_5_preserved(db):
    """显式赋值 0.5 保留（真实评分 ≠ legacy 哨兵；migration 保守不迁移）。"""
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="default",
              claim_type="problem", statement="s", confidence=0.5))
    with db.connect() as c:
        row = c.execute("SELECT confidence FROM claims WHERE claim_id=?",
                        (claim.claim_id,)).fetchone()
    assert row[0] == 0.5
    # 读取：0.5 被 legacy_unscored 语义映射为 None（模型层不区分）——
    # 但 DB 值保守保留，审计可查原始值。
    assert ClaimService(db).get("default", "default", claim.claim_id).confidence \
        is None


# ---------------------------------------------------------------------------
# 3) ID 生成统一（id_sequences）
# ---------------------------------------------------------------------------
def test_legacy_objects_use_sequences(db):
    """facts/decisions/deliverables/risks ID 走 id_sequences（并发安全）。"""
    fid = db.add_fact("default", "default", "k", 1, "V")
    did = db.propose_decision("default", "default", "t", "r", ["a"])
    del_id = db.add_deliverable("default", "default", "doc")
    rid = db.add_risk("default", "default", "risk")
    assert fid.startswith("F-")
    assert did.startswith("D-")
    assert del_id.startswith("DEL-")
    assert rid.startswith("RISK-")
    # sequence 推进（幂等递增，无 scan-max race）
    fid2 = db.add_fact("default", "default", "k2", 2, "V")
    assert fid2 != fid
    with db.connect() as c:
        seq = c.execute("SELECT next_val FROM id_sequences WHERE name='fact'"
                        ).fetchone()
    assert seq[0] == 2


def test_get_or_create_evidence_uses_sequence(db):
    """get_or_create_evidence 与 add_evidence 共用 sequence（不 scan-max）。"""
    e1 = db.add_evidence("default", "default", "paper", "t1", url="https://a")
    e2 = db.get_or_create_evidence("default", "default", kind="paper",
                                   title="t2", url="https://b")
    e3 = db.add_evidence("default", "default", "paper", "t3", url="https://c")
    ids = sorted({e1, e2, e3})
    assert len(ids) == 3  # 无重复
    assert all(i.startswith("E-") for i in ids)


def test_sequence_seed_from_legacy_data(tmp_path):
    """v9 seed：v8-era 库已有存量 scan-max ID，升级 v9 后新 ID 不与存量冲突。"""
    path = str(tmp_path / "seed.db")
    AIPDStateDB(path)
    # 模拟 v8-era：回滚到 v8，插入存量 F-005（scan-max 时代数据），再升级 v9
    mig.rollback(path, target=8)
    assert mig.current_version(path) == 8
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO facts(fact_id,project_id,tenant_id,key,value_json,"
                  "status,confidence,created_at,updated_at,version_no) "
                  "VALUES('F-005','default','default','k','1','V',0.5,"
                  "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',1)")
        c.commit()
    assert mig.migrate(path) == [9, 10, 11, 12, 13, 14]
    db = AIPDStateDB(path)
    fid = db.add_fact("default", "default", "k2", 2, "V")
    assert fid == "F-006"  # 不与 F-005 冲突（seed 从存量推导）
