"""Provider SDK 兼容性测试套件。"""
from __future__ import annotations

import pytest
from jsonschema import Draft7Validator

from aipd_os.providers import (
    Provider,
    ProviderRegistry,
    available,
    capability_schema,
    unavailable,
    validate_capabilities,
)
from aipd_os.providers.example_plugin import ExamplePlugin


class _FakeProvider(Provider):
    name = "fake"

    def capabilities(self):
        return [{
            "id": "fake.cap",
            "name": "Fake Capability",
            "domain": "generic",
            "category": "execution",
            "evidence": {"impl_file": "fake.py"},
        }]

    def probe(self):
        return available()

    def run(self, context):
        return {"ok": True, "ran": True}


class _ProbeFailingProvider(_FakeProvider):
    name = "failing"

    def probe(self):
        return unavailable("no credentials")


def test_capability_schema_is_valid_json_schema():
    Draft7Validator.check_schema(capability_schema)


def test_validate_capabilities_accepts_valid():
    errors = validate_capabilities([{
        "id": "a.b", "name": "A", "domain": "model",
        "category": "generation", "evidence": {"impl_file": "x.py"},
    }])
    assert errors == []


def test_validate_capabilities_rejects_missing_fields():
    errors = validate_capabilities([{"id": "a.b"}])
    assert errors, "缺少 required 字段应当报错"


def test_validate_capabilities_rejects_bad_ceiling():
    errors = validate_capabilities([{
        "id": "a.b", "name": "A", "domain": "model",
        "category": "generation", "evidence": {"impl_file": "x.py"},
        "maturity_ceiling": "C99",
    }])
    assert errors, "非法成熟度上限应当报错"


def test_probe_result_helpers():
    av = available()
    assert av.ok is True and av.available is True and bool(av)
    assert av.to_dict() == {"ok": True, "available": True, "reason": ""}

    un = unavailable("missing key")
    assert un.ok is False and un.available is False and not un
    assert un.reason == "missing key"
    assert un.to_dict()["reason"] == "missing key"


def test_registry_register_discover_query():
    reg = ProviderRegistry()
    reg.register(ExamplePlugin())
    reg.register(_FakeProvider())

    assert "example.echo" in reg
    assert len(reg) == 2
    assert sorted(reg.names()) == ["example.echo", "fake"]
    assert "generic.echo" in reg.capability_ids()
    assert "fake.cap" in reg.capability_ids()

    p = reg.get_by_capability("generic.echo")
    assert p is not None and p.name == "example.echo"
    assert reg.get("fake") is not None


def test_registry_rejects_duplicate_name():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    with pytest.raises(ValueError):
        reg.register(_FakeProvider())


def test_registry_rejects_invalid_capabilities():
    class Bad(_FakeProvider):
        name = "bad"
        def capabilities(self):
            return [{"id": "x"}]

    reg = ProviderRegistry()
    with pytest.raises(ValueError):
        reg.register(Bad())


def test_registry_rejects_shared_capability_id():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    class Dup(_FakeProvider):
        name = "dup"
        def capabilities(self):
            return [{"id": "fake.cap", "name": "dup", "domain": "generic",
                     "category": "execution",
                     "evidence": {"impl_file": "dup.py"}}]
    with pytest.raises(ValueError):
        reg.register(Dup())


def test_discover_reports_probe_status():
    reg = ProviderRegistry()
    reg.register(_ProbeFailingProvider())
    info = reg.discover()
    assert info[0]["available"] is False
    assert info[0]["probe_reason"] == "no credentials"


def test_example_plugin_run_and_configure():
    p = ExamplePlugin()
    assert p.run({"message": "hi"})["echo"] == "hi"
    p.configure({"prefix": "A:"})
    assert p.run({"message": "hi"})["echo"] == "A:hi"


def test_provider_validate_capabilities_method():
    p = ExamplePlugin()
    assert p.validate_capabilities() == []