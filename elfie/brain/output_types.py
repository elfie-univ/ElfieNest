"""Typed batches, receipts, and executor results for Brain outputs."""

from __future__ import annotations

from enum import Enum, unique
from typing import NamedTuple, Optional, Tuple

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.perception_types import ExecutionStatus
from elfie.message_types import (
    ErrorInfo,
    EventId,
    FrozenContractModel,
    IntentId,
    PlanId,
    TurnId,
    UTCDateTime,
)


@unique
class ExecutorKind(str, Enum):
    """Closed output targets understood by the scheduler."""

    BODY = "body"
    COMMUNICATION = "communication"
    INTERNAL = "internal"
    ACTIVITY = "activity"


class ExecutionBatch(FrozenContractModel):
    """Atomic acceptance evidence for one complete DecisionPlan."""

    batch_id: EventId
    plan_id: PlanId
    turn_id: TurnId
    accepted_at: UTCDateTime
    intent_ids: Tuple[IntentId, ...]


class BatchRejection(FrozenContractModel):
    """Observable reason a complete plan was rejected before execution."""

    plan_id: PlanId
    turn_id: TurnId
    rejected_at: UTCDateTime
    error: ErrorInfo


class ExecutionReceipt(FrozenContractModel):
    """One correlatable state transition for one decision intent."""

    receipt_id: EventId
    plan_id: PlanId
    turn_id: TurnId
    intent_id: IntentId
    executor: ExecutorKind
    status: ExecutionStatus
    occurred_at: UTCDateTime
    error: Optional[ErrorInfo] = None

    @model_validator(mode="after")
    def validate_error(self) -> ExecutionReceipt:
        """Require typed failure evidence only for non-success transitions."""
        failed = self.status in {
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.CANCELLED,
        }
        if failed != (self.error is not None):
            raise PydanticCustomError(
                "execution_receipt_error",
                "failure statuses require error and success statuses forbid it",
            )
        return self


class IntentExecutionResult(NamedTuple):
    """Terminal result returned by one target-specific executor."""

    status: ExecutionStatus
    error: Optional[ErrorInfo]

    @classmethod
    def completed(cls) -> IntentExecutionResult:
        return cls(ExecutionStatus.COMPLETED, None)

    @classmethod
    def failed(cls, error: ErrorInfo) -> IntentExecutionResult:
        return cls(ExecutionStatus.FAILED, error)

    @classmethod
    def interrupted(cls, reason: str) -> IntentExecutionResult:
        return cls(
            ExecutionStatus.INTERRUPTED,
            ErrorInfo(code="interrupted", message=reason),
        )

    @classmethod
    def timed_out(cls, reason: str) -> IntentExecutionResult:
        return cls(
            ExecutionStatus.TIMED_OUT,
            ErrorInfo(code="timed_out", message=reason),
        )


__all__ = (
    "BatchRejection",
    "ExecutionBatch",
    "ExecutionReceipt",
    "ExecutorKind",
    "IntentExecutionResult",
)
