"""Elfie Lab 调试回合的显式状态注入。"""

from __future__ import annotations

from typing import Any, Dict

from elfie import Elfie
from elfie.diagnostics import ElfieDiagnostics


class StateInjectionError(ValueError):
    """Developer-provided state injection is invalid."""


def apply_state_injection(
    elfie: Elfie,
    injection: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply supported developer-only state overrides and return their diff."""
    if not injection:
        return {}
    allowed = {"energy", "fatigue", "is_sleeping", "emotions"}
    unknown = set(injection) - allowed
    if unknown:
        raise StateInjectionError(f"不支持的状态注入字段: {', '.join(sorted(unknown))}")

    changes: Dict[str, Any] = {}
    diagnostics = ElfieDiagnostics(elfie)
    energy = diagnostics.energy
    emotion = diagnostics.emotion
    energy_changed = False
    emotion_changed = False
    if "energy" in injection:
        value = _bounded_number(injection["energy"], "energy")
        changes["energy"] = {
            "before": energy.energy,
            "after": value,
        }
        energy.energy = value
        energy_changed = True
    if "fatigue" in injection:
        value = _bounded_number(injection["fatigue"], "fatigue")
        changes["fatigue"] = {
            "before": energy.fatigue,
            "after": value,
        }
        energy.fatigue = value
        energy_changed = True
    if "is_sleeping" in injection:
        value = bool(injection["is_sleeping"])
        changes["is_sleeping"] = {
            "before": energy.is_sleeping,
            "after": value,
        }
        energy.is_sleeping = value
        energy_changed = True
    if "emotions" in injection:
        emotions = injection["emotions"]
        if not isinstance(emotions, dict):
            raise StateInjectionError("emotions 必须是字典")
        changes["emotions"] = {}
        for name, raw_value in emotions.items():
            if name not in emotion.emotions:
                raise StateInjectionError(f"未知情绪: {name}")
            value = _bounded_number(raw_value, name)
            changes["emotions"][name] = {
                "before": emotion.emotions[name],
                "after": value,
            }
            emotion.emotions[name] = value
            emotion_changed = True
    if energy_changed:
        energy.revision += 1
    if emotion_changed:
        emotion.revision += 1
    return changes


def model_skip_reason(trace: Dict[str, Any]) -> str:
    """Infer the legacy Lab skip label from the recorded typed stages."""
    stages = trace.get("stages", {})
    if "brainstem_reflex" in stages and stages["brainstem_reflex"].get("event", {}).get(
        "triggered"
    ):
        return "brainstem_reflex"
    if "sleep_gate" in stages:
        return "sleep_gate"
    if not stages.get("sensory_filter", {}).get("passed", True):
        return "sensory_filter"
    return "attention_path_without_model"


def _bounded_number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StateInjectionError(f"{field_name} 必须是数字") from exc
    if not 0.0 <= number <= 100.0:
        raise StateInjectionError(f"{field_name} 必须在 0 到 100 之间")
    return number
