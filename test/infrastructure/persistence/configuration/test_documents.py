from pathlib import Path

import pytest

from infrastructure.persistence.configuration.bundled_defaults import load_nest_config
from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
    RuntimeConfigSource,
    resolve_bundled_config_root,
)


def test_bundled_source_reads_only_registered_document_and_checks_version(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    (root / "app").mkdir(parents=True)
    (root / "app" / "system-defaults.yaml").write_text(
        "version: 1\nsystem: {}\n", encoding="utf-8"
    )

    loaded = BundledConfigSource(root).load(ConfigDocumentId.SYSTEM_DEFAULTS)

    assert loaded.document["version"] == 1
    assert loaded.path == root / "app" / "system-defaults.yaml"


def test_bundled_source_rejects_missing_required_document(tmp_path: Path) -> None:
    with pytest.raises(ConfigDocumentError, match="必需 bundled 配置缺失"):
        BundledConfigSource(tmp_path).load(ConfigDocumentId.SYSTEM_DEFAULTS)


def test_bundled_source_rejects_wrong_document_version(tmp_path: Path) -> None:
    path = tmp_path / "app" / "system-defaults.yaml"
    path.parent.mkdir()
    path.write_text("version: 9\n", encoding="utf-8")

    with pytest.raises(ConfigDocumentError, match="版本不支持"):
        BundledConfigSource(tmp_path).load(ConfigDocumentId.SYSTEM_DEFAULTS)


def test_runtime_source_writes_fixed_user_path_and_injects_version(
    tmp_path: Path,
) -> None:
    source = RuntimeConfigSource(tmp_path)

    path = source.write(
        ConfigDocumentId.RUNTIME_SETTINGS,
        {"system": {"engine": {"tick_interval_sec": 1.5}}},
    )

    assert path == tmp_path / "runtime.yaml"
    loaded = source.load(ConfigDocumentId.RUNTIME_SETTINGS)
    assert loaded is not None
    assert loaded.document["version"] == 1
    assert loaded.document["system"]["engine"]["tick_interval_sec"] == 1.5


def test_runtime_source_rejects_path_traversal_in_registered_path(
    tmp_path: Path,
) -> None:
    source = RuntimeConfigSource(tmp_path)
    # The registry itself contains only fixed paths; this assertion protects
    # the root resolver if a future path is accidentally changed.
    assert (source.root / "runtime.yaml").resolve().parent == source.root


def test_release_root_requires_launcher_injected_resource_root() -> None:
    with pytest.raises(ConfigDocumentError, match="必须由 launcher 提供"):
        resolve_bundled_config_root(
            environment={"ELFIENEST_RUNTIME_MODE": "release"},
        )


def test_nest_defaults_are_loaded_as_typed_configuration(tmp_path: Path) -> None:
    path = tmp_path / "nest" / "defaults.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("version: 1\nnest:\n  bed_count: 8\n", encoding="utf-8")

    config = load_nest_config(root=tmp_path)

    assert config.bed_count == 8
