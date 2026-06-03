"""情绪检测器模块 - 统一接口

提供文本、图像、语音情绪的统一检测接口。
"""

from pathlib import Path
from typing import Any, Dict, Union

from elfie.brain.emotion.detector.audio_detector import AudioEmotionDetector
from elfie.brain.emotion.detector.image_detector import ImageEmotionDetector
from elfie.brain.emotion.detector.text_detector import TextEmotionDetector
from elfie.brain.emotion.emotion_input import EmotionInput


class EmotionDetector:
    """统一情绪检测器

    根据输入类型自动选择对应的检测器。
    """

    def __init__(self):
        self._text_detector = None
        self._image_detector = None
        self._audio_detector = None

    def _get_text_detector(self):
        if self._text_detector is None:
            self._text_detector = TextEmotionDetector()
        return self._text_detector

    def _get_image_detector(self):
        if self._image_detector is None:
            self._image_detector = ImageEmotionDetector()
        return self._image_detector

    def _get_audio_detector(self):
        if self._audio_detector is None:
            self._audio_detector = AudioEmotionDetector()
        return self._audio_detector

    def detect(self, input_data: dict[str, Any]) -> EmotionInput:
        """
        检测情绪

        Args:
            input_data: 输入数据字典，格式：
                - 文本: {'type': 'text', 'content': '...', 'event_id': '...'}
                - 图像: {'type': 'image', 'path': '...', 'event_id': '...'}
                - 语音: {'type': 'audio', 'path': '...', 'event_id': '...'}

        Returns:
            EmotionInput 对象
        """
        input_type = input_data.get("type", "text")
        event_id = input_data.get("event_id", "unknown")

        if input_type == "text":
            content = input_data.get("content", "")
            emotion, intensity = self._get_text_detector().detect(content)
            return EmotionInput(
                emotion=emotion, intensity=intensity, source="text", event_id=event_id
            )

        elif input_type == "image":
            path = input_data.get("path", "")
            emotion, intensity = self._get_image_detector().detect(path)
            return EmotionInput(
                emotion=emotion, intensity=intensity, source="image", event_id=event_id
            )

        elif input_type == "audio":
            path = input_data.get("path", "")
            emotion, intensity = self._get_audio_detector().detect(path)
            return EmotionInput(
                emotion=emotion, intensity=intensity, source="audio", event_id=event_id
            )

        else:
            # 未知类型，返回默认
            return EmotionInput(
                emotion="calm", intensity=0.3, source="unknown", event_id=event_id
            )


# 导出所有检测器
__all__ = [
    "EmotionDetector",
    "TextEmotionDetector",
    "ImageEmotionDetector",
    "AudioEmotionDetector",
]
