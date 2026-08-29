"""Emotion input data structure for ElfieNest creature.

Defines the input structure for emotion events.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

VALID_SOURCES = {
    "text",
    "image",
    "audio",
    "physical",
    "brain",
    "social",
    "execution",
    "model",
}


@dataclass
class EmotionInput:
    """Input data for an emotion event.

    Attributes:
        emotion: The emotion type (one of 8 basic emotions)
        intensity: Emotion intensity from 0.0 to 1.0
        source: The source of the emotion (text/image/audio/physical/brain)
        event_id: Unique identifier for this event
        timestamp: Unix timestamp when the event occurred
        metadata: Optional additional data
    """

    emotion: str
    intensity: float
    source: str
    event_id: str
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[Dict] = None

    def validate(self) -> bool:
        """Validate the emotion input.

        Returns:
            True if valid, False otherwise.
        """
        if not 0.0 <= self.intensity <= 1.0:
            return False
        if self.source not in VALID_SOURCES:
            return False
        return True
