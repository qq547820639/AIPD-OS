"""ECR/ECO 工程变更单（capability 落点，F-C6-ECO 第 26 片）。

这一片补的是 C6 交付物普查里最后一格「变更单零实现」：本仓有 `changes` 表，
但那是**审计流水**（谁在什么时候改了什么），不是**工程变更单**——后者要答的是
「哪一项变更、为什么、影响哪些件（带改前/改后哈希）、谁批的、生效了没有、复验了没有」。

三条不能打折的形状规矩（每条都有常驻用例与变异电池对着）：

1. **不许自批**：`APPROVED` 只认「与创建人不同的、而且是人」的 actor。
   机器身份表 `NON_HUMAN_ACTORS`（`aipd_os/actors.py`，第 32 片起与 `gates`
   共用一份）不是装饰：本仓曾经把 `gates.approved_by` 建成
   `NOT NULL DEFAULT 'AI-internal'`（`state/migrations/schema.py` 的 V1 冻结文本，
   改不掉，由 migration v20 重建修掉），照抄那个形状就等于任何写入点不写审批人
   也算「已批准」。这里 `creator` 与 `approver` 是两列，且 `approver` 没有默认值。
2. **影响清单必须带哈希**：`UPDATE` 要改前 + 改后两个 sha256，`ADD` 要改后，
   `REMOVE` 要改前；送审（离开 `DRAFT`）之后清单冻结，要改就重开一张单。
3. **「已实施 / 已复验」不是给自己盖章**：进 `IMPLEMENTED` 要有落地凭据
   （`evidence_ref`）与生效时间，进 `VERIFIED` 要有复验凭据；
   转移流水 `eco_transitions` **只追加**，仓储层不提供任何 UPDATE/DELETE 入口。

状态机（对齐公开可查的厂商模型，不自己发明）：
`DRAFT → PENDING_REVIEW → APPROVED → IMPLEMENTED → VERIFIED`，
分支 `REJECTED`（评审不通过）与 `SUPERSEDED`（被另一张单替代，必须指出是哪张）。
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from aipd_os.actors import is_human_actor
from aipd_os.state.errors import (
    ConcurrentModificationError,
    InvalidTransitionError,
    NotFoundError,
)

# 状态词表：与 issues 域同一风格（frozenset + 显式常量），不复用别的名词。
DRAFT = "DRAFT"
PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"
IMPLEMENTED = "IMPLEMENTED"
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
SUPERSEDED = "SUPERSEDED"

ECO_STATUSES = frozenset({DRAFT, PENDING_REVIEW, APPROVED, IMPLEMENTED,
                          VERIFIED, REJECTED, SUPERSEDED})
TERMINAL_STATUSES = frozenset({VERIFIED, REJECTED, SUPERSEDED})

#: 已批但还没复验的：内容可以进发布吗？不行，但它是**活的**单，等复验就行。
VERIFICATION_PENDING = frozenset({APPROVED, IMPLEMENTED})
#: 已经死掉的单（被否或被替代）。它们**不能给内容背书**——
#: 哈希恰好对得上也不算覆盖：那等于用一张作废的批件证明现在的东西是对的。
DEAD_STATUSES = frozenset({REJECTED, SUPERSEDED})

#: 允许的转移边。少一条与多一条都是同一类缺陷，所以写成数据而不是 if。
ECO_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PENDING_REVIEW, REJECTED, SUPERSEDED}),
    PENDING_REVIEW: frozenset({DRAFT, APPROVED, REJECTED, SUPERSEDED}),
    APPROVED: frozenset({IMPLEMENTED, SUPERSEDED}),
    IMPLEMENTED: frozenset({VERIFIED, SUPERSEDED}),
    VERIFIED: frozenset(),
    REJECTED: frozenset(),
    SUPERSEDED: frozenset(),
}

#: 「决定性的」转移：批/否/替代。这几步的 actor 必须是与创建人不同的人。
DECISION_STATUSES = frozenset({APPROVED, REJECTED})

#: actor 不合法时错误信息里必须出现的短语（用例按它匹配，免得测试与文案各说各话）。
INVALID_ACTOR_HINT = "actor 必须是人"

KINDS = frozenset({"ECR", "ECO"})
CHANGE_TYPES = frozenset({"ADD", "REMOVE", "UPDATE"})

#: 每种变更类型必须交哪些哈希。`UPDATE` 两头都要——只有改后值的「变更」
#: 事后无法证明改的是什么。
REQUIRED_HASHES = {
    "ADD": ("after_sha256",),
    "REMOVE": ("before_sha256",),
    "UPDATE": ("before_sha256", "after_sha256"),
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_COLUMNS = ("eco_id", "tenant_id", "project_id", "kind", "title", "reason",
            "status", "creator", "approver", "approved_at",
            "applied_evidence_ref", "effective_at", "verified_evidence_ref",
            "verified_at", "closed_at", "source_commit", "version",
            "created_at", "updated_at")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.match(str(value or "")))


def _parse_time(value: Any) -> datetime | None:
    """解析 ISO-8601；接受尾部 `Z`。解析不出来返回 None（调用方决定是不是必须）。"""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class EcoError(ValueError):
    """输入不合法（与「状态机拒绝」区分开：后者是 InvalidTransitionError）。"""


class EcoStore:
    """ECR/ECO 单据仓储。表由 migration v19 建，这里不建表（迁移链是唯一真值）。"""

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------- 建单与清单
    def create(self, *, tenant_id: str, project_id: str, title: str, creator: str,
               kind: str = "ECO", reason: str = "", source_commit: str = "") -> dict:
        """开一张 `DRAFT` 单。

        `creator` 必须是**人**：单据的作者身份决定「谁不能批它」，
        作者写成 `AI-internal` 会让整张单的审批形同虚设（直接拒）。
        """
        if not str(title or "").strip():
            raise EcoError("ECO 要有标题：空标题的单子事后无法追溯改的是什么")
        if kind not in KINDS:
            raise EcoError(f"kind 只能是 {sorted(KINDS)}，收到 {kind!r}")
        if not is_human_actor(creator):
            raise EcoError(f"creator 必须是人（收到 {creator!r}）："
                           "机器身份开单可以让单子存在，但作者身份是「谁不能批」的依据")
        ts = now_iso()
        with self._db.transaction() as c:
            eco_id = self._next_id(c, tenant_id, project_id)
            c.execute(
                "INSERT INTO eco_records(eco_id,tenant_id,project_id,kind,title,reason,"
                "status,creator,source_commit,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (eco_id, tenant_id, project_id, kind, str(title).strip(),
                 reason or "", DRAFT, str(creator).strip(), source_commit or "", ts, ts))
            self._log_transition(c, eco_id=eco_id, tenant_id=tenant_id,
                                 project_id=project_id, frm="", to=DRAFT,
                                 actor=creator, reason="建单", evidence_ref="")
            self._audit(c, actor=creator, action="eco_created", tenant_id=tenant_id,
                        project_id=project_id, after={"eco_id": eco_id, "kind": kind,
                                                      "title": title})
        return self.get(eco_id=eco_id, tenant_id=tenant_id, project_id=project_id)

    @staticmethod
    def _next_id(c: sqlite3.Connection, tenant_id: str, project_id: str) -> str:
        """单号在本事务内取号：`id_sequences` 的 UPSERT 是原子的，
        但把取号与插行放进同一个事务，避免「取了号却没建单」的空号。"""
        c.execute("INSERT INTO id_sequences(name, next_val) VALUES(?, ?) "
                  "ON CONFLICT(name) DO UPDATE SET next_val = next_val + 1",
                  ("eco", 1))
        row = c.execute("SELECT next_val FROM id_sequences WHERE name=?",
                        ("eco",)).fetchone()
        return f"ECO-{int(row[0]):03d}"

    def add_affected(self, *, eco_id: str, tenant_id: str, project_id: str,
                     object_type: str, object_id: str, change_type: str,
                     before_sha256: str = "", after_sha256: str = "",
                     note: str = "", actor: str = "") -> dict:
        """往影响清单里加一行。只有 `DRAFT` 单可加（送审即冻结）。"""
        if change_type not in CHANGE_TYPES:
            raise EcoError(f"change_type 只能是 {sorted(CHANGE_TYPES)}，收到 {change_type!r}")
        if not str(object_type or "").strip() or not str(object_id or "").strip():
            raise EcoError("影响对象要同时给 object_type 与 object_id")
        hashes = {"before_sha256": str(before_sha256 or "").strip().lower(),
                  "after_sha256": str(after_sha256 or "").strip().lower()}
        for side in REQUIRED_HASHES[change_type]:
            if not _is_sha256(hashes[side]):
                raise EcoError(f"{change_type} 必须带 {side}"
                               "（64 位十六进制 sha256）：没有哈希的影响清单"
                               "事后无法证明改的是哪一份东西")
        for side, value in hashes.items():
            if value and not _is_sha256(value):
                raise EcoError(f"{side} 给了值但不是 64 位十六进制 sha256：{value[:12]!r}…")
        record = self.get(eco_id=eco_id, tenant_id=tenant_id, project_id=project_id)
        if record["status"] != DRAFT:
            raise InvalidTransitionError(
                f"{eco_id} 已是 {record['status']}：影响清单送审后冻结，"
                "要改影响范围就另开一张单并把它 SUPERSEDED")
        ts = now_iso()
        with self._db.transaction() as c:
            row = c.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM eco_affected "
                            "WHERE eco_id=? AND tenant_id=? AND project_id=?",
                            (eco_id, tenant_id, project_id)).fetchone()
            seq = int(row[0])
            c.execute(
                "INSERT INTO eco_affected(eco_id,tenant_id,project_id,seq,object_type,"
                "object_id,change_type,before_sha256,after_sha256,note,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (eco_id, tenant_id, project_id, seq, str(object_type).strip(),
                 str(object_id).strip(), change_type, hashes["before_sha256"],
                 hashes["after_sha256"], note or "", ts))
            c.execute("UPDATE eco_records SET updated_at=? WHERE eco_id=? AND tenant_id=?"
                      " AND project_id=?", (ts, eco_id, tenant_id, project_id))
            self._audit(c, actor=actor or record["creator"], action="eco_affected_added",
                        tenant_id=tenant_id, project_id=project_id,
                        after={"eco_id": eco_id, "seq": seq, "object_type": object_type,
                               "object_id": object_id, "change_type": change_type,
                               "before_sha256": hashes["before_sha256"],
                               "after_sha256": hashes["after_sha256"]})
        return dict(eco_id=eco_id, seq=seq, object_type=object_type, object_id=object_id,
                    change_type=change_type, before_sha256=hashes["before_sha256"],
                    after_sha256=hashes["after_sha256"], note=note)

    # ----------------------------------------------------------------- 转移
    def transition(self, *, eco_id: str, tenant_id: str, project_id: str,
                   to_status: str, actor: str, reason: str = "",
                   evidence_ref: str = "", effective_at: str = "") -> dict:
        """走一步状态。所有前置条件都在这里判，判不过就抛，**不静默留在原状态**。"""
        if to_status not in ECO_STATUSES:
            raise EcoError(f"未知状态 {to_status!r}；可用：{sorted(ECO_STATUSES)}")
        record = self.get(eco_id=eco_id, tenant_id=tenant_id, project_id=project_id)
        frm = record["status"]
        if to_status not in ECO_TRANSITIONS[frm]:
            raise InvalidTransitionError(f"{eco_id}：{frm} → {to_status} 不是合法转移"
                                         f"（可去：{sorted(ECO_TRANSITIONS[frm]) or '无，终态'}）")
        if not is_human_actor(actor):
            raise InvalidTransitionError(
                f"{eco_id}：{frm} → {to_status}：{INVALID_ACTOR_HINT}"
                f"（收到 {actor!r}）——机器身份不能充当审批人")
        if to_status in DECISION_STATUSES and \
                str(actor).strip() == str(record["creator"]).strip():
            verb = "批准" if to_status == APPROVED else "否掉"
            raise InvalidTransitionError(
                f"{eco_id}：创建人 {record['creator']} 不能自己{verb}自己开的单（不许自批）")
        if to_status == APPROVED and not self.affected(eco_id=eco_id, tenant_id=tenant_id,
                                                       project_id=project_id):
            raise InvalidTransitionError(f"{eco_id}：影响清单为空，不批准一张什么都不改的单")
        if to_status == IMPLEMENTED:
            if not str(evidence_ref or "").strip():
                raise InvalidTransitionError(
                    f"{eco_id}：进 IMPLEMENTED 要交落地凭据 evidence_ref"
                    "（改了哪一版/哪次发布），没有凭据就是自称已实施")
            if _parse_time(effective_at) is None:
                raise InvalidTransitionError(
                    f"{eco_id}：进 IMPLEMENTED 要交生效时间 effective_at（ISO-8601），"
                    f"收到 {effective_at!r} 读不出来")
        if to_status == VERIFIED and not str(evidence_ref or "").strip():
            raise InvalidTransitionError(
                f"{eco_id}：进 VERIFIED 要交复验凭据 evidence_ref（复验记录/试验编号），"
                "「实施完了」不等于「变更有效」")
        if to_status == SUPERSEDED:
            if not str(reason or "").strip():
                raise InvalidTransitionError(f"{eco_id}：SUPERSEDED 必须写清为什么")
            replacement = (self._find_by_id(eco_id=evidence_ref, tenant_id=tenant_id,
                                            project_id=project_id)
                           if str(evidence_ref or "").strip() else None)
            if replacement is None or evidence_ref == eco_id:
                raise InvalidTransitionError(
                    f"{eco_id}：SUPERSEDED 的 evidence_ref 要指向**另一张已存在的**单"
                    f"（收到 {evidence_ref!r}）：说「被替代」却不指出替代者，"
                    "等于把这张单的历史抹掉")

        ts = now_iso()
        sets: dict[str, Any] = {"status": to_status, "updated_at": ts}
        if to_status == APPROVED:
            sets.update(approver=str(actor).strip(), approved_at=ts)
        elif to_status == IMPLEMENTED:
            sets.update(applied_evidence_ref=str(evidence_ref).strip(),
                        effective_at=str(effective_at).strip())
        elif to_status == VERIFIED:
            sets.update(verified_evidence_ref=str(evidence_ref).strip(), verified_at=ts,
                        closed_at=ts)
        elif to_status in (REJECTED, SUPERSEDED):
            sets.update(closed_at=ts)
        expected = int(record["version"])
        with self._db.transaction() as c:
            columns = ", ".join(f"{key}=?" for key in sets)
            cur = c.execute(
                f"UPDATE eco_records SET {columns}, version=version+1 "
                "WHERE eco_id=? AND tenant_id=? AND project_id=? AND version=?",
                (*sets.values(), eco_id, tenant_id, project_id, expected))
            if cur.rowcount != 1:
                raise ConcurrentModificationError(
                    f"{eco_id} 版本 {expected} 已被别处改动（concurrent modification）")
            self._log_transition(c, eco_id=eco_id, tenant_id=tenant_id,
                                 project_id=project_id, frm=frm, to=to_status,
                                 actor=actor, reason=reason, evidence_ref=evidence_ref)
            self._audit(c, actor=actor, action=f"eco_{to_status.casefold()}",
                        tenant_id=tenant_id, project_id=project_id,
                        before={"status": frm, "version": expected},
                        after={"status": to_status, "evidence_ref": evidence_ref,
                               "reason": reason})
        return self.get(eco_id=eco_id, tenant_id=tenant_id, project_id=project_id)

    # ----------------------------------------------------------------- 读
    def get(self, *, eco_id: str, tenant_id: str, project_id: str) -> dict:
        row = self._find_by_id(eco_id=eco_id, tenant_id=tenant_id, project_id=project_id)
        if row is None:
            raise NotFoundError(f"{tenant_id}/{project_id} 里没有单据 {eco_id}")
        return row

    def _find_by_id(self, *, eco_id: str, tenant_id: str, project_id: str) -> dict | None:
        with self._db.connect() as c:
            row = c.execute("SELECT * FROM eco_records WHERE eco_id=? AND tenant_id=?"
                            " AND project_id=?", (eco_id, tenant_id, project_id)).fetchone()
        return None if row is None else self._row_to_dict(row)

    def list_orders(self, *, tenant_id: str, project_id: str,
                  status: str | None = None,
             open_only: bool = False) -> list[dict]:
        """列单。`status` 与 `open_only` 互斥地服务两类读者：看某一状态的、看未闭合的。"""
        sql = "SELECT * FROM eco_records WHERE tenant_id=? AND project_id=?"
        params: list[Any] = [tenant_id, project_id]
        if status is not None:
            if status not in ECO_STATUSES:
                raise EcoError(f"未知状态 {status!r}")
            sql += " AND status=?"
            params.append(status)
        if open_only:
            sql += " AND status NOT IN ('VERIFIED','REJECTED','SUPERSEDED')"
        sql += " ORDER BY created_at, eco_id"
        with self._db.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def affected(self, *, eco_id: str, tenant_id: str, project_id: str) -> list[dict]:
        with self._db.connect() as c:
            rows = c.execute("SELECT * FROM eco_affected WHERE eco_id=? AND tenant_id=?"
                             " AND project_id=? ORDER BY seq",
                             (eco_id, tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def transitions(self, *, eco_id: str, tenant_id: str, project_id: str) -> list[dict]:
        with self._db.connect() as c:
            rows = c.execute("SELECT * FROM eco_transitions WHERE eco_id=? AND tenant_id=?"
                             " AND project_id=? ORDER BY transition_id",
                             (eco_id, tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def open_orders_touching(self, *, tenant_id: str, project_id: str,
                             object_type: str, object_id: str) -> list[dict]:
        """哪些未闭合的单动过这个对象。发布前用来回答「这版改动有没有对应的单」。"""
        sql = ("SELECT DISTINCT r.* FROM eco_records r JOIN eco_affected a "
               "ON a.eco_id=r.eco_id AND a.tenant_id=r.tenant_id "
               "AND a.project_id=r.project_id "
               "WHERE r.tenant_id=? AND r.project_id=? AND a.object_type=? AND a.object_id=?"
               " AND r.status NOT IN ('VERIFIED','REJECTED','SUPERSEDED')"
               " ORDER BY r.created_at, r.eco_id")
        with self._db.connect() as c:
            rows = c.execute(sql, (tenant_id, project_id, object_type, object_id)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------- 内部小工具
    @staticmethod
    def _row_to_dict(row: Any) -> dict:
        data = dict(row)
        return {key: data.get(key) for key in _COLUMNS}

    @staticmethod
    def _log_transition(c: sqlite3.Connection, **fields: Any) -> None:
        c.execute("INSERT INTO eco_transitions(eco_id,tenant_id,project_id,from_status,"
                  "to_status,actor,reason,evidence_ref,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (fields["eco_id"], fields["tenant_id"], fields["project_id"],
                   fields["frm"], fields["to"], str(fields["actor"]).strip(),
                   fields.get("reason") or "", fields.get("evidence_ref") or "", now_iso()))

    @staticmethod
    def _audit(c: sqlite3.Connection, *, actor: str, action: str, tenant_id: str,
               project_id: str, before: Any = None, after: Any = None) -> None:
        import json as _json
        c.execute("INSERT INTO audit_log(actor,action,project_id,tenant_id,timestamp,"
                  "before_json,after_json) VALUES(?,?,?,?,?,?,?)",
                  (actor, action, project_id, tenant_id, now_iso(),
                   _json.dumps(before, sort_keys=True, ensure_ascii=False, default=str)
                   if before is not None else None,
                   _json.dumps(after, sort_keys=True, ensure_ascii=False, default=str)
                   if after is not None else None))
