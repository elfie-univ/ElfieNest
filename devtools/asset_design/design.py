"""Independent object adoption with live confirmed reference previews."""

import copy
import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from devtools.asset_design.catalog import load_catalog
from devtools.asset_design.deletion import checked_file, write_json
from devtools.asset_design.design_catalog import GROUPS, inventory
from devtools.asset_design.design_groups import (
    can_confirm,
    reference_needed,
    review_scopes,
)
from devtools.asset_design.design_models import read_model
from devtools.asset_design.glb_resources import read_glb
from devtools.asset_design.template_instances import (
    resolve_templates,
    template_dependencies,
)

ASSET_LOCK = RLock()
STATE_FILE = "adoptions.json"


def read_state(root):
    file = checked_file(root.resolve(), STATE_FILE)
    if not file.exists():
        return {"current": {}, "history": []}
    try:
        data = json.loads(file.read_text())
        if not isinstance(data["current"], dict) or not isinstance(
            data["history"], list
        ):
            raise ValueError("Invalid adoption state")
        return data
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(409, "Confirmation data needs inspection") from error


def assert_not_adopted(root, asset_id):
    assets = load_catalog(root).assets
    asset = next((a for a in assets if a.id == asset_id), None)
    if asset and asset.designObject and asset.designObject["id"].startswith("part:"):
        identifier = asset.designObject["id"]
        revisions = [
            a
            for a in assets
            if a.designObject and a.designObject["id"] == identifier and not a.archived
        ]
        if len(revisions) == 1:
            for consumer in assets:
                if consumer.archived or not consumer.designVersion:
                    continue
                doc, _ = read_glb(
                    checked_file(root.resolve(), consumer.designVersion["file"])
                )
                if any(
                    i["object"] == identifier
                    for i in doc.get("extras", {}).get("templateInstances", [])
                ):
                    raise HTTPException(
                        409, "Last furniture mother retained by a scene reference"
                    )
    retained_ids = {asset_id}
    if asset and asset.designVersion:
        retained_ids.add(asset.designVersion["id"])
    if any(
        record["version"] in retained_ids
        for record in read_state(root)["current"].values()
    ):
        raise HTTPException(409, "Current object confirmation retains this version")


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sceneId: str
    expectedCurrent: Optional[str] = None


