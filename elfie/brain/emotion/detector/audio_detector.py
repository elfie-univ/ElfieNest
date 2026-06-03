import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioEmotionDetector:
    """语音情绪检测器 - 基于音频特征分析"""

    def __init__(self):
        self._libsora_available = False
        self._pyworld_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """检查依赖库"""
        try:
            import librosa

            self._libsora_available = True
        except ImportError:
            logger.warning("librosa未安装，语音检测将使用fallback")

        try:
            import pyworld

            self._pyworld_available = True
        except ImportError:
            logger.warning("pyworld未安装，语音检测将使用fallback")

    def detect(self, audio_path: str | Path) -> tuple[str, float]:
        """
        检测语音情绪

        Args:
            audio_path: 音频文件路径

        Returns:
            (emotion, intensity) 元组
        """
        if not (self._libsora_available and self._pyworld_available):
            return self._fallback_detect()

        try:
            import librosa

            # 加载音频
            y, sr = librosa.load(str(audio_path), duration=5.0)

            # 提取特征
            features = self._extract_features(y, sr)

            # 规则判断
            return self._classify(features)

        except Exception as e:
            logger.warning(f"语音检测失败: {e}")
            return self._fallback_detect()

    def _extract_features(self, y, sr) -> dict:
        """提取音频特征"""
        import librosa
        import numpy as np

        # 能量 (响度)
        energy = np.mean(librosa.feature.rms(y=y))

        # 基频 (音高)
        f0 = librosa.yin(y, fmin=50, fmax=500)
        f0_mean = np.mean(f0[f0 > 0]) if any(f0 > 0) else 0
        f0_std = np.std(f0[f0 > 0]) if any(f0 > 0) else 0

        # 语速 (通过onset检测)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0]

        return {
            "energy": energy,
            "f0_mean": f0_mean,
            "f0_std": f0_std,
            "tempo": tempo,
        }

    def _classify(self, features: dict) -> tuple[str, float]:
        """根据特征判断情绪"""
        energy = features["energy"]
        f0_std = features["f0_std"]
        tempo = features["tempo"]

        # 高能量 + 高音高变化 + 快速 → 愤怒
        if energy > 0.1 and f0_std > 50 and tempo > 120:
            return "anger", 0.7

        # 低能量 + 低音高 → 悲伤
        elif energy < 0.03 and f0_std < 30:
            return "sadness", 0.6

        # 高能量 + 快速 → 兴奋/快乐
        elif energy > 0.08 and tempo > 100:
            return "happiness", 0.6

        # 正常
        else:
            return "calm", 0.5

    def _fallback_detect(self) -> tuple[str, float]:
        """Fallback"""
        return "calm", 0.3
