import logging

logger = logging.getLogger("elfie.nervous_system.sensors.audio")


class AudioSensor:
    """神经交互总线：耳朵 (空间与虚拟听觉语音传感器)"""

    def __init__(self):
        self.last_heard_audio = ""
        self.last_audio_source = "ambient"

    def receive_virtual_audio(self, audio_event: str, source: str = "ambient") -> str:
        """
        接收来自虚拟房间/空间中的声音，或者从外部输入（比如主人的语音微信 ASR）得到的听觉输入
        :param audio_event: 听到的声音转化成文本或语音大纲 (如 "轰隆隆！窗外打雷了哒！" 或 "小精灵，过来吃饭啦！")
        :param source: 声音源 ("spatial_audio_broadcaster", "user_voice_message", "elfie_buddy")
        :return: 听觉文本
        """
        logger.info(
            f"👂 [神经听觉总线] 接收到听觉音频 (来源: {source}): '{audio_event}'"
        )
        self.last_heard_audio = audio_event.strip()
        self.last_audio_source = source
        return self.last_heard_audio

    def get_last_heard(self) -> str:
        return self.last_heard_audio

    def get_last_source(self) -> str:
        return self.last_audio_source
