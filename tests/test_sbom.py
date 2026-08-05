"""SBOM 生成与校验测试。"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.security import generate_sbom, verify_sbom

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_generate_sbom_returns_dict_with_components():
    bom = generate_sbom(str(REPO_ROOT))
    assert isinstance(bom, dict)
    assert bom["bomFormat"] == "CycloneDX"
    assert isinstance(bom["components"], list)
    assert "aipd" in bom
    assert isinstance(bom["aipd"]["selfModules"], list)
    assert bom["aipd"]["selfModules"], "should list project modules"
    assert any(m == "aipd_os" or m.startswith("aipd_os.") for m in bom["aipd"]["selfModules"])


def test_verify_sbom_passes():
    bom = generate_sbom(str(REPO_ROOT))
    assert verify_sbom(bom) is True
    assert verify_sbom({}) is False
    bom["components"] = "nope"
    assert verify_sbom(bom) is False


def test_generate_sbom_deterministic(tmp_path):
    bom1 = generate_sbom(str(REPO_ROOT))
    bom2 = generate_sbom(str(REPO_ROOT))
    assert bom1 == bom2


def test_generate_sbom_writes_file(tmp_path):
    out = tmp_path / "sbom.json"
    bom = generate_sbom(str(REPO_ROOT), str(out))
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == bom
    assert verify_sbom(loaded) is True


def test_verify_sbom_rejects_bad_input():
    assert verify_sbom(None) is False
    assert verify_sbom([]) is False
    assert verify_sbom({"bomFormat": "NotCycloneDX", "metadata": {}, "components": []}) is False
