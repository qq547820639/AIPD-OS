"""AIPD-OS 统一配置模块。

从环境变量（前缀 ``AIPD_``）以及可选的 YAML / JSON 配置文件读取配置，
提供统一的 :class:`Settings` 数据类与缓存的 :func:`get_settings`。

本模块不强制依赖 pyyaml：若已安装则支持 YAML，否则回退到 JSON 文件。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

try:  # pyyaml 为可选依赖
    import yaml  # type: ignore

    _HAS_YAML = True
except Exception:  # pragma: no cover - 环境回退分支
    yaml = None  # type: ignore
    _HAS_YAML = False

ENV_PREFIX = "AIPD_"
DEFAULT_CONFIG_FILES = ["aipd.json", "aipd.yaml", "aipd.yml", "config/aipd.yaml"]

# 遵循环境变量允许的布尔值
_TRUE_VALUES = {"1", "true", "yes", "on", "y"}


def _env(name: str, default: Any = None) -> Any:
    """读取 ``AIPD_<NAME>`` 形式的环境变量，未设置时返回 default。"""
    key = ENV_PREFIX + name
    if key in os.environ:
        return os.environ[key]
    return default


@dataclass
class Settings:
    """AIPD-OS 运行配置。

    优先级（从高到低）：环境变量 > YAML/JSON 配置文件 > 默认值。
    """

    db_dir: str = "data"
    log_level: str = "INFO"
    mode: str = "local"  # "local" / "server"
    data_encryption_key: str = ""
    retention_days: int = 90
    host: str = "127.0.0.1"
    port: int = 8080
    # 外部 Provider 配置（model / image / vision / CAD / mail）
    model_provider: str = ""
    image_provider: str = ""
    vision_provider: str = ""
    cad_provider: str = ""
    mail_provider: str = ""
    # 通用 LLM Provider（OpenAI 兼容）配置（v5.9.2 N-1）。
    # model_name 未配置时 LLM 侧用合理默认（如 "gpt-4o-mini"），Settings 保持空串。
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = ""
    config_files: List[Path] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Settings:
        """从字典构造 Settings，忽略未知字段，未知字段放入 ``extra``。"""
        known = {f for f in cls.__dataclass_fields__}
        values: Dict[str, Any] = {}
        extra: Dict[str, Any] = {}
        for key, val in data.items():
            if key in known:
                values[key] = val
            else:
                extra[key] = val
        values["extra"] = extra
        return cls(**values)

    def apply_env(self) -> None:
        """用环境变量覆盖配置（高优先级）。

        v5.8.2 Commit 9：加密 key canonical 化 ——
        ``AIPD_ENCRYPTION_KEY`` 是 canonical；``AIPD_DATA_ENCRYPTION_KEY``
        是 deprecated alias（读取优先级：canonical → alias → 默认）。
        两者同时配置且不同 → RuntimeError（不静默选择）。
        """
        if _env("DB_DIR") is not None:
            self.db_dir = str(_env("DB_DIR"))
        if _env("LOG_LEVEL") is not None:
            self.log_level = str(_env("LOG_LEVEL")).upper()
        if _env("MODE") is not None:
            self.mode = str(_env("MODE")).lower()
        canonical = _env("ENCRYPTION_KEY")
        alias = _env("DATA_ENCRYPTION_KEY")
        if canonical is not None and alias is not None and canonical != alias:
            raise RuntimeError(
                "conflicting encryption keys: AIPD_ENCRYPTION_KEY (canonical) "
                "and AIPD_DATA_ENCRYPTION_KEY (deprecated alias) are both set "
                "with different values; set only AIPD_ENCRYPTION_KEY")
        if canonical is not None:
            self.data_encryption_key = str(canonical)
        elif alias is not None:
            self.data_encryption_key = str(alias)
        if _env("RETENTION_DAYS") is not None:
            self.retention_days = int(_env("RETENTION_DAYS"))
        if _env("HOST") is not None:
            self.host = str(_env("HOST"))
        if _env("PORT") is not None:
            self.port = int(_env("PORT"))
        if _env("MODEL_PROVIDER") is not None:
            self.model_provider = str(_env("MODEL_PROVIDER"))
        if _env("IMAGE_PROVIDER") is not None:
            self.image_provider = str(_env("IMAGE_PROVIDER"))
        if _env("VISION_PROVIDER") is not None:
            self.vision_provider = str(_env("VISION_PROVIDER"))
        if _env("CAD_PROVIDER") is not None:
            self.cad_provider = str(_env("CAD_PROVIDER"))
        if _env("MAIL_PROVIDER") is not None:
            self.mail_provider = str(_env("MAIL_PROVIDER"))
        if _env("MODEL_API_KEY") is not None:
            self.model_api_key = str(_env("MODEL_API_KEY"))
        if _env("MODEL_BASE_URL") is not None:
            self.model_base_url = str(_env("MODEL_BASE_URL"))
        if _env("MODEL_NAME") is not None:
            self.model_name = str(_env("MODEL_NAME"))


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件 {path} 顶层必须是对象")
    return data


def _load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(open(path, encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件 {path} 顶层必须是对象")
    return data


def _load_file(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if not _HAS_YAML:
            raise RuntimeError(
                f"检测到 YAML 配置文件 {path}，但未安装 pyyaml。"
                "请安装 pyyaml 或改用 .json 配置文件。"
            )
        return _load_yaml(path)
    if suffix == ".json":
        return _load_json(path)
    # 无后缀时先尝试 JSON，失败再尝试 YAML
    try:
        return _load_json(path)
    except Exception:
        if _HAS_YAML:
            return _load_yaml(path)
        raise


def _resolve_config_files() -> List[Path]:
    """解析配置文件路径：优先 ``AIPD_CONFIG`` 环境变量，否则扫描默认路径。"""
    explicit = _env("CONFIG")
    if explicit:
        return [Path(explicit)]
    found: List[Path] = []
    for rel in DEFAULT_CONFIG_FILES:
        p = Path(rel)
        if p.is_file():
            found.append(p)
    return found


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """读取并缓存全局配置。"""
    settings = Settings()

    files = _resolve_config_files()
    for path in files:
        data = _load_file(path)
        settings = settings.from_dict(data)
    settings.config_files = files

    settings.apply_env()
    return settings


def reload_settings() -> Settings:
    """清除缓存并重新加载配置。"""
    get_settings.cache_clear()
    return get_settings()


__all__ = [
    "Settings",
    "get_settings",
    "reload_settings",
    "ENV_PREFIX",
]
