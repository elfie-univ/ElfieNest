"""App orchestration adapter tests for the Brain runtime port."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread

from elfie.brain.emotion.appraiser import BrainClockPulse
from elfie.brain.reasoning.food_port import MainFoodSelection
from elfie.brain.reasoning.model_port import (
    JsonSchemaDocument,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelResponseMode,
    StructuredOutputMode,
)
from elfie.brain.workspace.contracts import (
    ActivityScope,
    CommunicationScope,
    ExternalExecutionDomain,
    ResponseScope,
    SourceDomain,
)
from elfie.brain.workspace.system import EventWorkspace
from infrastructure.models.model_execution_adapter import (
    ModelExecutionRequestAbandonedError,
    SerializedModelExecutionAdapter,
)
from infrastructure.models.model_execution_contracts import StructuredGenerationMode
from test.elfie.brain.reasoning.test_coordinator import (
    ELFIE_ID,
    NOW,
    RecordingPlanSink,
    _coordinator,
    _physical,
)


def _request(turn_id: str = "turn-1") -> ModelGenerationRequest:
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
    return ModelGenerationRequest(
        turn_id=turn_id,
        frame_id="frame-1",
        context_revision=1,
        capability_revision=1,
        created_at=now,
        deadline=now + timedelta(seconds=45),
        cause_event_ids=("event-1",),
        source_domain=SourceDomain.ACTIVITY,
        interaction_scope=ActivityScope(cause_id="event-1"),
        response_scope=ResponseScope(external_domain=None),
        system_prompt="You are Elfie.",
        user_prompt="Return a decision plan.",
        response_schema=JsonSchemaDocument(
            name="DecisionPlan",
            schema={"type": "object"},
        ),
        allowed_tools=(),
        temperature=0.1,
        max_tokens=200,
    )


class FakeStructuredModelExecution:
    def __init__(self, capabilities):
        self._capabilities = capabilities
        self.requests = []
        self.capability_food_keys = []

    def structured_capabilities(self, food_key=None, food_unavailable=False):
        self.capability_food_keys.append(food_key)
        return self._capabilities

    def generate_structured(self, request):
        self.requests.append(request)
        return request.to_result(text='{"ok": true}', prompt_tokens=3)


class BlockingStructuredModelExecution(FakeStructuredModelExecution):
    def __init__(self, capabilities):
        super().__init__(capabilities)
        self.release = Event()
        self.first_started = Event()
        self.second_started = Event()
        self.lock = Lock()

    def generate_structured(self, request):
        with self.lock:
            self.requests.append(request)
            call_count = len(self.requests)
        self.first_started.set()
        if call_count == 2:
            self.second_started.set()
        self.release.wait()
        return request.to_result(text='{"ok": true}', prompt_tokens=3)


def _schema_capabilities() -> ModelGenerationCapabilities:
    return ModelGenerationCapabilities(
        provider="openai",
        model_key="openai/gpt-test",
        supports_json_schema=True,
        supports_tool_calling=True,
        supports_json_mode=True,
        supports_plain_text=True,
        max_output_tokens=2048,
    )


def test_adapter_uses_schema_mode_for_schema_capable_runtime():
    runtime = FakeStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)

    result = adapter.generate(_request())

    assert result.selected_mode is StructuredOutputMode.JSON_SCHEMA
    assert result.provider == "openai"
    assert result.model_key == "openai/gpt-test"
    assert len(runtime.requests) == 1
    assert runtime.requests[0].selected_mode.value == "json_schema"


def test_adapter_resolves_elfie_food_for_each_generation():
    runtime = FakeStructuredModelExecution(_schema_capabilities())
    selected = {"food_key": "food_primary"}
    adapter = SerializedModelExecutionAdapter(
        runtime,
        food_key_resolver=lambda: selected["food_key"],
    )

    adapter.generate(_request("turn-1"))
    selected["food_key"] = "food_updated"
    adapter.generate(_request("turn-2"))

    assert runtime.capability_food_keys == ["food_primary", "food_updated"]
    assert [request.food_key for request in runtime.requests] == [
        "food_primary",
        "food_updated",
    ]


def test_adapter_preserves_main_food_unavailability_and_workspace():
    runtime = FakeStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(
        runtime,
        scope_id="elfie-1",
        food_key_resolver=lambda: MainFoodSelection("food_primary", unavailable=True),
    )

    adapter.generate(_request())

    assert runtime.requests[0].food_key == "food_primary"
    assert runtime.requests[0].food_unavailable is True
    assert runtime.requests[0].scope_id == "elfie-1"


def test_adapter_uses_plain_text_for_text_only_runtime():
    runtime = FakeStructuredModelExecution(
        ModelGenerationCapabilities(
            provider="ollama",
            model_key="ollama/qwen3.5:0.8b",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=False,
            supports_plain_text=True,
            max_output_tokens=512,
        )
    )
    adapter = SerializedModelExecutionAdapter(runtime)

    result = adapter.generate(_request())

    assert result.selected_mode is StructuredOutputMode.PLAIN_TEXT
    assert result.text == '{"ok": true}'
    assert len(runtime.requests) == 1
    assert runtime.requests[0].selected_mode.value == "plain_text"


def test_adapter_propagates_brain_reasoning_mode_to_runtime():
    runtime = FakeStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)

    adapter.generate(_request().model_copy(update={"reasoning_mode": "long"}))

    assert runtime.requests[0].reasoning_mode == "long"


def test_adapter_keeps_structured_mode_for_fast_owner_communication():
    runtime = FakeStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)
    request = _request().model_copy(
        update={
            "source_domain": SourceDomain.COMMUNICATION,
            "interaction_scope": CommunicationScope(
                channel_id="chat",
                conversation_id="owner:1",
            ),
            "response_scope": ResponseScope(
                external_domain=ExternalExecutionDomain.COMMUNICATION,
                channel_id="chat",
                conversation_id="owner:1",
            ),
            "reasoning_mode": "fast",
            "response_mode": ModelResponseMode.DIRECT_REPLY,
        }
    )

    result = adapter.generate(request)

    assert result.selected_mode is StructuredOutputMode.JSON_SCHEMA
    assert runtime.requests[0].selected_mode is StructuredGenerationMode.JSON_SCHEMA


def test_adapter_uses_schema_for_fast_owner_decision_plan() -> None:
    runtime = FakeStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)
    request = _request().model_copy(
        update={
            "source_domain": SourceDomain.COMMUNICATION,
            "interaction_scope": CommunicationScope(
                channel_id="chat",
                conversation_id="owner:1",
            ),
            "response_scope": ResponseScope(
                external_domain=ExternalExecutionDomain.COMMUNICATION,
                channel_id="chat",
                conversation_id="owner:1",
            ),
            "reasoning_mode": "fast",
            "response_mode": ModelResponseMode.DECISION_PLAN,
        }
    )

    result = adapter.generate(request)

    assert result.selected_mode is StructuredOutputMode.JSON_SCHEMA
    assert runtime.requests[0].selected_mode is StructuredGenerationMode.JSON_SCHEMA


def test_adapter_abandon_rotates_serialization_lease_for_replacement_call():
    # Given: the first provider call holds the current healthy serialization lease.
    runtime = BlockingStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)
    first_request = _request("turn-1")
    second_request = _request("turn-2")
    first_errors: list[RuntimeError] = []

    def run_first() -> None:
        try:
            adapter.generate(first_request)
        except RuntimeError as error:
            first_errors.append(error)

    first = Thread(target=run_first)
    second = Thread(target=adapter.generate, args=(second_request,))
    first.start()
    assert runtime.first_started.wait(1)

    try:
        # When: Brain abandons the timed-out request and starts its replacement.
        adapter.abandon(first_request)
        second.start()

        # Then: the replacement enters Runtime without waiting for the hung call.
        assert runtime.second_started.wait(0.2)
    finally:
        runtime.release.set()
        first.join(timeout=1)
        if second.ident is not None:
            second.join(timeout=1)
    assert len(first_errors) == 1
    assert isinstance(first_errors[0], ModelExecutionRequestAbandonedError)


def test_adapter_serializes_healthy_provider_calls() -> None:
    # Given: two healthy requests share the same current serialization lease.
    runtime = BlockingStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)
    first = Thread(target=adapter.generate, args=(_request("turn-1"),))
    second = Thread(target=adapter.generate, args=(_request("turn-2"),))
    first.start()
    assert runtime.first_started.wait(1)

    try:
        # When: the second request starts without abandoning the first.
        second.start()

        # Then: it cannot enter the provider until the first releases its lease.
        assert not runtime.second_started.wait(0.05)
        runtime.release.set()
        assert runtime.second_started.wait(1)
    finally:
        runtime.release.set()
        first.join(timeout=1)
        second.join(timeout=1)


def test_coordinator_timeout_rotates_the_production_runtime_adapter() -> None:
    # Given: the real orchestration adapter wraps a blocked structured Runtime.
    workspace = EventWorkspace(ELFIE_ID)
    runtime = BlockingStructuredModelExecution(_schema_capabilities())
    adapter = SerializedModelExecutionAdapter(runtime)
    coordinator, _, _ = _coordinator(workspace, adapter, RecordingPlanSink())
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    assert runtime.first_started.wait(1)

    try:
        # When: the coordinator times out the first turn and starts the next frame.
        coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 46.0))
        coordinator.wait_for_outcome_count(1)
        workspace.publish(_physical(2, 45_000, salience=0.95))
        coordinator.notify_perception()

        # Then: the second call crosses the production adapter before release.
        assert runtime.second_started.wait(1)
        coordinator.stop()
        coordinator.join()
    finally:
        runtime.release.set()
        coordinator.stop()
        coordinator.join()
