"""Local object adoption and pinned preview plans, isolated from production data."""

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
    asset = next((a for a in load_catalog(root).assets if a.id == asset_id), None)
    for record in read_state(root)["history"]:
        if asset_id in {record["version"], *(ref["version"] for ref in record["refs"])}:
            raise HTTPException(409, "Version retained by an object confirmation")
        if asset and asset.designObject:
            for entry in [record, *record["refs"]]:
                if entry["object"] == asset.designObject["id"] and (
                    entry["version"] == asset.designVersion["id"]
                    or entry.get("contentDigest")
                    == asset.designVersion["contentDigest"]
                ):
                    raise HTTPException(
                        409, "Independent model retained by a confirmation"
                    )


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
            layers, issues = [], []
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
                            record = state["current"][candidate["id"]]
                            for ref in record["refs"]:
                                current = state["current"].get(ref["object"])
                                if not current or (current.get("contentDigest"),) != (
                                    ref.get("contentDigest"),
                                ):
                                    issues.append(
                                        {
                                            "object": candidate["id"],
                                            "reason": "参考版本已变，待检查",
                                        }
                                    )
                            if candidate["group"] == "layout" and not any(
                                ref["object"].startswith("building:")
                                for ref in record["refs"]
                            ):
                                issues.append(
                                    {
                                        "object": candidate["id"],
                                        "reason": "尚未结合已确认建筑检查",
                                    }
                                )
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
                    needed = reference_needed(obj, candidate)
                    if needed:
                        reference = current_layer(
                            objects, candidate["id"], state, issues, True
                        )
                        if (
                            reference is None
                            and candidate["group"] == "building"
                            and candidate["id"] not in state["current"]
                            and candidate["versions"]
                        ):
                            reference = layer(candidate, candidate["versions"][0], True)
                            reference["unconfirmed"] = True
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
            previous = state["current"].get(object)
            adopted = bool(
                previous
                and layers
                and previous.get("contentDigest")
                and previous["contentDigest"] == layers[0].get("contentDigest")
            )
            if adopted:
                old_refs = {
                    r["object"]: r.get("contentDigest") for r in previous["refs"]
                }
                new_refs = {
                    r["object"]: r.get("contentDigest")
                    for r in layers
                    if r["reference"]
                }
                if old_refs != new_refs:
                    issues.append(
                        {
                            "object": object,
                            "reason": "对象已确认；参考组合已变化，待检查",
                        }
                    )
            plan = {
                "object": object,
                "version": version
                or (obj["versions"][0]["id"] if obj and object != "overview" else None),
                "layers": layers,
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
            for entry in plan["layers"]:
                _, source = version_for(objects, entry["object"], entry["version"])
                if source.get("contentDigest") != entry.get(
                    "contentDigest"
                ) or not entry.get("contentDigest"):
                    raise HTTPException(
                        409, "Preview source changed; reload before confirming"
                    )
            source = plan["layers"][0]
            record = {
                "id": uuid4().hex,
                "object": plan["object"],
                "version": source["version"],
                "digest": source["digest"],
                "contentDigest": source["contentDigest"],
                "refs": [
                    {
                        "object": e["object"],
                        "version": e["version"],
                        "digest": e["digest"],
                        "contentDigest": e["contentDigest"],
                    }
                    for e in plan["layers"]
                    if e["reference"]
                ],
                "at": datetime.now(timezone.utc).isoformat(),
            }
            state["current"][plan["object"]] = record
            state["history"].append(record)
            root.mkdir(parents=True, exist_ok=True)
            write_json(checked_file(root.resolve(), STATE_FILE), state)
            return record

    return router
