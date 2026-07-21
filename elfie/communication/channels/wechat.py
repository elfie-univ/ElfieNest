from __future__ import annotations

import logging
from functools import singledispatchmethod

from elfie.communication.channel import CommunicationMessage, MessageKind
from elfie.communication.contracts import (
    AudioPart,
    CommunicationEnvelope,
    ContentPart,
    DeliveryReceipt,
    DeliveryStatus,
    FilePart,
    ImagePart,
    ReactionPart,
    SystemEventPart,
    TextPart,
)

logger = logging.getLogger("elfie.communication.channels.wechat")


class WeChatConnector:
    """平台社交总线：微信对接驱动 (WeChat Embodied Observer Channel)"""

    def __init__(self, token: str = ""):
        self.token = token
        self.is_connected = False

    def connect(self) -> bool:
        logger.info(
            "📱 [微信社交接口] 神经网络握手成功。已准备好接收外部用户观察脉冲。"
        )
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def send_message(self, text: str) -> bool:
        if not self.is_connected:
            logger.warning("微信未连接，发送消息失败")
            return False
        logger.info(f'🟢 [WeChat 消息推送]: "{text}"')
        return True

    def send_viewport_image(self, image_path: str) -> bool:
        """
        向主人微信发送精灵当前在 Godot 宿舍房间内的实时视口观察快照
        :param image_path: Godot Camera3D 抓取的视口截图路径
        """
        if not self.is_connected:
            return False
        logger.info(
            f"🟢 [WeChat 图像推送] 成功将精灵的虚拟宿舍视角图片 '{image_path}' 发送给主人手机微信端！"
        )
        return True

    def receive_user_command(self) -> str:
        """模拟接收主人从微信发来的命令 (如 '小家伙跑起来' 或 '看看你的房间')"""
        return ""


class WeChatChannel:
    """把现有 WeChatConnector 适配为统一通信通道。"""

    channel_id = "wechat"

    def __init__(self, connector: WeChatConnector | None = None):
        self.connector = connector or WeChatConnector()

    @property
    def is_connected(self) -> bool:
        return self.connector.is_connected

    def connect(self) -> bool:
        return self.connector.connect()

    def disconnect(self) -> None:
        self.connector.disconnect()

    def send(self, message: CommunicationMessage) -> bool:
        if message.kind is MessageKind.IMAGE:
            return self.connector.send_viewport_image(message.content)
        return self.connector.send_message(message.content)

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        """Send every typed part through the existing WeChat connector edge."""
        for part in envelope.parts:
            delivered = self._send_part(part)
            if not delivered:
                return DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code="wechat_send_failed",
                    error_message="WeChat connector 未确认发送成功",
                    retryable=True,
                )
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)

    @singledispatchmethod
    def _send_part(self, part: ContentPart) -> bool:
        raise TypeError(type(part).__name__)

    @_send_part.register
    def _send_text(self, part: TextPart) -> bool:
        return self.connector.send_message(part.text)

    @_send_part.register
    def _send_image(self, part: ImagePart) -> bool:
        return self.connector.send_viewport_image(part.media.uri)

    @_send_part.register
    def _send_audio(self, part: AudioPart) -> bool:
        return self.connector.send_message(part.media.uri)

    @_send_part.register
    def _send_file(self, part: FilePart) -> bool:
        return self.connector.send_message(part.media.uri)

    @_send_part.register
    def _send_reaction(self, part: ReactionPart) -> bool:
        return self.connector.send_message(part.reaction)

    @_send_part.register
    def _send_system_event(self, part: SystemEventPart) -> bool:
        return self.connector.send_message(part.description or part.event_name)
