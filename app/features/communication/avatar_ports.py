"""Consumer-owned boundaries for reading the current Elfie portrait."""

from __future__ import annotations

from typing import Protocol


class ElfiePortraitPort(Protocol):
    """Read the private headshot used as an external bot profile image."""

    def load_portrait(
        self, elfie_id: str, *, kind: str = "headshot"
    ) -> bytes | None: ...


__all__ = ("ElfiePortraitPort",)
