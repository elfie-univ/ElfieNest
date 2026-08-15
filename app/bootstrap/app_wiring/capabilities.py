"""Composition for the capability adapters.

The feature-facing adapters remain storage-agnostic; this module is the
application composition root that binds them to the local configuration and
secret stores.
"""

from __future__ import annotations

from pathlib import Path

from infrastructure.persistence.configuration.secrets import (
    resolve_secret,
    set_tool_secret,
)
from infrastructure.persistence.layout.data_home import (
    get_config_path,
    get_tool_config_path,
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
    tool_path = (
        get_tool_config_path()
        if config_path == get_config_path()
        else config_path.with_name("tools.yaml")
    )

    return (
        RuntimeCapabilitiesAdapter(
            tool_path,
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
