"""Serve the validated Nest asset review using the existing Godot Web shell."""

import argparse
import hashlib
import json
import shutil
from os import walk
from pathlib import Path
from typing import Iterator

from export_menu_assets import prepare_menu_assets
from organize_furniture_assets import (
    COURTYARD_COUNT,
    COURTYARD_DEPENDENCIES,
    LOCATIONS,
)
from organize_furniture_assets import DESTINATION as FURNITURE
from review_asset_menu import build_menu, catalog_leaves
from review_asset_sizes import add_asset_sizes

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "build/godot-asset-migration/asset-review"
SHARED = REVIEW.parent / "shared-v044-candidate"
WEB = ROOT / "build/components/godot-web"
GODOT = ROOT / "godot_project"
NEST = GODOT / "nest"
NEST_INDEX = NEST / "assembly/asset-index.json"
NEST_WEB = REVIEW.parent / "nest-web"
NEST_ASSET_FOLDERS = (
    "furniture/layouts",
    "furniture/sets",
    "furniture/shared",
    "furniture/textures",
    "buildings",
    "courtyard",
    "assembly",
)


def audit_furniture_files(graph, menu, report):
    assets = FURNITURE / "assets"
    entries = graph["entries"]
    furniture = next(row for row in graph["categories"] if row["id"] == "furniture")
    for group in furniture["children"]:
        for location in group["children"]:
            assert LOCATIONS[location["id"]] == location["label"], location["id"]
            assert location["children"] and all(
                "children" not in item for item in location["children"]
            ), (group["id"], location["id"], "Furniture menu must have three levels")
    browse_ids = [
        leaf["id"]
        for category in graph["categories"]
        for leaf in catalog_leaves(category["children"])
    ]
    owned = {key: row["owner"] for key, row in entries.items() if "owner" in row}
    assert owned == COURTYARD_DEPENDENCIES
    assert menu == [*browse_ids, *owned]
    assert set(owned).isdisjoint(browse_ids)
    for key, owner in owned.items():
        assembly = entries[owner]
        folder = Path(assembly["file"])
        assert Path(entries[key]["file"]).parent == folder.with_suffix("")
        assert any(part["id"] == key for part in assembly["parts"]), (owner, key)
    courtyard = next(row for row in graph["categories"] if row["id"] == "courtyard")
    courtyard_ids = {leaf["id"] for leaf in catalog_leaves(courtyard["children"])}
    assert len(courtyard_ids) == report["courtyard_previews"] == COURTYARD_COUNT
    for section in courtyard["children"]:
        extension = ".glb" if section["id"] == "courtyard-parts" else ".scn"
        for leaf in catalog_leaves(section["children"]):
            assert entries[leaf["id"]]["file"].endswith(extension), leaf["id"]
    assert courtyard_ids | owned.keys() == {
        key for key, row in entries.items() if row["file"].startswith("courtyard/")
    }
    assert set(menu) == entries.keys(), "Asset index and menu differ"
    menu_files = {entries[key]["file"] for key in menu}
    assert len(menu_files) == len(menu) == report["assets"], "Duplicate menu file"
    files = {
        path.relative_to(assets).as_posix()
        for path in assets.rglob("*")
        if path.is_file()
    }
    assert menu_files <= files, f"Missing asset files: {sorted(menu_files - files)}"
    textures = {
        file for file in files if file.startswith("textures/") and file.endswith(".png")
    }
    assert files - textures == menu_files, (
        f"Asset files outside the menu: {sorted(files - textures - menu_files)}"
    )
    assemblies = {
        key
        for key, entry in entries.items()
        if entry["file"].endswith(".scn")
        and entry["file"].startswith(("furniture/", "courtyard/"))
    }
    assert set(report["glb_assemblies"]) == assemblies, "Unverified GLB assemblies"
    for key in assemblies:
        file = assets / entries[key]["file"]
        assert (
            hashlib.sha256(file.read_bytes()).hexdigest()
            == report["glb_assemblies"][key]
        ), key
    previews = json.loads((FURNITURE / "asset-previews.json").read_text())
    assert previews.keys() == entries.keys(), "Asset index and preview index differ"
    for key, entry in entries.items():
        for part in entry.get("parts", []):
            target = entries[part["id"]]
            if "component" in part:
                assert any(
                    item["id"] == part["component"] for item in target["components"]
                ), (key, part["id"])
        assert set(entry.get("members", [])) <= entries.keys(), key
    geometry = json.loads((FURNITURE / "geometry-owners.json").read_text())
    assert set(geometry.values()) <= menu_files, "Geometry source missing from menu"
    pending = [
        leaf["id"]
        for leaf in catalog_leaves(furniture_browse_categories(graph["categories"]))
    ]
    reachable = set()
    while pending:
        key = pending.pop()
        if key in reachable:
            continue
        reachable.add(key)
        pending.extend(entries[key].get("members", []))
        pending.extend(part["id"] for part in entries[key].get("parts", []))
    assert reachable == entries.keys(), (
        "Files unreachable from menu",
        entries.keys() - reachable,
    )
    return {
        "menu_files": len(menu_files),
        "references": sum(len(entry.get("parts", [])) for entry in entries.values()),
        "textures": len(textures),
    }


