"""图像情绪检测器 - 基于DeepFace

提供从图像中检测面部表情情绪的能力，支持懒加载和fallback机制。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageEmotionDetector:
    """图像情绪检测器 - 基于DeepFace

    使用DeepFace库进行面部表情识别，支持懒加载以避免启动时的性能开销。
    当DeepFace不可用或检测失败时，提供fallback机制返回默认情绪。

    Attributes:
        EMOTION_MAP: DeepFace情绪到系统情绪的映射字典
    """

    # DeepFace情绪映射到系统情绪
    EMOTION_MAP = {
        "happy": "happiness",
        "sad": "sadness",
        "angry": "anger",
        "fear": "fear",
        "surprise": "surprise",
        "disgust": "disgust",
        "neutral": "calm",
    }

    def __init__(self):
        """初始化图像情绪检测器

        模型不会在初始化时加载，而是在首次调用detect()时懒加载。
        """
        self._model_loaded = False

    def _load_model(self):
        """懒加载模型

        仅在首次需要时加载DeepFace模型。如果加载失败，会设置标志位，
        后续调用将直接使用fallback机制。
        """
        if self._model_loaded:
            return

        try:
            import deepface  # noqa: F401

            self._model_loaded = True
            logger.info("图像情绪检测模型加载成功")
        except ImportError as e:
            logger.warning(f"DeepFace未安装，使用fallback模式: {e}")
            self._model_loaded = False
        except Exception as e:
            logger.warning(f"DeepFace加载失败: {e}")
            self._model_loaded = False

    def detect(self, image_path: str | Path) -> tuple[str, float]:
        """检测图像中的面部表情情绪

        Args:
            image_path: 图像文件路径，支持str或Path对象

        Returns:
            Tuple[str, float]: (emotion, intensity) 元组
                - emotion: 情绪名称 (如 'happiness', 'sadness' 等)
                - intensity: 情绪强度，范围 0.0-1.0

        Example:
            >>> detector = ImageEmotionDetector()
            >>> emotion, intensity = detector.detect('photo.jpg')
            >>> print(f"检测到情绪: {emotion}, 强度: {intensity}")
        """
        self._load_model()

        if not self._model_loaded:
            return self._fallback_detect()

        try:
            from deepface import DeepFace

            result = DeepFace.analyze(
                img_path=str(image_path),
                actions=["emotion"],
                enforce_detection=False,  # 允许检测不到人脸
            )

            # DeepFace可能返回列表或字典
            if isinstance(result, list):
                result = result[0]

            emotions = result["emotion"]
            dominant = result["dominant_emotion"]

            # 映射到系统情绪
            emotion = self.EMOTION_MAP.get(dominant, "calm")
            intensity = emotions[dominant] / 100.0  # DeepFace返回0-100，转换为0-1

            logger.debug(f"图像检测成功: {emotion} ({intensity:.2f})")
            return emotion, intensity

        except Exception as e:
            logger.warning(f"图像检测失败: {e}")
            return self._fallback_detect()

    def _fallback_detect(self) -> tuple[str, float]:
        """Fallback检测 - 返回默认情绪

        当DeepFace不可用或检测失败时，返回默认的平静情绪。
        未来可扩展为基于随机或上下文的智能fallback。

        Returns:
            Tuple[str, float]: ('calm', 0.5) 默认情绪和中等强度
        """
        return "calm", 0.5
