"""对象存储分层：``StateBackend`` 抽象 + 本地文件适配器 + 远端适配器桩。

统一状态服务依赖一个对象存储后端来承载手工批次、附件、Visual Bible、
生成任务与返工计划等非结构化对象。本模块提供：

  - :class:`StateBackend`：统一接口（真实实现所需的抽象）；
  - :class:`LocalStateBackend`：真实实现，基于文件系统（复用 :class:`ObjectStore`）；
  - :class:`RemoteStateBackend`：诚实桩。云对象存储需要真实凭据/端点，
    当前未配置，调用即抛 :class:`ExternalDependencyError`，绝不伪造云持久化。

``snapshot`` / ``restore`` 用于把某项目对象整体导出/导回，配合统一备份流程把
数据库 + 对象 + 附件索引作为一个单元保存与恢复。
"""
from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from pathlib import Path

from .objects import ObjectStore

DEFAULT_TENANT = "default"


class ExternalDependencyError(RuntimeError):
    """所需能力依赖外部系统（如云对象存储），当前未配置真实凭据。"""


class StateBackend(ABC):
    """对象存储统一接口。所有实现必须支持 put/get/list/delete/snapshot/restore。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """后端标识，如 ``local`` / ``remote``。"""

    @abstractmethod
    def put(self, project_id: str, key: str, data: bytes,
            tenant_id: str = DEFAULT_TENANT) -> str:
        """写入对象，返回对象引用（路径/键）。"""

    @abstractmethod
    def get(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> bytes:
        """读取对象；不存在抛 KeyError。"""

    @abstractmethod
    def list(self, project_id: str, tenant_id: str = DEFAULT_TENANT) -> builtins.list[dict]:
        """列出项目中全部对象元数据。"""

    @abstractmethod
    def delete(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> None:
        """删除对象。"""

    @abstractmethod
    def snapshot(self, project_id: str, tenant_id: str, out_dir: str) -> str:
        """把项目对象整体导出到 out_dir，返回 out_dir。"""

    @abstractmethod
    def restore(self, snapshot_dir: str, project_id: str,
                tenant_id: str = DEFAULT_TENANT) -> int:
        """从 snapshot_dir 导回到本项目，返回恢复的对象数量。"""


class LocalStateBackend(StateBackend):
    """文件系统对象存储适配器（真实实现，复用 :class:`ObjectStore`）。"""

    def __init__(self, store: ObjectStore | None = None,
                 base_dir: str | Path | None = None,
                 retention_days: int = 90):
        if store is None:
            if base_dir is None:
                raise ValueError("必须提供 store 或 base_dir")
            store = ObjectStore(base_dir, retention_days=retention_days)
        self._store = store

    @property
    def name(self) -> str:
        return "local"

    def put(self, project_id: str, key: str, data: bytes,
            tenant_id: str = DEFAULT_TENANT) -> str:
        return self._store.put(project_id, key, data, tenant_id)

    def get(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> bytes:
        return self._store.get(project_id, key, tenant_id)

    def list(self, project_id: str, tenant_id: str = DEFAULT_TENANT) -> builtins.list[dict]:
        return self._store.list(project_id, tenant_id)

    def delete(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> None:
        self._store.delete(project_id, key, tenant_id)

    def snapshot(self, project_id: str, tenant_id: str, out_dir: str) -> str:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for obj in self._store.list(project_id, tenant_id):
            data = self._store.get(project_id, obj["key"], tenant_id)
            (out / obj["key"]).write_bytes(data)
        return str(out)

    def restore(self, snapshot_dir: str, project_id: str,
                tenant_id: str = DEFAULT_TENANT) -> int:
        src = Path(snapshot_dir)
        restored = 0
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    self._store.put(project_id, f.name, f.read_bytes(), tenant_id)
                    restored += 1
        return restored


class RemoteStateBackend(StateBackend):
    """远端（云）对象存储适配器桩。

    诚实实现：云对象存储需要真实端点与凭据，当前未配置。任何实际读写操作都会
    抛出 :class:`ExternalDependencyError`，标记为 ``external_dependency``，绝不
    伪造云持久化。接入真实云存储时由本类实现同一接口即可无缝替换。
    """

    EXTERNAL_DEPENDENCY = "remote object storage"

    def __init__(self, endpoint: str | None = None, credentials: bool = False):
        self.endpoint = endpoint
        self._configured = bool(endpoint and credentials)

    @property
    def name(self) -> str:
        return "remote"

    def _raise(self) -> None:
        raise ExternalDependencyError(
            f"{self.EXTERNAL_DEPENDENCY} not configured: no real cloud credentials. "
            "Implement RemoteStateBackend.put/get/... against your provider to enable "
            "cloud object persistence.")

    def put(self, project_id: str, key: str, data: bytes,
            tenant_id: str = DEFAULT_TENANT) -> str:
        self._raise()

    def get(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> bytes:
        self._raise()

    def list(self, project_id: str, tenant_id: str = DEFAULT_TENANT) -> builtins.list[dict]:
        self._raise()

    def delete(self, project_id: str, key: str, tenant_id: str = DEFAULT_TENANT) -> None:
        self._raise()

    def snapshot(self, project_id: str, tenant_id: str, out_dir: str) -> str:
        self._raise()

    def restore(self, snapshot_dir: str, project_id: str,
                tenant_id: str = DEFAULT_TENANT) -> int:
        self._raise()


__all__ = [
    "StateBackend", "LocalStateBackend", "RemoteStateBackend",
    "ExternalDependencyError", "DEFAULT_TENANT",
]
