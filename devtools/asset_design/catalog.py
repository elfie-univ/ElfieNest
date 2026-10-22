"""Typed local asset index; geometry stays in the original design files."""

from pathlib import Path
from stat import S_ISREG
from typing import Optional

from devtools.asset_design.catalog_models import Asset as Asset
from devtools.asset_design.catalog_models import AssetFile as AssetFile
from devtools.asset_design.catalog_models import Catalog as Catalog
from devtools.asset_design.catalog_models import ImageReference as ImageReference
from devtools.asset_design.catalog_models import Lamp as Lamp
from devtools.asset_design.catalog_observation import observe_catalog
from devtools.asset_design.catalog_registration import registered_path

ASSET_ROOT = Path(__file__).parent / "assets"


def load_catalog(root: Path) -> Catalog:
    """Read current saved data without rewriting assets or creating directories."""
    return observe_catalog(root)[0].model_copy(deep=True)


def registered_file(root: Path, relative: str) -> Optional[Path]:
    """Allow only indexed files that resolve inside this workbench's asset root."""
    root = root.resolve()
    index = root / "catalog.json"
    try:
        stat = index.stat()
    except FileNotFoundError:
        return None
    if not S_ISREG(stat.st_mode) or not registered_path(root, relative):
        return None
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    if path.suffix.lower() in {".html", ".js", ".mjs", ".cjs", ".css", ".py"}:
        return None
    return path
