"""Discover the generated Web client build without falling back to source assets."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

WEB_MANIFEST_NAME: Final = "manifest.json"
WEB_ENTRYPOINT: Final = "index.html"


class WebBuildManifestMissingError(FileNotFoundError):
    """Raised when Core cannot find the generated Vite manifest."""


class WebBuildManifestMalformedError(ValueError):
    """Raised when a Vite manifest is unreadable or lacks a required shell."""


@dataclass(frozen=True)
class WebBuild:
    """A verified generated Web client layout for Core resource discovery."""

    directory: Path
    manifest_path: Path
    manifest: dict[str, object]

    def shell_path(self) -> Path:
        """Resolve the only generated React application shell inside the build root."""
        self._entry(WEB_ENTRYPOINT)
        return self._safe_file(WEB_ENTRYPOINT)

    def asset_path(self, relative_path: str) -> Path:
        """Resolve a manifest-listed public application asset without traversal."""
        assets = set(self._entry_assets(WEB_ENTRYPOINT))
        if relative_path not in assets:
            raise FileNotFoundError(relative_path)
        return self._safe_file(relative_path)

    def _entry(self, page: str) -> dict[str, object]:
        raw_entry = self.manifest.get(page)
        if not isinstance(raw_entry, dict):
            raise WebBuildManifestMalformedError(
                f"Web build manifest entry {page!r} must be an object."
            )
        return raw_entry

    def _entry_assets(self, page: str) -> Iterable[str]:
        entry = self._entry(page)
        file_name = entry.get("file")
        if isinstance(file_name, str):
            yield file_name
        css = entry.get("css", [])
        if isinstance(css, list):
            yield from (item for item in css if isinstance(item, str))
        public_assets = entry.get("assets", [])
        if isinstance(public_assets, list):
            yield from (item for item in public_assets if isinstance(item, str))
        imports = entry.get("imports", [])
        if isinstance(imports, list):
            for imported in imports:
                if isinstance(imported, str):
                    yield from self._entry_assets(imported)

    def _safe_file(self, relative_path: str) -> Path:
        candidate = (self.directory / relative_path).resolve()
        if self.directory.resolve() not in candidate.parents:
            raise FileNotFoundError(relative_path)
        return candidate


def discover_web_build(directory: Path) -> WebBuild:
    """Return a verified generated build, or a diagnosis that Core can expose."""
    manifest_path = directory / WEB_MANIFEST_NAME
    if not manifest_path.is_file():
        raise WebBuildManifestMissingError(
            f"Web build manifest is missing: {manifest_path}. "
            "Run `cd app/interfaces/web/frontend && pnpm build`."
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise WebBuildManifestMalformedError(
            f"Web build manifest is malformed: {manifest_path}."
        ) from error

    if not isinstance(manifest, dict):
        raise WebBuildManifestMalformedError(
            f"Web build manifest must contain an object: {manifest_path}."
        )

    if WEB_ENTRYPOINT not in manifest:
        raise WebBuildManifestMalformedError(
            f"Web build manifest is missing required entry ({WEB_ENTRYPOINT}): "
            f"{manifest_path}."
        )

    return WebBuild(
        directory=directory,
        manifest_path=manifest_path,
        manifest=manifest,
    )
