"""Strict Thalamus assembly for one sealed cortical frame."""

from __future__ import annotations

import logging
from typing import Optional

from elfie.brain.context_types import (
    BrainContext,
    ConversationContext,
    EffectiveCapabilities,
    EmotionSnapshot,
    HomeostasisSnapshot,
    MemoryContext,
    OrientationSnapshot,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
)
from elfie.brain.perception_types import TurnFrame
from elfie.message_types import UTCDateTime

logger = logging.getLogger("elfie.brain.context_builder")


class ThalamusContextBuilder:
    """Build immutable BrainContext only from sealed typed inputs."""

    def assemble(
        self,
        *,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        homeostasis: HomeostasisSnapshot,
        conversation: ConversationContext,
        memory: MemoryContext,
        capabilities: EffectiveCapabilities,
        orientation: Optional[OrientationSnapshot] = None,
        selfhood: Optional[SelfhoodSnapshot] = None,
        profile_anchors: Optional[ProfileAnchorSnapshot] = None,
        captured_at: Optional[UTCDateTime] = None,
        revision: Optional[int] = None,
    ) -> BrainContext:
        """Assemble one immutable context without reading or draining sources."""
        context_captured_at = (
            captured_at if captured_at is not None else frame.captured_at
        )
        context_revision = revision if revision is not None else frame.revision
        logger.info("丘脑已接收单域 TurnFrame，正在组装不可变 BrainContext。")
        return BrainContext(
            revision=context_revision,
            captured_at=context_captured_at,
            frame=frame,
            emotion=emotion,
            homeostasis=homeostasis,
            conversation=conversation,
            memory=memory,
            capabilities=capabilities,
            orientation=orientation
            if orientation is not None
            else OrientationSnapshot.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
            selfhood=selfhood
            if selfhood is not None
            else SelfhoodSnapshot.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
            profile_anchors=profile_anchors
            if profile_anchors is not None
            else ProfileAnchorSnapshot.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
        )
