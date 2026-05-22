import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.interface.sensors.audio")

class AudioSensor:
    """底层：感官输入 - 耳朵 (听觉语音传感器)"""

    def __init__(self):
        self.last_heard_text = ""

    def hear_voice(self, speech_text: str) -> str:
        """
        接收到外界的语音输入 (经过 ASR 语音识别后转化为文本)
        :param speech_text: 语音听写出的文本内容
        :return: 经过归一化处理后的文本
        """
        logger.info(f"👂 [听觉感官捕获语音]: '{speech_text}'")
        self.last_heard_text = speech_text.strip()
        return self.last_heard_text

    def get_last_heard(self) -> str:
        return self.last_heard_text
