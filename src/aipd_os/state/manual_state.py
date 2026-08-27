"""Manual State Repository — canonicalize legacy JSON state.

P2-M4: Manual State Canonicalization

将 manual_chain 的 JSON 直接读写收敛到 Repository 模式。
Phase A: read canonical → fallback legacy JSON → write canonical
Phase B: on legacy read → import once → write canonical
Phase C: legacy JSON read only under explicit compatibility flag
Phase D: remove after documented deprecation window

当前实现 Phase A/B: 支持 legacy JSON 导入 + canonical 读写。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_hash(path: Path) -> str:
    """计算文件内容 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManualStateRepository:
    """Manual workflow state 的 Repository。

    支持：
    - canonical JSON 文件读写（primary）
    - legacy JSON 文件导入（one-time migration）
    - 幂等导入（相同内容不重复）
    - tenant/project scope 注入
    """

    def __init__(
        self,
        canonical_dir: str | Path,
        tenant_id: str = "default",
        project_id: str = "",
    ) -> None:
        self._canonical_dir = Path(canonical_dir)
        self._canonical_dir.mkdir(parents=True, exist_ok=True)
        self._tenant_id = tenant_id
        self._project_id = project_id

    def _canonical_path(self, workflow_id: str) -> Path:
        """canonical state 文件路径。"""
        return self._canonical_dir / f"{workflow_id}.canonical.json"

    def _import_ledger_path(self) -> Path:
        """导入记录路径。"""
        return self._canonical_dir / ".import_ledger.json"

    def _load_import_ledger(self) -> dict[str, Any]:
        """加载导入记录。"""
        path = self._import_ledger_path()
        if path.exists():
            result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return result
        return {}

    def _save_import_ledger(self, ledger: dict[str, Any]) -> None:
        """保存导入记录。"""
        self._import_ledger_path().write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def read(self, workflow_id: str) -> dict[str, Any] | None:
        """读取 canonical state。"""
        path = self._canonical_path(workflow_id)
        if path.exists():
            result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return result
        return None

    def write(self, workflow_id: str, state: dict[str, Any]) -> None:
        """写入 canonical state。"""
        state["_tenant_id"] = self._tenant_id
        state["_project_id"] = self._project_id
        state["_updated_at"] = _now()
        self._canonical_path(workflow_id).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def import_from_legacy(
        self,
        workflow_id: str,
        legacy_path: str | Path,
        force: bool = False,
    ) -> dict[str, Any]:
        """从 legacy JSON 导入到 canonical。

        幂等：相同内容不重复导入。
        如果 canonical 已存在且内容不同，需要 force=True。
        """
        legacy = Path(legacy_path)
        if not legacy.exists():
            raise FileNotFoundError(f"legacy file not found: {legacy}")

        legacy_hash = _file_hash(legacy)
        ledger = self._load_import_ledger()
        import_key = f"{workflow_id}:{legacy_hash}"

        # 幂等检查
        if import_key in ledger and not force:
            return {"status": "NO_OP", "reason": "already imported"}

        # 冲突检查
        existing = self.read(workflow_id)
        if existing and not force:
            existing_hash = hashlib.sha256(
                json.dumps(existing, sort_keys=True).encode()).hexdigest()
            if existing_hash != legacy_hash:
                return {"status": "CONFLICT", "reason": "canonical exists with different content"}

        # 执行导入
        legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
        self.write(workflow_id, legacy_data)

        # 记录导入
        ledger[import_key] = {
            "imported_at": _now(),
            "legacy_path": str(legacy),
            "legacy_hash": legacy_hash,
            "tenant_id": self._tenant_id,
            "project_id": self._project_id,
        }
        self._save_import_ledger(ledger)

        return {"status": "IMPORTED", "legacy_hash": legacy_hash}

    def export_to_json(self, workflow_id: str, export_path: str | Path) -> None:
        """导出 canonical state 到 JSON（projection, not truth）。"""
        state = self.read(workflow_id)
        if state is None:
            raise FileNotFoundError(f"workflow {workflow_id} not found")
        state["_export_type"] = "projection"
        state["_exported_at"] = _now()
        Path(export_path).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8")
