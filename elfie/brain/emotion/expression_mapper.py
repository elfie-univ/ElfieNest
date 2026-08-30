"""情绪表达映射引擎 - Expression Mapper"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List, TypedDict

ExpressionConfig = Dict[str, Any]


class EmotionExpression(TypedDict):
    """Legacy expression payload consumed by Body compatibility code."""

    expression: str
    actions: List[str]
    voice_modifier: str
    intensity: float
    emotion: str


class ExpressionMapper:
    """情绪表达映射器。

    Production Bootstrap passes the validated bundled document.  The small
    in-code mapping is retained only for direct domain/unit construction where
    no composition root is present; it is not a second packaged resource.
    """

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self._config: Dict[str, Any] = (
            dict(config) if config is not None else self._get_default_config()
        )

    def _get_default_config(self) -> ExpressionConfig:
        """Return the neutral safety fallback for direct domain construction."""
        return {
            "emotions": {},
            "default_expression": {
                "expression": "neutral_face",
                "actions": [],
                "voice_modifier": "neutral",
            },
        }

    def _get_intensity_level(self, value: float) -> str:
        """根据情绪值获取强度等级"""
        if value < 0.4:
            return "low"
        elif value < 0.7:
            return "medium"
        else:
            return "high"

    def get_expression_for_emotions(
        self,
        emotions: Dict[str, float],
    ) -> EmotionExpression:
        """根据情绪字典获取表达参数

        Args:
            emotions: 情绪名称到数值的字典

        Returns:
            dict: {
                "expression": str,
                "actions": list,
                "voice_modifier": str,
                "intensity": float,
                "emotion": str
            }
        """
        if not emotions:
            return self._get_default_expression()

        config: Dict[str, Any] = self._config
        emotion_configs: Dict[str, Any] = config.get("emotions", {})

        dominant_emotion = None
        dominant_value = 0.0
        dominant_intensity = "low"

        for emotion_name, emotion_value in emotions.items():
            if emotion_name not in emotion_configs:
                continue

            config = emotion_configs[emotion_name]
            threshold = config.get("threshold", 0.2)

            if emotion_value >= threshold and emotion_value > dominant_value:
                dominant_emotion = emotion_name
                dominant_value = emotion_value
                dominant_intensity = self._get_intensity_level(emotion_value)

        if dominant_emotion is None:
            return self._get_default_expression()

        config = emotion_configs[dominant_emotion]
        actions = config.get("actions", {})
        intensity_actions = actions.get(dominant_intensity, [])

        return {
            "expression": config.get("expression", "neutral_face"),
            "actions": intensity_actions,
            "voice_modifier": config.get("voice_modifier", "neutral"),
            "intensity": dominant_value,
            "emotion": dominant_emotion,
        }

    def _get_default_expression(self) -> EmotionExpression:
        """获取默认表达"""
        default = self._config.get("default_expression", {})
        return {
            "expression": default.get("expression", "neutral_face"),
            "actions": default.get("actions", []),
            "voice_modifier": default.get("voice_modifier", "neutral"),
            "intensity": 0.0,
            "emotion": "neutral",
        }
