"""首次使用体验（P2-3）：一句话建项 → 立即产出第一份结果 → 展示能力与
需外部配置项 → 引导配置 Image/Model/CAD/Mail Provider → 示例项目 → 恢复/重置。

全部确定性、可测、可运行于 CI；外部能力缺失时如实标 external_dependency，
绝不把未配置的能力描述为可用。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..state.backup import BackupManager
from ..state.db import AIPDStateDB
from .impact_analysis import type_cn
from .owner_dashboard import build_dashboard

# 需要外部配置的 Provider 与其环境变量/说明。
# 提示文案必须与实现真实读取的环境变量一致（envs 为多候选：任一非空即已配置）。
EXTERNAL_PROVIDERS = [
    {"name": "Image 图像生成",
     "envs": ["AIPD_IMGGEN_BACKEND", "AIPD_IMAGE_PROVIDER_URL"],
     "guide": "设置 AIPD_IMGGEN_BACKEND 指向可用的图像后端（或 AIPD_IMAGE_PROVIDER_URL + AIPD_IMAGE_API_KEY 走真实图像端点）。未配置时，手册页会生成为外部任务包并标记 HOLD，绝不伪造图片。"},  # noqa: E501
    {"name": "Model 模型",
     "envs": ["AIPD_MODEL_API_KEY", "AIPD_EVAL_MODEL_ENDPOINT"],
     "guide": "同时设置 AIPD_MODEL_API_KEY 与 AIPD_MODEL_BASE_URL 可启用产品智能与想法结构化；评估真实端点另设 AIPD_EVAL_MODEL_ENDPOINT。未配置时评估使用确定性 contract-test 夹具，不描述为真实模型。"},  # noqa: E501
    {"name": "CAD 内核",
     "envs": [],
     "guide": "安装 cadquery 内核（pip install aipd-os[cad]）后 CAD 可达到 C2 及以上；未安装时如实标 external_dependency，绝不越级。"},  # noqa: E501
    {"name": "Mail 邮件",
     "envs": ["AIPD_SMTP_HOST", "AIPD_MAILPIT_SMTP_HOST"],
     "guide": "设置 AIPD_SMTP_HOST（配合 AIPD_SMTP_USER / AIPD_SMTP_PASSWORD）以启用 RFQ 收发。未配置时供应链保持 HOLD。"},  # noqa: E501
]


def _project_id_for(idea: str, project_id: str | None) -> str:
    if project_id:
        return project_id
    return "p_" + hashlib.sha1(idea.encode("utf-8")).hexdigest()[:8]


def _first_result(db: AIPDStateDB, project_id: str, idea: str,
                  tenant_id: str) -> list[dict[str, Any]]:
    """立即产出第一份有价值的结果：写入目标事实、初始风险、首个待审决策与
    一份需求规格交付物。返回产出的条目列表。"""
    produced: list[dict[str, Any]] = []

    # 1) 项目目标写入 Product Truth
    db.add_fact(tenant_id, project_id, "product_goal", idea, "C",
                source="onboarding", conditions="产品所有者一句话需求")
    produced.append({"kind": "fact", "label": "记录项目目标", "detail": idea})

    # 2) 初始风险（确定性：含量产/供应链/成本字样给供应链风险，否则给需求澄清风险）
    if any(w in idea for w in ("量产", "供应链", "成本")):
        db.add_risk(tenant_id, project_id, "量产与供应链投入待评估",
                    probability="medium", impact="high",
                    mitigation="先完成设计与验证，再评估量产路径")
        produced.append({"kind": "risk", "label": "识别初始风险", "detail": "量产与供应链投入待评估"})  # noqa: E501
    else:
        db.add_risk(tenant_id, project_id, "需求细节需进一步澄清",
                    probability="low", impact="medium",
                    mitigation="通过会话逐步澄清规格")
        produced.append({"kind": "risk", "label": "识别初始风险", "detail": "需求细节需进一步澄清"})

    # 3) 一份需求规格交付物（首份可见产物）
    spec_id = db.add_deliverable(tenant_id, project_id, "spec",
                                 path=f"/out/{project_id}/spec.md",
                                 status="planned", version="0.1",
                                 metadata={"title": "需求规格"})
    produced.append({"kind": "deliverable", "label": "创建需求规格",
                     "detail": type_cn("spec"), "deliverable_id": spec_id})

    # 4) 首个待审决策：给所有者一个可立即决定的方向
    db.propose_decision(tenant_id, project_id, "首个方案方向",
                        "推荐先完成需求与规格冻结",
                        ["按推荐：先冻结需求与规格", "先做市场调研再定规格", "直接进入概念设计"],
                        trigger="onboarding_first_decision")
    produced.append({"kind": "decision", "label": "提出首个待决定事项",
                     "detail": "首个方案方向"})
    return produced


def provider_config_status() -> list[dict[str, Any]]:
    """返回各 Provider 的配置状态（configured / external_dependency）。"""
    out: list[dict[str, Any]] = []
    for p in EXTERNAL_PROVIDERS:
        if p["name"] == "CAD 内核":
            try:
                import importlib.util
                configured = importlib.util.find_spec("cadquery") is not None
            except Exception:  # noqa: BLE001
                configured = False
        else:
            configured = any(
                os.environ.get(e, "").strip() for e in p["envs"])
        out.append({
            "name": p["name"], "env": " / ".join(p["envs"]) or "cadquery",
            "configured": bool(configured),
            "status": "ok" if configured else "external_dependency",
            "guide": p["guide"],
        })
    return out


def list_examples(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """列出内置示例项目（来自 evals/golden_projects 与 assets/examples）。"""
    examples: list[dict[str, Any]] = []
    root = repo_root or Path(__file__).resolve().parents[3]
    golden = root / "evals" / "golden_projects"
    if golden.is_dir():
        for d in sorted(golden.iterdir()):
            if d.is_dir():
                pj = d / "project.json"
                if pj.exists():
                    try:
                        data = json.loads(pj.read_text(encoding="utf-8"))
                    except Exception:  # noqa: BLE001
                        data = {}
                    examples.append({"source": "golden", "name": d.name,
                                     "goal": data.get("goal") or data.get("name") or d.name})
    assets = root / "assets" / "examples"
    if assets.is_dir():
        for f in sorted(assets.glob("*.json")):
            examples.append({"source": "asset", "name": f.stem, "goal": f.stem})
    return examples


def onboard(db: AIPDStateDB, idea: str, project_id: str | None = None,
            tenant_id: str = "default") -> dict[str, Any]:
    """首次使用引导主流程，返回引导结果（含第一份结果、能力、外部配置、示例、恢复信息）。"""
    idea = (idea or "").strip()
    if not idea:
        raise ValueError("请提供一句话产品想法（--idea）。")
    pid = _project_id_for(idea, project_id)
    name = idea if len(idea) <= 24 else idea[:24]

    db.ensure_default_tenant(tenant_id)
    db.init_project(tenant_id, pid, name, idea)
    produced = _first_result(db, pid, idea, tenant_id)

    # 先做一次备份，便于 reset/recover
    backup_path = str(Path(db.path).parent / "backups")
    BackupManager(db.path, backup_dir=backup_path).create_backup(db, out_dir=backup_path)

    providers = provider_config_status()
    return {
        "project_id": pid,
        "name": name,
        "goal": idea,
        "produced": produced,
        "first_result": build_dashboard(db, pid, tenant_id),
        "capabilities": providers,
        "external_config_needed": [c for c in providers
                                   if c["status"] == "external_dependency"],
        "examples": list_examples(),
        "reset": "可用 `aipd reset --db <db> --project <id>` 重置本项目",
        "recover": "可用 `aipd recover --db <db> --project <id>` 回滚最近可撤销操作 / 从备份恢复",
    }


def reset_project(db: AIPDStateDB, project_id: str,
                  tenant_id: str = "default") -> dict[str, Any]:
    """重置项目：先备份再删除，返回重置结果。"""
    backup_path = str(Path(db.path).parent / "backups")
    backup_dir = BackupManager(db.path, backup_dir=backup_path).create_backup(
        db, out_dir=backup_path)
    db.delete_project(tenant_id, project_id)
    return {"project_id": project_id, "reset": True,
            "backup": backup_dir,
            "note": "已重置该项目；如需恢复请使用 `aipd recover` / `aipd resume --backup`."}


def recover_project(db_path: str, project_id: str | None = None,
                    backup: str | None = None) -> dict[str, Any]:
    """恢复：从备份恢复数据库，或返回最近备份列表。"""
    db_path_obj = Path(db_path)
    manager = BackupManager(db_path_obj)
    if backup:
        restored = manager.restore_backup(backup, db_path=str(db_path_obj))
        return {"restored": restored, "note": "已从备份恢复数据库"}
    backups = manager.list_backups()
    return {"backups": backups, "note": "未指定备份；可用 --backup <dir> 恢复",
            "latest": backups[0] if backups else None}


__all__ = ["onboard", "reset_project", "recover_project", "provider_config_status",
           "list_examples", "EXTERNAL_PROVIDERS"]
