"""Composition for the capability adapters.

The feature-facing adapters remain storage-agnostic; this module is the
application composition root that binds them to the local configuration and
secret stores.
"""

from __future__ import annotations

from pathlib import Path

from infrastructure.persistence.configuration.config_store import (
    read_yaml_mapping,
    write_yaml_mapping,
)
from infrastructure.persistence.configuration.runtime_settings import (
    read_runtime_settings,
    write_runtime_settings,
)
from infrastructure.persistence.configuration.secrets import (
    resolve_secret,
    set_tool_secret,
)
from infrastructure.persistence.model_execution_config import (
    load_model_execution_config,
)
from infrastructure.tools import (
    DirectCapabilityValidationAdapter,
    RuntimeCapabilitiesAdapter,
    ToolCapabilitySecretAdapter,
)
from infrastructure.tools.validation.direct_validation import DirectToolValidationRunner
from infrastructure.tools.web_search.search import WebSearchPlugin


def build_capability_adapters(
    config_path: Path,
    secret_path: Path | None,
) -> tuple[
    RuntimeCapabilitiesAdapter,
    ToolCapabilitySecretAdapter,
    DirectCapabilityValidationAdapter,
]:
    def read_document(path: Path):
        if path == config_path:
            return read_runtime_settings()
        return read_yaml_mapping(path)

    def write_document(path: Path, document):
        if path == config_path:
            write_runtime_settings(document)
        else:
            write_yaml_mapping(path, document)

    return (
        RuntimeCapabilitiesAdapter(
            config_path,
            read_document=read_document,
            write_document=write_document,
        ),
        ToolCapabilitySecretAdapter(
            secret_path,
            resolve=resolve_secret,
            write=set_tool_secret,
        ),
        DirectCapabilityValidationAdapter(
            config_loader=load_model_execution_config,
            runner_factory=lambda config: DirectToolValidationRunner(
                config,
                search_plugin=WebSearchPlugin.from_model_execution_policy(
                    config.runtime_policy,
                    secret_resolver=resolve_secret,
                ),
            ),
        ),
    )


__all__ = ("build_capability_adapters",)
