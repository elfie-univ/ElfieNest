"""Catalog response models shared by storage and HTTP delivery."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


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
