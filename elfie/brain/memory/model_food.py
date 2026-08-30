"""Memory algorithms consume one narrow, Food-aware model Port.

The normal Brain model boundary is structured around ``ModelGenerationRequest``
while the Memory algorithms deliberately depend on the much smaller
``ask_with_food`` capability.  ``ModelPortMemoryAdapter`` is the one bridge
between those contracts.  It keeps the selected primary Food/model in the
composition root and gives maintenance a bounded, internal generation
request; Memory never selects a provider or model itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Protocol, cast
from uuid import uuid4

from elfie.brain.reasoning.model_port import (
    JsonSchemaDocument,
    ModelGenerationRequest,
    ModelPort,
    ModelResponseMode,
)
from elfie.brain.workspace.contracts import (
    InternalScope,
    ResponseScope,
    SourceDomain,
)
from elfie.message_types import EventId, TurnId

from .memory_records import JsonValue

MEMORY_PROJECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "importance_event": {
                        "type": "string",
                        "enum": ["routine", "meaningful", "major", "core"],
                    },
                },
                "required": ["label"],
            },
        },
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "surface_text": {"type": "string"},
                    "label": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["surface_text"],
            },
        },
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject_ref": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object_ref": {"type": "string"},
                    "object_literal": {},
                    "polarity": {"type": "string"},
                    "epistemic_status": {"type": "string"},
                    "viewpoint": {"type": "string"},
                    "context": {"type": "string"},
                    "confidence": {"type": "number"},
                    "importance_event": {
                        "type": "string",
                        "enum": ["routine", "meaningful", "major", "core"],
                    },
                },
                "required": ["predicate"],
            },
        },
    },
    "required": ["nodes", "mentions", "assertions"],
}


class MemoryModelPort(Protocol):
    """Narrow semantic text-generation capability used by memory algorithms."""

    def ask_with_food(
        self,
        prompt: str,
        *,
        food_key: str | None,
        elfie_id: str | None,
        scene: str,
        semantic_role: str,
        energy: float,
        task_complexity: int,
        allowed_skills: list[str] | None,
    ) -> str: ...


class ModelPortMemoryAdapter:
    """Adapt Brain's primary model port for bounded Memory maintenance.

    This adapter intentionally has no model-selection logic.  The injected
    ``ModelPort`` already represents the selected primary Food/model; future
    night-only selection can be supplied by injecting a different ModelPort
    without changing Memory's contracts.
    """

    def __init__(
        self,
        model_port: ModelPort,
        *,
        elfie_id: str | None = None,
        clock=None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model_port = model_port
        self._elfie_id = elfie_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    def ask_with_food(
        self,
        prompt: str,
        *,
        food_key: str | None,
        elfie_id: str | None,
        scene: str,
        semantic_role: str,
        energy: float,
        task_complexity: int,
        allowed_skills: list[str] | None,
    ) -> str:
        del food_key, scene, energy, task_complexity, allowed_skills
        captured_at = self._clock()
        request_id = uuid4().hex
        request = ModelGenerationRequest(
            turn_id=TurnId(f"memory-{request_id}"),
            frame_id=EventId(f"memory-frame-{request_id}"),
            context_revision=0,
            capability_revision=0,
            created_at=captured_at,
            deadline=captured_at + timedelta(seconds=self._timeout_seconds),
            cause_event_ids=(EventId(f"memory-cause-{request_id}"),),
            source_domain=SourceDomain.INTERNAL,
            interaction_scope=InternalScope(
                cause_id=f"memory:{semantic_role or 'maintenance'}"
            ),
            response_scope=ResponseScope(external_domain=None),
            system_prompt=(
                "你是 Elfie 的记忆维护模型。只输出符合 MemoryProjection JSON Schema "
                "的对象；不要补写 Episode 原文没有的事实。"
            ),
            user_prompt=prompt,
            response_schema=JsonSchemaDocument(
                name="MemoryProjection",
                document=cast(Mapping[str, JsonValue], MEMORY_PROJECTION_SCHEMA),
            ),
            reasoning_mode="fast",
            response_mode=ModelResponseMode.DECISION_PLAN,
            allowed_tools=(),
            max_tokens=1024,
        )
        result = self._model_port.generate(request)
        return result.text


def ask_memory_model(
    model_port: MemoryModelPort,
    prompt: str,
    *,
    elfie_id: str | None,
    semantic_role: str,
    complexity: int,
) -> str:
    return model_port.ask_with_food(
        prompt=prompt,
        food_key=None,
        elfie_id=elfie_id,
        scene="memory",
        semantic_role=semantic_role,
        energy=50.0,
        task_complexity=complexity,
        allowed_skills=[],
    )


__all__ = (
    "MEMORY_PROJECTION_SCHEMA",
    "MemoryModelPort",
    "ModelPortMemoryAdapter",
    "ask_memory_model",
)