def furniture_browse_categories(items):
    """Keep assembly resources indexed without giving them duplicate browse entries."""
    return [
        {**item, "children": furniture_browse_categories(item["children"])}
        if "children" in item
        else item
        for item in items
        if not item["id"].startswith("placement:bedroom-")
        and item["id"] != "view:central-games-bookshelf"
    ]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nest_menu_ids(items, path=()):
    assert items, f"Empty menu folder: {path}"
    assert len({item["id"] for item in items}) == len(items), path
    assert len({item["label"] for item in items}) == len(items), path
    for item in items:
        if "children" in item:
            yield from nest_menu_ids(item["children"], (*path, item["label"]))
        else:
            yield item["id"]


def nest_files(*folders: str) -> Iterator[Path]:
    """Use the same authoring directory boundary as the Godot importer."""
    for folder in folders:
        for directory, children, names in walk(NEST / folder):
            if ".gdignore" in names:
                children.clear()
                continue
            parent = Path(directory)
            for name in names:
                path = parent / name
                if path.is_file():
                    yield path


def audit_nest_files(index):
    graph = index["fileGraph"]
    entries = graph["entries"]
    asset_files = {
        path.relative_to(NEST).as_posix()
        for path in nest_files(*NEST_ASSET_FOLDERS)
        if path.suffix in {".glb", ".scn", ".tscn"}
    }
    files = {entry["file"] for entry in entries.values()}
    assert len(files) == len(entries), "More than one entry for a formal file"
    assert files == asset_files, (
        f"Missing files: {sorted(files - asset_files)}",
        f"Unindexed files: {sorted(asset_files - files)}",
    )
    assert entries.keys() == index["previews"].keys(), "Preview and file index differ"
    menu = list(nest_menu_ids(graph["categories"]))
    assert len(set(menu)) == len(menu), "Duplicate formal menu entry"
    menu_ids = set(menu)
    assert menu_ids == entries.keys(), (
        f"Files without a menu entry: {sorted(entries.keys() - menu_ids)}",
        f"Menu entries without a file: {sorted(menu_ids - entries.keys())}",
    )
    references = set()
    referenced_by = set()
    for key, entry in entries.items():
        assert entry["preview"] == key, key
        assert set(entry.get("members", [])) <= entries.keys(), key
        paths = [path for group in index["previews"][key]["groups"] for path in group]
        if paths:
            assert len(paths) == len(set(paths)) and set(paths) == set(
                entry["focus"]
            ), key
        references.update((key, row["id"]) for row in entry.get("parts", []))
        referenced_by.update((row["id"], key) for row in entry.get("usedBy", []))
    assert all(source in entries and target in entries for source, target in references)
    assert references == referenced_by, (
        f"Missing reverse references: {sorted(references - referenced_by)}",
        f"Orphan reverse references: {sorted(referenced_by - references)}",
    )
    courtyard = next(
        category for category in graph["categories"] if category["id"] == "courtyard"
    )
    for section in courtyard["children"]:
        if section["id"] == "courtyard-overview":
            continue  # The full garden and its environment each have a file.
        extensions = (
            {".glb"} if section["id"] == "courtyard-parts" else {".scn", ".tscn"}
        )
        for leaf in catalog_leaves(section["children"]):
            assert Path(entries[leaf["id"]]["file"]).suffix in extensions, leaf
    return graph


def nest_source_fingerprint():
    sources = {
        GODOT / "project.godot",
        NEST / "nest.tscn",
        Path(__file__),
        GODOT / "tools/pack_nest_assets.gd",
        GODOT / "tools/static_asset_review.gd",
        GODOT / "tools/review_asset_sizes.py",
    }
    sources.update(
        path
        for path in nest_files(*NEST_ASSET_FOLDERS, "rendering")
        if path.suffix != ".md"
    )
    digest = hashlib.sha256()
    for path in sorted(sources):
        digest.update(f"{path.relative_to(ROOT).as_posix()}\0{sha256(path)}\0".encode())
    return digest.hexdigest()


