"""文件对象存储，带保留期清理。

文件按 ``<base_dir>/<tenant>/<project>/<key>`` 组织，key 经过路径安全化处理。
"""
from __future__ import annotations

import builtins
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_TENANT = "default"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(name: str) -> str:
    return _SAFE.sub("_", name)


class ObjectStore:
    def __init__(self, base_dir: str | Path, retention_days: int = 90):
        self._base = Path(base_dir)
        self._retention_days = retention_days
        self._base.mkdir(parents=True, exist_ok=True)

    def _dir(self, project_id: str, tenant_id: str) -> Path:
        d = self._base / _safe(tenant_id) / _safe(project_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def put(self, project_id: str, key: str, data: bytes, tenant_id: str = DEFAULT_TENANT) -> str:
        d = self._dir(project_id, tenant_id)
        target = d / _safe(key)
        target.write_bytes(data)
        return str(target)

    def get(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> bytes:
        target = self._dir(project_id, tenant_id) / _safe(key)
        if not target.exists():
            raise KeyError(key)
        return target.read_bytes()

    def list(self, project_id: str, tenant_id: str = DEFAULT_TENANT) -> builtins.list[dict]:
        d = self._base / _safe(tenant_id) / _safe(project_id)
        items = []
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file():
                    st = p.stat()
                    items.append({"key": p.name, "size": st.st_size,
                                  "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
        return items

    def delete(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> None:
        target = self._base / _safe(tenant_id) / _safe(project_id) / _safe(key)
        if target.exists():
            target.unlink()

    def retention_prune(self, age_days: int | None = None) -> int:
        """删除超过 age_days 未被修改的对象，返回删除数量。"""
        age = age_days if age_days is not None else self._retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=age)
        removed = 0
        for tenant in self._base.iterdir():
            if not tenant.is_dir():
                continue
            for project in tenant.iterdir():
                if not project.is_dir():
                    continue
                for p in project.iterdir():
                    if not p.is_file():
                        continue
                    mtime = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
                    if mtime < cutoff:
                        p.unlink()
                        removed += 1
        return removed


__all__ = ["ObjectStore"]
