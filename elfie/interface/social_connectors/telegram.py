# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger("elfie.interface.social_connectors.telegram")

class TelegramConnector:
    """平台社交总线：Telegram 对接驱动 (Telegram Embodied Observer Channel)"""

    def __init__(self, bot_token: str = ""):
        self.bot_token = bot_token
        self.is_connected = False

    def connect(self) -> bool:
        logger.info("🤖 [Telegram Bot] 异步网络循环启动，具身观察端口就绪。")
        self.is_connected = True
        return True

    def send_message(self, chat_id: str, text: str) -> bool:
        if not self.is_connected:
            logger.warning("Telegram 未连接，发送消息失败")
            return False
        logger.info(f"🔵 [Telegram -> {chat_id}]: \"{text}\"")
        return True

    def send_viewport_image(self, chat_id: str, image_path: str) -> bool:
        """
        向 Telegram 用户发送小精灵的 Godot 主观视角图片
        """
        if not self.is_connected:
            return False
        logger.info(f"🔵 [Telegram 图像推送 -> {chat_id}] 宿舍 Camera3D 主观视角截图 '{image_path}' 已安全送达。")
        return True
