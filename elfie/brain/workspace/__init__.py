"""Event Workspace: admission, lane isolation, and immutable Turn framing."""

from .contracts import (
    CommunicationScope,
    EmbodiedScope,
    ExternalExecutionDomain,
    IngestReceipt,
    InternalScope,
    PerceptionEvent,
    ResponseScope,
    SourceDomain,
    TurnFrame,
)
from .system import EventWorkspace

__all__ = (
    "CommunicationScope",
    "EmbodiedScope",
    "ExternalExecutionDomain",
    "IngestReceipt",
    "InternalScope",
    "PerceptionEvent",
    "EventWorkspace",
    "ResponseScope",
    "SourceDomain",
    "TurnFrame",
)
