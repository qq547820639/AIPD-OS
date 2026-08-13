"""AIPD-OS v5.1 版本真实性审计脚本（Task 1）。

读取仓库的真实运行时状态（git 提交、pyproject 版本、Release Manifest 哈希、
CI job、遗留 CAD 冲突等），生成机器可读的 JSON 与人类可读的 Markdown 报告。

该脚本可被 import（``audit_repo(repo_root) -> dict``）也可作为 CLI 运行：
    python scripts/audit_repo.py --repo . --json-out docs/audit/audit.json
    python scripts/audit_repo.py --repo . --json-out docs/audit/audit.json \
        --markdown-out docs/audit/audit.md

仅依赖标准库（pathlib / re / json / hashlib / subprocess），不访问网络。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path

# 需要扫描遗留 CAD 冲突的文件后缀
_CAD_SCAN_SUFFIXES = {".py", ".json", ".md", ".yaml", ".yml"}
# 默认排除的目录（相对仓库根）
_CAD_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    ".trae",
    ".ruff_cache",
    "tests",
}
# 遗留 CAD 冲突标记：CAD-L<数字> 级联追溯记号
_CAD_LEVEL_RE = re.compile(r"CAD-L\d+")
# 过度声称模式：声称 faceted 已达 C2+ 等（占位，可扩展）
_OVERCLAIM_RE = re.compile(r"faceted\s+reach(?:ing|ed)?\s+C[2-9]", re.IGNORECASE)
# 版本解析：pyproject.toml 中 `version = "..."`（顶层 [project] 下）
_VERSION_RE = re.compile(r"^\s*version\s*=\s*[\"']([^\"']+)[\"']\s*$")
# 依赖锁文件候选
_LOCKFILES = {
    "requirements.txt",
    "requirements-quality.txt",
    "requirements-dev.txt",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
}


def _run_git(repo_root: Path, args: list) -> str:
    """在仓库根目录执行 git 命令，返回去尾空白的 stdout；失败返回空串。"""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _run_git_raw(repo_root: Path, args: list) -> str:
    """执行 git 命令并返回原始 stdout（不 strip，用于 porcelain 等对空白敏感的输出）。"""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _sha256(path: Path) -> str:
    """计算文件 SHA-256 值。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_version(repo_root: Path) -> str:
    """从 pyproject.toml 解析版本号。"""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return ""
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("version"):
            m = _VERSION_RE.match(line)
            if m:
                return m.group(1)
    return ""


def _parse_ci_jobs(repo_root: Path) -> list:
    """解析 .github/workflows/*.yml 中的 job 名称。"""
    jobs: list = []
    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.exists():
        return jobs
    job_key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    for wf in sorted(workflows_dir.glob("*.yml")):
        try:
            lines = wf.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        in_jobs = False
        for line in lines:
            if re.match(r"^\s*jobs:\s*$", line):
                in_jobs = True
                continue
            if in_jobs:
                if line and not line.startswith(" ") and line.strip():
                    in_jobs = False
                    continue
                m = job_key_re.match(line)
                if m:
                    jobs.append(m.group(1))
    seen: set[str] = set()
    unique: list[str] = []
    for j in jobs:
        if j not in seen:
            seen.add(j)
            unique.append(j)
    return unique


