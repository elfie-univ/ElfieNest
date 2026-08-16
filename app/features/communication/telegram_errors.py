"""Stable product errors for owner-managed Telegram accounts."""


class TelegramAccountError(RuntimeError):
    """Base product error for external Telegram account use-cases."""


class TelegramAccountNotFound(TelegramAccountError):
    """The Elfie is absent or is not owned by the current principal."""


class TelegramAccountInvalid(TelegramAccountError):
    """A token or pairing request is not valid."""


class TelegramAccountConflict(TelegramAccountError):
    """The requested account conflicts with an existing platform fact."""


class TelegramAccountUnavailable(TelegramAccountError):
    """Persistence, secret storage, or Telegram inspection is unavailable."""


__all__ = (
    "TelegramAccountConflict",
    "TelegramAccountError",
    "TelegramAccountInvalid",
    "TelegramAccountNotFound",
    "TelegramAccountUnavailable",
)
