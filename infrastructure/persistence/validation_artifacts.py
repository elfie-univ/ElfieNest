"""File persistence for validation report artifacts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.models.validation.validation_models import ValidationReport
from infrastructure.persistence.layout.data_home import get_runtime_validation_dir


def save_validation_report(
    report: ValidationReport,
    directory: Path | None = None,
) -> Path:
    report_dir = directory or get_runtime_validation_dir()
    report_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(report_dir, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"runtime-validation-{stamp}.json"
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if os.name != "nt":
        os.chmod(temp_path, 0o600)
    temp_path.replace(path)
    return path


__all__ = ("save_validation_report",)
