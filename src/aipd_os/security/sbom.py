"""确定性 SBOM 生成（CycloneDX 风格）。

基于 ``pyproject.toml`` 的依赖声明 + 项目自身模块清单，生成确定性的软件物料
清单 JSON。**无网络访问**，输出可复现（所有列表排序）。

TASKS 说明：
- 列出项目自身模块（``src/<pkg>/**`` 下的 Python 模块）；
- 读取 ``pyproject.toml`` 的 ``dependencies`` 与各 ``[project.optional-dependencies]``
  组作为依赖组件；
- ``verify_sbom`` 校验结构完整性。

本模块不依赖任何第三方库（Python 3.9 无标准库 ``tomllib``，故内置轻量解析）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CYCLONEDX_VERSION = "1.5"
SPEC_URL = "https://cyclonedx.org/schema/bom-1.5.schema.json"

# 解析 TOML 顶层 section 范围
_SECTION_RE = re.compile(r"^\[(.+?)\]\s*$", re.MULTILINE)


def _parse_arrays(text: str, section_body: str) -> dict[str, list[str]]:
    """解析某个 section 内的 ``key = ["a", "b"]`` 简单字符串数组。"""
    result: dict[str, list[str]] = {}
    for m in re.finditer(r"^(\w[\w\-]*)\s*=\s*\[([^\]]*)\]", section_body, re.MULTILINE):
        key = m.group(1)
        items = re.findall(r'"([^"]*)"', m.group(2))
        result[key] = [i for i in items if i.strip()]
    return result


def _split_sections(text: str) -> dict[str, str]:
    """按 [[section]] / [section] 切分 TOML，返回 section 名 -> 正文。"""
    matches = list(_SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[m.group(1).strip()] = text[start:end]
    return sections


def _read_project_meta(sections: dict[str, str]) -> dict[str, Any]:
    """从 ``[project]`` 提取 name / version / description。"""
    meta: dict[str, Any] = {"name": "aipd-os", "version": "0.0.0", "description": ""}
    body = sections.get("project", "")
    for key in ("name", "version", "description"):
        m = re.search(rf"^{key}\s*=\s*\"([^\"]*)\"", body, re.MULTILINE)
        if m:
            meta[key] = m.group(1)
    return meta


def _project_modules(project_root: Path, pkg_name: str) -> list[str]:
    """列出项目自身模块（src/pkg 下的入口模块与子包）。"""
    modules: list[str] = []
    src = project_root / "src"
    pkg = src / pkg_name
    if pkg.is_dir():
        for py in sorted(pkg.rglob("*.py")):
            if py.name == "__init__.py":
                rel = py.relative_to(pkg).parent
                modules.append(pkg_name if str(rel) == "." else f"{pkg_name}.{rel.as_posix().replace('/', '.')}")  # noqa: E501
            else:
                rel = py.relative_to(pkg)
                modules.append(f"{pkg_name}.{rel.with_suffix('').as_posix().replace('/', '.')}")
    # 顶层脚本目录脚本（scripts）作为模块清单补充
    return sorted(set(modules))


def _dependency_components(dependencies: list[str], optional: dict[str, list[str]]) -> list[dict[str, Any]]:  # noqa: E501
    """把依赖声明转为 CycloneDX 组件。"""
    comps: dict[str, dict[str, Any]] = {}
    for item in dependencies:
        name = _dep_name(item)
        comps.setdefault(name, {"type": "library", "name": name, "purl": _purl(name, item)})
    for group, items in optional.items():
        for item in items:
            name = _dep_name(item)
            base = comps.setdefault(name, {"type": "library", "name": name, "purl": _purl(name, item)})  # noqa: E501
            group_tags = base.setdefault("optional", [])
            if group not in group_tags:
                group_tags.append(group)
    return sorted(comps.values(), key=lambda c: c["name"])


def _dep_name(item: str) -> str:
    """从 ``name>=x`` / ``name[extra]>=x`` 提取包名。"""
    name = item.split("[")[0]
    name = name.split(">")[0].split("<")[0].split("=")[0].split("!")[0].strip()
    return name


def _purl(name: str, item: str) -> str:
    """生成简化的 package URL。"""
    return f"pkg:pypi/{name}"

def _coerce_version(item: str) -> str:
    m = re.search(r"[>=<~!]+([0-9][\w.\-]*)", item)
    return m.group(1) if m else ""


def generate_sbom(project_root: str, out_path: str | None = None) -> dict[str, Any]:
    """生成 CycloneDX 风格 SBOM 并（可选）写入文件。

    :param project_root: 项目根目录（含 pyproject.toml）
    :param out_path: 可选输出 JSON 路径
    :returns: SBOM 字典（确定性排序）
    """
    root = Path(project_root)
    pyproject = root / "pyproject.toml"
    sections = _split_sections(pyproject.read_text(encoding="utf-8"))
    meta = _read_project_meta(sections)

    arrays = _parse_arrays("", sections.get("project", ""))
    dependencies = arrays.get("dependencies", [])
    optional: dict[str, list[str]] = {}
    for k in sorted(sections):
        if k.startswith("project.optional-dependencies"):
            parsed = _parse_arrays("", sections[k])
            for group, items in parsed.items():
                optional[group] = [i for i in items if i.strip()]

    modules = _project_modules(root, meta["name"].replace("-", "_"))
    dep_components = _dependency_components(dependencies, optional)

    bom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_VERSION,
        "serialNumber": f"urn:uuid:aipd-os-{meta['version']}-sbom",
        "version": 1,
        "metadata": {
            "timestamp": "1970-01-01T00:00:00Z",  # 确定性：无网络、可复现
            "component": {
                "type": "application",
                "bom-ref": meta["name"],
                "name": meta["name"],
                "version": meta["version"],
                "description": meta["description"],
            },
        },
        "components": dep_components,
        "services": [],
        "aipd": {
            "selfModules": modules,
            "dependencies": sorted(dependencies),
            "optionalDependencies": {k: sorted(v) for k, v in sorted(optional.items())},
        },
    }

    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(bom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bom


def verify_sbom(sbom: dict[str, Any]) -> bool:
    """校验 SBOM 结构是否完整有效。"""
    if not isinstance(sbom, dict):
        return False
    if sbom.get("bomFormat") != "CycloneDX":
        return False
    if not isinstance(sbom.get("specVersion"), str):
        return False
    meta = sbom.get("metadata")
    if not isinstance(meta, dict) or not isinstance(meta.get("component"), dict):
        return False
    comp = meta["component"]
    if not comp.get("name") or not comp.get("version"):
        return False
    if not isinstance(sbom.get("components"), list):
        return False
    return all(not (not isinstance(c, dict) or not c.get("name")) for c in sbom["components"])


__all__ = ["generate_sbom", "verify_sbom", "CYCLONEDX_VERSION"]
