"""Consumer-owned Ports for the model Runtime coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping, Optional, Protocol

from pydantic import JsonValue

from app.features.configuration.food import StoredModelEvidence
from elfie.brain.reasoning.tool_port import ToolPort

if TYPE_CHECKING:
    from infrastructure.models.runtime_config import LLMRuntimeConfig
    from infrastructure.models.runtime_observations import (
        FallbackObservation,
        FoodDecisionObservation,
    )


class RuntimeObserverPort(Protocol):
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


class RuntimeToolLoopPort(Protocol):
    def run(
        self,
        messages: list[dict[str, str]],
        max_loops: int,
        call_llm: Callable[[list[dict[str, str]]], str],
    ) -> str: ...


RuntimePolicy = Mapping[str, JsonValue]
ToolConfigLoader = Callable[[Optional[RuntimePolicy]], dict[str, dict[str, JsonValue]]]
EffectiveToolKeys = Callable[
    [Optional[RuntimePolicy], tuple[str, ...]], tuple[str, ...]
]
SearchFactory = Callable[[Optional[RuntimePolicy]], RuntimeSearchPort]
PermissionFactory = Callable[
    ["LLMRuntimeConfig", RuntimeObserverPort], RuntimePermissionPort
]
FileAccessFactory = Callable[[str, int, int], RuntimeFileAccessPort]
ToolLoopFactory = Callable[
    [ToolPort, tuple[str, ...], Optional[str]], RuntimeToolLoopPort
]
PromptInjector = Callable[
    [list[dict[str, JsonValue]], list[str]], list[dict[str, JsonValue]]
]
ConfigPaths = Callable[[], tuple[Path, ...]]
ModelEvidenceSource = Callable[[], Mapping[str, StoredModelEvidence]]
RuntimeConfigLoader = Callable[[], "LLMRuntimeConfig"]


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
        model_evidence_source: ModelEvidenceSource,
        tool_loop_factory: ToolLoopFactory,
        prompt_injector: PromptInjector,
        runtime_config_loader: RuntimeConfigLoader,
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
        self.runtime_config_loader = runtime_config_loader


__all__ = (
    "ConfigPaths",
    "EffectiveToolKeys",
    "FileAccessFactory",
    "PermissionFactory",
    "RuntimeAgentPorts",
    "RuntimeFileAccessPort",
    "ModelEvidenceSource",
    "RuntimeObserverPort",
    "ToolCallObservationPortModel",
    "ToolPermissionObservationPortModel",
    "RuntimePermissionPort",
    "RuntimePolicy",
    "RuntimeSearchPort",
    "SearchFactory",
    "ToolConfigLoader",
    "ToolLoopFactory",
    "PromptInjector",
    "RuntimeConfigLoader",
    "RuntimeToolLoopPort",
)
