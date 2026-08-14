"""schema_check 真实校验的回归测试（schema 元校验 + 模板数据校验）。"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.scripts.schema_check import validate_schemas


def _mk(tmp_path: Path, schema_name: str, schema: dict, data: dict) -> tuple[Path, Path]:
    sd = tmp_path / "assets" / "schemas"
    sd.mkdir(parents=True)
    td = tmp_path / "assets" / "templates"
    td.mkdir(parents=True)
    sp = sd / f"{schema_name}.schema.json"
    sp.write_text(json.dumps(schema), encoding="utf-8")
    dp = td / f"{schema_name}.json"
    dp.write_text(json.dumps(data), encoding="utf-8")
    return sd, dp


def test_schema_check_valid_data_passes(tmp_path):
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    sd, _ = _mk(tmp_path, "demo", schema, {"name": "ok"})
    assert validate_schemas(sd, tmp_path) == 0


def test_schema_check_invalid_data_fails(tmp_path):
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    sd, _ = _mk(tmp_path, "demo", schema, {"name": 123})
    assert validate_schemas(sd, tmp_path) == 1


def test_schema_check_invalid_schema_fails(tmp_path):
    # 非合法 JSON Schema：type 必须是合法值
    bad = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "not-a-type"}
    sd, _ = _mk(tmp_path, "demo", bad, {})
    assert validate_schemas(sd, tmp_path) >= 1
