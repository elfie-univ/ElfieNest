"""文本情绪检测器 - 基于RoBERTa（中文）"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class TextEmotionDetector:
    """文本情绪检测器 - 基于RoBERTa（中文）"""
    
    # 情绪映射：模型输出 -> 我们的8种情绪
    EMOTION_MAP = {
        'positive': 'happiness',
        'negative': 'sadness',  # 需要进一步细化
        'neutral': 'calm',
    }
    
    # 关键词映射（fallback）
    KEYWORD_INTENSITY = {
        '高兴': ('happiness', 0.8),
        '开心': ('happiness', 0.7),
        '难过': ('sadness', 0.7),
        '伤心': ('sadness', 0.8),
        '生气': ('anger', 0.8),
        '愤怒': ('anger', 0.9),
        '害怕': ('fear', 0.8),
        '恐惧': ('fear', 0.9),
        '惊讶': ('surprise', 0.7),
        '恶心': ('disgust', 0.8),
        '无聊': ('boredom', 0.6),
        '依恋': ('attachment', 0.7),
    }
    
    def __init__(self):
        self._model = None
        self._pipeline = None
    
    def _load_model(self):
        """懒加载模型"""
        if self._pipeline is not None:
            return
        
        try:
            from transformers import pipeline
            self._pipeline = pipeline(
                "sentiment-analysis",
                model="IDEA-CCNL/Erlangshen-RoBERTa-110M-Sentiment",
                device=-1  # CPU
            )
            logger.info("文本情绪检测模型加载成功")
        except Exception as e:
            logger.warning(f"模型加载失败，将使用关键词检测: {e}")
            self._pipeline = None
    
    def detect(self, text: str) -> Tuple[str, float]:
        """
        检测文本情绪
        
        Args:
            text: 输入文本
            
        Returns:
            (emotion, intensity) 元组
        """
        # 尝试使用模型
        if self._pipeline is None:
            self._load_model()
        
        if self._pipeline is not None:
            try:
                result = self._pipeline(text)[0]
                label = result['label'].lower()
                score = result['score']
                
                # 映射到我们的情绪
                emotion = self.EMOTION_MAP.get(label, 'calm')
                
                # 进一步细化负面情绪
                if emotion == 'sadness':
                    emotion = self._refine_negative(text)
                
                return emotion, score
            except Exception as e:
                logger.warning(f"模型检测失败: {e}")
        
        # Fallback到关键词检测
        return self._keyword_detect(text)
    
    def _refine_negative(self, text: str) -> str:
        """细化负面情绪类型"""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ['生气', '愤怒', '气死', '火大']):
            return 'anger'
        elif any(kw in text_lower for kw in ['害怕', '恐惧', '吓', '危险']):
            return 'fear'
        elif any(kw in text_lower for kw in ['厌恶', '恶心', '讨厌']):
            return 'disgust'
        return 'sadness'
    
    def _keyword_detect(self, text: str) -> Tuple[str, float]:
        """关键词检测（fallback）"""
        text_lower = text.lower()
        
        for keyword, (emotion, intensity) in self.KEYWORD_INTENSITY.items():
            if keyword in text_lower:
                return emotion, intensity
        
        # 默认返回calm
        return 'calm', 0.3
