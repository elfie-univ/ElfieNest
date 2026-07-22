"""Temporary synchronous Lab facade over the production typed pipeline.

This adapter expires with D1/D1b. It owns no cognition algorithm and exists only
to let the current Lab wait for an asynchronous production turn.
"""

from __future__ import annotations

from datetime import datetime
from threading import Lock

from devtools.elfie_lab.schemas import StimulusBundle
from elfie import Elfie
from elfie.body import (
    BodyId,
    BodySensorEvent,
    EnvironmentSample,
    TactileImpact,
    UtteranceFinal,
)
from elfie.brain.output_types import ExecutionReceipt
from elfie.brain.runtime_port import (
    CorticalRuntimePort,
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
)
from elfie.brain.turn_outcome import TurnOutcome
from elfie.message_types import ActorRef, EventId


class RuntimeSelectionMissingError(RuntimeError):
    """The Lab attempted a turn before selecting its requested runtime."""


class SelectedLabRuntime:
    """Stable runtime port whose per-turn delegate is selected by the Lab."""

    def __init__(self) -> None:
        self._selected: CorticalRuntimePort | None = None
        self._lock = Lock()

    def select(self, runtime: CorticalRuntimePort) -> None:
        with self._lock:
            self._selected = runtime

    def capabilities(self) -> ModelGenerationCapabilities:
        return self._current().capabilities()

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        return self._current().generate(request)

    def abandon(self, request: ModelGenerationRequest) -> None:
        self._current().abandon(request)

    def _current(self) -> CorticalRuntimePort:
        with self._lock:
            selected = self._selected
        if selected is None:
            raise RuntimeSelectionMissingError("Lab runtime is not selected")
        return selected


class DeprecatedSyncCognitionAdapter:
    """Convert Lab stimuli once, then wait on the production lifecycle."""

    def __init__(self, elfie: Elfie) -> None:
        self._elfie = elfie
        self._runtime = SelectedLabRuntime()
        self._elfie.configure_cognition(self._runtime)
        self._elfie.start()

    def run(
        self,
        stimulus: StimulusBundle,
        event_id: str,
        runtime: CorticalRuntimePort,
    ) -> tuple[TurnOutcome, tuple[ExecutionReceipt, ...]]:
        self._runtime.select(runtime)
        previous_count = len(self._elfie.turn_outcomes())
        self._elfie.pump_body_events(self._events(stimulus, event_id))
        self._elfie.advance_clock(5.0)
        self._elfie.wait_for_outcome_count(previous_count + 1, timeout=5.0)
        outcome = self._elfie.turn_outcomes()[-1]
        self._elfie.wait_for_output(outcome.turn_id, timeout=5.0)
        return outcome, self._elfie.execution_receipts(outcome.turn_id)

    def close(self) -> None:
        self._elfie.stop()
        self._elfie.join()

    def _events(
        self,
        stimulus: StimulusBundle,
        event_id: str,
    ) -> tuple[BodySensorEvent, ...]:
        now = self._elfie.cognitive_datetime
        source = ActorRef(actor_id="elfie-lab", source_kind="developer_tool")
        body_id = BodyId(
            self._elfie.current_body.body_id
            if self._elfie.current_body is not None
            else "elfie-lab-body"
        )
        events: list[BodySensorEvent] = []
        message = stimulus.message.strip()
        if message:
            events.append(
                self._event(
                    EventId(event_id),
                    body_id,
                    source,
                    now,
                    UtteranceFinal(kind="utterance_final", text=message),
                )
            )
        events.append(
            self._event(
                EventId(f"{event_id}:environment"),
                body_id,
                source,
                now,
                EnvironmentSample(
                    kind="environment_sample",
                    temperature_celsius=stimulus.temperature,
                ),
            )
        )
        if stimulus.impact_force > 0 or stimulus.gentle_stroke > 0:
            events.append(
                self._event(
                    EventId(f"{event_id}:tactile"),
                    body_id,
                    source,
                    now,
                    TactileImpact(
                        kind="tactile_impact",
                        location=stimulus.impact_direction or "body",
                        force_newtons=max(stimulus.impact_force, stimulus.gentle_stroke),
                    ),
                )
            )
        return tuple(events)

    @staticmethod
    def _event(
        event_id: EventId,
        body_id: BodyId,
        source: ActorRef,
        now: datetime,
        payload: EnvironmentSample | TactileImpact | UtteranceFinal,
    ) -> BodySensorEvent:
        return BodySensorEvent(
            event_id=event_id,
            body_id=body_id,
            source=source,
            occurred_at=now,
            received_at=now,
            payload=payload,
        )


__all__ = ("DeprecatedSyncCognitionAdapter",)
