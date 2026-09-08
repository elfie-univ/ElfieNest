"""Elfie Lab 回合输入与模型调用的摘要投影。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from devtools.elfie_lab.schemas import StimulusBundle
from elfie.brain.observation import BrainObservation

_MODEL_CALL_BOUNDARY = "reasoning.agent_loop"
_MODEL_CALL_KIND = "model_call"


def model_call_summary(call: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only model-call fields exposed by the Lab API."""
    allowed = {
        "food_key",
        "call_index",
        "provider",
        "model",
        "energy",
        "task_complexity",
        "duration_ms",
        "food_used",
        "execution_stage",
        "degraded",
        "skipped",
        "reason",
        "error",
    }
    return {key: value for key, value in call.items() if key in allowed}


def turn_model_call_observations(
    observations: Sequence[BrainObservation],
) -> List[BrainObservation]:
    """Return the captured ``model_call`` envelopes in emit order."""
    return [
        event
        for event in observations
        if event.boundary == _MODEL_CALL_BOUNDARY and event.kind == _MODEL_CALL_KIND
    ]


def model_call_summary_from_observations(
    observations: Sequence[BrainObservation],
    *,
    food_key: str,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the Lab model-call summary from the Brain's model_call envelopes.

    The Brain emits one ``model_call`` observation per ModelPort call (todo 6
    of the observation-surface plan), so the summary sources provider/model/
    duration from that single semantic record instead of a Lab-side capture.
    ``food_used``/``execution_stage``/``degraded`` stay deterministic
    food-key derivations exactly as the former generate-path capture recorded
    them. When no model call happened the legacy skipped summary is returned.
    """
    model_calls = turn_model_call_observations(observations)
    if not model_calls:
        return model_call_summary(
            {
                "food_key": food_key,
                "skipped": True,
                "reason": fallback_reason,
            }
        )
    event = model_calls[-1]
    payload = event.payload
    summary = model_call_summary(
        {
            "food_key": food_key,
            "call_index": len(model_calls),
            "provider": payload.provider,
            "model": payload.model_key,
            "duration_ms": (
                round(event.duration_ms, 2) if event.duration_ms is not None else None
            ),
            "food_used": food_key,
            "execution_stage": "mock" if food_key == "mock" else "primary",
            "degraded": False,
        }
    )
    if event.error is not None:
        summary["error"] = event.error.type
    return summary


def stimulus_modalities(stimulus: StimulusBundle) -> List[str]:
    """Project a stimulus bundle into the modalities shown in the trace."""
    modalities: List[str] = []
    if stimulus.source_domain == "communication":
        if stimulus.message.strip():
            modalities.append("text")
        if stimulus.message_attachments:
            modalities.append("attachment")
        return modalities
    if stimulus.message.strip():
        modalities.append("hearing")
    if stimulus.vision_media is not None:
        modalities.append("vision")
    modalities.append("environment")
    if stimulus.impact_force > 0 or stimulus.gentle_stroke > 0:
        modalities.append("touch")
    return modalities
