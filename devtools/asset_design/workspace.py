"""Organize and audit the portable design workspace without importing Godot."""

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from devtools.asset_design.catalog import ASSET_ROOT, Catalog, load_catalog
from devtools.asset_design.catalog_store import read_catalog, save_catalog
from devtools.asset_design.deletion import checked_file, write_json
from devtools.asset_design.design_catalog import inventory
from devtools.asset_design.glb_resources import RESOURCE_DIRECTORY
from devtools.asset_design.paths import WORK_ROOT, object_directory, revision_file


def copy_asset(source, target):
    """Use independent copy-on-write files on macOS, never mutable hard links."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.run(["/bin/cp", "-c", str(source), str(target)], check=True)
    else:
        shutil.copy2(source, target)
    if (
        hashlib.sha256(source.read_bytes()).digest()
        != hashlib.sha256(target.read_bytes()).digest()
    ):
        raise ValueError("Copied asset differs: " + str(source))


def audit_workspace(root):
    root = root.resolve()
    catalog = load_catalog(root)
    issues = []
    paths = {f.path for a in catalog.assets for f in a.files}
    paths.update(i.path for i in catalog.imageReferences)
    for relative in sorted(paths):
        if not checked_file(root, relative).is_file():
            issues.append({"file": relative, "reason": "Missing registered file"})
    if issues:
        return {"files": len(paths), "issues": issues}
    data = inventory(root)
    issues.extend(data["issues"])
    objects = {o["id"]: o for o in data["objects"]}
    state = (
        json.loads((root / "adoptions.json").read_text())
        if (root / "adoptions.json").exists()
        else {"current": {}}
    )
    for identifier, record in state["current"].items():
        version = next(
            (
                v
                for v in objects.get(identifier, {}).get("versions", [])
                if v["id"] == record["version"]
            ),
            None,
        )
        if not version or version.get("contentDigest") != record.get("contentDigest"):
            issues.append(
                {"object": identifier, "reason": "Confirmed content missing or changed"}
            )
    return {"files": len(paths), "objects": len(objects), "issues": issues}


def organize_workspace(source, target):
    """Copy retained object versions and their pictures; leave legacy exports local."""
    source, target = source.resolve(), target.resolve()
    if target.exists():
        raise ValueError("Destination exists; nothing overwritten")
    raw = read_catalog(source)
    catalog = copy.deepcopy(raw)
    catalog["assets"] = [
        a for a in catalog["assets"] if a.get("designObject") or not a.get("archived")
    ]
    mapping, owners = {}, {}
    virtual = set()
    versions = {}

    def relative(path):
        return path.relative_to(target).as_posix()

    for asset in catalog["assets"]:
        obj = asset.get("designObject")
        if not obj:
            continue
        folder = object_directory(target, obj["id"])
        version = asset["designVersion"]
        version_dir = revision_file(folder, version["revision"]).parent
        versions[(obj["id"], version["id"])] = version_dir
        mapping[version["file"]] = relative(version_dir / "model.glb")
        if version.get("archiveFile"):
            virtual.add(version["file"])
            mapping[version["archiveFile"]] = relative(version_dir / "model.glb.gz")
        old_folder = Path(version["file"]).parent
        for file in asset["files"]:
            old = file["path"]
            owners.setdefault(old, (folder, version_dir))
            if old in mapping:
                continue
            if old.endswith("/source.glb") or old.endswith("/source/model.glb"):
                mapping[old] = relative(folder / "source/model.glb")
            elif Path(old).name == "build.json":
                mapping[old] = relative(folder / "source/build.json")
            elif (
                Path(old).parts[: len(RESOURCE_DIRECTORY.parts)]
                == RESOURCE_DIRECTORY.parts
            ):
                # GLB files keep relative URIs into the shared content-addressed
                # store. Keep that store at its canonical root during a workspace
                # relocation instead of copying each payload beside one version.
                mapping[old] = relative(target / old)
            elif file["kind"] == "image":
                mapping[old] = relative(version_dir / "images" / Path(old).name)
            else:
                mapping[old] = relative(version_dir / "source" / Path(old).name)
        # Every object retains its editable source, even if only an older revision registered it.
        for old, new in [
            (str(old_folder / "source.glb"), folder / "source/model.glb"),
            (str(old_folder / "build.json"), folder / "source/build.json"),
        ]:
            if (source / old).is_file():
                mapping.setdefault(old, relative(new))
    for image in catalog.get("imageReferences", []):
        old = image["path"]
        owner = image["objects"][0]
        folder = (
            target / "layouts/terraces"
            if owner == "layout:terraces"
            else object_directory(
                target, "building:central" if owner == "overview" else owner
            )
        )
        version_dir = versions.get((owner, image.get("version")))
        mapping.setdefault(
            old,
            relative(
                (version_dir / "images" if version_dir else folder / "references")
                / Path(old).name
            ),
        )
    for asset in catalog["assets"]:
        for f in asset["files"]:
            if f["path"] not in mapping:
                # Image-only records use their explicit owner from imageReferences.
                raise ValueError("Unclassified saved file: " + f["path"])
    if len(set(mapping.values())) != len(mapping):
        duplicates = [
            v for v in mapping.values() if list(mapping.values()).count(v) > 1
        ]
        # Identical copies of the same authored file may share a destination.
        for destination in set(duplicates):
            inputs = [source / k for k, v in mapping.items() if v == destination]
            if len({hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}) != 1:
                raise ValueError("Conflicting destination: " + destination)
    for old in mapping:
        if old not in virtual and not checked_file(source, old).is_file():
            raise ValueError("Missing input: " + old)

    def remap(value):
        if isinstance(value, str):
            return mapping.get(value, value)
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}
        return value

    catalog = remap(catalog)
    indexed = {f["path"] for a in catalog["assets"] for f in a["files"]}
    for image in catalog.get("imageReferences", []):
        if image["path"] in indexed:
            continue
        owner = image["objects"][0]
        asset = next(
            (
                a
                for a in catalog["assets"]
                if a.get("designObject", {}).get("id") == owner
            ),
            catalog["assets"][0],
        )
        original = next(old for old, new in mapping.items() if new == image["path"])
        asset["files"].append(
            {
                "path": image["path"],
                "name": Path(image["path"]).name,
                "kind": "image",
                "bytes": (source / original).stat().st_size,
            }
        )
        indexed.add(image["path"])
    Catalog.model_validate(catalog)
    target.mkdir(parents=True)
    for old, new in mapping.items():
        if old not in virtual and not (target / new).exists():
            copy_asset(source / old, target / new)
    for asset in catalog["assets"]:
        if asset.get("designObject"):
            folder = object_directory(target, asset["designObject"]["id"])
            build = folder / "source/build.json"
            if build.exists():
                data = json.loads(build.read_text())
                data["source"] = "model.glb"
                write_json(build, data)
    state = source / "adoptions.json"
    if not state.exists():
        state = source / ".design-adoptions.json"
    if state.exists():
        copy_asset(state, target / "adoptions.json")
    save_catalog(target, catalog)
    result = audit_workspace(target)
    if result["issues"]:
        raise ValueError("Workspace audit failed: " + str(result["issues"]))
    return {**result, "copiedFiles": len(mapping), "legacyRootRequired": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["organize", "scan"])
    parser.add_argument("--root", type=Path, default=ASSET_ROOT)
    parser.add_argument("--from-root", type=Path)
    args = parser.parse_args()
    if args.action == "organize":
        if args.from_root is None:
            parser.error("organize requires --from-root")
        report = organize_workspace(args.from_root, args.root)
    else:
        report = audit_workspace(args.root)
        if not report["issues"]:
            write_json(WORK_ROOT / "catalog.json", load_catalog(args.root).model_dump())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
