"""Audit object revisions and explicitly bind saved confirmations to their content."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from devtools.asset_design.catalog import ASSET_ROOT, load_catalog
from devtools.asset_design.catalog_store import snapshot_catalog
from devtools.asset_design.deletion import write_json
from devtools.asset_design.design_catalog import inventory
from devtools.asset_design.object_content import content_digest
from devtools.asset_design.paths import WORK_ROOT


def reconcile(root, *, apply=False):
    catalog_before = snapshot_catalog(root)
    raw = inventory(root, independent=False)
    objects = {o["id"]: o for o in raw["objects"]}
    state_file = root / "adoptions.json"
    original = state_file.read_bytes() if state_file.exists() else None
    state = json.loads(original) if original else {"current": {}, "history": []}
    upgraded = copy.deepcopy(state)

    def bind(record, object_id):
        obj = objects.get(object_id, {})
        version = next(
            (v for v in obj.get("versions", []) if v["id"] == record["version"]), None
        )
        if version is None:
            raise ValueError(
                f"Confirmed source missing: {object_id}/{record['version']}"
            )
        value = content_digest(root, version["file"], version["nodes"])
        if record.get("contentDigest"):
            if record["contentDigest"] != value:
                raise ValueError(f"Confirmed object changed: {object_id}")
        elif version["digest"] != record["digest"]:
            raise ValueError(f"Original confirmation source changed: {object_id}")
        record["contentDigest"] = value

    for object_id, record in upgraded["current"].items():
        bind(record, object_id)

    grouped = inventory(root)
    catalog = load_catalog(root)
    indexed = {f.path for a in catalog.assets for f in a.files}
    report = {
        "modelsModified": False,
        "historyDeleted": False,
        "confirmationBackupDigest": hashlib.sha256(original).hexdigest()
        if original
        else None,
        "confirmedObjects": list(upgraded["current"]),
        "issues": grouped["issues"],
        "objects": [
            {
                "id": o["id"],
                "label": o["label"],
                "classification": "historical-view"
                if o.get("historical")
                else "composition-view"
                if o.get("aggregate") or o["id"] == "overview"
                else "independent-object",
                "versions": [
                    {
                        k: v[k]
                        for k in (
                            "id",
                            "title",
                            "file",
                            "digest",
                            "contentDigest",
                            "sources",
                        )
                        if k in v
                    }
                    for v in o["versions"]
                ],
            }
            for o in grouped["objects"]
        ],
        "unindexedFiles": sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).as_posix() not in indexed
        ),
    }
    if apply and original and upgraded != state:
        if grouped["issues"]:
            raise ValueError(
                "Unclassified model content; inspect audit before applying"
            )
        backup = (
            WORK_ROOT
            / "audit"
            / "backups"
            / (report["confirmationBackupDigest"] + ".json")
        )
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists() and backup.read_bytes() != original:
            raise ValueError("Confirmation backup conflict")
        if not backup.exists():
            backup.write_bytes(original)
        if (
            state_file.read_bytes() != original
            or snapshot_catalog(root) != catalog_before
        ):
            raise ValueError("Confirmations changed during audit; rerun")
        write_json(state_file, upgraded)
        report["confirmationBackup"] = str(backup)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ASSET_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = reconcile(args.root.resolve(), apply=args.apply)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(
        json.dumps(
            {
                "report": str(args.report),
                "issues": report["issues"],
                "confirmedObjects": report["confirmedObjects"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
