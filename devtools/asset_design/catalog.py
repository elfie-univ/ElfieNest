"""Typed local asset index; geometry stays in the original design files."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

ASSET_ROOT = Path(__file__).resolve().parents[2] / "build" / "asset_previews"


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


class Catalog(BaseModel):
    assets: list[Asset] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


def load_catalog(root: Path) -> Catalog:
    """Read current saved data without rewriting assets or creating directories."""
    index = root / "catalog.json"
    return (
        Catalog.model_validate_json(index.read_text()) if index.is_file() else Catalog()
    )


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
