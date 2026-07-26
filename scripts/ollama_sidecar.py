"""Acquire one pinned, target-specific Ollama archive for a release build."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Optional, Protocol

import httpx

from scripts import package_python_core

DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class SidecarResponse(Protocol):
    """The small streaming response surface needed by the release downloader."""

    def raise_for_status(self) -> None:
        """Raise when the remote server did not supply a successful response."""

    def iter_bytes(self, chunk_size: int = DOWNLOAD_CHUNK_SIZE) -> object:
        """Yield downloaded binary chunks."""


class SidecarHttpClient(Protocol):
    """A synchronous HTTP client capable of opening one streamed response."""

    def stream(
        self, method: str, url: str
    ) -> AbstractContextManager[SidecarResponse]:
        """Open one streamed HTTP response."""


class OllamaSidecarDownloadError(RuntimeError):
    """Raised when a pinned sidecar cannot be safely cached for packaging."""


def create_download_client() -> httpx.Client:
    """Create the bounded, redirect-following client used only for release assets."""
    transport = httpx.HTTPTransport(retries=3)
    timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)
    limits = httpx.Limits(
        max_connections=4,
        max_keepalive_connections=2,
        keepalive_expiry=30.0,
    )
    return httpx.Client(
        transport=transport,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
        http2=False,
    )


def download_sidecar(
    source: package_python_core.OllamaSource,
    destination: Path,
    client: Optional[SidecarHttpClient] = None,
) -> Path:
    """Download, checksum-verify, and atomically cache one pinned sidecar archive."""
    if client is not None:
        return _download_sidecar(source, destination, client)
    with create_download_client() as owned_client:
        return _download_sidecar(source, destination, owned_client)


def _download_sidecar(
    source: package_python_core.OllamaSource,
    destination: Path,
    client: SidecarHttpClient,
) -> Path:
    """Use one caller-owned HTTP client to obtain a verified binary cache entry."""
    if destination.name != source.filename:
        raise OllamaSidecarDownloadError(
            "ollama-sidecar-destination-filename-mismatch "
            f"expected={source.filename} actual={destination.name}"
        )
    if destination.is_file():
        try:
            package_python_core.verify_ollama_source(destination, source)
        except package_python_core.OllamaSourceError:
            destination.unlink()
        else:
            return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.part")
    _remove_if_file(partial)
    try:
        with client.stream("GET", source.url) as response:
            response.raise_for_status()
            with partial.open("wb") as output:
                for chunk in response.iter_bytes(DOWNLOAD_CHUNK_SIZE):
                    output.write(chunk)
        partial.replace(destination)
        package_python_core.verify_ollama_source(destination, source)
    except package_python_core.OllamaSourceChecksumError as error:
        _remove_if_file(partial)
        _remove_if_file(destination)
        raise OllamaSidecarDownloadError(
            f"ollama-sidecar-checksum-failed target={source.target}"
        ) from error
    except (httpx.HTTPError, OSError, package_python_core.OllamaSourceError) as error:
        _remove_if_file(partial)
        _remove_if_file(destination)
        raise OllamaSidecarDownloadError(
            f"ollama-sidecar-download-or-verify-failed target={source.target}"
        ) from error
    return destination


def _remove_if_file(path: Path) -> None:
    """Remove only an owned cache file, preserving unknown directory contents."""
    if path.is_file():
        path.unlink()
