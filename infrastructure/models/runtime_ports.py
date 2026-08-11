"""Consumer-owned Ports for the model Runtime coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol


class RuntimeObserverPort(Protocol):
    def record_tool_observation(self, observation: Any) -> None: ...

    def record_permission_observation(self, observation: Any) -> None: ...

    def record_fallback(self, observation: Any) -> None: ...

    def record_food_decision(self, observation: Any) -> None: ...


class RuntimeSearchPort(Protocol):
    def search(self, query: str, max_results: int | None = None) -> str: ...


class RuntimePermissionPort(Protocol):
    def verify_action(
        self,
        action: str,
        file_path: str | None = None,
        token: str | None = None,
    ) -> bool: ...


class RuntimeFileAccessPort(Protocol):
    def read_text(self, relative_path: str) -> str: ...

    def list_files(self, relative_path: str = ".") -> list[str]: ...


RuntimePolicy = Mapping[str, Any]
ToolConfigLoader = Callable[[Optional[RuntimePolicy]], dict[str, dict[str, Any]]]
EffectiveToolKeys = Callable[
    [Optional[RuntimePolicy], tuple[str, ...]], tuple[str, ...]
]
SearchFactory = Callable[[Optional[RuntimePolicy]], RuntimeSearchPort]
PermissionFactory = Callable[[Any, RuntimeObserverPort], RuntimePermissionPort]
FileAccessFactory = Callable[[str, int, int], RuntimeFileAccessPort]
ConfigPaths = Callable[[], tuple[Path, ...]]


class RuntimeAgentPorts:
    """All technical capabilities required by ``RuntimeAgent``."""

    def __init__(
        self,
        *,
        observer: RuntimeObserverPort,
        config_paths: ConfigPaths,
        search_factory: SearchFactory,
        permission_factory: PermissionFactory,
        tool_config_loader: ToolConfigLoader,
        effective_tool_keys: EffectiveToolKeys,
        file_access_factory: FileAccessFactory,
    ) -> None:
        self.observer = observer
        self.config_paths = config_paths
        self.search_factory = search_factory
        self.permission_factory = permission_factory
        self.tool_config_loader = tool_config_loader
        self.effective_tool_keys = effective_tool_keys
        self.file_access_factory = file_access_factory


__all__ = (
    "ConfigPaths",
    "EffectiveToolKeys",
    "FileAccessFactory",
    "PermissionFactory",
    "RuntimeAgentPorts",
    "RuntimeFileAccessPort",
    "RuntimeObserverPort",
    "RuntimePermissionPort",
    "RuntimePolicy",
    "RuntimeSearchPort",
    "SearchFactory",
    "ToolConfigLoader",
)
