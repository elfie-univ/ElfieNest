"""情绪表达映射引擎 - Expression Mapper"""

import logging
import os
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger("elfie.brain.emotion.expression_mapper")


class ExpressionMapper:
    """情绪表达映射器 - 单例模式缓存配置"""

    _instance: Optional["ExpressionMapper"] = None
    _config: Optional[Dict] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """加载YAML配置文件"""
        if self._config is not None:
            return

        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config",
            "emotion_expressions.yaml",
        )

        try:
            with open(config_path, encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
            logger.info(f"情绪表达映射配置已加载: {config_path}")
        except FileNotFoundError:
            logger.warning(f"配置文件未找到: {config_path}，使用默认配置")
            self._config = self._get_default_config()
        except yaml.YAMLError as e:
            logger.error(f"YAML解析错误: {e}，使用默认配置")
            self._config = self._get_default_config()

    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "emotions": {
                "happiness": {
                    "expression": "happy_face",
                    "actions": {
                        "low": ["wag_tail"],
                        "medium": ["wiggle_ears"],
                        "high": ["jump", "wag_tail"],
                    },
                    "voice_modifier": "cheerful",
                    "threshold": 30,
                },
                "sadness": {
                    "expression": "sad_face",
                    "actions": {
                        "low": ["droop_head"],
                        "medium": ["slow_movement"],
                        "high": ["droop_head", "slow_movement"],
                    },
                    "voice_modifier": "sorrowful",
                    "threshold": 40,
                },
                "anger": {
                    "expression": "angry_face",
                    "actions": {
                        "low": ["shake_head"],
                        "medium": ["stomp"],
                        "high": ["shake_head", "stomp"],
                    },
                    "voice_modifier": "firm",
                    "threshold": 40,
                },
                "fear": {
                    "expression": "fearful_face",
                    "actions": {
                        "low": ["tremble"],
                        "medium": ["hide"],
                        "high": ["tremble", "hide"],
                    },
                    "voice_modifier": "nervous",
                    "threshold": 35,
                },
                "surprise": {
                    "expression": "surprised_face",
                    "actions": {
                        "low": ["blink_eyes"],
                        "medium": ["jump"],
                        "high": ["jump", "blink_eyes"],
                    },
                    "voice_modifier": "excited",
                    "threshold": 30,
                },
                "disgust": {
                    "expression": "disgusted_face",
                    "actions": {
                        "low": ["shake_head"],
                        "medium": ["step_back"],
                        "high": ["shake_head", "step_back"],
                    },
                    "voice_modifier": "disgusted",
                    "threshold": 45,
                },
            },
            "default_expression": {
                "expression": "neutral_face",
                "actions": [],
                "voice_modifier": "neutral",
            },
        }

    def _get_intensity_level(self, value: float) -> str:
        """根据情绪值获取强度等级"""
        if value < 40:
            return "low"
        elif value < 70:
            return "medium"
        else:
            return "high"

    def get_expression_for_emotions(self, emotions: Dict[str, float]) -> dict:
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

        assert self._config is not None, "Config should be loaded in __new__"
        config: Dict[str, Any] = self._config
        emotion_configs: Dict[str, Any] = config.get("emotions", {})

        dominant_emotion = None
        dominant_value = 0.0
        dominant_intensity = "low"

        for emotion_name, emotion_value in emotions.items():
            if emotion_name not in emotion_configs:
                continue

            config = emotion_configs[emotion_name]
            threshold = config.get("threshold", 30)

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

    def _get_default_expression(self) -> dict:
        """获取默认表达"""
        assert self._config is not None, "Config should be loaded in __new__"
        default = self._config.get("default_expression", {})
        return {
            "expression": default.get("expression", "neutral_face"),
            "actions": default.get("actions", []),
            "voice_modifier": default.get("voice_modifier", "neutral"),
            "intensity": 0.0,
            "emotion": "neutral",
        }