def build_design_router(root: Path):
    router = APIRouter(prefix="/assets/design/design")
    plans = OrderedDict()

    def items():
        data = inventory(root)
        return data, {o["id"]: o for o in data["objects"]}

    def version_for(objects, obj_id, version_id):
        obj = objects.get(obj_id)
        version = (
            next(
                (
                    v
                    for v in [*obj["versions"], *obj.get("archivedVersions", [])]
                    if v["id"] == version_id
                    or any(s["asset"] == version_id for s in v.get("sources", []))
                ),
                None,
            )
            if obj
            else None
        )
        if version is None:
            raise HTTPException(409, "Saved object version unavailable")
        if version.get("archiveFile"):
            raise HTTPException(
                409, "Object revision archived; restore it before previewing"
            )
        return obj, version

    def layer(obj, version, reference=False):
        return {
            **version,
            "object": obj["id"],
            "version": version["id"],
            "group": obj["group"],
            "module": obj["module"],
            "floor": obj["floor"],
            "reference": reference,
            "label": obj["label"],
        }

    def current_layer(objects, obj_id, state, issues, reference=False):
        record = state["current"].get(obj_id)
        if record is None:
            issues.append({"object": obj_id, "reason": "待确认"})
            return None
        try:
            obj, version = version_for(objects, obj_id, record["version"])
        except HTTPException:
            issues.append({"object": obj_id, "reason": "已确认源文件缺失"})
            return None
        if not record.get("contentDigest"):
            issues.append({"object": obj_id, "reason": "原确认记录待对象内容核验"})
            return None
        if version.get("contentDigest") != record["contentDigest"]:
            issues.append({"object": obj_id, "reason": "已确认源文件已改变"})
            return None
        return layer(obj, version, reference)

    @router.get("/index")
    def index(response: Response):
        response.headers["Cache-Control"] = "no-store"
        with ASSET_LOCK:
            data, _ = items()
            state = read_state(root)
            for obj in data["objects"]:
                obj["current"] = state["current"].get(obj["id"])
                obj.pop("archivedVersions", None)
                for version in obj["versions"]:
                    version.pop("nodes", None)
            return {**data, "groups": GROUPS}

    @router.get("/scene")
    def scene(
        response: Response, object: str = Query(...), version: Optional[str] = None
    ):
        response.headers["Cache-Control"] = "no-store"
        with ASSET_LOCK:
            _, objects = items()
            state = read_state(root)
            layers: list[dict] = []
            issues: list[dict[str, str]] = []
            obj = objects.get(object)
            if object == "overview" and version is None:
                for candidate in objects.values():
                    if (
                        candidate["group"] in {"building", "layout", "landscape"}
                        and candidate["space"] == "estate"
                        and not candidate.get("aggregate")
                        and not candidate.get("historical")
                    ):
                        selected = current_layer(
                            objects, candidate["id"], state, issues
                        )
                        if selected:
                            if selected.get("instanceCount", 0) > len(
                                selected.get("placements", {})
                            ):
                                issues.append(
                                    {
                                        "object": candidate["id"],
                                        "reason": "缺少小屋定位，待检查",
                                    }
                                )
                                continue
                            layers.append(selected)

            else:
                if obj is None:
                    raise HTTPException(404, "Object unavailable")
                obj, selected = version_for(
                    objects, object, version or obj["versions"][0]["id"]
                )
                if selected.get("members"):
                    for member in selected["members"]:
                        member_obj, member_version = version_for(
                            objects, member["object"], member["version"]
                        )
                        layers.append(layer(member_obj, member_version))
                else:
                    layers.append(layer(obj, selected))
                for candidate in objects.values():
                    if reference_needed(obj, candidate):
                        reference = current_layer(
                            objects, candidate["id"], state, issues, True
                        )
                        if reference:
                            # A part's surrounding kit excludes its old counterpart.
                            if obj["id"].startswith("part:"):
                                records, _ = read_model(root, reference["file"])
                                excluded = {
                                    r["node"]
                                    for r in records
                                    if re.sub(
                                        r"_drawer_\d+$", "", str(r.get("assembly", ""))
                                    )
                                    == obj["id"].removeprefix("part:")
                                }
                                reference["nodes"] = sorted(
                                    set(reference["nodes"]) - excluded
                                )
                            layers.append(reference)
            try:
                for entry in layers:
                    instances = resolve_templates(root, entry, objects, state)
                    if obj and obj["id"].startswith("part:") and entry["reference"]:
                        instances = [i for i in instances if i["object"] != obj["id"]]
                    if instances:
                        entry["templateInstances"] = instances
                dependencies = template_dependencies(layers)
            except (ValueError, KeyError, IndexError, OSError, TypeError) as error:
                raise HTTPException(
                    409, "Furniture composition unavailable: " + str(error)
                ) from error
            previous = state["current"].get(object)
            adopted = bool(
                previous
                and layers
                and not layers[0].get("draft")
                and previous.get("contentDigest")
                and previous["contentDigest"] == layers[0].get("contentDigest")
                and previous["version"] == layers[0]["version"]
            )
            plan = {
                "object": object,
                "version": version
                or (obj["versions"][0]["id"] if obj and object != "overview" else None),
                "layers": layers,
                "templates": dependencies,
                "issues": issues,
                "expectedCurrent": previous["id"] if previous else None,
                "review": review_scopes(objects, obj) if obj else None,
                "confirmable": can_confirm(obj),
                "adopted": adopted,
            }
            plan["id"] = hashlib.sha256(
                json.dumps(plan, sort_keys=True).encode()
            ).hexdigest()
            plans[plan["id"]] = copy.deepcopy(plan)
            while len(plans) > 256:
                plans.popitem(last=False)
            return plan

    @router.post("/confirm")
    def confirm(change: Confirmation, request: Request):
        origin = request.headers.get("origin")
        if (
            origin and origin != str(request.base_url).rstrip("/")
        ) or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Confirm from this local workbench")
        with ASSET_LOCK:
            plan = plans.get(change.sceneId)
            if not plan or not plan["confirmable"]:
                raise HTTPException(409, "Reload the object preview before confirming")
            state = read_state(root)
            previous = state["current"].get(plan["object"])
            expected = previous["id"] if previous else None
            if (
                change.expectedCurrent != expected
                or change.expectedCurrent != plan["expectedCurrent"]
            ):
                raise HTTPException(
                    409, "Object was confirmed elsewhere; reload before confirming"
                )
            _, objects = items()
            owned_layers = [entry for entry in plan["layers"] if not entry["reference"]]
            for entry in owned_layers:
                _, source = version_for(objects, entry["object"], entry["version"])
                if (
                    source.get("contentDigest") != entry.get("contentDigest")
                    or not entry.get("contentDigest")
                    or (entry.get("draft") and source["digest"] != entry["digest"])
                ):
                    raise HTTPException(
                        409, "Preview source changed; reload before confirming"
                    )
            from devtools.asset_design.working_drafts import freeze_working_layers

            saved_layers = freeze_working_layers(root, owned_layers)
            source = saved_layers[0]
            record = {
                "id": uuid4().hex,
                "object": plan["object"],
                "version": source["version"],
                "digest": source["digest"],
                "contentDigest": source["contentDigest"],
                "at": datetime.now(timezone.utc).isoformat(),
            }
            state["current"][plan["object"]] = record
            state["history"].append(record)
            root.mkdir(parents=True, exist_ok=True)
            write_json(checked_file(root.resolve(), STATE_FILE), state)
            return record

    return router
