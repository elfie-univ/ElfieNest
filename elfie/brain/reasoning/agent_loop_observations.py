"""Named frozen payload for the Reasoning agent-loop model-call boundary.

``ModelCallObservation`` is the §B5 Agent Loop ``model_call`` payload emitted
at the Brain-side ``ModelPort.generate`` boundary, covering both the primary
generation and the repair/revision generation of one Run.  It records exactly
what the Brain knows at that boundary: the request text and parameters it
sent, the raw response text and serving identity the provider returned, and
the boundary-measured wall-clock duration.

The Brain does NOT redact: raw prompt and response text flows into the
payload, and redaction is the sink side's responsibility.  The one exception
is ``ObservationError.message`` on failed calls, which the emit site
sanitizes to the exception class name because provider exception text is
untrusted at this boundary.

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from elfie.message_types import FrozenContractModel


class ModelCallObservation(FrozenContractModel):
    """One Brain-side model call at the agent-loop boundary (§B5-1).

    Request-side fields mirror ``ModelGenerationRequest``.  Response-side
    fields are ``None`` exactly when the model call failed.  ``provider`` and
    ``model_key`` carry the identity the Brain actually knows here: the served
    model from ``ModelGenerationResult`` on success, the selected capability
    identity on failure.  ``duration_ms`` is the boundary-measured wall-clock
    duration of the ``generate`` call; ``provider_latency_ms`` is the
    provider-reported latency when the result supplies one.
    """

    iteration_index: int = Field(ge=1)
    # Request side (what the Brain sent; raw text, the sink side redacts).
    system_prompt: str
    user_prompt: str
    reasoning_mode: str
    response_mode: str
    response_schema_name: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1)
    context_revision: int = Field(ge=0)
    capability_revision: int = Field(ge=0)
    # Response side (None when the model call failed).
    response_text: Optional[str] = None
    selected_mode: Optional[str] = None
    provider: Optional[str] = None
    model_key: Optional[str] = None
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    provider_latency_ms: Optional[float] = Field(default=None, ge=0.0)
    # Boundary-measured wall-clock duration of the generate call.
    duration_ms: float = Field(ge=0.0)


__all__ = ("ModelCallObservation",)
