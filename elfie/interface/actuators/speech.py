import logging

logger = logging.getLogger("elfie.interface.actuators.speech")

class SpeechActuator:
    """底层：行动输出 - 嘴巴 (TTS语音与文字交互通道)"""

    def __init__(self):
        pass

    def speak(self, text: str) -> str:
        """
        通过说话渠道输出文字 (模拟硬件 TTS 发生或向聊天软件推送)
        :param text: 准备说的话
        :return: 播报的最终文字内容
        """
        if not text:
            return ""
            
        logger.info(f"🗣️ [TTS 播报语音输出]: \"{text}\"")
        # 如果在真实硬件中，这里会调用边缘 TTS 引擎输出音频流
        return text
