"""No internal state operation may masquerade as a successful output."""

import pytest
from pydantic import TypeAdapter, ValidationError

from elfie.brain.reasoning.decision_types import DecisionIntent, NoOpIntent
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.brain.reasoning.internal_execution import NoOpExecutor
from test.elfie.brain.reasoning.test_output_router import _base, _plan


def test_only_noop_crosses_the_internal_output_boundary() -> None:
    executor = NoOpExecutor()
    noop = NoOpIntent(type="noop", reason="wait safely", **_base("noop"))
    plan = _plan((noop,))

    assert executor.execute(plan, noop) == IntentExecutionResult.completed()

    with pytest.raises(ValidationError):
        TypeAdapter(DecisionIntent).validate_python(
            {
                "type": "internal",
                "operation": "reflect",
                "content": "pretend this succeeded",
                **_base("internal"),
            }
        )
