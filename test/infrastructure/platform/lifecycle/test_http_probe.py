"""Focused test for bounded HTTP readiness transport."""

from infrastructure.platform.lifecycle import http_probe


class _Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return b"ready"


def test_http_probe_returns_only_transport_facts(monkeypatch) -> None:
    calls = []

    def urlopen(url: str, *, timeout: float):
        calls.append((url, timeout))
        return _Response()

    monkeypatch.setattr(http_probe.urllib.request, "urlopen", urlopen)

    result = http_probe.UrllibHttpProbeAdapter().get(
        "http://127.0.0.1:8000/api/health", timeout_seconds=2.0
    )

    assert result.status == 204
    assert result.body == b"ready"
    assert calls == [("http://127.0.0.1:8000/api/health", 2.0)]
