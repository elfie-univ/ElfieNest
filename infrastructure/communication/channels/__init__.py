"""具体消息通道。"""

from infrastructure.communication.channels.telegram import (
    TelegramChannel,
    TelegramConnector,
)
from infrastructure.communication.channels.wechat import WeChatChannel, WeChatConnector
from infrastructure.communication.discord.channel import (
    DiscordChannel,
    DiscordConnector,
)

__all__ = [
    "WeChatConnector",
    "WeChatChannel",
    "TelegramConnector",
    "TelegramChannel",
    "DiscordConnector",
    "DiscordChannel",
]
