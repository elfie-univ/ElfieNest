"""Recoverable removal of one indexed design version, never an entire directory."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from devtools.asset_design.catalog import ASSET_ROOT, Catalog
from devtools.asset_design.paths import WORK_ROOT


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


def write_json(path: Path, data: dict) -> None:
    write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


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


def asset_paths(asset: dict) -> set:
    return {
        *[f["path"] for f in asset.get("files", [])],
        *asset.get("models", []),
        *asset.get("images", []),
        *asset.get("referenceFloors", {}).values(),
        *[
            asset[k]
            for k in ("primaryModel", "thumbnail", "measurements")
            if asset.get(k)
        ],
    }


def delete_asset(asset_root: Path, asset_id: str) -> dict:
    from devtools.asset_design.design import assert_not_adopted

    assert_not_adopted(asset_root, asset_id)
    root = asset_root.resolve()
    catalog_path = checked_file(root, "catalog.json")
    mark_path = checked_file(root, ".cleanup-marks.json")
    if not catalog_path.is_file():
        raise HTTPException(404, "Saved asset unavailable")
    catalog_before = catalog_path.read_bytes()
    raw = json.loads(catalog_before)
    selected = next((a for a in raw["assets"] if a["id"] == asset_id), None)
    if selected is None:
        raise HTTPException(404, "Saved asset unavailable")
    remaining = [a for a in raw["assets"] if a["id"] != asset_id]
    indexed = {f["path"]: f for a in raw["assets"] for f in a.get("files", [])}
    targets = asset_paths(selected)
    for relative in targets:
        checked_file(root, relative)
    shared = set().union(*(asset_paths(a) for a in remaining)) if remaining else set()
    # Source and support inputs stay available to builders, including unindexed ones.
    consumers = []
    selected_inputs = {
        f["path"]
        for f in selected.get("files", [])
        if f["kind"] not in {"model", "image"}
    }
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in selected_inputs or path in {catalog_path, mark_path}:
            continue
        if path.suffix.lower() in {".py", ".json", ".gltf", ".gd", ".obj", ".mtl"}:
            consumers.append((relative, path.read_text(errors="replace")))
        elif path.suffix.lower() == ".glb" and relative in shared:
            # GLB's JSON chunk declares any external buffer or texture URIs.
            with path.open("rb") as stream:
                header = stream.read(20)
                if header[:4] == b"glTF" and header[16:20] == b"JSON":
                    chunk_length = int.from_bytes(header[12:16], "little")
                    consumers.append(
                        (relative, stream.read(chunk_length).decode(errors="replace"))
                    )
    inventory, movable, references = [], [], []
    for relative in sorted(targets):
        path = checked_file(root, relative)
        file = indexed.get(relative)
        used_by = [
            name
            for name, text in consumers
            if name != relative and (relative in text or path.name in text)
        ]
        reason = (
            "shared with retained assets"
            if relative in shared
            else "referenced by build or model input"
            if used_by
            else "source/support input retained"
            if not file or file["kind"] not in {"model", "image"}
            else "missing file"
            if not path.is_file()
            else "archive"
        )
        row = {"path": relative, "action": reason, "consumers": used_by}
        if path.is_file():
            row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory.append(row)
        if reason == "archive":
            movable.append(relative)
        else:
            references.append(row)
    # A retained reference may have been registered only by the removed record.
    for asset in remaining:
        registered = {f["path"] for f in asset.get("files", [])}
        asset.setdefault("files", []).extend(
            indexed[p] for p in sorted(asset_paths(asset) - registered) if p in indexed
        )
    raw["assets"] = remaining
    files = {f["path"]: f for a in remaining for f in a.get("files", [])}
    raw["stats"] = {
        **raw.get("stats", {}),
        "directories": sum(path.is_dir() for path in root.iterdir()),
        "records": len(remaining),
        "files": len(files),
        "models": sum(f["kind"] == "model" for f in files.values()),
        "images": sum(f["kind"] == "image" for f in files.values()),
        "sources": sum(f["kind"] == "source" for f in files.values()),
        "bytes": sum(f["bytes"] for f in files.values()),
    }
    Catalog.model_validate(raw)
    marks_before = mark_path.read_bytes() if mark_path.is_file() else None
    marks = json.loads(marks_before) if marks_before else {"markedIds": []}
    marks["markedIds"] = [i for i in marks["markedIds"] if i != asset_id]
    backup = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex
    archive_base = (
        (WORK_ROOT / "cleanup")
        if root == ASSET_ROOT.resolve()
        else root.parent / "asset_cleanup"
    )
    if archive_base.is_symlink():
        raise HTTPException(409, "Unsafe archive path; nothing deleted")
    archive = archive_base / backup
    archive.mkdir(parents=True)
    (archive / "catalog.before.json").write_bytes(catalog_before)
    if marks_before is not None:
        (archive / "marks.before.json").write_bytes(marks_before)
    report = {
        "target": asset_id,
        "inventory": inventory,
        "references": references,
        "verification": "catalog validated; file hashes recorded before moving",
        "residuals": [r for r in inventory if r["action"] != "archive"],
        "status": "prepared",
    }
    write_json(archive / "report.json", report)
    moved = []
    try:
        for relative in movable:
            destination = archive / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(root / relative, destination)
            moved.append(relative)
        write_json(catalog_path, raw)
        write_json(mark_path, marks)
        report["status"] = "deleted"
        write_json(archive / "report.json", report)
    except Exception:
        for relative in reversed(moved):
            os.replace(archive / "files" / relative, root / relative)
        write_bytes(catalog_path, catalog_before)
        if marks_before is not None:
            write_bytes(mark_path, marks_before)
        else:
            mark_path.unlink(missing_ok=True)
        report["status"] = "rolled back"
        write_json(archive / "report.json", report)
        raise
    return {
        "deletedId": asset_id,
        "backup": backup,
        "archivedFiles": len(moved),
        "retainedFiles": len(references),
    }
