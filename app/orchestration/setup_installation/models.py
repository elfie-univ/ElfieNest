"""Commands and results for Setup installation."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.setup import SetupPrincipal, StoredSetupInstallation


@dataclass(frozen=True)
class ConfirmSetupInstallationCommand:
    principal: SetupPrincipal
    confirmed: bool


@dataclass(frozen=True)
class CancelSetupInstallationCommand:
    principal: SetupPrincipal


@dataclass(frozen=True)
class ConfirmSetupInstallationResult:
    installation: StoredSetupInstallation
    session_token: str
    session_ttl_seconds: int


@dataclass(frozen=True)
class CancelSetupInstallationResult:
    installation: StoredSetupInstallation


__all__ = (
    "CancelSetupInstallationCommand",
    "CancelSetupInstallationResult",
    "ConfirmSetupInstallationCommand",
    "ConfirmSetupInstallationResult",
)
