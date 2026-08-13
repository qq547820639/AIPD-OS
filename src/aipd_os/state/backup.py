"""备份管理：创建 / 列示 / 恢复 / 保留期清理。

备份 = 数据库文件副本 + 携带校验和（sha256）的 manifest JSON。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import AIPDStateDB


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class BackupManager:
    def __init__(self, db_path: str | Path, backup_dir: str | Path | None = None):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.db_path.parent / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, db: str | Path | AIPDStateDB, out_dir: str | Path | None = None) -> str:
        """复制数据库文件并写入 manifest（含校验和）。返回备份目录路径。"""
        src = Path(db.path) if isinstance(db, AIPDStateDB) else Path(db)
        out = Path(out_dir) if out_dir else self.backup_dir
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ%f")
        backup_dir = out / f"backup_{stamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        db_file = backup_dir / src.name
        shutil.copy2(src, db_file)
        checksum = _checksum(db_file)
        manifest = {
            "backup_created_at": datetime.now(timezone.utc).isoformat(),
            "source_db": str(src),
            "db_name": src.name,
            "checksum": checksum,
            "size": db_file.stat().st_size,
        }
        (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return str(backup_dir)

    def list_backups(self, base_dir: str | Path | None = None) -> list[dict[str, Any]]:
        base = Path(base_dir) if base_dir else self.backup_dir
        backups = []
        if base.is_dir():
            for d in sorted(base.iterdir(), key=lambda p: p.name):
                manifest_path = d / "manifest.json"
                if not d.is_dir() or not manifest_path.exists():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                manifest["backup_dir"] = str(d)
                backups.append(manifest)
        backups.sort(key=lambda b: b.get("backup_created_at", ""), reverse=True)
        return backups

    def restore_backup(self, backup: str | dict, db_path: str | Path | None = None) -> str:
        """把备份恢复到指定 db_path（校验 checksum）。返回恢复后的 db 路径。"""
        if isinstance(backup, dict):
            backup_dir = Path(backup["backup_dir"])
            db_name = backup.get("db_name")
            checksum = backup.get("checksum")
        else:
            backup_dir = Path(backup)
            manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
            db_name = manifest.get("db_name")
            checksum = manifest.get("checksum")
        src_file = backup_dir / (db_name or self.db_path.name)
        if not src_file.exists():
            raise FileNotFoundError(f"backup db file missing: {src_file}")
        if checksum and _checksum(src_file) != checksum:
            raise ValueError("backup checksum mismatch; refusing to restore corrupted backup")
        target = Path(db_path) if db_path else self.db_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, target)
        return str(target)

    def retention_prune(self, backups: list[dict[str, Any]] | None = None,
                        retention_days: int = 90) -> list[str]:
        """按保留期删除过期备份，返回被删除的备份目录列表。"""
        if backups is None:
            backups = self.list_backups()
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed = []
        for b in backups:
            created = b.get("backup_created_at", "")
            try:
                dt = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                continue
            if dt < cutoff:
                d = Path(b["backup_dir"])
                if d.is_dir():
                    shutil.rmtree(d)
                    removed.append(str(d))
        return removed


__all__ = ["BackupManager"]
