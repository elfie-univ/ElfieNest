"""Event Workspace: admission, lane isolation, and immutable Turn framing."""

from .contracts import (
    ActivityScope,
    CommunicationScope,
    EmbodiedScope,
    ExternalExecutionDomain,
    IngestReceipt,
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
    "ActivityScope",
    "PerceptionEvent",
    "EventWorkspace",
    "ResponseScope",
    "SourceDomain",
    "TurnFrame",
)
