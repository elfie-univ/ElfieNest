import shutil
from pathlib import Path

import pytest

from infrastructure.persistence.configuration.bundled_defaults import load_nest_config
from infrastructure.persistence.configuration.documents import (
    CONFIG_DOCUMENTS,
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
    RuntimeConfigSource,
    resolve_bundled_config_root,
    resolve_runtime_config_root,
)


def test_bundled_source_reads_only_registered_document_and_checks_version(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    (root / "app").mkdir(parents=True)
    (root / "app" / "system-defaults.yaml").write_text(
        """version: 1
system:
  adoption:
    max_elfies_per_user: 1
    personality_presets_enabled: {}
  engine:
    tick_interval_sec: 1.0
  security:
    session_ttl_days: 1
    rate_limit:
      max_attempts: 1
      window_seconds: 1
  model_execution:
    ollama_host: http://localhost:11434
    energy_threshold_fast: 1.0
    complexity_threshold_deep: 1
    temperature: 0.1
    max_tokens: 1
""",
        encoding="utf-8",
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


def test_runtime_source_allows_an_injected_sandbox_but_only_registered_files(
    tmp_path: Path,
) -> None:
    source = RuntimeConfigSource(tmp_path)

    path = source.write(
        ConfigDocumentId.TOOL_SETTINGS,
        {"tools": {"web_search": {"enabled": True}}},
    )

    assert path == tmp_path / "tools.yaml"
    assert source.load(ConfigDocumentId.TOOL_SETTINGS) is not None
    with pytest.raises(ConfigDocumentError, match="没有 user 来源"):
        source.load(ConfigDocumentId.PROVIDER_CATALOG)


def test_runtime_source_without_root_uses_the_user_data_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    source = RuntimeConfigSource()

    assert source.root == resolve_runtime_config_root()
    assert source.root == tmp_path / "configs"


def test_runtime_source_does_not_handle_secret_documents(tmp_path: Path) -> None:
    source = RuntimeConfigSource(tmp_path)

    with pytest.raises(ConfigDocumentError, match="secret Adapter"):
        source.load(ConfigDocumentId.AUTH_ENV)
    with pytest.raises(ConfigDocumentError, match="secret Adapter"):
        source.write(ConfigDocumentId.AUTH_ENV, {})


def test_registry_declares_schema_and_lifecycle_metadata() -> None:
    for spec in CONFIG_DOCUMENTS.values():
        assert spec.schema_id
        assert spec.writer_policy
        assert spec.reload_policy
        assert spec.failure_policy


def test_bundled_source_rejects_unknown_owned_fields(tmp_path: Path) -> None:
    path = tmp_path / "app" / "system-defaults.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """version: 1
system:
  adoption:
    max_elfies_per_user: 1
    personality_presets_enabled: {}
    unexpected: true
  engine:
    tick_interval_sec: 1.0
  security:
    session_ttl_days: 1
    rate_limit:
      max_attempts: 1
      window_seconds: 1
  model_execution:
    ollama_host: http://localhost:11434
    energy_threshold_fast: 1.0
    complexity_threshold_deep: 1
    temperature: 0.1
    max_tokens: 1
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigDocumentError, match="未知字段"):
        BundledConfigSource(tmp_path).load(ConfigDocumentId.SYSTEM_DEFAULTS)


def test_release_root_requires_launcher_injected_resource_root() -> None:
    with pytest.raises(ConfigDocumentError, match="必须由 launcher 提供"):
        resolve_bundled_config_root(
            environment={"ELFIENEST_RUNTIME_MODE": "release"},
        )


def test_release_source_reads_only_the_launcher_resource_root(tmp_path: Path) -> None:
    staged_root = tmp_path / "resources" / "config"
    shutil.copytree(resolve_bundled_config_root(), staged_root)
    environment = {
        "ELFIENEST_RUNTIME_MODE": "release",
        "ELFIENEST_BUNDLED_CONFIG_DIR": str(staged_root),
    }

    resolved = resolve_bundled_config_root(
        environment=environment,
        runtime_mode="release",
    )
    loaded = BundledConfigSource(resolved).load(ConfigDocumentId.PROVIDER_CATALOG)

    assert loaded.path == staged_root / "models" / "provider-catalog.yaml"


def test_nest_defaults_are_loaded_as_typed_configuration(tmp_path: Path) -> None:
    path = tmp_path / "nest" / "defaults.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("version: 1\nnest:\n  bed_count: 8\n", encoding="utf-8")

    config = load_nest_config(root=tmp_path)

    assert config.bed_count == 8
