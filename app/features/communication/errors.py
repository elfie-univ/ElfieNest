"""Stable product errors for Communication use-cases."""


class CommunicationError(RuntimeError):
    """Base error exposed by the Communication facade."""


class ConversationNotFound(CommunicationError):
    """The principal cannot see the requested conversation."""


class MessageInvalid(CommunicationError):
    """A user-visible message violates the existing text contract."""


class CommunicationUnavailable(CommunicationError):
    """The authoritative conversation history cannot be accessed."""


__all__ = (
    "CommunicationError",
    "CommunicationUnavailable",
    "ConversationNotFound",
    "MessageInvalid",
)
