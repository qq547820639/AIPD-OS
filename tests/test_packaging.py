"""打包与基础模块的冒烟测试。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import aipd_os
from aipd_os import __version__
from aipd_os.config import Settings, get_settings, reload_settings
from aipd_os.logging_utils import get_logger, log_event

ROOT = Path(__file__).resolve().parent.parent


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_manifest() -> Path | None:
    """定位发布清单：仓库根目录优先，其次 releases/ 下的最新版本。"""
    candidates = [ROOT / "RELEASE_MANIFEST.json"]
    releases_dir = ROOT / "releases"
    if releases_dir.is_dir():
        candidates += sorted(releases_dir.glob("*/RELEASE_MANIFEST.json"))
    for c in candidates:
        if c.exists():
            return c
    return None


def test_version() -> None:
    assert __version__ == "5.3.0"
    assert aipd_os.__version__ == "5.3.0"


def test_config_imports_and_defaults() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.mode in {"local", "server"}
    assert settings.retention_days > 0


def test_config_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIPD_LOG_LEVEL", "DEBUG")
    settings = reload_settings()
    assert settings.log_level == "DEBUG"


def test_logging_event() -> None:
    logger = get_logger("aipd.tests")
    log_event(logger, "test_event", foo="bar", n=1)
    assert logger.name == "aipd.tests"


def test_release_manifest_is_internally_consistent() -> None:
    """发布清单内部一致性：不引用自身、路径唯一、条目字段齐全。"""
    manifest_path = _find_manifest()
    if manifest_path is None:
        pytest.skip("未找到 RELEASE_MANIFEST.json，跳过打包可复现性检查")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict), "清单必须是 JSON 对象"
    files = manifest.get("files")
    assert isinstance(files, list) and files, "清单必须包含非空的 files 列表"

    paths = [f["path"] for f in files]
    assert manifest_path.name not in paths, "清单不得自引用自身"
    assert len(paths) == len(set(paths)), "清单中存在重复路径"

    for f in files:
        assert isinstance(f.get("path"), str), f"缺失 path: {f}"
        assert isinstance(f.get("sha256"), str), f"缺失 sha256: {f}"
        assert isinstance(f.get("size"), int), f"缺失 size: {f}"


def test_release_manifest_hashes_match_disk() -> None:
    """发布清单的 SHA-256 必须与磁盘上实际文件一致（可复现性）。"""
    manifest_path = _find_manifest()
    if manifest_path is None:
        pytest.skip("未找到 RELEASE_MANIFEST.json，跳过打包可复现性检查")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for f in manifest["files"]:
        p = ROOT / f["path"]
        if not p.exists():
            mismatches.append(f"{f['path']}: 文件不存在")
            continue
        if _sha256_hex(p) != f["sha256"]:
            mismatches.append(f"{f['path']}: SHA-256 不匹配")
        if f.get("size") is not None and p.stat().st_size != f["size"]:
            mismatches.append(f"{f['path']}: 大小不匹配")

    assert not mismatches, "发布清单与磁盘不一致：\n" + "\n".join(mismatches)