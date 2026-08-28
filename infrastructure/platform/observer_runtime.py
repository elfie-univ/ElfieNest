"""Operating-system clock and secure capability adapters for Observer sessions."""

from __future__ import annotations

import secrets
import time


class SystemObserverClock:
    def now(self) -> float:
        return time.monotonic()


class SecureObserverCapabilityIssuer:
    def issue(self) -> str:
        return f"observer_{secrets.token_urlsafe(32)}"


__all__ = ("SecureObserverCapabilityIssuer", "SystemObserverClock")
