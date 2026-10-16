"""Typed local asset index; geometry stays in the original design files."""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

ASSET_ROOT = Path(__file__).parent / "assets"


class AssetFile(BaseModel):
    path: str
    name: str
    kind: str
    bytes: int


class Lamp(BaseModel):
    floor: int
    position: list[float]
    module: str = "central"


class Asset(BaseModel):
    id: str
    category: str
    title: str
    description: str = ""
    version: Optional[int] = None
    primaryModel: Optional[str] = None
    models: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    thumbnail: Optional[str] = None
    modes: list[str] = Field(default_factory=list)
    measurements: Optional[str] = None
    referenceFloors: dict[str, str] = Field(default_factory=dict)
    lamps: list[Lamp] = Field(default_factory=list)
    files: list[AssetFile] = Field(default_factory=list)
    designObject: Optional[dict] = None
    designVersion: Optional[dict] = None
    archived: bool = False


class ImageReference(BaseModel):
    path: str
    objects: list[str] = Field(min_length=1)
    title: str
    kind: Literal["reference", "render", "layout", "history"]
    version: Optional[str] = None


class Catalog(BaseModel):
    assets: list[Asset] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    imageReferences: list[ImageReference] = Field(default_factory=list)


def load_catalog(root: Path) -> Catalog:
    """Read current saved data without rewriting assets or creating directories."""
    index = root / "catalog.json"
    catalog = (
        Catalog.model_validate_json(index.read_text()) if index.is_file() else Catalog()
    )
    files = {}
    for asset in catalog.assets:
        for file in asset.files:
            path = (root / file.path).resolve()
            if path.is_relative_to(root.resolve()) and path.is_file():
                file.bytes = path.stat().st_size
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
    return catalog


def registered_file(root: Path, relative: str) -> Optional[Path]:
    """Allow only indexed files that resolve inside this workbench's asset root."""
    if not any(
        relative == file.path
        for asset in load_catalog(root).assets
        for file in asset.files
    ):
        return None
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return None
    if path.suffix.lower() in {".html", ".js", ".mjs", ".cjs", ".css", ".py"}:
        return None
    return path
