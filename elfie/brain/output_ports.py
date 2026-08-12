"""Narrow capabilities consumed by the output router."""

from typing import Optional, Protocol

from elfie.brain.context_types import EffectiveCapabilities
from elfie.brain.decision_types import DecisionIntent, DecisionPlan
from elfie.brain.output_types import IntentExecutionResult
from elfie.message_types import ErrorInfo, IntentId, TurnId


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


class ActivityPreflightExecutor(IntentExecutor, Protocol):
    """Activity executor extension used before a batch is durably accepted."""

    def preflight(
        self,
        plan: DecisionPlan,
        intent: DecisionIntent,
    ) -> Optional[ErrorInfo]:
        """Check an Activity without durable or external side effects."""


__all__ = ("EffectiveCapabilitiesSource", "IntentExecutor")
