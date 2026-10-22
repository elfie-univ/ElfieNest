"""Observe file identities once; reuse catalog statistics until an input changes."""

from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from stat import S_ISREG
from threading import RLock

from devtools.asset_design.catalog_models import AssetFile, Catalog
from devtools.asset_design.catalog_store import read_catalog, snapshot_catalog
from devtools.asset_design.paths import object_directory

_LOCK = RLock()
_CATALOGS: OrderedDict[Path, tuple[tuple, Catalog]] = OrderedDict()


def file_stamp(path: Path) -> tuple:
    try:
        value = path.stat()
        link = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return ()
    return (
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_size,
        value.st_ino,
        value.st_mode,
        link.st_ctime_ns,
        link.st_ino,
        link.st_mode,
    )


@lru_cache(maxsize=8)
def _registered(root: Path, metadata: tuple) -> Catalog:
    del metadata
    return Catalog.model_validate(read_catalog(root))


def observe_catalog(root: Path) -> tuple[Catalog, tuple]:
    """Return a read-only projection and a signature covering registered inputs."""
    root = root.resolve()
    with _LOCK:
        metadata = tuple(snapshot_catalog(root).items())
        base = _registered(root, metadata)
        paths = {file.path for asset in base.assets for file in asset.files}
        for asset in base.assets:
            paths.update(asset.models)
            if asset.primaryModel:
                paths.add(asset.primaryModel)
            if asset.designVersion:
                paths.add(asset.designVersion["file"])
            if asset.designObject:
                folder = object_directory(root, asset.designObject["id"]) / "source"
                paths.update(
                    (folder / name).relative_to(root).as_posix()
                    for name in ("build.json", "model.glb")
                )
        states, parents = {}, {root}
        for relative in sorted(paths):
            value = Path(relative)
            if value.is_absolute() or ".." in value.parts:
                states[relative] = ()
                continue
            path = root / value
            states[relative] = file_stamp(path)
            for parent in path.parents:
                if parent in parents:
                    break
                parents.add(parent)
                if parent == root:
                    break
        signature = (
            metadata,
            tuple(states.items()),
            tuple((str(p), file_stamp(p)) for p in sorted(parents)),
            tuple(
                file_stamp(root / p)
                for p in ("adoptions.json", ".design-adoptions.json")
            ),
        )
        cached = _CATALOGS.get(root)
        if cached and cached[0] == signature:
            return cached[1], signature
        catalog = base.model_copy(deep=True)
        files: dict[str, AssetFile] = {}
        safe: dict[str, bool] = {}
        for asset in catalog.assets:
            for file in asset.files:
                state = states[file.path]
                if not state or not S_ISREG(state[4]):
                    continue
                if file.path not in safe:
                    safe[file.path] = (root / file.path).resolve().is_relative_to(root)
                if safe[file.path]:
                    file.bytes = state[2]
                    files[file.path] = file
        catalog.stats = {
            "directories": sum(
                p.is_dir() and not p.name.startswith(".") for p in root.iterdir()
            )
            if root.is_dir()
            else 0,
            "records": len(catalog.assets),
            "files": len(files),
            "models": sum(f.kind == "model" for f in files.values()),
            "sources": sum(f.kind == "source" for f in files.values()),
            "images": sum(f.kind == "image" for f in files.values()),
            "bytes": sum(f.bytes for f in files.values()),
        }
        _CATALOGS[root] = (signature, catalog)
        _CATALOGS.move_to_end(root)
        while len(_CATALOGS) > 8:
            _CATALOGS.popitem(last=False)
        return catalog, signature
