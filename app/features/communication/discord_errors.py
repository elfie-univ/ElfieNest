"""Stable product errors for owner-managed Discord accounts."""


class DiscordAccountError(RuntimeError):
    """Base product error for external Discord account use-cases."""


class DiscordAccountNotFound(DiscordAccountError):
    """The Elfie is absent or is not owned by the current principal."""


class DiscordAccountInvalid(DiscordAccountError):
    """A token or pairing request is not valid."""


class DiscordAccountConflict(DiscordAccountError):
    """The requested account conflicts with an existing platform fact."""


class DiscordAccountUnavailable(DiscordAccountError):
    """Persistence, secret storage, or Discord inspection is unavailable."""


__all__ = (
    "DiscordAccountConflict",
    "DiscordAccountError",
    "DiscordAccountInvalid",
    "DiscordAccountNotFound",
    "DiscordAccountUnavailable",
)
