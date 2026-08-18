"""Composition for the capability adapters.

The feature-facing adapters remain storage-agnostic; this module is the
application composition root that binds them to the local configuration and
secret stores.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from infrastructure.persistence.configuration.bundled_defaults import load_tool_defaults
from infrastructure.persistence.configuration.capabilities import (
    RuntimeCapabilitiesAdapter,
)
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
    ToolCapabilitySecretAdapter,
)
from infrastructure.tools.validation.direct_validation import DirectToolValidationRunner
from infrastructure.tools.web_search.search import WebSearchPlugin


def build_capability_adapters(
    config_path: Path,
    secret_path: Path | None,
    *,
    data_home: Path | None = None,
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
    tool_defaults = load_tool_defaults()

    config_loader = (
        load_model_execution_config
        if data_home is None
        else partial(load_model_execution_config, str(data_home))
    )

    return (
        RuntimeCapabilitiesAdapter(
            tool_path,
            defaults=tool_defaults,
        ),
        ToolCapabilitySecretAdapter(
            secret_path,
            resolve=resolve_secret,
            write=set_tool_secret,
        ),
        DirectCapabilityValidationAdapter(
            config_loader=config_loader,
            runner_factory=lambda config: DirectToolValidationRunner(
                config,
                search_plugin=WebSearchPlugin.from_model_execution_policy(
                    config.runtime_policy,
                    defaults=tool_defaults,
                    secret_resolver=(lambda name: resolve_secret(name, secret_path)),
                ),
            ),
        ),
    )


__all__ = ("build_capability_adapters",)
