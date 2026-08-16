"""Compatibility import for the production Telegram channel package."""

from elfie.communication.contracts import CommunicationEnvelope
from infrastructure.communication.telegram.channel import (
    TelegramChannel,
    TelegramConnector,
)

__all__ = ("CommunicationEnvelope", "TelegramChannel", "TelegramConnector")
