"""Thread-safe Adapter between Brain and model-execution contracts."""

from __future__ import annotations

from _thread import LockType
from threading import Lock
from typing import Callable, Dict, Protocol, Set

from elfie.brain.reasoning.food_port import MainFoodSelection
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.brain.reasoning.tool_port import ToolPort
from elfie.message_types import TurnId
from infrastructure.models.model_execution_contracts import (
    StructuredGenerationMode,
    StructuredMessage,
    StructuredModelExecutionRequest,
    StructuredModelExecutionResult,
)


class StructuredModelExecution(Protocol):
    """Narrow ModelExecutionAgent surface consumed by this adapter."""

    def structured_capabilities(
        self,
        food_key: str | None = None,
        food_unavailable: bool = False,
    ) -> StructuredCapabilityView:
        """Return the selected model target's capabilities."""

    def generate_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        """Execute one structured request."""


class StructuredCapabilityView(Protocol):
    """Structural capability shape shared by execution and test fakes."""

    provider: str
    model_key: str
    supports_json_schema: bool
    supports_tool_calling: bool
    supports_json_mode: bool
    supports_plain_text: bool
    max_output_tokens: int


class ModelExecutionRequestAbandonedError(RuntimeError):
    """A retired serialization lease rejected an abandoned request."""

    __slots__ = ("turn_id",)

    def __init__(self, turn_id: TurnId) -> None:
        self.turn_id = turn_id
        super().__init__(turn_id)

    def __str__(self) -> str:
        return f"model execution request {self.turn_id} was abandoned"


class SerializedModelExecutionAdapter:
    """Serialize healthy calls and rotate the lease after a hard timeout."""

    def __init__(
        self,
        execution: StructuredModelExecution,
        *,
        scope_id: str | None = None,
        food_key_resolver: Callable[[], str | MainFoodSelection | None] | None = None,
    ) -> None:
        self._execution = execution
        self._scope_id = scope_id
        self._food_key_resolver = food_key_resolver or (lambda: None)
        self._state_lock = Lock()
        self._current_lease = Lock()
        self._request_leases: Dict[TurnId, LockType] = {}
        self._abandoned: Set[TurnId] = set()

    def capabilities(self) -> ModelGenerationCapabilities:
        """Convert execution capabilities into the Brain-owned contract."""
        selection = self._food_selection()
        raw = self._execution.structured_capabilities(
            selection.food_id,
            selection.unavailable,
        )
        return self._convert_capabilities(raw)

    @property
    def tool_port(self) -> ToolPort | None:
        """Expose the already-scoped semantic tool view to Brain."""
        return getattr(self._execution, "tool_port", None)

    @staticmethod
    def _convert_capabilities(
        raw: StructuredCapabilityView,
    ) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider=raw.provider,
            model_key=raw.model_key,
            supports_json_schema=raw.supports_json_schema,
            supports_tool_calling=raw.supports_tool_calling,
            supports_json_mode=raw.supports_json_mode,
            supports_plain_text=raw.supports_plain_text,
            max_output_tokens=raw.max_output_tokens,
        )

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        """Choose one mode, execute once, and translate the result."""
        selection = self._food_selection()
        raw_capabilities = self._execution.structured_capabilities(
            selection.food_id,
            selection.unavailable,
        )
        capabilities = self._convert_capabilities(raw_capabilities)
        selected_mode = self._select_mode(capabilities, request)
        model_execution_request = StructuredModelExecutionRequest(
            prompt=request.user_prompt,
            messages=(
                StructuredMessage(role="system", content=request.system_prompt),
                StructuredMessage(role="user", content=request.user_prompt),
            ),
            response_schema_name=request.response_schema.name,
            response_schema=request.response_schema.document,
            selected_mode=StructuredGenerationMode(selected_mode.value),
            reasoning_mode=request.reasoning_mode,
            allowed_tools=request.allowed_tools,
            provider=capabilities.provider,
            model_key=capabilities.model_key,
            food_key=selection.food_id,
            food_unavailable=selection.unavailable,
            scope_id=self._scope_id,
            temperature=request.temperature,
            max_tokens=min(request.max_tokens, capabilities.max_output_tokens),
        )
        lease = self._acquire_current_lease(request.turn_id)
        try:
            result = self._execution.generate_structured(model_execution_request)
        finally:
            with self._state_lock:
                abandoned = request.turn_id in self._abandoned
                self._request_leases.pop(request.turn_id, None)
                self._abandoned.discard(request.turn_id)
            lease.release()
        if abandoned:
            raise ModelExecutionRequestAbandonedError(request.turn_id)
        return ModelGenerationResult(
            text=result.text,
            selected_mode=StructuredOutputMode(result.selected_mode.value),
            provider=result.provider,
            model_key=result.model_key,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        """Retire the request's lease without waiting for provider return."""
        with self._state_lock:
            lease = self._request_leases.get(request.turn_id)
            if lease is None:
                return
            self._abandoned.add(request.turn_id)
            if lease is self._current_lease:
                self._current_lease = Lock()

    def _acquire_current_lease(self, turn_id: TurnId) -> LockType:
        while True:
            with self._state_lock:
                lease = self._current_lease
                self._request_leases[turn_id] = lease
            lease.acquire()
            with self._state_lock:
                if turn_id in self._abandoned:
                    self._request_leases.pop(turn_id, None)
                    self._abandoned.discard(turn_id)
                    lease.release()
                    raise ModelExecutionRequestAbandonedError(turn_id)
                if lease is self._current_lease:
                    return lease
            lease.release()

    def _food_selection(self) -> MainFoodSelection:
        resolved = self._food_key_resolver()
        if isinstance(resolved, MainFoodSelection):
            return resolved
        return MainFoodSelection(resolved)

    @staticmethod
    def _select_mode(
        capabilities: ModelGenerationCapabilities,
        request: ModelGenerationRequest,
    ) -> StructuredOutputMode:
        if capabilities.supports_json_schema:
            return StructuredOutputMode.JSON_SCHEMA
        if capabilities.supports_tool_calling:
            return StructuredOutputMode.TOOL_CALL
        if capabilities.supports_json_mode:
            return StructuredOutputMode.JSON_TEXT
        # A genuinely text-only model is the sole case where a direct reply
        # may remain plain text.  Remote/modern models must not lose the
        # DecisionPlan envelope merely because the response is conversational.
        if capabilities.supports_plain_text:
            return StructuredOutputMode.PLAIN_TEXT
        return StructuredOutputMode.JSON_TEXT


__all__ = (
    "ModelExecutionRequestAbandonedError",
    "SerializedModelExecutionAdapter",
    "StructuredModelExecution",
)
