"""Bounded local HTTP probe adapter for Runtime readiness."""

from __future__ import annotations

import urllib.request

from app.orchestration.lifecycle.ports import HttpProbeResult


class UrllibHttpProbeAdapter:
    """Perform one bounded HTTP GET without mapping product health semantics."""

    def get(self, url: str, *, timeout_seconds: float) -> HttpProbeResult:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return HttpProbeResult(status=response.status, body=response.read())
