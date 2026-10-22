"""Keep original local exports and source-only versions in their content collection."""

from typing import Optional

from devtools.asset_design.catalog import Asset
from devtools.asset_design.design_groups import historical_collection


def add_history(
    objects: dict[str, dict],
    asset: Asset,
    file: Optional[str] = None,
    records: Optional[list[dict]] = None,
    digest: str = "",
) -> bool:
    if file and not records:
        return False
    content = [record for record in records or [] if not record.get("reference")]
    family, label, group, combined = historical_collection(asset.category, content)
    if not file and asset.category in {"pod", "room", "early", "central"}:
        family = "building:central" if asset.category == "central" else "building:pod"
        label, group = ("主楼" if asset.category == "central" else "小屋"), "building"
    key = "saved:" + asset.id
    objects[key] = {
        "id": key,
        "label": "仅源文件"
        if not file
        else "历史整套（含建筑和家具）"
        if combined
        else "历史完整模型",
        "group": group,
        "space": "archive",
        "module": "",
        "floor": "",
        "collection": family,
        "collectionLabel": label,
        "historical": True,
        "versions": [
            {
                "id": asset.id,
                "asset": asset.id,
                "title": asset.title,
                "file": file,
                "digest": digest,
                "nodes": sorted(r["node"] for r in records or []),
                "measurements": asset.measurements,
                "sourceOnly": not file,
            }
        ],
    }
    return True
