"""重新生成仓库根目录的 RELEASE_MANIFEST.json（完整仓库可复现清单）。

以 ``git ls-files`` 为准（已跟踪文件），排除发布产物与本地生成物，
逐文件计算 size 与 SHA-256，并刷新版本/日期头字段。
用法：python scripts/regenerate_release_manifest.py [--version 5.4.0]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# 排除：清单自身、发布产物、虚拟环境、构建与缓存目录
_EXCLUDE_PREFIXES = (
    "RELEASE_MANIFEST.json",
    "releases/",
    "build/",
    "dist/",
    ".venv/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "__pycache__/",
    "src/aipd_os.egg-info/",
)


def _tracked_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="5.4.0")
    args = parser.parse_args()
    repo = _REPO

    files: list[dict] = []
    for rel in _tracked_files(repo):
        if rel.startswith(_EXCLUDE_PREFIXES):
            continue
        p = repo / rel
        if not p.is_file():
            continue
        files.append({
            "path": rel,
            "size": p.stat().st_size,
            "sha256": _sha256(p),
        })
    files.sort(key=lambda e: e["path"])

    manifest = {
        "name": "aipd-orchestrator",
        "version": args.version,
        "release_date": date.today().isoformat(),
        "release_type": "AI full-chain product development and delivery supervisor",
        "theory_reference": "references/AIPD-OS-v4.0.docx",
        "files": files,
    }
    (repo / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RELEASE_MANIFEST.json 已刷新：{len(files)} 个文件，version={args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())