def publish_nest_assets(source_fingerprint=None):
    report = json.loads((NEST_WEB / "report.json").read_text())
    index = json.loads(NEST_INDEX.read_text())
    graph = audit_nest_files(index)
    assert report["assets"].keys() == graph["entries"].keys()
    assert all(count > 0 for count in report["assets"].values())
    assert report["index_sha256"] == sha256(NEST_INDEX)
    assert report["controller_sha256"] == sha256(GODOT / "tools/static_asset_review.gd")
    for resource, expected in report["source_hashes"].items():
        source = GODOT / resource.removeprefix("res://")
        assert sha256(source) == expected, f"Source changed after packing: {resource}"
    pack = NEST_WEB / "nest-assets.pck"
    pack_sha = sha256(pack)
    assert pack_sha == report["pack_sha256"], "Formal pack changed after verification"
    add_asset_sizes(graph["entries"], NEST)
    graph["root"] = "res://nest/"
    publish_pack(
        pack,
        {
            "assets": len(graph["entries"]),
            "sha256": pack_sha,
            "packBytes": pack.stat().st_size,
            "sourceFingerprint": source_fingerprint or nest_source_fingerprint(),
            "shellSha256": sha256(WEB / "elfienest.html"),
            "fileGraph": graph,
        },
    )
    print(f"Nest Lab now serves {len(graph['entries'])} formal asset files")


def nest_assets_current(fingerprint=None):
    fingerprint = fingerprint or nest_source_fingerprint()
    try:
        manifest = json.loads((WEB / "nest-assets.json").read_text())
        if (
            manifest.get("sourceFingerprint") == fingerprint
            and manifest.get("shellSha256") == sha256(WEB / "elfienest.html")
            and (WEB / "nest-assets.html").is_file()
            and (WEB / "nest-assets.pck").stat().st_size == manifest.get("packBytes")
        ):
            return sha256(WEB / "nest-assets.pck") == manifest.get("sha256")
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return False


def publish(shared: bool = False, furniture: bool = False) -> None:
    if furniture:
        portable = json.loads((FURNITURE / "review-report.json").read_text())
        pack = FURNITURE / "v044-furniture-assets.pck"
    elif shared:
        portable = json.loads((SHARED / "review-report.json").read_text())
        pack = SHARED / "v044-shared-assets.pck"
    else:
        report = json.loads((REVIEW / "assembly-report.json").read_text())
        portable = json.loads((REVIEW / "portable-report.json").read_text())
        assert report["passed"] and portable["assets"] == report["asset_views"]
        pack = REVIEW / "v044-assets.pck"
    assert portable["passed"]
    pack_sha = sha256(pack)
    assert portable["pack_sha256"] == pack_sha
    manifest = {"assets": portable["assets"], "sha256": pack_sha}
    if furniture:
        graph = json.loads((FURNITURE / "file-graph.json").read_text())
        menu = json.loads((FURNITURE / "menu.json").read_text())
        portable["file_audit"] = audit_furniture_files(graph, menu, portable)
        graph["categories"] = furniture_browse_categories(graph["categories"])
        add_asset_sizes(graph["entries"], FURNITURE / "assets")
        (FURNITURE / "review-report.json").write_text(
            json.dumps(portable, ensure_ascii=False, indent=2) + "\n"
        )
        manifest["fileGraph"] = graph
    elif shared:
        plan = json.loads((SHARED / "assembly-plan.json").read_text())
        assert plan["snapshot_sha256"] == portable["frozen_sha256"]
        inventory = json.loads(
            (SHARED.parent / "full-inventory/static-nodes.json").read_text()
        )
        catalog = json.loads(
            (
                ROOT / "godot_project/tools/nest_authoring/v044-asset-catalog.json"
            ).read_text()
        )
        assert len(plan["views"]) == portable["assets"]
        authoring = prepare_menu_assets(SHARED, plan)
        manifest["fileGraph"] = build_menu(
            plan, inventory, catalog["categories"], SHARED, authoring
        )
    publish_pack(pack, manifest)
    print("V044 review published on the existing /godot-web mount")


def publish_pack(pack, manifest):
    shell = (WEB / "elfienest.html").read_text()
    marker = "const engine = new Engine(GODOT_CONFIG);"
    assert shell.count(marker) == 1
    shell = shell.replace(
        marker,
        f"GODOT_CONFIG.mainPack = '{pack.name}';\n"
        f"GODOT_CONFIG.fileSizes['{pack.name}'] = {pack.stat().st_size};\n" + marker,
    )
    target = WEB / pack.name
    temp = target.with_suffix(".tmp")
    shutil.copyfile(pack, temp)
    temp.replace(target)
    (WEB / f"{pack.stem}.html").write_text(shell)
    manifest_path = WEB / f"{pack.stem}.json"
    temp_manifest = manifest_path.with_suffix(".json.tmp")
    temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False))
    temp_manifest.replace(manifest_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--shared-candidate", action="store_true")
    mode.add_argument("--furniture-candidate", action="store_true")
    mode.add_argument("--nest-assets", action="store_true")
    mode.add_argument("--check-nest-assets", action="store_true")
    parser.add_argument("--web-output", type=Path, default=WEB)
    arguments = parser.parse_args()
    WEB = arguments.web_output.resolve()
    if arguments.check_nest_assets:
        raise SystemExit(0 if nest_assets_current() else 1)
    elif arguments.nest_assets:
        publish_nest_assets()
    else:
        publish(
            shared=arguments.shared_candidate, furniture=arguments.furniture_candidate
        )
