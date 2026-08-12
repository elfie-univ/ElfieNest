"""Outbound storage boundary owned by the Elfie profile domain."""

from __future__ import annotations

from typing import Protocol

from .models import ElfieProfile


class ProfileStorePort(Protocol):
    """Load and save one already validated Elfie profile."""

    def exists(self) -> bool: ...

    def load(self) -> ElfieProfile: ...

    def save(self, profile: ElfieProfile) -> None: ...


__all__ = ["ProfileStorePort"]
