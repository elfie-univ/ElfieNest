#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pydantic>=2", "PyYAML>=6"]
# ///
# How to run: uv run --no-sync python scripts/export_elfie_contract_schemas.py
"""Export deterministic JSON Schema for Elfie cross-module contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

from pydantic import TypeAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from elfie.body.contracts import BodyCommand, BodySensorEvent
from elfie.brain.context_types import BrainContext
from elfie.brain.decision_types import DecisionPlan
from elfie.brain.output_types import ExecutionReceipt
from elfie.communication.contracts import CommunicationEnvelope
from elfie.message_types import MessageMeta

DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "contracts" / "elfie" / "v1"


def render_contract_schemas() -> Dict[str, str]:
    """Return filename-to-JSON mappings with stable key and file ordering."""
    schemas = {
        "body-command.schema.json": TypeAdapter(BodyCommand).json_schema(),
        "body-sensor-event.schema.json": BodySensorEvent.model_json_schema(),
        "brain-context.schema.json": BrainContext.model_json_schema(),
        "communication-envelope.schema.json": (
            CommunicationEnvelope.model_json_schema()
        ),
        "decision-plan.schema.json": DecisionPlan.model_json_schema(),
        "execution-receipt.schema.json": ExecutionReceipt.model_json_schema(),
        "message-meta.schema.json": MessageMeta.model_json_schema(),
    }
    return {
        filename: json.dumps(
            schema,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
        for filename, schema in sorted(schemas.items())
    }


def export_contract_schemas(output_dir: Path = DEFAULT_OUTPUT) -> None:
    """Write every version-one schema and remove stale schema files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_contract_schemas()
    for stale in output_dir.glob("*.schema.json"):
        if stale.name not in rendered:
            stale.unlink()
    for filename, content in rendered.items():
        (output_dir / filename).write_text(content, encoding="utf-8")


def main() -> int:
    """Export schemas to the canonical documentation directory."""
    export_contract_schemas()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
