"""Contracts for acquiring the target-specific Ollama binary sidecar."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

import pytest

from scripts import ollama_sidecar, package_python_core


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, chunk_size: int) -> tuple[bytes, ...]:
        assert chunk_size > 0
        return (self._content,)


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.urls: list[str] = []

    def stream(self, method: str, url: str) -> _FakeResponse:
        assert method == "GET"
        self.urls.append(url)
        return self.response


def _source(payload: bytes) -> package_python_core.OllamaSource:
    return package_python_core.OllamaSource(
        target="darwin-arm64",
        version="test",
        url="https://github.com/ollama/ollama/releases/download/vtest/ollama-darwin.tgz",
        filename="ollama-darwin.tgz",
        sha256=hashlib.sha256(payload).hexdigest(),
        license_notice="desktop/packaging/third_party/ollama/LICENSE",
    )


def test_download_sidecar_streams_the_pinned_asset_and_verifies_it(tmp_path: Path) -> None:
    # Given: a verified official source and an empty build cache.
    payload = b"ollama-release-bytes"
    source = _source(payload)
    client = _FakeClient(_FakeResponse(payload))
    destination = tmp_path / source.filename

    # When: release preparation obtains the sidecar.
    resolved = ollama_sidecar.download_sidecar(
        source=source,
        destination=destination,
        client=client,
    )

    # Then: only the verified target archive remains in the cache.
    assert resolved == destination
    assert destination.read_bytes() == payload
    assert client.urls == [source.url]
    assert not list(tmp_path.glob("*.part"))


def test_download_sidecar_removes_bytes_that_fail_the_pinned_checksum(tmp_path: Path) -> None:
    # Given: a response whose bytes differ from the checked-in provenance.
    source = _source(b"trusted")
    destination = tmp_path / source.filename

    # When/Then: acquisition fails and leaves no archive a packager could consume.
    with pytest.raises(ollama_sidecar.OllamaSidecarDownloadError, match="checksum"):
        ollama_sidecar.download_sidecar(
            source=source,
            destination=destination,
            client=_FakeClient(_FakeResponse(b"tampered")),
        )
    assert not destination.exists()
    assert not list(tmp_path.glob("*.part"))


def test_download_client_uses_the_locked_httpx_install_without_http2_extra() -> None:
    # Given/When: the release downloader creates its real client.
    with ollama_sidecar.create_download_client() as client:
        # Then: client construction itself does not require the optional h2 package.
        assert client is not None
