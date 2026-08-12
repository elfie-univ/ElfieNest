"""Stable workflow errors for message delivery."""


class MessageDeliveryError(RuntimeError):
    """Base workflow error."""


class MessageDeliveryUnavailable(MessageDeliveryError):
    """The Elfie or realtime delivery boundary is unavailable."""


class DuplicateMessage(MessageDeliveryError):
    """The Elfie boundary already admitted the same source message."""


class MessageRejected(MessageDeliveryError):
    """The Elfie boundary rejected the message without a retry path."""


__all__ = (
    "DuplicateMessage",
    "MessageDeliveryError",
    "MessageDeliveryUnavailable",
    "MessageRejected",
)
