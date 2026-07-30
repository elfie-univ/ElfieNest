"""验证结果的稳定数据契约。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.storage.data_home import get_report_exports_dir


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: CheckStatus
    message: str
    duration_ms: float | None = None
    provider: str | None = None
    model: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["details"] = dict(self.details)
        return payload


@dataclass(frozen=True)
class ValidationSuite:
    name: str
    results: tuple[CheckResult, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(result.status is CheckStatus.FAILED for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "summary": {
                status.value: sum(
                    1 for result in self.results if result.status is status
                )
                for status in CheckStatus
            },
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class ValidationReport:
    suites: tuple[ValidationSuite, ...]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def passed(self) -> bool:
        return all(suite.passed for suite in self.suites)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "passed": self.passed,
            "suites": [suite.to_dict() for suite in self.suites],
        }

    def save(self, directory: Path | None = None) -> Path:
        report_dir = directory or get_report_exports_dir()
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = report_dir / f"runtime-validation-{stamp}.json"
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)
        return path
