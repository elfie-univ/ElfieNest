"""Object-owned catalog metadata; the HTTP catalog remains a flat projection."""

import copy
import json
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from devtools.asset_design.catalog_io import catalog_json, write_bytes
from devtools.asset_design.catalog_models import Catalog
from devtools.asset_design.paths import object_directory

_LOCK = RLock()


class ObjectReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    index: str


class VersionReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    file: str
    order: int


class ObjectIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    designObject: dict
    versions: list[VersionReference]


def metadata_path(root: Path, relative: str) -> Path:
    return _metadata_path(root.resolve(), relative, set())


def _metadata_path(root: Path, relative: str, checked: set[Path]) -> Path:
    path = root / relative
    if (
        Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or path.suffix != ".json"
    ):
        raise ValueError("Unsafe catalog metadata path: " + relative)
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent not in checked:
            if parent.is_symlink():
                raise ValueError("Unsafe catalog metadata path: " + relative)
            checked.add(parent)
    return path


@lru_cache(maxsize=2048)
def _content(path: Path, stamp: tuple) -> bytes:
    del stamp
    return path.read_bytes()


@lru_cache(maxsize=2048)
def _decode(content: bytes) -> dict:
    return json.loads(content)


def _document(path: Path, snapshot: dict[Path, bytes]) -> dict:
    stat = path.stat()
    snapshot[path] = _content(
        path, (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    )
    return _decode(snapshot[path])


def metadata_document(root: Path, relative: str) -> tuple[dict, bytes]:
    path = metadata_path(root, relative)
    snapshot: dict[Path, bytes] = {}
    value = _document(path, snapshot)
    return value, snapshot[path]


def _read(root: Path) -> tuple[dict, dict[Path, bytes]]:
    root = root.resolve()
    checked: set[Path] = set()
    index = _metadata_path(root, "catalog.json", checked)
    if not index.exists():
        return {"assets": []}, {}
    snapshot: dict[Path, bytes] = {}
    data = _document(index, snapshot)
    if "objects" not in data:
        # Existing unowned export inputs are still used by the explicit split CLI.
        # Object revisions must use indexes; never fall back to inline copies.
        if any(a.get("designObject") for a in data.get("assets", [])):
            raise ValueError("Object revisions require object indexes")
        return data, snapshot
    projected = {k: v for k, v in data.items() if k not in {"objects", "imports"}}
    rows = [(item["order"], item["asset"]) for item in data.get("imports", [])]
    object_ids, asset_ids, orders = set(), set(), set()
    for value in data["objects"]:
        ref = ObjectReference.model_validate(value)
        if ref.id in object_ids:
            raise ValueError("Duplicate object index: " + ref.id)
        object_ids.add(ref.id)
        path = _metadata_path(root, ref.index, checked)
        if path != object_directory(root, ref.id) / "object.json":
            raise ValueError("Object index path does not match owner")
        obj = ObjectIndex.model_validate(_document(path, snapshot))
        if obj.designObject.get("id") != ref.id:
            raise ValueError("Object index identity mismatch")
        for version in obj.versions:
            path = _metadata_path(root, version.file, checked)
            if path.parent.parent != object_directory(root, ref.id) / "versions":
                raise ValueError("Version metadata path does not match owner")
            row = _document(path, snapshot)
            if "designObject" in row or row.get("id") != version.id:
                raise ValueError("Version metadata identity mismatch")
            if path != _metadata_path(
                root,
                str(Path(row["designVersion"]["file"]).parent / "version.json"),
                checked,
            ):
                raise ValueError("Version model and metadata paths differ")
            rows.append(
                (version.order, {**row, "designObject": obj.designObject.copy()})
            )
    for order, row in rows:
        if order in orders or row["id"] in asset_ids:
            raise ValueError("Duplicate version identity or order")
        orders.add(order)
        asset_ids.add(row["id"])
    projected["assets"] = [row for _, row in sorted(rows, key=lambda item: item[0])]
    return projected, snapshot


def read_catalog(root: Path) -> dict:
    with _LOCK:
        return copy.deepcopy(_read(root)[0])


def snapshot_catalog(root: Path) -> dict[Path, bytes]:
    with _LOCK:
        return _read(root)[1]


def restore_catalog(snapshot: dict[Path, bytes]) -> None:
    for path, content in snapshot.items():
        if not path.exists() or path.read_bytes() != content:
            write_bytes(path, content)


def save_catalog(
    root: Path, data: dict, *, expected: Optional[dict[Path, bytes]] = None
) -> dict[Path, Optional[bytes]]:
    """Write changed metadata only and restore touched files on a failed save."""
    with _LOCK:
        return _save_catalog(root, data, expected=expected)


def _version_orders(root: Path, rows: list[dict]) -> dict[str, int]:
    orders = {}
    if (root / "catalog.json").exists():
        index, _ = metadata_document(root, "catalog.json")
        for ref in index.get("objects", []):
            obj, _ = metadata_document(root, ref["index"])
            orders.update({v["id"]: v["order"] for v in obj["versions"]})
        orders.update({v["asset"]["id"]: v["order"] for v in index.get("imports", [])})
    next_order = max(orders.values(), default=-1) + 1
    result = {}
    for row in rows:
        if row["id"] not in orders:
            orders[row["id"]] = next_order
            next_order += 1
        result[row["id"]] = orders[row["id"]]
    if list(result.values()) != sorted(result.values()):
        return {row["id"]: i for i, row in enumerate(rows)}
    return result


def _save_catalog(
    root: Path, data: dict, *, expected: Optional[dict[Path, bytes]]
) -> dict[Path, Optional[bytes]]:
    Catalog.model_validate(data)
    root = root.resolve()
    objects: dict[Path, dict[str, Any]] = {}
    imports: list[dict[str, Any]] = []
    output: dict[Path, dict[str, Any]] = {}
    orders = _version_orders(root, data.get("assets", []))
    if len(orders) != len(data.get("assets", [])):
        raise ValueError("Duplicate asset identity")
    for row in data.get("assets", []):
        order = orders[row["id"]]
        metadata = row.get("designObject")
        if not metadata:
            imports.append({"order": order, "asset": row})
            continue
        folder = object_directory(root, metadata["id"])
        obj = objects.setdefault(folder, {"designObject": metadata, "versions": []})
        if obj["designObject"] != metadata:
            raise ValueError("Object metadata differs across revisions")
        path = metadata_path(
            root, str(Path(row["designVersion"]["file"]).parent / "version.json")
        )
        if path.parent.parent != folder / "versions":
            raise ValueError("Version metadata path does not match owner")
        if path in output:
            raise ValueError("Duplicate version metadata path")
        output[path] = {k: v for k, v in row.items() if k != "designObject"}
        obj["versions"].append(
            {"id": row["id"], "file": path.relative_to(root).as_posix(), "order": order}
        )
    index = {k: v for k, v in data.items() if k != "assets"}
    index["objects"] = []
    for folder, obj in objects.items():
        path = metadata_path(
            root, (folder / "object.json").relative_to(root).as_posix()
        )
        output[path] = obj
        index["objects"].append(
            {
                "id": obj["designObject"]["id"],
                "index": path.relative_to(root).as_posix(),
            }
        )
    if imports:
        index["imports"] = imports
    output[metadata_path(root, "catalog.json")] = index
    if expected is not None and snapshot_catalog(root) != expected:
        raise ValueError("Catalog changed during preparation; nothing overwritten")
    before = {}
    try:
        for path, value in output.items():
            content = (catalog_json(value) + "\n").encode()
            old = path.read_bytes() if path.exists() else None
            if expected is not None and path in expected and old != expected[path]:
                raise ValueError("Catalog changed during write")
            if old == content:
                continue
            before[path] = old
            path.parent.mkdir(parents=True, exist_ok=True)
            write_bytes(path, content)
    except BaseException:
        rollback_catalog(before)
        raise
    return before


def rollback_catalog(before: dict[Path, Optional[bytes]]) -> None:
    for path, content in reversed(list(before.items())):
        if content is None:
            path.unlink(missing_ok=True)
        elif not path.exists() or path.read_bytes() != content:
            write_bytes(path, content)
