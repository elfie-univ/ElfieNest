import logging

logger = logging.getLogger("elfie.nervous_system.actuators.speech")


class SpeechActuator:
    """把精灵的说话意图转换为可广播的发言文本。"""

    def __init__(self):
        pass

    def speak(self, text: str) -> str:
        """校验并返回要交给身体或消息渠道广播的发言文本。"""
        if not text:
            return ""
        logger.info("精灵发言: %s", text)
        return text
