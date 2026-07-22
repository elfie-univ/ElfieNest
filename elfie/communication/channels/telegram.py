from __future__ import annotations

import logging
from functools import singledispatchmethod

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

logger = logging.getLogger("elfie.communication.channels.telegram")


class TelegramConnector:
    """平台社交总线：Telegram 对接驱动 (Telegram Embodied Observer Channel)"""

    def __init__(self, bot_token: str = ""):
        self.bot_token = bot_token
        self.is_connected = False

    def connect(self) -> bool:
        logger.info("🤖 [Telegram Bot] 异步网络循环启动，具身观察端口就绪。")
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def send_message(self, chat_id: str, text: str) -> bool:
        if not self.is_connected:
            logger.warning("Telegram 未连接，发送消息失败")
            return False
        logger.info(f'🔵 [Telegram -> {chat_id}]: "{text}"')
        return True

    def send_viewport_image(self, chat_id: str, image_path: str) -> bool:
        """
        向 Telegram 用户发送小精灵的 Godot 主观视角图片
        """
        if not self.is_connected:
            return False
        logger.info(
            f"🔵 [Telegram 图像推送 -> {chat_id}] 宿舍 Camera3D 主观视角截图 '{image_path}' 已安全送达。"
        )
        return True


class TelegramChannel:
    """把现有 TelegramConnector 适配为统一通信通道。"""

    channel_id = "telegram"

    def __init__(self, connector: TelegramConnector | None = None):
        self.connector = connector or TelegramConnector()

    @property
    def is_connected(self) -> bool:
        return self.connector.is_connected

    def connect(self) -> bool:
        return self.connector.connect()

    def disconnect(self) -> None:
        self.connector.disconnect()

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        """Send every typed part through the existing Telegram connector edge."""
        recipient_id = str(envelope.recipients[0].actor_id)
        for part in envelope.parts:
            delivered = self._send_part(part, recipient_id)
            if not delivered:
                return DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code="telegram_send_failed",
                    error_message="Telegram connector 未确认发送成功",
                    retryable=True,
                )
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)

    @singledispatchmethod
    def _send_part(self, part: ContentPart, recipient_id: str) -> bool:
        raise TypeError(type(part).__name__)

    @_send_part.register
    def _send_text(self, part: TextPart, recipient_id: str) -> bool:
        return self.connector.send_message(recipient_id, part.text)

    @_send_part.register
    def _send_image(self, part: ImagePart, recipient_id: str) -> bool:
        return self.connector.send_viewport_image(recipient_id, part.media.uri)

    @_send_part.register
    def _send_audio(self, part: AudioPart, recipient_id: str) -> bool:
        return self.connector.send_message(recipient_id, part.media.uri)

    @_send_part.register
    def _send_file(self, part: FilePart, recipient_id: str) -> bool:
        return self.connector.send_message(recipient_id, part.media.uri)

    @_send_part.register
    def _send_reaction(self, part: ReactionPart, recipient_id: str) -> bool:
        return self.connector.send_message(recipient_id, part.reaction)

    @_send_part.register
    def _send_system_event(
        self,
        part: SystemEventPart,
        recipient_id: str,
    ) -> bool:
        return self.connector.send_message(
            recipient_id,
            part.description or part.event_name,
        )
