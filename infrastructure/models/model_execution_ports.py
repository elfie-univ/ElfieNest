"""Consumer-owned Ports required by model execution."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping, Optional, Protocol

from pydantic import JsonValue

from app.features.configuration.food import StoredModelEvidence
from elfie.brain.reasoning.tool_port import ToolPort

if TYPE_CHECKING:
    from infrastructure.models.model_execution_config import ModelExecutionConfig
    from infrastructure.models.model_execution_observations import (
        FallbackObservation,
        FoodDecisionObservation,
    )


class ModelExecutionObserverPort(Protocol):
    def record_tool_observation(
        self, observation: ToolCallObservationPortModel
    ) -> None: ...

    def record_permission_observation(
        self, observation: ToolPermissionObservationPortModel
    ) -> None: ...

    def record_fallback(self, observation: FallbackObservation) -> None: ...

    def record_food_decision(self, observation: FoodDecisionObservation) -> None: ...


class ToolCallObservationPortModel(Protocol):
    """Structural tool result view shared with the technical ToolPort."""

    @property
    def tool_name(self) -> str: ...

    @property
    def ok(self) -> bool: ...

    @property
    def metadata(self) -> Mapping[str, JsonValue]: ...


class ToolPermissionObservationPortModel(Protocol):
    """Structural permission decision view shared with the technical ToolPort."""

    @property
    def action(self) -> str: ...

    @property
    def resource(self) -> str: ...

    @property
    def allowed(self) -> bool: ...

    @property
    def mode(self) -> str: ...

    @property
    def reason(self) -> str: ...


class ModelExecutionSearchPort(Protocol):
    def search(self, query: str, max_results: int | None = None) -> str: ...


class ModelExecutionPermissionPort(Protocol):
    def verify_action(
        self,
        action: str,
        file_path: str | None = None,
        token: str | None = None,
    ) -> bool: ...


class ModelExecutionFileAccessPort(Protocol):
    def read_text(self, relative_path: str) -> str: ...

    def list_files(self, relative_path: str = ".") -> list[str]: ...


class ModelExecutionToolLoopPort(Protocol):
    def run(
        self,
        messages: list[dict[str, str]],
        max_loops: int,
        call_llm: Callable[[list[dict[str, str]]], str],
    ) -> str: ...


ModelExecutionPolicy = Mapping[str, JsonValue]
ToolConfigLoader = Callable[
    [Optional[ModelExecutionPolicy]], dict[str, dict[str, JsonValue]]
]
EffectiveToolKeys = Callable[
    [Optional[ModelExecutionPolicy], tuple[str, ...]], tuple[str, ...]
]
SearchFactory = Callable[[Optional[ModelExecutionPolicy]], ModelExecutionSearchPort]
PermissionFactory = Callable[
    ["ModelExecutionConfig", ModelExecutionObserverPort], ModelExecutionPermissionPort
]
FileAccessFactory = Callable[[str, int, int], ModelExecutionFileAccessPort]
ToolLoopFactory = Callable[
    [ToolPort, tuple[str, ...], Optional[str]], ModelExecutionToolLoopPort
]
PromptInjector = Callable[
    [list[dict[str, JsonValue]], list[str]], list[dict[str, JsonValue]]
]
ConfigPaths = Callable[[], tuple[Path, ...]]
ModelEvidenceSource = Callable[[], Mapping[str, StoredModelEvidence]]
ModelExecutionConfigLoader = Callable[[], "ModelExecutionConfig"]


class ModelExecutionAgentPorts:
    """All technical capabilities required by ``ModelExecutionAgent``."""

    def __init__(
        self,
        *,
        observer: ModelExecutionObserverPort,
        config_paths: ConfigPaths,
        search_factory: SearchFactory,
        permission_factory: PermissionFactory,
        tool_config_loader: ToolConfigLoader,
        effective_tool_keys: EffectiveToolKeys,
        file_access_factory: FileAccessFactory,
        model_evidence_source: ModelEvidenceSource,
        tool_loop_factory: ToolLoopFactory,
        prompt_injector: PromptInjector,
        model_execution_config_loader: ModelExecutionConfigLoader,
    ) -> None:
        self.observer = observer
        self.config_paths = config_paths
        self.search_factory = search_factory
        self.permission_factory = permission_factory
        self.tool_config_loader = tool_config_loader
        self.effective_tool_keys = effective_tool_keys
        self.file_access_factory = file_access_factory
        self.model_evidence_source = model_evidence_source
        self.tool_loop_factory = tool_loop_factory
        self.prompt_injector = prompt_injector
        self.model_execution_config_loader = model_execution_config_loader


__all__ = (
    "ConfigPaths",
    "EffectiveToolKeys",
    "FileAccessFactory",
    "PermissionFactory",
    "ModelExecutionAgentPorts",
    "ModelExecutionFileAccessPort",
    "ModelEvidenceSource",
    "ModelExecutionObserverPort",
    "ToolCallObservationPortModel",
    "ToolPermissionObservationPortModel",
    "ModelExecutionPermissionPort",
    "ModelExecutionPolicy",
    "ModelExecutionSearchPort",
    "SearchFactory",
    "ToolConfigLoader",
    "ToolLoopFactory",
    "PromptInjector",
    "ModelExecutionConfigLoader",
    "ModelExecutionToolLoopPort",
)
