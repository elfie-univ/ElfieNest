"""Split legacy exports once; publish each object's editable GLB independently."""

import argparse
import copy
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from devtools.asset_design.catalog import ASSET_ROOT, Catalog
from devtools.asset_design.deletion import write_json
from devtools.asset_design.design_catalog import legacy_inventory
from devtools.asset_design.design_models import read_model
from devtools.asset_design.object_content import content_digest
from devtools.asset_design.object_glb import extract_glb
from devtools.asset_design.paths import WORK_ROOT, object_directory, revision_file


def slug(identifier):
    return identifier.replace(":", "_")


def file_entry(root, relative, kind):
    return {
        "path": relative,
        "name": Path(relative).name,
        "kind": kind,
        "bytes": (root / relative).stat().st_size,
    }


def backup(root):
    directory = WORK_ROOT / "backups" / ("object-split-" + uuid4().hex)
    directory.mkdir(parents=True)
    for name in ("catalog.json", "adoptions.json"):
        if (root / name).exists():
            shutil.copy2(root / name, directory / name)
    return directory


def commit_catalog(root, catalog, before):
    Catalog.model_validate(catalog)
    if (root / "catalog.json").read_bytes() != before:
        raise ValueError(
            "Catalog changed during preparation; sources and confirmations untouched"
        )
    write_json(root / "catalog.json", catalog)


