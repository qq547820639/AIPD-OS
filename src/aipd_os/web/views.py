"""Owner Web Console 共享应用服务。

``WebConsole`` 是 CLI（``aipd ui``）、Web UI 与 JSON API 共用的唯一业务逻辑层：
所有中心（项目总览 / 决策 / 制品 / 运行控制 / 外部等待 / 首次使用向导）都通过
同一组方法构建数据，HTML 页面与 JSON 端点调用相同的函数，绝不形成三套逻辑。

设计要点：
  - 复用既有 experience 模块（build_dashboard / build_decision_card /
    artifact_preview / onboard / run_operation_loop / summarize_external_wait 等）；
  - 默认不暴露内部 ID / 内部代号，用安全展示编号（ref = 短哈希）代替；
  - 全部确定性、可测、可运行于 CI，不依赖任何第三方框架。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aipd_os.config import get_settings

# 复用经验层
from aipd_os.experience.artifact_preview import artifact_preview
from aipd_os.experience.decision_card import build_decision_card
from aipd_os.experience.external_wait import summarize_external_wait
from aipd_os.experience.impact_analysis import type_cn
from aipd_os.experience.intent_engine import parse_intent
from aipd_os.experience.operations import ProgressTracker, run_operation_loop
from aipd_os.experience.owner_dashboard import build_dashboard
from aipd_os.experience.project_summary import build_project_summary
from aipd_os.experience.resume_summary import build_resume_summary
from aipd_os.state.checkpoint import CheckpointManager
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.objects import ObjectStore

DEFAULT_TENANT = "default"

# 状态代号 → 中文（不在正文暴露内部代号）
_STATUS_CN = {
    "planned": "已计划", "in_progress": "推进中", "done": "已完成",
    "released": "已发布", "archived": "已归档", "stale": "待重做",
    "blocked_external": "等待外部", "proposed": "待审", "resolved": "已裁定",
    "open": "未闭环", "closed": "已闭环",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_ref(internal_id: str | None) -> str | None:
    """把内部 ID 映射为安全展示编号（短哈希），默认不暴露原始内部代号。"""
    if not internal_id:
        return None
    return "id-" + hashlib.sha1(str(internal_id).encode("utf-8")).hexdigest()[:8]


def _status_cn(status: str | None) -> str:
    return _STATUS_CN.get(str(status or "").lower(), str(status or ""))


def _preview_kind(dtype: str | None) -> str:
    """根据制品类型推断预览形态（image / pdf / table / text / cad / file）。"""
    t = (dtype or "").lower()
    if "cad" in t:
        return "cad"
    if "pdf" in t:
        return "pdf"
    if "bom" in t or "table" in t or "sheet" in t or "xlsx" in t:
        return "table"
    if "txt" in t or "text" in t or "md" in t:
        return "text"
    if "manual" in t or "page" in t or "drawing" in t or "image" in t or "png" in t:
        return "image"
    return "file"


def _metadata(d: dict[str, Any]) -> dict[str, Any]:
    raw = d.get("metadata_json") or d.get("metadata")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


class RunController:
    """运行控制：跟踪一次操作的进度事件、心跳与状态机。

    状态：idle / running / paused / cancelled / done / needs_approval /
    needs_clarification / failed。供运行控制中心与 JSON API 使用。
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state: str = "idle"
        self.events: list[dict[str, Any]] = []
        self.heartbeat_at: str | None = None
        self.started_at: str | None = None
        self.last_intent_text: str | None = None
        self.last_result: dict[str, Any] | None = None
        self.failure_reason: str | None = None
        self.attempts: int = 0
        self._cancel_requested = False

    def start(self, intent_text: str, events: list[dict[str, Any]],
              result: dict[str, Any]) -> None:
        self.started_at = _now_iso()
        self.heartbeat_at = _now_iso()
        self.events = list(events)
        self.last_intent_text = intent_text
        self.last_result = result
        self.attempts += 1
        self._cancel_requested = False
        status = result.get("status")
        if status == "needs_clarification":
            self.state = "needs_clarification"
            self.failure_reason = result.get("clarifying_question", "需要澄清")
        elif status == "needs_approval":
            self.state = "needs_approval"
            self.failure_reason = result.get("why_need_decide", "需要您批准")
        elif status == "cancelled":
            self.state = "cancelled"
            self.failure_reason = "已取消"
        else:
            self.state = "done"
            self.failure_reason = None

    # ---- 控制动作（确定性状态机）----
    def can(self, action: str) -> bool:
        return action in self.available_actions()

    def available_actions(self) -> list[str]:
        s = self.state
        actions: list[str] = []
        # 已 paused 时不再提供 pause（pause() 不处理 paused 状态，属无效动作）
        if s in ("running", "needs_approval", "needs_clarification"):
            actions.append("pause")
        if s == "paused":
            actions.append("resume")
        if s in ("running", "paused", "needs_approval", "needs_clarification", "failed"):
            actions.append("cancel")
        if s in ("done", "cancelled", "failed") or (s == "idle" and self.last_intent_text):
            actions.append("retry")
        return actions

    def pause(self) -> None:
        if self.state in ("running", "needs_approval", "needs_clarification"):
            self.state = "paused"
            self._touch()

    def resume(self) -> None:
        if self.state == "paused":
            self.state = "running"
            self._touch()

    def cancel(self) -> None:
        if self.state not in ("done", "cancelled"):
            self._cancel_requested = True
            self.state = "cancelled"
            self.failure_reason = "已取消"
            self._touch()

    def request_cancel(self) -> bool:
        return self._cancel_requested

    def _touch(self) -> None:
        self.heartbeat_at = _now_iso()

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "heartbeat_at": self.heartbeat_at,
            "started_at": self.started_at,
            "attempts": self.attempts,
            "events": self.events,
            "failure_reason": self.failure_reason,
            "last_status": (self.last_result or {}).get("status"),
            "actions": self.available_actions(),
        }


