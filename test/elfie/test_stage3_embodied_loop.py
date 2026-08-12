"""Stage-three acceptance tests for the virtual embodied turn loop."""

from __future__ import annotations

import json
from datetime import datetime

from elfie import ElfieFactory
from elfie.body import BodyId, BodySensorEvent, HeadlessBody, UtteranceFinal
from elfie.brain.runtime_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.factory import ElfieAssembly
from elfie.message_types import ActorRef
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


class EmbodiedMotionRuntime:
    """Deterministic model port that turns one physical observation into motion."""

    def __init__(self) -> None:
        self.requests: list[ModelGenerationRequest] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="stage3-test",
            model_key="stage3/embodied",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        plan = {
            "schema_version": 1,
            "plan_id": f"plan-{request.turn_id}",
            "turn_id": str(request.turn_id),
            "frame_id": str(request.frame_id),
            "context_revision": request.context_revision,
            "capability_revision": request.capability_revision,
            "created_at": request.created_at.isoformat(),
            "deadline": request.deadline.isoformat(),
            "cause_event_ids": list(request.cause_event_ids),
            "intents": [
                {
                    "type": "motion",
                    "intent_id": f"motion-{request.turn_id}",
                    "cause_event_ids": list(request.cause_event_ids),
                    "dependency_ids": [],
                    "deadline": request.deadline.isoformat(),
                    "cancel_policy": "if_not_started",
                    "motion": "walk",
                    "target": "room-center",
                }
            ],
        }
        return ModelGenerationResult(
            text=json.dumps(plan),
            selected_mode=StructuredOutputMode.JSON_SCHEMA,
            provider="stage3-test",
            model_key="stage3/embodied",
        )


def _new_elfie(body: HeadlessBody, runtime: EmbodiedMotionRuntime):
    return ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id="stage3-elfie",
                display_name="阶段三精灵",
                species_id="fox",
                seed=3,
            ),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=body,
            model_port=runtime,
        )
    )


def test_physical_observation_drives_current_virtual_body_and_returns_receipt() -> None:
    body = HeadlessBody(body_id="stage3-body")
    runtime = EmbodiedMotionRuntime()
    elfie = _new_elfie(body, runtime)
    elfie.start()
    now = elfie.cognitive_datetime
    event = BodySensorEvent(
        event_id="stage3-room-speech",
        body_id=BodyId(body.body_id),
        source=ActorRef(actor_id="room-neighbor", source_kind="room"),
        occurred_at=now,
        received_at=now,
        payload=UtteranceFinal(kind="utterance_final", text="come to the center"),
    )

    elfie.pump_body_events((event,))
    # A room utterance follows the normal quiet/oldest-event trigger policy.
    elfie.advance_clock(5.0)
    elfie.wait_for_outcome_count(1, timeout=1.0)
    outcome = elfie.turn_outcomes()[0]
    elfie.wait_for_output(outcome.turn_id, timeout=1.0)

    decision = elfie.turn_decision(outcome.turn_id)
    assert decision is not None
    assert decision.source_domain.value == "embodied"
    assert decision.interaction_scope.body_id == body.body_id
    assert decision.interaction_scope.body_generation == elfie.current_body_generation
    assert runtime.requests[0].interaction_scope.body_generation == 1
    assert runtime.requests[0].response_scope.body_generation == 1
    receipts = elfie.execution_receipts(outcome.turn_id)
    assert receipts[-1].status.value == "completed"
    assert body.snapshot_body(now=elfie.cognitive_datetime).last_status is not None

    elfie.stop()
    elfie.join()
