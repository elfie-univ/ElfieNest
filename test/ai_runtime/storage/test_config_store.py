import os

import pytest

from ai_runtime.storage.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)


def test_yaml_store_round_trip_and_owner_only_mode(tmp_path):
    path = tmp_path / "config.yaml"

    write_yaml_mapping(path, {"providers": {"ollama": {"api_mode": "ollama"}}})

    assert read_yaml_mapping(path)["providers"]["ollama"]["api_mode"] == "ollama"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_yaml_store_rejects_non_mapping_root(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ConfigStoreError):
        read_yaml_mapping(path)