def split_assets(root):
    root = root.resolve()
    before = (root / "catalog.json").read_bytes()
    catalog = json.loads(before)
    if any(a.get("designObject") for a in catalog["assets"]):
        raise ValueError("Assets already split; use publish for one object")
    state_path = root / "adoptions.json"
    state_before = state_path.read_bytes() if state_path.exists() else None
    state = json.loads(state_before) if state_before else {"current": {}, "history": []}
    inventory = legacy_inventory(root)
    if inventory["issues"]:
        raise ValueError(
            "Resolve inventory issues before splitting: " + str(inventory["issues"])
        )
    destination = backup(root)
    write_json(destination / "legacy-objects.json", inventory)
    write_json(
        destination / "legacy-files.json",
        {
            "policy": "Retained in place; no historical path is moved or deleted",
            "paths": [
                {
                    "path": p.relative_to(root).as_posix(),
                    "kind": "symlink"
                    if p.is_symlink()
                    else "directory"
                    if p.is_dir()
                    else "file",
                    "action": "retain",
                }
                for p in sorted(root.rglob("*"))
            ],
        },
    )
    added, mapping, verified = [], {}, []
    for obj in inventory["objects"]:
        if obj.get("historical") or obj.get("aggregate") or obj["id"] == "overview":
            continue
        metadata = {k: v for k, v in obj.items() if k not in {"versions", "current"}}
        current = state["current"].get(obj["id"])
        adopted_revision = next(
            (
                v["revision"]
                for v in obj["versions"]
                if current and v["contentDigest"] == current["contentDigest"]
            ),
            0,
        )
        pinned_contents = {
            entry.get("contentDigest")
            for record in state["current"].values()
            for entry in [record, *record["refs"]]
            if entry["object"] == obj["id"]
        }
        folder = object_directory(root, obj["id"])
        if folder.exists():
            raise ValueError("Object output exists: " + str(folder))
        folder.mkdir(parents=True)
        for version in obj["versions"]:
            old_path = root / version["file"]
            records, old_digest = read_model(root, version["file"])
            if old_digest != version["digest"]:
                raise ValueError("Legacy source changed: " + str(old_path))
            anchors = version.get("placements", {})
            helpers = [
                r["node"]
                for r in records
                if r.get("reference") is True
                and (
                    not obj["module"]
                    or r.get("module") == obj["module"]
                    or r.get("module") in anchors
                )
                and (not obj["floor"] or str(r.get("floor", 1)) == obj["floor"])
            ]
            data, remap = extract_glb(
                old_path, [*version["nodes"], *helpers], anchors.values()
            )
            if shutil.disk_usage(root).free < len(data) + 512 * 1024**2:
                raise ValueError(
                    "Insufficient free space; original catalog and confirmations retained"
                )
            target = revision_file(folder, version["revision"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            relative = target.relative_to(root).as_posix()
            nodes = [remap[i] for i in version["nodes"]]
            digest = content_digest(root, relative, nodes)
            if digest != version["contentDigest"]:
                raise ValueError(
                    "Object content changed during extraction: " + obj["id"]
                )
            identifier = slug(obj["id"]) + f"_v{version['revision']:03d}"
            independent = {
                **copy.deepcopy(version),
                "asset": identifier,
                "file": relative,
                "digest": hashlib.sha256(data).hexdigest(),
                "nodes": nodes,
                "measurements": None,
            }
            if anchors:
                independent["placements"] = {k: remap[v] for k, v in anchors.items()}
            record = {
                "id": identifier,
                "category": obj["group"],
                "title": version["title"],
                "description": "独立对象模型；构建只读取本对象的 source/model.glb。",
                "primaryModel": relative,
                "models": [relative],
                "files": [file_entry(root, relative, "model")],
                "designObject": metadata,
                "designVersion": independent,
                "archived": False,
            }
            if version["revision"] < adopted_revision and digest not in pinned_contents:
                archive = target.with_suffix(".glb.gz")
                compressed = gzip.compress(data, compresslevel=6, mtime=0)
                if gzip.decompress(compressed) != data:
                    raise ValueError("Compressed archive failed verification")
                archive.write_bytes(compressed)
                independent["archiveFile"] = archive.relative_to(root).as_posix()
                record.update(
                    archived=True,
                    primaryModel=None,
                    models=[],
                    files=[file_entry(root, independent["archiveFile"], "archive")],
                )
                target.unlink()  # Only this newly extracted, verified copy is compressed.
            added.append(record)
            for alias in {
                version["id"],
                *(s["asset"] for s in version.get("sources", [])),
            }:
                mapping[(obj["id"], alias)] = independent
            verified.append(
                {
                    "object": obj["id"],
                    "version": version["title"],
                    "file": relative,
                    "contentDigest": digest,
                    "source": version["file"],
                    "archiveFile": independent.get("archiveFile"),
                    "exact": True,
                }
            )
        chosen = (
            mapping[(obj["id"], current["version"])]
            if current
            else mapping[(obj["id"], obj["versions"][0]["id"])]
        )
        source = folder / "source" / "model.glb"
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / chosen["file"], source)
        write_json(
            folder / "source" / "build.json",
            {
                "object": obj["id"],
                "source": "model.glb",
                "placements": chosen.get("placements", {}),
                "instanceCount": chosen.get("instanceCount", 0),
            },
        )
        chosen_asset = next(a for a in added if a["id"] == chosen["asset"])
        chosen_asset["files"].extend(
            [
                file_entry(root, source.relative_to(root).as_posix(), "source"),
                file_entry(
                    root,
                    (folder / "source" / "build.json").relative_to(root).as_posix(),
                    "data",
                ),
            ]
        )
    for asset in added:
        write_json(
            (root / asset["designVersion"]["file"]).parent / "version.json", asset
        )
    # Resolve every live confirmation and pinned reference before changing any state.
    for record in state["current"].values():
        for entry in [record, *record["refs"]]:
            selected = mapping[(entry["object"], entry["version"])]
            if entry.get("contentDigest") != selected["contentDigest"]:
                raise ValueError(
                    "Confirmed object content mismatch: " + entry["object"]
                )
            entry["digest"] = selected["digest"]
    if (state_path.read_bytes() if state_path.exists() else None) != state_before:
        raise ValueError("Confirmations changed during preparation")
    # Old object revisions are archived only after all extracted content was verified.
    catalog["assets"] = [{**a, "archived": True} for a in catalog["assets"]] + added
    commit_catalog(root, catalog, before)
    try:
        if state_before is not None:
            write_json(state_path, state)
    except BaseException:
        (root / "catalog.json").write_bytes(before)
        raise
    report = {
        "backup": str(destination),
        "verified_versions": len(verified),
        "objects": len({a["designObject"]["id"] for a in added}),
        "versions": verified,
        "history_files_deleted": 0,
        "archived_object_versions": sum(a["archived"] for a in added),
        "confirmed_objects": list(state["current"]),
    }
    write_json(destination / "split-report.json", report)
    return report


def register_images(root, catalog, asset, images, references):
    folder = object_directory(root, asset["designObject"]["id"])
    version = asset["designVersion"]
    planned = []
    for kind, inputs in (("render", images), ("reference", references)):
        for source in inputs:
            source = Path(source).resolve()
            if (
                source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
                or not source.is_file()
            ):
                raise ValueError("Expected an existing design image: " + str(source))
            directory = (
                Path(version["file"]).parent / "images"
                if kind == "render"
                else folder.relative_to(root) / "references"
            )
            target = root / directory / source.name
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError(
                    "Image already exists with different content: " + str(target)
                )
            planned.append((kind, source, target))
    for kind, source, target in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target:
            shutil.copy2(source, target)
        relative = target.relative_to(root).as_posix()
        if not any(f["path"] == relative for f in asset["files"]):
            asset["files"].append(file_entry(root, relative, "image"))
        entry = {
            "path": relative,
            "objects": [asset["designObject"]["id"]],
            "title": source.name,
            "kind": kind,
        }
        if kind == "render":
            entry["version"] = version["id"]
        rows = catalog.setdefault("imageReferences", [])
        if entry not in rows:
            rows.append(entry)


def publish_object(root, object_id, *, images=(), references=()):
    root = root.resolve()
    before = (root / "catalog.json").read_bytes()
    catalog = json.loads(before)
    owned = [
        a
        for a in catalog["assets"]
        if (a.get("designObject") or {}).get("id") == object_id
    ]
    if not owned:
        raise ValueError("Unknown independent object: " + object_id)
    folder = object_directory(root, object_id)
    build = json.loads((folder / "source" / "build.json").read_text())
    source = folder / "source" / "model.glb"
    records, _ = read_model(root, source.relative_to(root).as_posix())
    selected = [r["node"] for r in records if not r.get("reference")]
    metadata = owned[0]["designObject"]
    for r in records:
        if r.get("reference"):
            continue
        furniture = bool(r.get("furniture") or r.get("role") == "furniture")
        if metadata["group"] == "building" and furniture:
            raise ValueError("Furniture cannot be published as a building revision")
        if metadata["group"] == "layout" and not furniture:
            raise ValueError("Architecture cannot be published as a furniture revision")
        if metadata["module"] and r.get("module") != metadata["module"]:
            raise ValueError("Source contains another object module")
        if metadata["floor"] and str(r.get("floor", 1)) != metadata["floor"]:
            raise ValueError("Source contains another floor")
        if object_id == "layout:pod" and str(r.get("floor", 1)) != "1":
            raise ValueError("Roof furniture belongs to its own terrace object")
        if object_id.startswith("part:") and re.sub(
            r"_drawer_\d+$", "", str(r.get("assembly", ""))
        ) != object_id.removeprefix("part:"):
            raise ValueError("Source contains another furniture part")
    digest = content_digest(root, source.relative_to(root).as_posix(), selected)
    existing = next(
        (a for a in owned if a["designVersion"]["contentDigest"] == digest), None
    )
    if existing:
        if images or references:
            register_images(root, catalog, existing, images, references)
            write_json(
                (root / existing["designVersion"]["file"]).parent / "version.json",
                existing,
            )
            commit_catalog(root, catalog, before)
        return {"changed": False, "version": existing["designVersion"]["title"]}
    number = max(a["designVersion"]["revision"] for a in owned) + 1
    target = revision_file(folder, number)
    if target.exists():
        raise ValueError("Revision already exists")
    data, remap = extract_glb(
        source, [r["node"] for r in records], build["placements"].values()
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    relative = target.relative_to(root).as_posix()
    identifier = slug(object_id) + f"_v{number:03d}"
    version = {
        "id": identifier,
        "asset": identifier,
        "title": metadata["label"] + f" · V{number:03d}",
        "revision": number,
        "file": relative,
        "digest": hashlib.sha256(data).hexdigest(),
        "contentDigest": digest,
        "nodes": [remap[i] for i in selected],
        "measurements": None,
        "placements": {k: remap[v] for k, v in build["placements"].items()},
        "instanceCount": build["instanceCount"],
    }
    if content_digest(root, relative, version["nodes"]) != digest:
        raise ValueError("Published content differs from source")
    catalog["assets"].append(
        {
            "id": identifier,
            "category": metadata["group"],
            "title": version["title"],
            "primaryModel": relative,
            "models": [relative],
            "files": [file_entry(root, relative, "model")],
            "designObject": metadata,
            "designVersion": version,
        }
    )
    register_images(root, catalog, catalog["assets"][-1], images, references)
    write_json(target.parent / "version.json", catalog["assets"][-1])
    commit_catalog(root, catalog, before)
    return {"changed": True, "version": version["title"], "file": relative}


def restore_version(root, object_id, revision):
    """Restore one archived independent revision without changing confirmations."""
    root = root.resolve()
    before = (root / "catalog.json").read_bytes()
    catalog = json.loads(before)
    asset = next(
        (
            a
            for a in catalog["assets"]
            if (a.get("designObject") or {}).get("id") == object_id
            and a["designVersion"]["revision"] == revision
        ),
        None,
    )
    if asset is None:
        raise ValueError("Archived independent revision unavailable")
    version = asset["designVersion"]
    if version.get("archiveFile"):
        data = gzip.decompress((root / version["archiveFile"]).read_bytes())
        if hashlib.sha256(data).hexdigest() != version["digest"]:
            raise ValueError("Archived file checksum mismatch")
        target = root / version["file"]
        if target.exists():
            raise ValueError("Restoration target already exists")
        target.write_bytes(data)
        asset["primaryModel"], asset["models"] = version["file"], [version["file"]]
        asset["files"].append(file_entry(root, version["file"], "model"))
        del version["archiveFile"]
    records, _ = read_model(root, asset["primaryModel"])
    if (
        content_digest(
            root,
            asset["primaryModel"],
            [r["node"] for r in records if not r.get("reference")],
        )
        != asset["designVersion"]["contentDigest"]
    ):
        raise ValueError("Archived revision content has changed")
    asset["archived"] = False
    write_json((root / version["file"]).parent / "version.json", asset)
    commit_catalog(root, catalog, before)
    return {"restored": asset["title"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["split", "publish", "restore"])
    parser.add_argument("--root", type=Path, default=ASSET_ROOT)
    parser.add_argument("--object")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--image", action="append", type=Path, default=[])
    parser.add_argument("--reference", action="append", type=Path, default=[])
    args = parser.parse_args()
    result = (
        split_assets(args.root)
        if args.action == "split"
        else restore_version(args.root, args.object, args.revision)
        if args.action == "restore"
        else publish_object(
            args.root, args.object, images=args.image, references=args.reference
        )
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "versions"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
