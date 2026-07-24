"""Discover the generated Web client build without falling back to source assets."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

WEB_MANIFEST_NAME: Final = "manifest.json"
WEB_ENTRYPOINTS: Final = ("login.html", "chat.html", "manage.html")


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

    def page_path(self, page: str) -> Path:
        """Resolve one verified generated page shell inside the build root."""
        self._entry(page)
        return self._safe_file(page)

    def is_login_asset(self, relative_path: str) -> bool:
        """Whether an asset is required to render the anonymous login page."""
        return relative_path in set(self._entry_assets("login.html"))

    def asset_path(self, relative_path: str) -> Path:
        """Resolve a manifest-listed generated asset without path traversal."""
        assets: set[str] = set()
        for page in WEB_ENTRYPOINTS:
            assets.update(self._entry_assets(page))
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
            "Run `pnpm --dir app/interfaces/web/frontend build`."
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

    missing_entries = [entry for entry in WEB_ENTRYPOINTS if entry not in manifest]
    if missing_entries:
        rendered_entries = ", ".join(missing_entries)
        raise WebBuildManifestMalformedError(
            f"Web build manifest is missing required entries ({rendered_entries}): "
            f"{manifest_path}."
        )

    return WebBuild(
        directory=directory,
        manifest_path=manifest_path,
        manifest=manifest,
    )
