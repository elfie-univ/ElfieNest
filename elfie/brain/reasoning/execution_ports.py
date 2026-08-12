"""Narrow capabilities consumed by the output router."""

from typing import Protocol

from elfie.brain.reasoning.context_types import EffectiveCapabilities
from elfie.brain.reasoning.decision_types import DecisionIntent, DecisionPlan
from elfie.brain.reasoning.execution_types import IntentExecutionResult
from elfie.message_types import IntentId, TurnId


class EffectiveCapabilitiesSource(Protocol):
    def current(self) -> EffectiveCapabilities:
        """Return the latest current-body and connected-channel snapshot."""


class IntentExecutor(Protocol):
    def execute(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> IntentExecutionResult:
        """Execute one already validated intent and return its terminal result."""

    def interrupt(self, turn_id: TurnId, intent_id: IntentId, reason: str) -> None:
        """Interrupt an already-started action when the target supports it."""


__all__ = ("EffectiveCapabilitiesSource", "IntentExecutor")
