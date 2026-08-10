"""Stable business errors for global product settings."""

from __future__ import annotations

from dataclasses import dataclass


class SettingsError(Exception):
    """Base class for expected Settings failures."""


@dataclass(frozen=True)
class SettingsForbidden(SettingsError):
    """The authenticated principal cannot administer global settings."""

    def __str__(self) -> str:
        return "只有家庭管理员可以管理全局设置"


@dataclass(frozen=True)
class SettingsValidationError(SettingsError):
    """A typed Settings command violates an existing product constraint."""

    field: str
    detail: str

    def __str__(self) -> str:
        return f"{self.field}: {self.detail}"


@dataclass(frozen=True)
class SettingsStorageError(SettingsError):
    """The authoritative Runtime settings document is unavailable."""

    detail: str

    def __str__(self) -> str:
        return self.detail


__all__ = (
    "SettingsError",
    "SettingsForbidden",
    "SettingsStorageError",
    "SettingsValidationError",
)