def _verify_release_manifest(repo_root: Path) -> dict:
    """读取并校验 RELEASE_MANIFEST.json 的文件哈希。"""
    manifest_path = repo_root / "RELEASE_MANIFEST.json"
    if not manifest_path.exists():
        return {"present": False}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": True, "version": None, "parsed": False}

    version = manifest.get("version")
    files = manifest.get("files", [])
    matches = 0
    mismatches: list = []
    for entry in files:
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not rel or not expected:
            continue
        target = repo_root / rel
        if not target.is_file():
            mismatches.append(
                {"path": rel, "reason": "missing", "expected": expected}
            )
            continue
        actual = _sha256(target)
        if actual == expected:
            matches += 1
        else:
            mismatches.append(
                {
                    "path": rel,
                    "reason": "hash_mismatch",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return {
        "present": True,
        "version": version,
        "parsed": True,
        "total_files": len(files),
        "hash_matches": matches,
        "hash_mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
    }


def _verify_source_manifest(repo_root: Path) -> dict:
    """读取并校验 SOURCE_MANIFEST.json 的文件哈希（P0-1 发布证据体系可复现）。"""
    manifest_path = repo_root / "SOURCE_MANIFEST.json"
    if not manifest_path.exists():
        return {"present": False}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": True, "version": None, "parsed": False}

    version = manifest.get("version")
    source_commit = manifest.get("source_commit")
    files = manifest.get("files", [])
    matches = 0
    mismatches: list = []
    for entry in files:
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not rel or not expected:
            continue
        target = repo_root / rel
        if not target.is_file():
            mismatches.append(
                {"path": rel, "reason": "missing", "expected": expected}
            )
            continue
        actual = _sha256(target)
        if actual == expected:
            matches += 1
        else:
            mismatches.append(
                {
                    "path": rel,
                    "reason": "hash_mismatch",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return {
        "present": True,
        "version": version,
        "source_commit": source_commit,
        "parsed": True,
        "total_files": len(files),
        "hash_matches": matches,
        "hash_mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
    }


def _collect_untracked_or_generated(repo_root: Path) -> list:
    """收集未跟踪/被修改文件，以及生成的目录（__pycache__、*.egg-info）。"""
    found: list = []
    porcelain = _run_git_raw(repo_root, ["status", "--porcelain"])
    for line in porcelain.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if any(c in status for c in "?MADRC"):
            found.append(status + " " + path)
    for pattern in ("**/__pycache__", "**/*.egg-info"):
        for p in repo_root.glob(pattern):
            if ".git" in p.parts:
                continue
            found.append(f"generated {p.relative_to(repo_root)}")
    return sorted(set(found))


def _scan_legacy_cad_conflicts(repo_root: Path) -> list:
    """扫描遗留 CAD 冲突（CAD-L\\d 与过度声称模式）。"""
    hits: list = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        parts = rel.parts
        if any(part in _CAD_EXCLUDE_DIRS for part in parts):
            continue
        if path.suffix.lower() not in _CAD_SCAN_SUFFIXES:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, start=1):
            m = _CAD_LEVEL_RE.search(line)
            if m:
                hits.append(
                    {"path": str(rel), "line": idx, "type": "cad_level", "match": m.group(0)}
                )
                continue
            om = _OVERCLAIM_RE.search(line)
            if om:
                hits.append(
                    {"path": str(rel), "line": idx, "type": "overclaim", "match": om.group(0)}
                )
    return hits


def audit_repo(repo_root, pin_commit: str | None = None) -> dict:
    """审计仓库真实状态，返回结果字典。输入可为 str 或 pathlib.Path。

    ``pin_commit`` 用于把 latest_commit_sha 固定到最终 tag SHA（如 ``--pin-commit``），
    使报告指向“被测试的发布提交”而非领先于 tag 的发布证据元数据提交（P0-1）。
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"仓库根目录不存在: {root}")

    default_branch = _run_git(root, ["symbolic-ref", "--short", "HEAD"])
    if not default_branch:
        default_branch = _run_git(root, ["branch", "--show-current"])
    if pin_commit:
        latest_commit_sha = _run_git(root, ["rev-parse", f"{pin_commit}^{{commit}}"]) or pin_commit
        latest_commit_time = _run_git(root, ["show", "-s", "--format=%ci", pin_commit])
    else:
        latest_commit_sha = _run_git(root, ["rev-parse", "HEAD"])
        latest_commit_time = _run_git(root, ["show", "-s", "--format=%ci", "HEAD"])

    tags = _run_git(root, ["tag", "-l"])
    tags_list = [t for t in tags.splitlines() if t] if tags else []

    top_entries: list = []
    per_dir_count: dict = {}
    try:
        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            name = entry.name
            if entry.is_dir():
                top_entries.append(f"{name}/")
                count = sum(1 for p in entry.iterdir() if p.is_file())
                per_dir_count[name] = count
            else:
                top_entries.append(name)
    except OSError:
        # noqa: EMPTY_EXCEPT - 目录统计尽力而为：权限/IO 失败不阻断审计
        pass

    ci_jobs = _parse_ci_jobs(root)
    manifest_verification = _verify_release_manifest(root)
    source_manifest_verification = _verify_source_manifest(root)
    untracked_or_generated = _collect_untracked_or_generated(root)
    legacy_cad_conflicts = _scan_legacy_cad_conflicts(root)

    sbom = root / "SBOM.md"
    signing = root / "RELEASE_SIGNING.md"
    sign_script = root / "scripts" / "sign_release.py"
    has_sbom = sbom.is_file()
    has_release_signing = signing.is_file() and sign_script.is_file()

    dep_lock_names = [f for f in sorted(_LOCKFILES) if (root / f).is_file()]
    dependency_lock = bool(dep_lock_names)

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        # v5.8.1 Commit 15（§38-39 Audit Freshness）：source_commit + package_version
        "source_commit": latest_commit_sha,
        "package_version": _parse_version(root),
        # v5.8.2 Commit 9：generator_version + command（机器报告 provenance 收口）
        "generator_version": "audit_repo_v1",
        "command": "python scripts/audit_repo.py",
        "repo_root": str(root),
        "default_branch": default_branch,
        "latest_commit_sha": latest_commit_sha,
        "latest_commit_time": latest_commit_time,
        "version": _parse_version(root),
        "file_tree": {
            "top_entries": top_entries,
            "per_dir_file_count": dict(sorted(per_dir_count.items())),
        },
        "tags": tags_list,
        "releases_dir_exists": (root / "releases").is_dir(),
        "ci_status": {
            "workflow_present": (root / ".github" / "workflows").exists(),
            "jobs": ci_jobs,
        },
        "release_manifest_verification": manifest_verification,
        "source_manifest_verification": source_manifest_verification,
        "untracked_or_generated": untracked_or_generated,
        "legacy_cad_conflicts": legacy_cad_conflicts,
        "has_sbom": has_sbom,
        "has_release_signing": has_release_signing,
        "dependency_lock": dependency_lock,
        "dependency_lock_files": dep_lock_names,
    }


def _render_markdown(report: dict) -> str:
    """将审计字典渲染为中文 Markdown 报告。"""
    lines: list = []
    lines.append("# AIPD-OS 版本真实性审计报告（v5.1）")
    lines.append("")
    lines.append(f"- 生成时间：`{report['generated_at']}`")
    lines.append(f"- 仓库根目录：`{report['repo_root']}`")
    lines.append("")

    lines.append("## 1. 仓库基本信息")
    lines.append("")
    lines.append(f"- 默认分支：`{report['default_branch'] or '（无法获取）'}`")
    lines.append(f"- 最新提交 SHA：`{report['latest_commit_sha'] or '（无法获取）'}`")
    lines.append(f"- 最新提交时间：`{report['latest_commit_time'] or '（无法获取）'}`")
    lines.append(f"- pyproject 版本：`{report['version'] or '（未解析到）'}`")
    lines.append(f"- Git 标签：{', '.join(f'`{t}`' for t in report['tags']) if report['tags'] else '（无）'}")
    lines.append(f"- `releases/` 目录存在：{'是' if report['releases_dir_exists'] else '否'}")
    lines.append("")

    lines.append("## 2. 文件树概览")
    lines.append("")
    ft = report["file_tree"]
    lines.append(f"- 顶层条目数：`{len(ft['top_entries'])}`")
    lines.append("- 顶层目录文件数（一层）：")
    lines.append("")
    lines.append("| 目录 | 文件数 |")
    lines.append("| --- | --- |")
    for name, count in ft["per_dir_file_count"].items():
        lines.append(f"| `{name}/` | {count} |")
    lines.append("")

    lines.append("## 3. CI 状态")
    lines.append("")
    ci = report["ci_status"]
    if ci["jobs"]:
        lines.append(f"- 检测到 Workflow：{len(ci['jobs'])} 个 job")
        lines.append(f"- Job 列表：{', '.join(f'`{j}`' for j in ci['jobs'])}")
    else:
        lines.append("- 未检测到 .github/workflows/*.yml 中的 job")
    lines.append("")

    lines.append("## 4. Release Manifest 校验")
    lines.append("")
    mv = report["release_manifest_verification"]
    if not mv.get("present"):
        lines.append("- 未发现 `RELEASE_MANIFEST.json`。")
    elif not mv.get("parsed"):
        lines.append("- `RELEASE_MANIFEST.json` 存在但解析失败。")
    else:
        lines.append(f"- Manifest 版本：`{mv.get('version')}`")
        lines.append(f"- 文件条目总数：`{mv.get('total_files')}`")
        lines.append(f"- 哈希匹配：`{mv.get('hash_matches')}` / `{mv.get('total_files')}`")
        lines.append(f"- 哈希不匹配：`{mv.get('hash_mismatch_count')}`")
        if mv.get("mismatches"):
            lines.append("- 不匹配明细（前 20 条）：")
            for mm in mv["mismatches"]:
                lines.append(f"  - `{mm['path']}`：{mm['reason']}（期望 {mm.get('expected', '')[:12]}…）")
    lines.append("")

    lines.append("## 5. 未跟踪 / 生成文件")
    lines.append("")
    ug = report["untracked_or_generated"]
    if ug:
        lines.append(f"- 共 `{len(ug)}` 项：")
        for item in ug:
            lines.append(f"  - `{item}`")
    else:
        lines.append("- 工作区干净，无不必要生成文件。")
    lines.append("")

    lines.append("## 6. 遗留 CAD 冲突")
    lines.append("")
    cad = report["legacy_cad_conflicts"]
    if cad:
        lines.append(f"- 发现 `{len(cad)}` 处潜在冲突：")
        for hit in cad:
            lines.append(f"  - `{hit['path']}:{hit['line']}` [{hit['type']}] `{hit['match']}`")
    else:
        lines.append("- 未发现 CAD-L 级联记号或过度声称模式。")
    lines.append("")

    lines.append("## 7. 交付产物完整性")
    lines.append("")
    lines.append(f"- SBOM.md 存在：{'是' if report['has_sbom'] else '否'}")
    lines.append(
        f"- 发布签名（RELEASE_SIGNING.md + scripts/sign_release.py）完备："
        f"{'是' if report['has_release_signing'] else '否'}"
    )
    lines.append(
        f"- 依赖锁文件存在：{'是' if report['dependency_lock'] else '否'}"
        f"{'（' + ', '.join(f'`{f}`' for f in report['dependency_lock_files']) + '）' if report['dependency_lock_files'] else ''}"
    )
    lines.append("")
    return "\n".join(lines)


def _write_report(report: dict, json_out: str, markdown_out: str) -> None:
    """写出 JSON 与 Markdown 报告文件。"""
    if json_out:
        out = Path(json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[audit_repo] JSON 已写入: {out.resolve()}")
    if markdown_out:
        out = Path(markdown_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_render_markdown(report) + "\n", encoding="utf-8")
        print(f"[audit_repo] Markdown 已写入: {out.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIPD-OS 版本真实性审计")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--json-out", default="", help="JSON 报告输出路径")
    parser.add_argument("--markdown-out", default="", help="Markdown 报告输出路径")
    parser.add_argument("--pin-commit", default="",
                        help="把报告 latest_commit_sha 固定到最终 tag SHA（默认取当前 HEAD）")
    args = parser.parse_args()

    report = audit_repo(args.repo, pin_commit=args.pin_commit or None)
    _write_report(report, args.json_out or "", args.markdown_out or "")
    if not args.json_out and not args.markdown_out:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
