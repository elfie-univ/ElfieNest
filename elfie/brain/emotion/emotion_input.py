"""Small direct-input helper used by diagnostics and local adapters."""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from elfie.brain.emotion.emotion_types import EMOTION_NAMES

VALID_SOURCES = {
    "text",
    "physical",
    "social",
    "execution",
    "internal",
    "model",
}


@dataclass
class EmotionInput:
    """One positive direct channel input for a local diagnostic."""

    emotion: str
    intensity: float
    source: str
    event_id: str
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[Dict] = None

    def validate(self) -> bool:
        return (
            self.emotion in EMOTION_NAMES
            and 0.0 <= self.intensity <= 1.0
            and self.source in VALID_SOURCES
        )
