"""``aipd doctor`` 一键体检命令。"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ._helpers import _repo_root


def _doctor_check(checks, name, status, detail):
    checks.append({"name": name, "status": status, "detail": detail})


def _check_repo_permissions(repo: Path) -> tuple:
    targets = [repo]
    from aipd_os.config import get_settings
    db_dir = get_settings().db_dir
    if db_dir and db_dir != "data":
        p = Path(db_dir)
        targets.append(p if p.is_dir() else p.parent)
    for t in targets:
        try:
            with tempfile.NamedTemporaryFile(dir=str(t), delete=True):
                pass
        except Exception as exc:  # noqa: BLE001
            return False, f"{t}: {exc}"
    return True, "writable"


def cmd_doctor(args):
    from aipd_os import __version__
    from aipd_os.config import get_settings

    repo = _repo_root()
    checks: list[dict[str, Any]] = []

    # 1) 包版本
    _doctor_check(checks, "version", "ok", __version__)

    # 2) 依赖可用性
    deps = {
        "jsonschema": "jsonschema",
        "PIL": "PIL",
        "reportlab": "reportlab",
        "requests": "requests",
        "yaml": "yaml",
        "cryptography": "cryptography",
    }
    for label, mod in deps.items():
        try:
            __import__(mod)
            status, detail = "ok", "import ok"
        except ImportError:
            status, detail = "missing", f"import failed: {mod}"
        _doctor_check(checks, f"dependency.{label}", status, detail)

    # 3) 配置
    s = get_settings()
    _doctor_check(checks, "config.mode", "ok", s.mode)
    _doctor_check(checks, "config.db_dir", "ok", s.db_dir)
    _doctor_check(checks, "config.log_level", "ok", s.log_level)
    _doctor_check(checks, "config.files",
                  "ok" if s.config_files else "info",
                  ", ".join(str(p) for p in s.config_files) or "none")

    # 4) 外部能力（配置 vs external_dependency）
    external_envs = {
        "vision_backend": "AIPD_VISION_BACKEND",
        "model_endpoint": "AIPD_EVAL_MODEL_ENDPOINT",
        "image_backend": "AIPD_IMGGEN_BACKEND",
        "mail": "AIPD_MAIL_PROVIDER",
    }
    for name, env in external_envs.items():
        val = os.environ.get(env, "").strip()
        status = "ok" if val else "external_dependency"
        detail = val or "not configured (external_dependency)"
        _doctor_check(checks, f"capability.{name}", status, detail)
    cq_ok = importlib.util.find_spec("cadquery") is not None
    _doctor_check(checks, "capability.cad_kernel",
                  "ok" if cq_ok else "external_dependency",
                  "cadquery available" if cq_ok else "cadquery not installed (external_dependency)")

    # 4b) 模型驱动能力实现状态（诚实区分「未实现」与「外部依赖」并给出下一步）
    api_key = os.environ.get("AIPD_MODEL_API_KEY", "").strip()
    base_url = os.environ.get("AIPD_MODEL_BASE_URL", "").strip()
    llm_configured = bool(api_key and base_url)
    _doctor_check(
        checks, "capability.product_intelligence",
        "ok" if llm_configured else "external_dependency",
        ("LLM 已配置（产品智能转译与想法结构化可用）" if llm_configured
         else "配置 AIPD_MODEL_API_KEY + AIPD_MODEL_BASE_URL 可启用产品智能转译"
              "与想法结构化（product.* + idea.decompose）"))
    _doctor_check(
        checks, "capability.research_not_implemented",
        "not_implemented",
        "当前未实现（规划中）：research.fulltext / research.related_work / "
        "research.novelty_check / research.idea_spark / research.asset_extract")

    # 5) 数据库
    try:
        from aipd_os.state.db import AIPDStateDB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name
        try:
            db = AIPDStateDB(str(db_path))
            db.ensure_default_tenant()
            _doctor_check(checks, "database", "ok", "AIPDStateDB init + default tenant ok")
        finally:
            with contextlib.suppress(OSError):
                os.unlink(db_path)  # 清理探测用临时 db 文件：不存在/被占用时忽略
    except Exception as exc:  # noqa: BLE001
        _doctor_check(checks, "database", "fail", str(exc))

    # 6) 对象存储
    try:
        from aipd_os.state.objects import ObjectStore
        with tempfile.TemporaryDirectory() as td:
            store = ObjectStore(td)
            store.put("probe", "probe-key", b"probe")
            _doctor_check(checks, "object_store", "ok", "ObjectStore put ok")
    except Exception as exc:  # noqa: BLE001
        _doctor_check(checks, "object_store", "fail", str(exc))

    # 7) 权限
    perm_ok, perm_detail = _check_repo_permissions(repo)
    _doctor_check(checks, "permissions", "ok" if perm_ok else "fail", perm_detail)

    # 8) 凭据保护与脱敏：检查常见敏感环境变量是否已登记、是否已脱敏
    from aipd_os.security.secrets import SecretStore, is_sensitive_var
    store = SecretStore()
    for env in ("AIPD_EVAL_MODEL_ENDPOINT_API_KEY", "AIPD_MAIL_PASSWORD",
                "AIPD_IMGGEN_API_KEY", "AIPD_VISION_API_KEY",
                # v5.8.2 Commit 9：canonical 是 AIPD_ENCRYPTION_KEY；
                # deprecated alias 一并登记（迁移期兼容）。
                "AIPD_ENCRYPTION_KEY", "AIPD_DATA_ENCRYPTION_KEY"):
        store.register(env, "...")
    sensitive_envs = [e for e in os.environ if is_sensitive_var(e)]
    registered = [e for e in sensitive_envs if store.is_registered(e)]
    unregistered = [e for e in sensitive_envs if not store.is_registered(e)]
    exposed = [e for e in sorted(sensitive_envs) if store.exposed(e)]
    leaked = [e for e in exposed if not store.is_registered(e)]
    masking_on = all(store.masked(e) is not None and store.masked(e) != e
                     for e in exposed) if exposed else True
    if leaked:
        _doctor_check(checks, "security.credentials",
                      "fail",
                      f"unregistered sensitive env set: {', '.join(leaked)}")
    else:
        _doctor_check(checks, "security.credentials",
                      "ok" if (not sensitive_envs or masking_on) else "warn",
                      f"registered={len(registered)} unregistered={len(unregistered)} "
                      f"exposed={len(exposed)} masking={masking_on}")
    _doctor_check(checks, "security.masking",
                  "ok" if masking_on else "fail",
                  "credential masking active" if masking_on else "credential masking disabled")

    failed = [c for c in checks if c["status"] == "fail"]
    result = {"command": "doctor", "ok": not failed, "version": __version__, "checks": checks}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"AIPD-OS doctor v{__version__}")
        for c in checks:
            print(f"[{c['status']:>18}] {c['name']}: {c['detail']}")
        print("体检结论：" + ("通过（无硬失败）" if result["ok"] else f"存在 {len(failed)} 项硬失败"))  # noqa: E501
    return 0 if result["ok"] else 1


__all__ = ["cmd_doctor"]
