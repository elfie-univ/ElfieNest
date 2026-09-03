"""Infrastructure Adapter for the Brain-owned semantic ``ToolPort``."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Mapping, Optional, Protocol, Tuple, cast

from pydantic import JsonValue

from elfie.brain.reasoning.tool_port import (
    ToolDefinition,
    ToolKey,
    ToolRequest,
    ToolResult,
)
from elfie.message_types import ErrorInfo

from .execution.executor import (
    FileAccessPlugin,
    PermissionManager,
    SearchPlugin,
    ToolExecutionContext,
    ToolExecutor,
)
from .execution.executor import ToolResult as TechnicalToolResult
from .execution.observation import ToolObservationPort
from .execution.permissions import PermissionManager as ConcretePermissionManager
from .local_file.local_files import LocalFileAccessPlugin
from .registry import ToolRegistry
from .web_search.search import WebSearchPlugin

WorkspaceResolver = Callable[[Optional[str]], Optional[Path]]
ToolConfigLoader = Callable[
    [Optional[Mapping[str, JsonValue]]], Mapping[str, Mapping[str, JsonValue]]
]
_TOOL_REGISTRY = ToolRegistry()


class ModelExecutionPolicySource(Protocol):
    runtime_policy: Mapping[str, JsonValue]


class DisabledToolPort:
    """Safe no-op view used by isolated tests and explicit offline runtimes."""

    def available_tool_keys(self) -> Tuple[ToolKey, ...]:
        return ()

    def available_tool_definitions(self) -> Tuple[ToolDefinition, ...]:
        return ()

    def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(
            tool_key=request.tool_key,
            ok=False,
            content="该工具在当前作用域未启用。",
            error=ErrorInfo(
                code="tool_unavailable",
                message="该工具在当前作用域未启用。",
                retryable=False,
            ),
        )


class ToolPortAdapter:
    """Scope and translate one Elfie's semantic requests to technical plugins."""

    def __init__(
        self,
        *,
        config: ModelExecutionPolicySource,
        search_plugin: SearchPlugin,
        permission_manager: PermissionManager,
        observation_port: ToolObservationPort,
        tool_config_loader: ToolConfigLoader,
        workspace_resolver: WorkspaceResolver | None = None,
        allowed_tool_keys: Iterable[str] = (),
    ) -> None:
        self._config = config
        self._search_plugin = search_plugin
        self._permission_manager = permission_manager
        self._observation_port = observation_port
        self._tool_config_loader = tool_config_loader
        self._workspace_resolver = workspace_resolver or (lambda _scope_id: None)
        self._allowed_tool_keys = frozenset(allowed_tool_keys)

    @classmethod
    def from_model_execution_config(
        cls,
        config: ModelExecutionPolicySource,
        *,
        observation_port: ToolObservationPort,
        tool_config_loader: ToolConfigLoader,
        workspace_resolver: WorkspaceResolver | None = None,
        allowed_tool_keys: Iterable[str] | None = None,
    ) -> ToolPortAdapter:
        runtime_policy = getattr(config, "runtime_policy", {})
        configured = (
            tuple(allowed_tool_keys)
            if allowed_tool_keys is not None
            else ("web_search", "local_file")
        )
        return cls(
            config=config,
            search_plugin=WebSearchPlugin.from_model_execution_policy(
                runtime_policy, config_loader=tool_config_loader
            ),
            permission_manager=ConcretePermissionManager(config, observation_port),
            observation_port=observation_port,
            tool_config_loader=tool_config_loader,
            workspace_resolver=workspace_resolver,
            allowed_tool_keys=configured,
        )

    def available_tool_keys(self) -> Tuple[ToolKey, ...]:
        runtime_policy = getattr(self._config, "runtime_policy", {})
        enabled = {
            key
            for key, config in self._tool_config_loader(runtime_policy).items()
            if config.get("enabled") is True
        }
        return tuple(
            definition.name
            for definition in _TOOL_REGISTRY.list_definitions()
            if definition.name in enabled and definition.name in self._allowed_tool_keys
        )

    def available_tool_definitions(self) -> Tuple[ToolDefinition, ...]:
        """Return definitions filtered by the same config and scope policy."""
        available = set(self.available_tool_keys())
        return tuple(
            definition
            for definition in _TOOL_REGISTRY.list_definitions()
            if definition.name in available
        )

    def execute(self, request: ToolRequest) -> ToolResult:
        if request.tool_key not in self.available_tool_keys():
            return self._failure(
                request,
                "tool_denied",
                "该工具未被此 Elfie 或全局策略授权。",
            )

        file_access = self._file_access_for(request.scope_id)
        context = ToolExecutionContext(
            allowed_tool_keys=(request.tool_key,),
            search_plugin=self._search_plugin,
            permission_manager=self._permission_manager,
            observation_port=self._observation_port,
            file_access_plugin=file_access,
            runtime_enabled_tools=self.available_tool_keys(),
            tool_configs=self._tool_config_loader(
                getattr(self._config, "runtime_policy", {})
            ),
        )
        result = self._executor(context).execute(request)
        return self._translate(request, result)

    def _executor(self, context: ToolExecutionContext) -> ToolExecutor:
        return ToolExecutor(context)

    def _file_access_for(self, scope_id: Optional[str]) -> FileAccessPlugin | None:
        root = self._workspace_resolver(scope_id)
        if root is None:
            return None
        config = self._tool_config_loader(getattr(self._config, "runtime_policy", {}))[
            "local_file"
        ]
        return cast(
            FileAccessPlugin,
            LocalFileAccessPlugin(
                root,
                max_read_bytes=_int_setting(config.get("max_read_bytes"), 65536),
                max_items=_int_setting(config.get("max_items"), 200),
            ),
        )

    @staticmethod
    def _translate(request: ToolRequest, result: TechnicalToolResult) -> ToolResult:
        metadata = result.metadata
        raw_error = metadata.get("error_type")
        error = None
        if not result.ok:
            error = ErrorInfo(
                code="tool_execution_failed",
                message=result.content,
                retryable=True,
                causes=(
                    ErrorInfo(
                        code="tool_error_type",
                        message=str(raw_error),
                    ),
                )
                if raw_error
                else (),
            )
        return ToolResult(
            tool_key=request.tool_key,
            ok=result.ok,
            content=result.content,
            truncated=bool(metadata.get("truncated", False)),
            retained_bytes=int(metadata.get("retained_bytes", 0) or 0),
            source_items=int(metadata.get("items", 0) or 0),
            error=error,
        )

    @staticmethod
    def _failure(request: ToolRequest, code: str, message: str) -> ToolResult:
        return ToolResult(
            tool_key=request.tool_key,
            ok=False,
            content=message,
            error=ErrorInfo(code=code, message=message, retryable=False),
        )


def _int_setting(value: JsonValue, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


__all__ = ("DisabledToolPort", "ToolPortAdapter", "WorkspaceResolver")
