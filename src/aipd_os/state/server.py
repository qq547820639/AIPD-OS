"""StateService：跨会话状态服务。

提供与旧 MCP server 相同的工具语义（init_project / project_summary / add_fact /
propose_decision / resolve_decision / export_checkpoint），并新增认证、审计、健康、
备份、检查点、对象存储等操作。

可插拔传输：
  - ``local``：纯 Python API（可直接调用 StateService 方法）；
  - ``server``：基于 Python 标准库 ``http.server`` 的极简 HTTP/JSON RPC，
    无需安装任何第三方框架，未安装 mcp 也可运行。
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from . import migrations
from .audit import AuditLogger
from .auth import AuthError, AuthManager
from .backup import BackupManager
from .checkpoint import CheckpointManager
from .db import AIPDStateDB
from .health import health_check
from .objects import ObjectStore

DEFAULT_TENANT = "default"

# 免令牌的公共引导 RPC：首次注册/登录必须可匿名调用，否则无法获得令牌。
PUBLIC_RPC_METHODS = frozenset({"auth_login", "auth_register"})

# 视为「弱/缺失」的 secret 取值（空串 / 历史默认值）。
_WEAK_SECRET_VALUES = ("", "change-me-secret")
# 生产模式（server）要求的最小 secret 长度。
MIN_STRONG_SECRET_LEN = 16


class StateService:
    """多租户多项目状态服务（本地模式 = 纯 Python API）。"""

    def __init__(self, db_path: str, encryption_key: str = "",
                 secret: str | None = None, object_dir: str | None = None,
                 backup_dir: Optional[str] = None, retention_days: int = 90,
                 default_tenant: str = DEFAULT_TENANT,
                 insecure_dev_mode: bool = False,
                 require_strong_secret: bool = False):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        migrations.migrate(db_path)
        self.db_path = str(db_path)
        self.default_tenant = default_tenant
        self.retention_days = retention_days
        self.insecure_dev_mode = insecure_dev_mode
        self.db = AIPDStateDB(db_path, encryption_key=encryption_key)
        self.auth = AuthManager(self.db, self._resolve_secret(
            secret, insecure_dev_mode=insecure_dev_mode,
            require_strong_secret=require_strong_secret))
        self.checkpoints = CheckpointManager(self.db)
        self._audit_logger = AuditLogger(self.db)
        base = Path(db_path).parent
        self.objects = ObjectStore(object_dir or str(base / "objects"), retention_days=retention_days)
        self.backup = BackupManager(db_path, backup_dir=str(base / "backups"))
        self.db.ensure_default_tenant(default_tenant)

    @staticmethod
    def _resolve_secret(secret: str | None, insecure_dev_mode: bool,
                        require_strong_secret: bool) -> str:
        """解析服务 secret：弱/缺失时按模式 fail-closed 或降级。

        - 强 secret（>=16 字符且非默认值）直接使用；
        - 弱/缺失 secret：``insecure_dev_mode`` 允许并 WARNING；
          ``require_strong_secret``（server 模式）fail-closed 抛错；
          否则（本地模式）生成随机临时 secret 并 WARNING。
        """
        weak = (secret is None or secret in _WEAK_SECRET_VALUES
                or len(secret) < MIN_STRONG_SECRET_LEN)
        if not weak:
            return secret
        if insecure_dev_mode:
            logging.warning("insecure dev mode: weak secret allowed (AIPD_INSECURE_DEV_MODE=1)")
            return secret or "change-me-secret"
        if require_strong_secret:
            raise RuntimeError(
                "missing or weak AIPD_SECRET: server mode requires a strong secret "
                f"(>= {MIN_STRONG_SECRET_LEN} chars and not 'change-me-secret'); "
                "set AIPD_SECRET, or set AIPD_INSECURE_DEV_MODE=1 to allow a weak "
                "secret in dev only")
        logging.warning(
            "no strong AIPD_SECRET provided; using a random ephemeral secret "
            "(local mode only; auth tokens will not survive restart)")
        return secrets.token_hex(32)

    # ----------------------------------------------------------- dispatch
    def call(self, method: str, **params: Any) -> Any:
        handler = getattr(self, method, None)
        if handler is None or method.startswith("_"):
            raise AttributeError(f"unknown method {method!r}")
        return handler(**params)

    def _authorize(self, actor: Optional[str], tenant_id: str, project_id: str) -> None:
        if actor is None:
            return  # 内部/系统调用，跳过授权
        self.auth.require_project_access(actor, tenant_id, project_id)

    def _audit(self, actor: Optional[str], action: str, tenant_id: str,
               project_id: str, before: Any = None, after: Any = None) -> None:
        self._audit_logger.log(actor or "system", action, project_id, tenant_id, before, after)

    # ------------------------------------------------------------- auth
    def auth_register(self, user_id: str, tenant_id: str, username: str, password: str,
                      project_id: Optional[str] = None) -> str:
        self.db.ensure_default_tenant(tenant_id)
        self.auth.register_user(user_id, tenant_id, username, password)
        # 仅当显式传入 project_id 时授予该项目访问权；不再隐式授予租户通配。
        if project_id is not None:
            self.auth.grant_access(user_id, tenant_id, project_id)
        token = self.auth.issue_token(user_id)
        self._audit(user_id, "register", tenant_id, project_id or "")
        return token

    def auth_login(self, username: str, password: str) -> str:
        user_id = self.auth.verify_password(username, password)
        if user_id is None:
            raise AuthError("invalid username or password")
        return self.auth.issue_token(user_id)

    def auth_verify(self, user: str, token: str) -> bool:
        return self.auth.authenticate(user, token)

    def grant_access(self, user_id: str, tenant_id: str, project_id: str | None = None,
                     actor: str | None = None) -> None:
        """授权操作仅限租户管理员（actor=None 视为内部/系统调用，跳过校验）。"""
        if actor is not None:
            self.auth.require_tenant_admin(actor, tenant_id)
        self.auth.grant_access(user_id, tenant_id, project_id)

    # ----------------------------------------------------------- projects
    def init_project(self, tenant_id: str, project_id: str, name: str, goal: str,
                     owner_policy: str = "AI executes; owner reviews decisions only",
                     actor: Optional[str] = None) -> Dict[str, Any]:
        self.db.ensure_default_tenant(tenant_id)
        self.db.init_project(tenant_id, project_id, name, goal, owner_policy)
        # 项目创建者自动成为该项目成员。
        if actor is not None:
            self.auth.grant_access(actor, tenant_id, project_id)
        after = self.db.summary(tenant_id, project_id)
        self._audit(actor, "init_project", tenant_id, project_id, after=after)
        return after

    def project_summary(self, tenant_id: str, project_id: str,
                        actor: Optional[str] = None) -> Dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return self.db.summary(tenant_id, project_id)

    def list_projects(self, tenant_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
        projects = self.db.list_projects(tenant_id)
        if actor is not None and not self.db.has_tenant_admin(actor, tenant_id):
            # 非管理员仅能看到自己有访问权的项目。
            projects = [p for p in projects
                        if self.db.has_access(actor, tenant_id, p["project_id"])]
        return {"tenant_id": tenant_id,
                "projects": [{k: v for k, v in p.items()} for p in projects]}

    def get_project(self, tenant_id: str, project_id: str,
                    actor: str | None = None) -> dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return self.db.get_project(tenant_id, project_id)

    def update_project(self, tenant_id: str, project_id: str, expected_version: int,
                       actor: Optional[str] = None, **fields: Any) -> Dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        before = self.db.get_project(tenant_id, project_id)
        after = self.db.update_project(tenant_id, project_id, expected_version, **fields)
        self._audit(actor, "update_project", tenant_id, project_id, before=before, after=after)
        return after

    # ---------------------------------------------------------------- facts
    def add_fact(self, tenant_id: str, project_id: str, key: str, value: Any, status: str,
                 unit: Optional[str] = "", source: Optional[str] = "", confidence: float = 0.5,
                 actor: Optional[str] = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        fid = self.db.add_fact(tenant_id, project_id, key, value, status, unit or None,
                               confidence=confidence, source=source or None)
        self._audit(actor, "add_fact", tenant_id, project_id, after={"fact_id": fid, "key": key})
        return fid

    def list_facts(self, tenant_id: str, project_id: str,
                   actor: str | None = None) -> dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return {"facts": self.db.list_facts(tenant_id, project_id)}

    # ------------------------------------------------------------ decisions
    def propose_decision(self, tenant_id: str, project_id: str, topic: str,
                         recommendation: str, options: Any, trigger: Optional[str] = "",
                         actor: Optional[str] = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        did = self.db.propose_decision(tenant_id, project_id, topic, recommendation, options, trigger or None)
        self._audit(actor, "propose_decision", tenant_id, project_id, after={"decision_id": did, "topic": topic})
        return did

    def resolve_decision(self, tenant_id: str, project_id: str, decision_id: str,
                         choice: str, comment: Optional[str] = "", actor: Optional[str] = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        self.db.resolve_decision(tenant_id, project_id, decision_id, choice, comment or None)
        self._audit(actor, "resolve_decision", tenant_id, project_id,
                    after={"decision_id": decision_id, "choice": choice})
        return "ok"

    def list_decisions(self, tenant_id: str, project_id: str,
                       actor: str | None = None) -> dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return {"decisions": self.db.list_decisions(tenant_id, project_id)}

    # ------------------------------------------------------------ evidence
    def add_evidence(self, tenant_id: str, project_id: str, kind: str, title: str,
                     url: Optional[str] = None, identifier: Optional[str] = None,
                     quality: Optional[str] = None, summary: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None,
                     actor: Optional[str] = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        eid = self.db.add_evidence(tenant_id, project_id, kind, title, url, identifier,
                                   quality, summary, metadata)
        self._audit(actor, "add_evidence", tenant_id, project_id, after={"evidence_id": eid, "title": title})
        return eid

    # ---------------------------------------------------------------- risks
    def add_risk(self, tenant_id: str, project_id: str, title: str,
                 probability: Optional[str] = None, impact: Optional[str] = None,
                 mitigation: Optional[str] = None, status: str = "open",
                 actor: Optional[str] = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        rid = self.db.add_risk(tenant_id, project_id, title, probability, impact, mitigation, status)
        self._audit(actor, "add_risk", tenant_id, project_id, after={"risk_id": rid, "title": title})
        return rid

    # ---------------------------------------------------------- deliverables
    def add_deliverable(self, tenant_id: str, project_id: str, dtype: str,
                        path: Optional[str] = None, status: str = "planned",
                        version: Optional[str] = None, gate: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None,
                        actor: Optional[str] = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        return self.db.add_deliverable(tenant_id, project_id, dtype, path, status, version, gate, metadata)

    # ------------------------------------------------------------ checkpoints
    def save_checkpoint(self, tenant_id: str, project_id: str, data: Any,
                        summary: Any = None, actor: Optional[str] = None) -> int:
        self._authorize(actor, tenant_id, project_id)
        cid = self.db.save_checkpoint(tenant_id, project_id, data, summary)
        self._audit(actor, "save_checkpoint", tenant_id, project_id, after={"checkpoint_id": cid})
        return cid

    def restore_checkpoint(self, tenant_id: str, project_id: str,
                           actor: str | None = None) -> Any:
        self._authorize(actor, tenant_id, project_id)
        return self.checkpoints.restore_latest(project_id, tenant_id)

    def resume_summary(self, tenant_id: str, project_id: str,
                       actor: Optional[str] = None) -> Dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return self.checkpoints.resume_summary(project_id, tenant_id)

    def export_checkpoint(self, tenant_id: str, project_id: str,
                          actor: Optional[str] = None) -> Dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return self.db.export(tenant_id, project_id)

    # -------------------------------------------------------------- objects
    def object_put(self, project_id: str, key: str, data_b64: str,
                   tenant_id: str = DEFAULT_TENANT, actor: str | None = None) -> str:
        import base64
        self._authorize(actor, tenant_id, project_id)
        return self.objects.put(project_id, key, base64.b64decode(data_b64), tenant_id)

    def object_get_b64(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT,
                       actor: str | None = None) -> str:
        import base64
        self._authorize(actor, tenant_id, project_id)
        return base64.b64encode(self.objects.get(project_id, key, tenant_id)).decode("ascii")

    def object_list(self, project_id: str, tenant_id: str = DEFAULT_TENANT,
                    actor: str | None = None) -> dict[str, Any]:
        self._authorize(actor, tenant_id, project_id)
        return {"objects": self.objects.list(project_id, tenant_id)}

    def object_delete(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT,
                      actor: str | None = None) -> str:
        self._authorize(actor, tenant_id, project_id)
        self.objects.delete(project_id, key, tenant_id)
        return "ok"

    # --------------------------------------------------------------- backup
    def create_backup(self, out_dir: str | None = None, actor: str | None = None) -> str:
        if actor is not None:
            self.auth.require_tenant_admin(actor, self.default_tenant)
        path = self.backup.create_backup(self.db_path, out_dir)
        manifest = json.loads((Path(path) / "manifest.json").read_text(encoding="utf-8"))
        self.db.add_backup(path, manifest["checksum"], manifest["size"])
        return path

    def list_backups(self, actor: str | None = None) -> dict[str, Any]:
        if actor is not None:
            self.auth.require_tenant_admin(actor, self.default_tenant)
        return {"backups": self.backup.list_backups()}

    def restore_backup(self, backup_dir: str, target: str | None = None,
                       actor: str | None = None) -> str:
        if actor is not None:
            self.auth.require_tenant_admin(actor, self.default_tenant)
        return self.backup.restore_backup(backup_dir, target or self.db_path)

    def retention_prune(self, retention_days: int | None = None,
                        actor: str | None = None) -> dict[str, Any]:
        if actor is not None:
            self.auth.require_tenant_admin(actor, self.default_tenant)
        days = retention_days if retention_days is not None else self.retention_days
        removed = self.backup.retention_prune(self.backup.list_backups(), days)
        return {"removed": removed}

    # ---------------------------------------------------------------- audit
    def audit(self, limit: int = 100, actor: str | None = None) -> dict[str, Any]:
        if actor is not None:
            self.auth.require_tenant_admin(actor, self.default_tenant)
        return {"records": self._audit_logger.read(limit)}

    #: ``audit`` 的明确命名别名（避免与实例属性命名歧义）。
    list_audit_events = audit

    # --------------------------------------------------------------- health
    def health(self) -> Dict[str, Any]:
        return health_check(self.db_path)


class UnauthorizedError(Exception):
    """RPC 请求未通过认证（HTTP 401）。"""


# =========================================================================
# HTTP/JSON 传输（仅用标准库 http.server，无第三方依赖）
#
# 注意：该传输是认证的。每个 POST /rpc 请求必须携带有效令牌
# ``{"user": ..., "token": ..., "method": ..., "params": ...}``，令牌由
# ``auth_login`` / ``auth_register`` 签发；未认证请求返回 HTTP 401。
# 例外：``auth_login`` / ``auth_register`` 属于公共引导方法（PUBLIC_RPC_METHODS），
# 免令牌可调用，否则首次注册/登录将形成引导死锁。
# 认证后的 actor 身份会覆盖注入到支持 ``actor`` 的方法（客户端无法冒充），
# 从而触发项目级授权；授权失败返回 HTTP 403，未认证返回 401。
# =========================================================================

class _RpcHandler(BaseHTTPRequestHandler):
    service: StateService = None  # type: ignore

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # 健康端点
        if self.path.rstrip("/") == "/health":
            self._send_json(200, health_check(self.service.db_path))
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):  # RPC 端点（必须认证）
        if self.path.rstrip("/") != "/rpc":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            method = req.get("method")
            params = req.get("params", {}) or {}
            # 认证：每个 RPC 请求必须携带有效令牌（user + token），
            # 否则拒绝（401），并将认证后的 actor 身份注入调用以触发授权。
            actor = self._authenticate(req)
            params = self._inject_actor(method, params, actor)
            result = self.service.call(method, **params)
            self._send_json(200, {"result": result})
        except UnauthorizedError as exc:
            self._send_json(401, {"error": str(exc), "error_type": "unauthorized"})
        except AuthError as exc:
            # 授权失败（项目/租户无权限）→ 403 Forbidden，而非 400。
            self._send_json(403, {"error": str(exc), "error_type": "forbidden"})
        except Exception as exc:  # noqa: BLE001 - 统一返回错误
            self._send_json(400, {"error": str(exc), "error_type": type(exc).__name__})

    def _authenticate(self, req: Dict[str, Any]) -> str:
        """校验请求中的 user/token；公共引导方法免令牌。失败抛 :class:`UnauthorizedError`。

        返回 user_id（公共方法返回空串，表示不注入 actor）。
        """
        method = req.get("method")
        if method in PUBLIC_RPC_METHODS:
            return ""
        user = req.get("user")
        token = req.get("token")
        if not user or not token:
            raise UnauthorizedError("missing auth credentials (user + token required)")
        if not self.service.auth.authenticate(user, token):
            raise UnauthorizedError("invalid or expired auth token")
        return user

    def _inject_actor(self, method: str, params: Dict[str, Any], actor: str) -> Dict[str, Any]:
        """对支持 actor 的方法注入认证身份，使 :meth:`StateService._authorize` 生效。

        认证后的 actor 身份**必须覆盖**客户端在 params 中提供的任何 ``actor``
        值（防止冒充：``setdefault`` 会让客户端 actor 优先，等于认证可被绕过）。
        公共引导方法返回空 actor，不注入。
        """
        if not actor:
            return params
        handler = getattr(self.service, method, None)
        if handler is None:
            return params
        try:
            params_sig = inspect.signature(handler).parameters
        except (TypeError, ValueError):
            return params
        if "actor" in params_sig:
            # 覆盖而非 setdefault：客户端塞入的 actor=None / actor=其他用户
            # 一律以认证身份为准，杜绝冒充与授权绕过。
            params["actor"] = actor
        return params

    def log_message(self, *args):  # 默认会打印到 stderr，静默处理
        pass


def run_http(service: StateService, host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    """启动 HTTP/JSON 状态服务（阻塞）。"""
    _RpcHandler.service = service
    httpd = ThreadingHTTPServer((host, port), _RpcHandler)
    httpd.serve_forever()


def main(argv: Optional[list] = None) -> None:
    """CLI 入口：AIPD_DB_DIR / AIPD_MODE / AIPD_PORT / AIPD_ENCRYPTION_KEY / AIPD_RETENTION_DAYS。"""
    import argparse

    parser = argparse.ArgumentParser(description="AIPD-OS state service")
    parser.add_argument("--db", default=os.environ.get("AIPD_DB_DIR", "data/state.db"))
    parser.add_argument("--mode", default=os.environ.get("AIPD_MODE", "local"),
                        choices=["local", "server"])
    parser.add_argument("--host", default=os.environ.get("AIPD_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AIPD_PORT", "8000")))
    parser.add_argument("--encryption-key", default=os.environ.get("AIPD_ENCRYPTION_KEY", ""))
    parser.add_argument("--secret", default=os.environ.get("AIPD_SECRET"))
    parser.add_argument("--insecure-dev-mode", action="store_true",
                        default=os.environ.get("AIPD_INSECURE_DEV_MODE", "")
                        not in ("", "0", "false", "False"))
    parser.add_argument("--retention-days", type=int, default=int(os.environ.get("AIPD_RETENTION_DAYS", "90")))
    args = parser.parse_args(argv)

    svc = StateService(args.db, encryption_key=args.encryption_key, secret=args.secret,
                       retention_days=args.retention_days,
                       insecure_dev_mode=args.insecure_dev_mode,
                       require_strong_secret=(args.mode == "server"))
    if args.mode == "server":
        run_http(svc, args.host, args.port)
    else:
        print(json.dumps({"health": svc.health()}, ensure_ascii=False))


if __name__ == "__main__":
    main()


__all__ = ["StateService", "AuthError", "UnauthorizedError", "run_http", "main"]
