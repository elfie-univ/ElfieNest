"""Tests for restricted internal and NoOp output execution."""

from elfie.brain.decision_types import (
    InternalIntent,
    InternalOperation,
    NoOpIntent,
)
from elfie.brain.internal_output import InternalIntentExecutor
from elfie.brain.output_types import IntentExecutionResult
from test.elfie.brain.test_output_router import _base, _plan


class RecordingInternalSink:
    def __init__(self) -> None:
        self.operations: list[InternalOperation] = []

    def execute(self, plan, intent) -> IntentExecutionResult:
        del plan
        self.operations.append(intent.operation)
        return IntentExecutionResult.completed()


def test_internal_intent_uses_restricted_sink_while_noop_is_audit_only() -> None:
    # Given: one restricted internal operation and one NoOp.
    sink = RecordingInternalSink()
    executor = InternalIntentExecutor(sink)
    internal = InternalIntent(
        type="internal",
        operation=InternalOperation.REFLECT,
        content="review recent facts",
        **_base("internal"),
    )
    noop = NoOpIntent(type="noop", reason="wait safely", **_base("noop"))
    plan = _plan((internal, noop))

    # When: both variants cross the internal output boundary.
    internal_result = executor.execute(plan, internal)
    noop_result = executor.execute(plan, noop)

    # Then: only the explicit operation reaches the sink; NoOp still completes.
    assert internal_result == IntentExecutionResult.completed()
    assert noop_result == IntentExecutionResult.completed()
    assert sink.operations == [InternalOperation.REFLECT]