class WebConsole:
    """Owner Web Console 共享应用服务（CLI / Web UI / JSON API 共用）。"""

    def __init__(self, db_path: str, tenant_id: str = DEFAULT_TENANT,
                 default_project: str | None = None):
        self.db_path = db_path
        self.tenant_id = tenant_id
        self._default_project = default_project
        self._db: AIPDStateDB | None = None
        self.runs = RunController()

    # ------------------------------------------------------------- 基础
    @property
    def db(self) -> AIPDStateDB:
        if self._db is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = AIPDStateDB(self.db_path)
            self._db.ensure_default_tenant(self.tenant_id)
        return self._db

    def is_initialized(self) -> bool:
        return bool(self.projects())

    def projects(self) -> list[dict[str, Any]]:
        return self.db.list_projects(self.tenant_id)

    def active_project(self) -> str | None:
        if self._default_project and self._project_exists(self._default_project):
            return self._default_project
        projects = self.projects()
        return projects[0]["project_id"] if projects else None

    def _project_exists(self, project_id: str) -> bool:
        return any(p["project_id"] == project_id for p in self.projects())

    def require_project(self) -> str:
        pid = self.active_project()
        if pid is None:
            raise ValueError("当前没有项目；请先在首次使用向导中创建/导入项目。")
        return pid

    # --------------------------------------------------------- 首次使用向导
    def onboarding_center(self) -> dict[str, Any]:
        """环境检测 + Provider 配置状态 + 可自动修复/需凭据项。"""
        checks: list[dict[str, Any]] = []

        # Python 环境
        py_ok = sys.version_info >= (3, 9)
        checks.append({"name": "Python 运行环境", "status": "ok" if py_ok else "fail",
                       "detail": platform.python_version(), "fixable": not py_ok})

        # 数据库
        try:
            self.db.ensure_default_tenant(self.tenant_id)
            checks.append({"name": "状态数据库", "status": "ok",
                           "detail": self.db_path, "fixable": False})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "状态数据库", "status": "fail",
                           "detail": str(exc), "fixable": True})

        # 对象存储
        try:
            with tempfile.TemporaryDirectory() as td:
                store = ObjectStore(td)
                store.put("probe", "probe-key", b"probe")
            checks.append({"name": "对象存储", "status": "ok",
                           "detail": "ObjectStore 读写正常", "fixable": False})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "对象存储", "status": "fail",
                           "detail": str(exc), "fixable": True})

        # 目标目录写权限
        try:
            target = Path(self.db_path).parent
            target.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=str(target), delete=True):
                pass
            checks.append({"name": "数据目录权限", "status": "ok",
                           "detail": str(target), "fixable": False})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "数据目录权限", "status": "fail",
                           "detail": str(exc), "fixable": True})

        providers = self._providers()
        for p in providers:
            checks.append({
                "name": p["name"], "status": "ok" if p["configured"] else "external_dependency",
                "detail": (p["value"] or "未配置（需凭据）"), "fixable": False,
                "env": p["env"], "guide": p["guide"],
            })

        auto_fixable = [c for c in checks if c.get("fixable")]
        needs_credentials = [c for c in checks if c["status"] == "external_dependency"]

        return {
            "checks": checks,
            "auto_fixable": auto_fixable,
            "needs_credentials": needs_credentials,
            "providers": providers,
            "has_project": self.is_initialized(),
            "projects": [{"ref": safe_ref(p["project_id"]), "name": p.get("name"),
                          "goal": p.get("goal"), "details": {"project_id": p["project_id"]}}
                         for p in self.projects()],
        }

    def _providers(self) -> list[dict[str, Any]]:
        # 提示文案必须与实现真实读取的环境变量一致（此前提示 *_PROVIDER
        # 字段，实现却读 *_API_KEY / *_BACKEND / cadquery，照着提示配会配错）。
        s = get_settings()
        model_configured = bool(s.model_api_key and s.model_base_url)
        image_configured = bool(os.environ.get("AIPD_IMGGEN_BACKEND")
                                or (os.environ.get("AIPD_IMAGE_PROVIDER_URL")
                                    and os.environ.get("AIPD_IMAGE_API_KEY")))
        vision_configured = bool(os.environ.get("AIPD_VISION_PROVIDER_URL")
                                 and os.environ.get("AIPD_VISION_API_KEY"))
        try:
            import importlib.util
            cad_configured = importlib.util.find_spec("cadquery") is not None
        except Exception:  # noqa: BLE001
            cad_configured = False
        mail_configured = bool(os.environ.get("AIPD_SMTP_HOST")
                               or os.environ.get("AIPD_MAILPIT_SMTP_HOST"))
        return [
            {"name": "Model 模型", "key": "model_provider",
             "env": "AIPD_MODEL_API_KEY + AIPD_MODEL_BASE_URL",
             "value": s.model_base_url or "",
             "configured": model_configured,
             "guide": "同时设置 AIPD_MODEL_API_KEY 与 AIPD_MODEL_BASE_URL 可启用产品智能转译与想法结构化（product.* / idea.decompose）；真实评估端点另设 AIPD_EVAL_MODEL_ENDPOINT。"},  # noqa: E501
            {"name": "Image 图像生成", "key": "image_provider",
             "env": "AIPD_IMGGEN_BACKEND（或 AIPD_IMAGE_PROVIDER_URL + AIPD_IMAGE_API_KEY）",
             "value": os.environ.get("AIPD_IMGGEN_BACKEND") or os.environ.get("AIPD_IMAGE_PROVIDER_URL", ""),  # noqa: E501
             "configured": image_configured,
             "guide": "设置 AIPD_IMGGEN_BACKEND 指向可用图像后端（或 AIPD_IMAGE_PROVIDER_URL + AIPD_IMAGE_API_KEY 走真实图像端点）；未配置时手册页生成为外部任务包并标记 HOLD，绝不伪造图片。"},  # noqa: E501
            {"name": "Vision 视觉", "key": "vision_provider",
             "env": "AIPD_VISION_PROVIDER_URL + AIPD_VISION_API_KEY",
             "value": os.environ.get("AIPD_VISION_PROVIDER_URL", ""),
             "configured": vision_configured,
             "guide": "同时设置 AIPD_VISION_PROVIDER_URL 与 AIPD_VISION_API_KEY 以启用视觉审计；未配置时视觉校验如实标记外部依赖，绝不假通过。"},  # noqa: E501
            {"name": "CAD 内核", "key": "cad_provider",
             "env": "pip install aipd-os[cad]",
             "value": "cadquery" if cad_configured else "",
             "configured": cad_configured,
             "guide": "安装 cadquery 内核（pip install aipd-os[cad]）后成熟度可达 C2 及以上；未安装时如实标记 external_dependency，绝不越级。"},  # noqa: E501
            {"name": "Mail 邮件", "key": "mail_provider",
             "env": "AIPD_SMTP_HOST（+ AIPD_SMTP_USER / AIPD_SMTP_PASSWORD）",
             "value": os.environ.get("AIPD_SMTP_HOST", ""),
             "configured": mail_configured,
             "guide": "设置 AIPD_SMTP_HOST（配合 AIPD_SMTP_USER / AIPD_SMTP_PASSWORD）"
                      "以启用 RFQ 收发；未配置时供应链保持 HOLD。"},
        ]

    def fix_issue(self, name: str) -> dict[str, Any]:
        """一键修复可自动修复的问题（数据库初始化 / 目录创建 / 对象存储探针）。"""
        if name == "状态数据库":
            self.db.ensure_default_tenant(self.tenant_id)
            return {"ok": True, "name": name, "detail": "已初始化状态数据库与默认租户"}
        if name == "对象存储":
            base = Path(self.db_path).parent / "objects"
            base.mkdir(parents=True, exist_ok=True)
            store = ObjectStore(str(base))
            store.put("probe", "probe-key", b"probe")
            return {"ok": True, "name": name, "detail": "对象存储目录已就绪并通过读写探针"}
        if name == "数据目录权限":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "name": name, "detail": "数据目录已创建"}
        if name == "Python 运行环境":
            raise ValueError("Python 版本不满足最低要求，请升级到 3.9+，无法自动修复。")
        raise ValueError(f"当前问题无法自动修复或未识别：{name}")

    # ----------------------------------------------------------- 项目总览
    def overview(self, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        view = build_dashboard(self.db, pid, self.tenant_id)
        rs = build_resume_summary(self.db, pid, self.tenant_id)
        ps = build_project_summary(self.db, pid, self.tenant_id)
        project = self.db.get_project(self.tenant_id, pid)

        facts = self.db.list_facts(self.tenant_id, pid)
        cost = next((str(f["value"]) for f in facts
                     if "cost" in (f.get("key") or "").lower()), None)
        cost_display = cost if cost else "未设定成本约束"

        return {
            "project_ref": safe_ref(pid),
            "project_name": project.get("name"),
            "current_goal": view.get("current_goal"),
            "current_phase": rs.get("current_phase") or "初始阶段",
            "completed": view.get("done"),
            "gaps": view.get("missing"),
            "top_risk": view.get("top_risk"),
            "next_milestone": view.get("next_milestone"),
            "external_wait": view.get("external_waits"),
            "cost": cost_display,
            "time_estimate": self._time_estimate(ps),
            "next_step": self._next_action_cn(rs),
            "health": view.get("health", "良好"),
            "details": {
                "project_id": pid,
                "gate": project.get("gate"),
                "status": project.get("status"),
                "counts": ps.get("details", {}).get("counts", {}),
            },
        }

    def _time_estimate(self, ps: dict[str, Any]) -> str:
        counts = ps.get("details", {}).get("counts", {})
        pending = counts.get("open_decisions", 0)
        base = "按当前阶段计划推进"
        if pending:
            return f"等待您决策（{pending} 项待处理）后继续推进"
        deliverables = counts.get("deliverables", 0)
        return f"{base}；当前 {deliverables} 项交付物"

    def _next_action_cn(self, rs: dict[str, Any]) -> str:
        na = rs.get("next_action", "") or ""
        if isinstance(na, str):
            if na.startswith("resolve proposed decisions: "):
                return "处理待审决策：" + na[len("resolve proposed decisions: "):]
            if na.startswith("continue phase "):
                return "继续推进当前阶段：" + na[len("continue phase "):]
        return str(na) if na else "无下一步待办"

    # ----------------------------------------------------------- 决策中心
    def decision_center(self, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        card = build_decision_card(self.db, pid, tenant_id=self.tenant_id)
        if card is None:
            return {"has_decision": False, "decision": None, "ref": None}

        evidence = [
            {"title": e.get("title"), "kind": e.get("kind"),
             "summary": e.get("summary")}
            for e in self.db.list_evidence(self.tenant_id, pid)
        ]
        return {
            "has_decision": True,
            "ref": safe_ref(card["decision_id"]),
            "display_id": "事项一",
            "topic": card["topic"],
            "ai_recommendation": card["ai_recommendation"],
            "options": card["options"],
            "impacts": card["impacts"],
            "after_approval": card["after_approval"],
            "evidence": evidence[:5],
            "details": {"decision_id": card["decision_id"]},
        }

    def approve_decision(self, ref: str, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        target = self._decision_by_ref(pid, ref)
        self.db.resolve_decision(self.tenant_id, pid, target["decision_id"],
                                 choice=target.get("recommendation") or "推荐方案",
                                 comment="已由产品所有者在 Owner Web Console 批准")
        return {"ok": True, "topic": target.get("topic")}

    def choose_decision(self, ref: str, choice: str,
                        project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        target = self._decision_by_ref(pid, ref)
        self.db.resolve_decision(self.tenant_id, pid, target["decision_id"],
                                 choice=choice, comment="已由产品所有者在 Owner Web Console 选择")
        return {"ok": True, "topic": target.get("topic"), "choice": choice}

    def _decision_by_ref(self, pid: str, ref: str) -> dict[str, Any]:
        for d in self.db.list_open_decisions(self.tenant_id, pid):
            if safe_ref(d["decision_id"]) == ref:
                return d
        raise ValueError("未找到对应的待审事项")

    # ----------------------------------------------------------- 制品中心
    def artifact_center(self, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        ap = artifact_preview(self.db, pid, self.tenant_id)
        deliverables = self.db.list_deliverables(self.tenant_id, pid)
        artifacts: list[dict[str, Any]] = []
        for i, d in enumerate(deliverables, start=1):
            meta = _metadata(d)
            artifacts.append({
                "ref": safe_ref(d["deliverable_id"]),
                "display_id": f"制品 {i}",
                "type": type_cn(d.get("type")),
                "status": _status_cn(d.get("status")),
                "status_raw": d.get("status"),
                "version": d.get("version"),
                "path": d.get("path"),
                "thumbnail": meta.get("thumbnail") or meta.get("preview_image"),
                "preview_kind": _preview_kind(d.get("type")),
                "details": {"deliverable_id": d["deliverable_id"]},
            })
        return {
            "artifacts": artifacts,
            "cad_versions": ap.get("cad_versions", []),
            "bom_diffs": ap.get("bom_diffs", []),
            "parameter_diffs": ap.get("parameter_diffs", []),
        }

    def _deliverable_by_ref(self, pid: str, ref: str) -> dict[str, Any]:
        for d in self.db.list_deliverables(self.tenant_id, pid):
            if safe_ref(d["deliverable_id"]) == ref:
                return d
        raise ValueError("未找到对应的制品")

    def approve_artifact(self, ref: str, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        d = self._deliverable_by_ref(pid, ref)
        self.db.update_deliverable(self.tenant_id, pid, d["deliverable_id"],
                                   expected_version=d["version_no"], status="done")
        self.db.add_change(self.tenant_id, pid, "deliverable", d["deliverable_id"],
                           "accept", before={"status": d.get("status")},
                           after={"status": "done"}, reason="制品中心批准")
        return {"ok": True, "ref": ref, "display_id": self._display_for(pid, ref)}

    def reject_artifact(self, ref: str, reason: str = "",
                        project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        d = self._deliverable_by_ref(pid, ref)
        self.db.update_deliverable(self.tenant_id, pid, d["deliverable_id"],
                                   expected_version=d["version_no"], status="planned")
        self.db.add_change(self.tenant_id, pid, "deliverable", d["deliverable_id"],
                           "reject", before={"status": d.get("status")},
                           after={"status": "planned"}, reason=reason or "制品中心退回")
        return {"ok": True, "ref": ref, "reason": reason or "制品中心退回"}

    def rework_artifact(self, ref: str, note: str = "",
                        project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        d = self._deliverable_by_ref(pid, ref)
        new_version = self._bump_version(d.get("version"))
        self.db.update_deliverable(
            self.tenant_id, pid, d["deliverable_id"],
            expected_version=d["version_no"], status="in_progress", version=new_version)
        self.db.add_change(
            self.tenant_id, pid, "deliverable", d["deliverable_id"], "rework",
            before={"version": d.get("version"), "status": d.get("status")},
            after={"version": new_version, "status": "in_progress"},
            reason=note or ("局部返工"))
        return {"ok": True, "ref": ref, "from_version": d.get("version"),
                "to_version": new_version}

    def download_artifact(self, ref: str, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        d = self._deliverable_by_ref(pid, ref)
        path = d.get("path")
        if not path:
            raise ValueError("该制品尚未生成可下载文件")
        return {"ok": True, "ref": ref, "path": path, "available": Path(path).exists()}

    def _bump_version(self, version: str | None) -> str:
        v = str(version or "0.0")
        parts = v.split(".")
        try:
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
        except ValueError:
            return f"{v}.1"

    def _display_for(self, pid: str, ref: str) -> str:
        for i, d in enumerate(self.db.list_deliverables(self.tenant_id, pid), start=1):
            if safe_ref(d["deliverable_id"]) == ref:
                return f"制品 {i}"
        return ref

    # ----------------------------------------------------------- 运行控制
    def run_control(self, project_id: str | None = None) -> dict[str, Any]:
        return self.runs.snapshot()

    def start_run(self, intent_text: str,
                  project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        intent = parse_intent(intent_text, self.db, pid, self.tenant_id)
        tracker = ProgressTracker()
        # 不自动批准：requires_approval 的操作停在预览，须经决策中心显式批准。
        result = run_operation_loop(
            self.db, pid, intent, tenant_id=self.tenant_id, approved=False,
            progress=tracker, should_cancel=self.runs.request_cancel)
        if result.get("status") == "needs_approval":
            # run_operation_loop 的 needs_approval 分支本身不落库；这里补一条
            # 待审决策，供决策中心展示并显式批准（批准后由后续 run 触发执行）。
            self.db.propose_decision(
                self.tenant_id, pid,
                topic=str(intent_text)[:120] or "运行需要批准",
                recommendation="按 AI 推荐继续执行",
                options=["按 AI 推荐继续执行", "暂停并补充信息", "改为人工介入"],
                trigger="owner_web_requires_approval")
        self.runs.start(intent_text, tracker.events(), result)
        return self.runs.snapshot()

    def retry_run(self, project_id: str | None = None) -> dict[str, Any]:
        if not self.runs.last_intent_text:
            raise ValueError("没有可重试的运行")
        return self.start_run(self.runs.last_intent_text, project_id)

    def pause_run(self) -> dict[str, Any]:
        self.runs.pause()
        return self.runs.snapshot()

    def resume_run(self) -> dict[str, Any]:
        self.runs.resume()
        return self.runs.snapshot()

    def cancel_run(self) -> dict[str, Any]:
        self.runs.cancel()
        return self.runs.snapshot()

    # ----------------------------------------------------------- 外部等待
    def external_wait_center(self, project_id: str | None = None) -> dict[str, Any]:
        pid = project_id or self.require_project()
        waiting = (CheckpointManager(self.db)
                   .resume_summary(pid, self.tenant_id)["external_waiting"])
        ew = summarize_external_wait(waiting)
        items: list[dict[str, Any]] = []
        for i, it in enumerate(waiting, start=1):
            items.append({
                "display_id": f"外部事项 {i}",
                "what": self._wait_what(it),
                "who": self._wait_who(it),
                "needs_upload": self._wait_needs(it),
                "deadline": "未设置截止时间",
                "auto_continue": "收到数据后系统自动继续相关推进",
                "details": {"source_type": it.get("source_type"),
                            "target_type": it.get("target_type")},
            })
        return {
            "count": ew.get("count", len(waiting)),
            "summary": ew.get("summary", "项目当前无外部等待事项。"),
            "items": items,
        }

    def _wait_what(self, it: dict[str, Any]) -> str:
        note = it.get("note")
        if note:
            return f"其他事项：{note}"
        src = it.get("source_type") or "外部方"
        tgt = it.get("target_type") or "交付物"
        return f"等待{src}完成{tgt}"

    def _wait_who(self, it: dict[str, Any]) -> str:
        src = it.get("source_type")
        cn = {"supplier": "供应商", "lab": "测试实验室", "quote": "外部方",
              "rfq": "外部方", "vendor": "厂商", "test": "测试实验室"}
        return cn.get(str(src or "").lower(), src or "外部方")

    def _wait_needs(self, it: dict[str, Any]) -> str:
        note = it.get("note")
        if note:
            return str(note)
        tgt = it.get("target_type")
        cn = {"quote": "报价单", "sample": "样品", "test": "测试数据",
              "pvt": "生产验证数据", "evt": "工程验证数据", "dvt": "设计验证数据"}
        return cn.get(str(tgt or "").lower(), f"待接收外部数据（{tgt or '未指定'}）")

    # ----------------------------------------------------------- 项目创建
    def create_project(self, name: str, goal: str,
                       project_id: str | None = None) -> dict[str, Any]:
        name = (name or "").strip()
        goal = (goal or "").strip()
        if not name or not goal:
            raise ValueError("请提供项目名称与目标")
        pid = project_id or "p_" + hashlib.sha1(goal.encode("utf-8")).hexdigest()[:8]
        self.db.init_project(self.tenant_id, pid, name, goal)
        return {"ok": True, "ref": safe_ref(pid), "name": name, "goal": goal,
                "details": {"project_id": pid}}

    def import_project_from_examples(self) -> dict[str, Any]:
        """从内置示例导入一个示例项目（复用 onboarding 的示例列表，不虚构）。"""
        from aipd_os.experience.onboarding import list_examples
        examples = list_examples()
        if not examples:
            raise ValueError("没有可用的示例项目")
        ex = examples[0]
        pid = "ex_" + hashlib.sha1(ex["name"].encode("utf-8")).hexdigest()[:8]
        name = str(ex["name"])[:24]
        goal = str(ex.get("goal") or name)
        self.db.ensure_default_tenant(self.tenant_id)
        self.db.init_project(self.tenant_id, pid, name, goal)
        return {"ok": True, "ref": safe_ref(pid), "name": name, "goal": goal,
                "details": {"project_id": pid}}


__all__ = ["WebConsole", "RunController", "safe_ref"]
