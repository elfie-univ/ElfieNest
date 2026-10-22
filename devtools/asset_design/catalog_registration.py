"""Recheck relevant owners for known resources, including direct metadata edits."""

from functools import lru_cache
from pathlib import Path
from threading import RLock

from devtools.asset_design.catalog_models import Asset, Catalog
from devtools.asset_design.catalog_store import (
    ObjectIndex,
    metadata_document,
    read_catalog,
)
from devtools.asset_design.paths import object_directory

_LOCK = RLock()


def _collect(root: Path) -> dict[str, list[tuple[str, str, str]]]:
    catalog = Catalog.model_validate(read_catalog(root))
    owners: dict[str, list[tuple[str, str, str]]] = {}
    for asset in catalog.assets:
        design_object = asset.designObject
        design_version = asset.designVersion
        owner = (
            (
                design_object["id"],
                asset.id,
                (Path(design_version["file"]).parent / "version.json").as_posix(),
            )
            if design_object is not None and design_version is not None
            else ("", asset.id, "")
        )
        for file in asset.files:
            owners.setdefault(file.path, []).append(owner)
    return owners


@lru_cache(maxsize=16)
def _sources(root: Path, index: bytes) -> dict[str, list[tuple[str, str, str]]]:
    del index
    return _collect(root)


def registered_path(root: Path, relative: str) -> bool:
    with _LOCK:
        _, content = metadata_document(root, "catalog.json")
        owners = _sources(root, content)
        for identifier, asset_id, version_path in owners.get(relative, []):
            if not identifier:
                return True  # Unowned import records live entirely in the root index.
            object_path = (
                (object_directory(root, identifier) / "object.json")
                .relative_to(root)
                .as_posix()
            )
            raw, _ = metadata_document(root, object_path)
            obj = ObjectIndex.model_validate(raw)
            if obj.designObject.get("id") != identifier:
                raise ValueError("Object index identity mismatch")
            if not any(
                v.id == asset_id and v.file == version_path for v in obj.versions
            ):
                continue
            raw, _ = metadata_document(root, version_path)
            asset = Asset.model_validate(raw)
            if asset.id != asset_id or asset.designObject:
                raise ValueError("Version metadata identity mismatch")
            if any(file.path == relative for file in asset.files):
                return True
        # New or removed registrations can change only a child file, with no root edit.
        refreshed = _collect(root)
        owners.clear()
        owners.update(refreshed)
        return relative in owners
