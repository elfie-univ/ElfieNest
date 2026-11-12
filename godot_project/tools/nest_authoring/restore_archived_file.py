"""Restore one old asset file into a new temporary review path."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ARCHIVE = TOOLS / ".archive"
RESTORE = TOOLS.parents[2] / "build/godot_assets/nest-authoring/recovered"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", help="Original path relative to build/")
    key = Path(parser.parse_args().original)
    if key.is_absolute() or ".." in key.parts:
        parser.error("Specify a path relative to build/")
    inventory = json.loads((ARCHIVE / "inventory.json").read_text(encoding="utf-8"))
    item = inventory["files"].get(key.as_posix()) or inventory["identical_copies"].get(
        key.as_posix()
    )
    if not item:
        parser.error(f"Not saved in the local archive: {key}")
    digest = item["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        parser.error("Invalid archive hash")
    src = ARCHIVE / "objects" / digest
    destination = RESTORE / key
    if destination.resolve() != destination or destination.exists():
        parser.error(f"Will not overwrite or follow a link: {destination}")

    checksum = hashlib.sha256()
    with src.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            checksum.update(chunk)
        if checksum.hexdigest() != digest:
            raise ValueError(f"Archive contents changed: {key}")
        reader.seek(0)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
    print(destination)


if __name__ == "__main__":
    main()
