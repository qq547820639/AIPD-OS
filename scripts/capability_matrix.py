"""AIPD-OS v5.6 能力矩阵审计产物生成器（Registry 驱动）。

与 v5.5 及之前的差异：不再维护一份与代码脱节的静态 CAPABILITIES 长表。
本脚本从统一 Capability Registry（``src/aipd_os/registry.py`` + ``registry_data.py``）
读取能力声明，并在运行时用证据推导分类，产出三份审计交付物：
- ``docs/audit/repository_snapshot.json``：仓库快照（audit_repo 提供）。
- ``docs/audit/capability_matrix.json``：能力矩阵（含运行时 probe 证据）。
- ``docs/audit/capability_matrix.md``：同一矩阵的可读 Markdown。

校验：
- schema 校验：registry.validate（id/name/domain/分类/partially 限制/实现文件存在性）。
- 实现文件存在性：registry.probe_file_has_impl。
- 入口可调用校验：registry.probe_entry_callable。
- 证据时效校验：记录 generated_at 与 HEAD SHA（由 snapshot 提供）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.audit_repo import audit_repo  # noqa: E402
from aipd_os.registry import (  # noqa: E402
    CLASSIFICATIONS, CLASSIFICATION_LABELS, CapabilityRegistry,
    load_default_registry, probe_classification, probe_entry_callable,
    probe_file_has_impl,
)


def _build_snapshot(repo: Path, pin_commit: str | None = None) -> dict:
    """基于 audit_repo 生成 repository_snapshot.json。"""
    report = audit_repo(repo, pin_commit=pin_commit)
    return {
        "generated_at": report["generated_at"],
        "repo_root": report["repo_root"],
        "default_branch": report["default_branch"],
        "latest_commit_sha": report["latest_commit_sha"],
        "latest_commit_time": report["latest_commit_time"],
        "version": report["version"],
        "file_tree": report["file_tree"],
        "tags": report["tags"],
        "releases_dir_exists": report["releases_dir_exists"],
        "ci_status": report["ci_status"],
        "release_manifest_verification": report["release_manifest_verification"],
        "untracked_or_generated": report["untracked_or_generated"],
        "legacy_cad_conflicts": report["legacy_cad_conflicts"],
        "has_sbom": report["has_sbom"],
        "has_release_signing": report["has_release_signing"],
        "dependency_lock": report["dependency_lock"],
        "dependency_lock_files": report["dependency_lock_files"],
    }


def _probe_capability(cap, repo: Path) -> dict:
    """对单能力做运行时证据探测，返回 probe 证据字典。"""
    return {
        "implementation_file_exists": probe_file_has_impl(repo, cap.implementation_file),
        "entry_callable": probe_entry_callable(cap.entry_point),
        "external_dependency_flag": bool(
            getattr(cap, "external_dependency", False)
        ),
    }


def _build_capability_matrix(repo: Path, registry: CapabilityRegistry) -> dict:
    """构建能力矩阵（JSON），分类由 registry.probe_classification 推导。"""
    snapshot = _build_snapshot(repo)
    domains = []
    for domain in registry.domains():
        items = []
        for cap in registry.all():
            if cap.domain != domain:
                continue
            cap.probe = _probe_capability(cap, repo)
            cap.classification = probe_classification(
                cap, repo, external_dependency=cap.probe["external_dependency_flag"]
            )
            items.append(cap.to_dict())
        domains.append({"domain": domain, "capabilities": items})

    counts = {c: 0 for c in CLASSIFICATIONS}
    for cap in registry.all():
        counts[cap.classification] = counts.get(cap.classification, 0) + 1

    return {
        "generated_at": snapshot["generated_at"],
        "repo": snapshot["repo_root"],
        "default_branch": snapshot["default_branch"],
        "latest_commit_sha": snapshot["latest_commit_sha"],
        "version": snapshot["version"],
        "classification_enum": CLASSIFICATIONS,
        "classification_labels": CLASSIFICATION_LABELS,
        "summary": {
            "total_capabilities": len(registry.all()),
            "by_classification": counts,
        },
        "domains": domains,
    }


def _md_cell(value) -> str:
    if value is None or value == "":
        return ""
    return str(value).replace("|", "\\|")


def _render_matrix_md(matrix: dict) -> str:
    lines: list = []
    lines.append("# AIPD-OS 能力矩阵（v5.6 Registry 驱动）")
    lines.append("")
    lines.append(f"- 生成时间：`{matrix['generated_at']}`")
    lines.append(f"- 仓库：`{matrix['repo']}`")
    lines.append(f"- 默认分支：`{matrix['default_branch']}`；HEAD：`{matrix['latest_commit_sha']}`")
    lines.append(f"- 版本：`{matrix['version']}`")
    lines.append(f"- 能力总数：`{matrix['summary']['total_capabilities']}`")
    lines.append("- 分类由 Capability Registry + 运行时证据推导，非静态表。")
    lines.append("")
    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 分类 | 数量 | 说明 |")
    lines.append("| --- | --- | --- |")
    for cls in CLASSIFICATIONS:
        n = matrix["summary"]["by_classification"].get(cls, 0)
        lines.append(f"| `{cls}` | {n} | {CLASSIFICATION_LABELS[cls]} |")
    lines.append("")
    for domain_entry in matrix["domains"]:
        domain = domain_entry["domain"]
        lines.append(f"## {domain}")
        lines.append("")
        lines.append("| 能力 | 分类 | 声明文件 | 实现文件 | 入口 | 运行命令 | 单元测试 | 当前限制 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for cap in domain_entry["capabilities"]:
            lines.append(
                "| " + " | ".join([
                    _md_cell(cap["name"]),
                    f"`{cap['classification']}`",
                    _md_cell(cap["declaration_file"]),
                    _md_cell(cap["implementation_file"]),
                    _md_cell(cap["entry_point"]),
                    "`" + _md_cell(cap["run_command"]) + "`",
                    _md_cell(cap["unit_test"]),
                    _md_cell(cap["current_limitation"]),
                ]) + " |"
            )
        lines.append("")
    return "\n".join(lines)


def generate(repo_root, out_dir, pin_commit: str | None = None) -> dict:
    """生成三份审计交付物，返回生成摘要。"""
    repo = Path(repo_root).resolve()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    registry = load_default_registry()
    errors = registry.validate(repo)
    if errors:
        raise ValueError("Capability Registry 校验失败：\n" + "\n".join(errors))

    snapshot = _build_snapshot(repo, pin_commit=pin_commit)
    matrix = _build_capability_matrix(repo, registry)

    (out / "repository_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "capability_matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "capability_matrix.md").write_text(
        _render_matrix_md(matrix) + "\n", encoding="utf-8")

    return {
        "generated_at": snapshot["generated_at"],
        "repo": str(repo),
        "output_dir": str(out),
        "version": snapshot["version"],
        "latest_commit_sha": snapshot["latest_commit_sha"],
        "total_capabilities": matrix["summary"]["total_capabilities"],
        "by_classification": matrix["summary"]["by_classification"],
        "written": [
            "repository_snapshot.json",
            "capability_matrix.json",
            "capability_matrix.md",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AIPD-OS 能力矩阵审计产物生成（Registry 驱动）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--out", default="docs/audit", help="输出目录（默认 docs/audit）")
    parser.add_argument("--pin-commit", default="",
                        help="把 snapshot/矩阵的 latest_commit_sha 固定到最终 tag SHA")
    args = parser.parse_args()
    summary = generate(args.repo, args.out, pin_commit=args.pin_commit or None)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()