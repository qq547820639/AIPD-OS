"""制品预览：面向所有者的产物视图。

制品在这里对应状态库里的 deliverables（类型如 manual / cad / bom / drawing 等）。
提供：手册页面缩略信息、CAD 版本变化、BOM 差异、参数差异。
纯数据 + 路径即可，不做任何图片渲染。
"""
from __future__ import annotations

import json
from typing import Any

from ..state.db import AIPDStateDB


def _metadata(d: dict[str, Any]) -> dict[str, Any]:
    """deliverables 表把 metadata 存为 metadata_json，需自行解码。"""
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


def _entry(d: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = _metadata(d)
    entry: dict[str, Any] = {
        "deliverable_id": d.get("deliverable_id"),
        "type": d.get("type"),
        "path": d.get("path"),
        "status": d.get("status"),
        "version": d.get("version"),
        "thumbnail": meta.get("thumbnail") or meta.get("preview_image"),
    }
    if extra:
        entry.update(extra)
    return entry


def artifact_preview(db: AIPDStateDB, project_id: str,
                     tenant_id: str = "default") -> dict[str, Any]:
    """返回制品的预览结构：手册页 / CAD 版本 / BOM 差异 / 参数差异。"""
    deliverables = db.list_deliverables(tenant_id, project_id)
    changes = db.list_changes(tenant_id, project_id)

    manual_pages: list[dict[str, Any]] = []
    cad_versions: list[dict[str, Any]] = []
    bom_diffs: list[dict[str, Any]] = []
    parameter_diffs: list[dict[str, Any]] = []

    for d in deliverables:
        dtype = (d.get("type") or "").lower()
        if "manual" in dtype or "page" in dtype:
            manual_pages.append(_entry(d))
        elif "cad" in dtype:
            cad_versions.append(_entry(d))
        elif "bom" in dtype:
            bom_diffs.append(_entry(d))

    # CAD 版本变化：从变更记录里提取 before/after version
    for ch in changes:
        if ch.get("object_type") == "deliverable" and ch.get("action") in ("update", "create"):
            before = ch.get("before") or {}
            after = ch.get("after") or {}
            if isinstance(before, dict) and isinstance(after, dict):
                if before.get("version") != after.get("version"):
                    cad_versions.append({
                        "deliverable_id": ch.get("object_id"),
                        "from_version": before.get("version"),
                        "to_version": after.get("version"),
                        "reason": ch.get("reason"),
                    })
        # 参数差异：fact 的变更通常是参数
        if ch.get("object_type") == "fact" and isinstance(ch.get("after"), dict):
            after = ch["after"]
            before = (ch.get("before") or {}) if isinstance(ch.get("before"), dict) else {}
            parameter_diffs.append({
                "parameter": ch.get("object_id"),
                "key": after.get("key"),
                "from": before.get("value"),
                "to": after.get("value"),
                "reason": ch.get("reason"),
            })

    return {
        "manual_pages": manual_pages,
        "cad_versions": cad_versions,
        "bom_diffs": bom_diffs,
        "parameter_diffs": parameter_diffs,
        "details": {
            "project_id": project_id,
            "tenant_id": tenant_id,
            "deliverable_count": len(deliverables),
            "change_count": len([c for c in changes if c.get("object_type") == "deliverable"]),
        },
    }


__all__ = ["artifact_preview"]
