"""验证结果的稳定数据契约。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from pydantic import JsonValue


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
    details: Mapping[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
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

    def to_dict(self) -> dict[str, JsonValue]:
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

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "created_at": self.created_at,
            "passed": self.passed,
            "suites": [suite.to_dict() for suite in self.suites],
        }
