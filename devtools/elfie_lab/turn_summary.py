"""Elfie Lab 回合输入与模型调用的摘要投影。"""

from __future__ import annotations

from typing import Any, Dict, List

from devtools.elfie_lab.schemas import StimulusBundle


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
