"""CLI for the read-only database change inventory and boundary guard."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

try:
    from scripts.architecture.database_change_inventory import (
        PROJECT_ROOT,
        DatabaseInventory,
        check,
        collect_inventory,
        render_inventory,
    )
except (
    ModuleNotFoundError
):  # Direct script execution places this directory on sys.path.
    from database_change_inventory import (  # type: ignore[no-redef]
        PROJECT_ROOT,
        DatabaseInventory,
        check,
        collect_inventory,
        render_inventory,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--base-sha", help="also report database files changed from this base"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the inventory as JSON"
    )
    parser.add_argument(
        "--check", action="store_true", help="fail on detected boundary violations"
    )
    return parser


def _print_inventory(inventory: DatabaseInventory, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "references": [
                        asdict(reference) for reference in inventory.references
                    ],
                    "parse_errors": list(inventory.parse_errors),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_inventory(inventory))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = args.project_root.resolve()
    inventory = collect_inventory(project_root)
    if args.check and args.base_sha is not None:
        failures = check(project_root, args.base_sha, inventory)
    else:
        _print_inventory(inventory, args.json)
        failures = check(project_root, inventory=inventory) if args.check else ()
    if failures:
        print("Database boundary violations:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
