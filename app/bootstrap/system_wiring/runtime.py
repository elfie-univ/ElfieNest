"""System composition for the model Runtime technical Ports."""

from __future__ import annotations

from typing import Any, cast

from infrastructure.models.runtime_observations import get_runtime_observer
from infrastructure.models.runtime_ports import (
    RuntimeAgentPorts,
    RuntimeFileAccessPort,
    RuntimeObserverPort,
    RuntimePermissionPort,
)
from infrastructure.persistence.layout.data_home import get_runtime_config_paths
from infrastructure.tools.execution.config import effective_tool_keys, load_tool_configs
from infrastructure.tools.execution.permissions import PermissionManager
from infrastructure.tools.local_file.local_files import LocalFileAccessPlugin
from infrastructure.tools.web_search.search import WebSearchPlugin


def build_runtime_agent_ports() -> RuntimeAgentPorts:
    observer = get_runtime_observer()

    def build_permission_manager(
        config: Any, observation_port: RuntimeObserverPort
    ) -> RuntimePermissionPort:
        return cast(
            RuntimePermissionPort,
            PermissionManager(config, observation_port),
        )

    def build_file_access(
        root: str, max_read_bytes: int, max_items: int
    ) -> RuntimeFileAccessPort:
        return cast(
            RuntimeFileAccessPort,
            LocalFileAccessPlugin(
                root,
                max_read_bytes=max_read_bytes,
                max_items=max_items,
            ),
        )

    return RuntimeAgentPorts(
        observer=observer,
        config_paths=get_runtime_config_paths,
        search_factory=WebSearchPlugin.from_runtime_policy,
        permission_factory=build_permission_manager,
        tool_config_loader=load_tool_configs,
        effective_tool_keys=effective_tool_keys,
        file_access_factory=build_file_access,
    )


__all__ = ("build_runtime_agent_ports",)
