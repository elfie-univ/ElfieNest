"""Thread-safe adapter between Brain contracts and AI Runtime contracts."""

from __future__ import annotations

from _thread import LockType
from threading import Lock
from typing import Dict, Protocol, Set

from ai_runtime.gateway.request import (
    StructuredGenerationMode,
    StructuredMessage,
    StructuredRuntimeRequest,
    StructuredRuntimeResult,
)
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.message_types import TurnId


class StructuredRuntime(Protocol):
    """Narrow RuntimeAgent surface consumed by this adapter."""

    def structured_capabilities(self) -> StructuredCapabilityView:
        """Return the selected runtime target's capabilities."""

    def generate_structured(
        self,
        request: StructuredRuntimeRequest,
    ) -> StructuredRuntimeResult:
        """Execute one structured request."""


class StructuredCapabilityView(Protocol):
    """Structural capability shape shared by Runtime and test fakes."""

    provider: str
    model_key: str
    supports_json_schema: bool
    supports_tool_calling: bool
    supports_json_mode: bool
    supports_plain_text: bool
    max_output_tokens: int


class RuntimeRequestAbandonedError(RuntimeError):
    """A retired serialization lease rejected an abandoned request."""

    __slots__ = ("turn_id",)

    def __init__(self, turn_id: TurnId) -> None:
        self.turn_id = turn_id
        super().__init__(turn_id)

    def __str__(self) -> str:
        return f"runtime request {self.turn_id} was abandoned"


class SerializedRuntimeAdapter:
    """Serialize healthy calls and rotate the lease after a hard timeout."""

    def __init__(self, runtime: StructuredRuntime) -> None:
        self._runtime = runtime
        self._state_lock = Lock()
        self._current_lease = Lock()
        self._request_leases: Dict[TurnId, LockType] = {}
        self._abandoned: Set[TurnId] = set()

    def capabilities(self) -> ModelGenerationCapabilities:
        """Convert Runtime capabilities into the Brain-owned contract."""
        raw = self._runtime.structured_capabilities()
        return self._convert_capabilities(raw)

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
        """Select one mode, call Runtime once, and translate the result."""
        capabilities = self.capabilities()
        selected_mode = self._select_mode(capabilities)
        runtime_request = StructuredRuntimeRequest(
            prompt=request.user_prompt,
            messages=(
                StructuredMessage(role="system", content=request.system_prompt),
                StructuredMessage(role="user", content=request.user_prompt),
            ),
            response_schema_name=request.response_schema.name,
            response_schema=request.response_schema.document,
            selected_mode=StructuredGenerationMode(selected_mode.value),
            allowed_tools=request.allowed_tools,
            provider=capabilities.provider,
            model_key=capabilities.model_key,
            temperature=request.temperature,
            max_tokens=min(request.max_tokens, capabilities.max_output_tokens),
        )
        lease = self._acquire_current_lease(request.turn_id)
        try:
            result = self._runtime.generate_structured(runtime_request)
        finally:
            with self._state_lock:
                abandoned = request.turn_id in self._abandoned
                self._request_leases.pop(request.turn_id, None)
                self._abandoned.discard(request.turn_id)
            lease.release()
        if abandoned:
            raise RuntimeRequestAbandonedError(request.turn_id)
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
                    raise RuntimeRequestAbandonedError(turn_id)
                if lease is self._current_lease:
                    return lease
            lease.release()

    @staticmethod
    def _select_mode(
        capabilities: ModelGenerationCapabilities,
    ) -> StructuredOutputMode:
        if capabilities.supports_json_schema:
            return StructuredOutputMode.JSON_SCHEMA
        if capabilities.supports_tool_calling:
            return StructuredOutputMode.TOOL_CALL
        return StructuredOutputMode.JSON_TEXT


__all__ = ("RuntimeRequestAbandonedError", "SerializedRuntimeAdapter")
