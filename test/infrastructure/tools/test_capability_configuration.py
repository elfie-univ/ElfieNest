from __future__ import annotations

from pathlib import Path

import yaml

from app.features.configuration.capabilities import (
    StoredLocalFileCapability,
    StoredWebSearchCapability,
)
from infrastructure.tools import RuntimeCapabilitiesAdapter


def test_adapter_reads_defaults_without_writing(tmp_path: Path):
    path = tmp_path / "runtime.yaml"
    adapter = RuntimeCapabilitiesAdapter(path)

    result = adapter.load_capabilities()

    assert result.web_search.provider == "duckduckgo"
    assert result.local_file.enabled is False
    assert not path.exists()


def test_adapter_updates_only_explicit_web_search_fields(tmp_path: Path):
    path = tmp_path / "runtime.yaml"
    path.write_text(
        "system:\n  marker: keep\nruntime_policy:\n  other: keep\n",
        encoding="utf-8",
    )
    adapter = RuntimeCapabilitiesAdapter(path)
    current = adapter.load_capabilities().web_search
    updated = StoredWebSearchCapability(
        enabled=True,
        provider="tavily",
        api_base="https://search.example.test",
        credential_ref=current.credential_ref,
        max_results=5,
        max_result_bytes=current.max_result_bytes,
        timeout_seconds=current.timeout_seconds,
        max_tool_calls=current.max_tool_calls,
        max_total_result_bytes=current.max_total_result_bytes,
    )

    adapter.save_web_search(
        updated,
        frozenset({"provider", "api_base", "max_results"}),
    )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    saved = raw["runtime_policy"]["tools"]["web_search"]
    assert saved == {
        "api_key_env": "ELFIE_WEB_SEARCH_API_KEY",
        "provider": "tavily",
        "api_base": "https://search.example.test",
        "max_results": 5,
    }
    assert raw["runtime_policy"]["other"] == "keep"
    assert raw["system"]["marker"] == "keep"


def test_adapter_updates_only_editable_local_file_fields(tmp_path: Path):
    path = tmp_path / "runtime.yaml"
    adapter = RuntimeCapabilitiesAdapter(path)
    current = adapter.load_capabilities().local_file
    updated = StoredLocalFileCapability(
        enabled=True,
        root=current.root,
        root_policy=current.root_policy,
        max_read_bytes=4096,
        max_items=current.max_items,
        max_result_bytes=current.max_result_bytes,
        max_tool_calls=current.max_tool_calls,
        max_total_result_bytes=current.max_total_result_bytes,
    )

    adapter.save_local_file(
        updated,
        frozenset({"enabled", "max_read_bytes"}),
    )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["runtime_policy"]["tools"]["local_file"] == {
        "enabled": True,
        "max_read_bytes": 4096,
    }
