"""Atomic JSON writes and contained paths for the asset workspace."""

import json
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException


def write_bytes(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def catalog_json(value: object, level: int = 0, inline_items: bool = False) -> str:
    """Keep catalog file records on one line without changing their structure."""
    if isinstance(value, dict):
        opening, closing = "{", "}"
        items = [
            json.dumps(key, ensure_ascii=False)
            + ": "
            + catalog_json(item, level + 1, key == "files")
            for key, item in value.items()
        ]
    elif isinstance(value, list):
        opening, closing = "[", "]"
        items = [
            json.dumps(item, ensure_ascii=False)
            if inline_items
            else catalog_json(item, level + 1)
            for item in value
        ]
    else:
        return json.dumps(value, ensure_ascii=False)
    if not items:
        return opening + closing
    prefix = "  " * level
    return (
        opening
        + "\n"
        + ",\n".join(prefix + "  " + item for item in items)
        + "\n"
        + prefix
        + closing
    )


def write_json(path: Path, data: dict) -> None:
    text = (
        catalog_json(data)
        if path.name == "catalog.json"
        else json.dumps(data, ensure_ascii=False, indent=2)
    )
    write_bytes(path, (text + "\n").encode())


def checked_file(root: Path, relative: str) -> Path:
    path = root / relative
    if (
        Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or not path.resolve().is_relative_to(root)
        or any(
            parent.is_symlink() for parent in (path, *path.parents) if parent != root
        )
    ):
        raise HTTPException(409, "Unsafe saved file path; nothing deleted")
    return path
