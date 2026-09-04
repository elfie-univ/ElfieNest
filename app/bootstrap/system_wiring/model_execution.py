"""System composition for model-execution technical Ports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import cast

from app.features.configuration.food import StoredModelEvidence
from elfie.public import ToolPort
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_execution_observations import (
    get_model_execution_observer,
)
from infrastructure.models.model_execution_ports import (
    ModelExecutionAgentPorts,
    ModelExecutionFileAccessPort,
    ModelExecutionObserverPort,
    ModelExecutionPermissionPort,
)
from infrastructure.persistence.configuration.bundled_defaults import load_tool_defaults
from infrastructure.persistence.configuration.secrets import resolve_secret
from infrastructure.persistence.layout.data_home import get_model_execution_config_paths
from infrastructure.persistence.model_execution_config import (
    load_model_execution_config,
)
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.tools.execution.config import effective_tool_keys, load_tool_configs
from infrastructure.tools.execution.permissions import PermissionManager
from infrastructure.tools.local_file.local_files import LocalFileAccessPlugin
from infrastructure.tools.port_adapter import ToolPortAdapter
from infrastructure.tools.web_search.search import WebSearchPlugin


def build_model_execution_agent_ports(
    *,
    model_evidence_source: Callable[[], Mapping[str, StoredModelEvidence]],
    report_writer: ReportStorageAdapter | None = None,
) -> ModelExecutionAgentPorts:
    observer = get_model_execution_observer(report_writer)
    tool_defaults = load_tool_defaults()
    tool_config_loader = partial(
        load_tool_configs, defaults=tool_defaults, secret_resolver=resolve_secret
    )
    allowed_tool_keys = partial(
        effective_tool_keys, defaults=tool_defaults, secret_resolver=resolve_secret
    )

    def build_permission_manager(
        config: ModelExecutionConfig, observation_port: ModelExecutionObserverPort
    ) -> ModelExecutionPermissionPort:
        return cast(
            ModelExecutionPermissionPort,
            PermissionManager(config, observation_port),
        )

    def build_file_access(
        root: str, max_read_bytes: int, max_items: int
    ) -> ModelExecutionFileAccessPort:
        return cast(
            ModelExecutionFileAccessPort,
            LocalFileAccessPlugin(
                root,
                max_read_bytes=max_read_bytes,
                max_items=max_items,
            ),
        )

    return ModelExecutionAgentPorts(
        observer=observer,
        config_paths=get_model_execution_config_paths,
        search_factory=partial(
            WebSearchPlugin.from_model_execution_policy,
            defaults=tool_defaults,
            secret_resolver=resolve_secret,
        ),
        permission_factory=build_permission_manager,
        tool_config_loader=tool_config_loader,
        effective_tool_keys=allowed_tool_keys,
        file_access_factory=build_file_access,
        model_evidence_source=model_evidence_source,
        model_execution_config_loader=load_model_execution_config,
    )


@dataclass(frozen=True)
class AgentValidationComposition:
    """Concrete tool composition supplied to model validation probes."""

    tool_port_factory: Callable[[ModelExecutionConfig, Path, str], ToolPort]


def build_agent_validation_composition(
    report_writer: ReportStorageAdapter | None = None,
) -> AgentValidationComposition:
    observer = get_model_execution_observer(report_writer)
    tool_defaults = load_tool_defaults()
    tool_config_loader = partial(
        load_tool_configs, defaults=tool_defaults, secret_resolver=resolve_secret
    )

    def tool_port_factory(
        config: ModelExecutionConfig, root: Path, tool_key: str
    ) -> ToolPort:
        return ToolPortAdapter.from_model_execution_config(
            config,
            observation_port=observer,
            tool_config_loader=tool_config_loader,
            workspace_resolver=lambda scope_id: (
                root if scope_id == "validation" else None
            ),
            allowed_tool_keys=(tool_key,),
        )

    return AgentValidationComposition(
        tool_port_factory=tool_port_factory,
    )


__all__ = (
    "AgentValidationComposition",
    "build_agent_validation_composition",
    "build_model_execution_agent_ports",
)
