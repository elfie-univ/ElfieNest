"""Strict context assembly for one sealed reasoning frame."""

from __future__ import annotations

import logging
from typing import Optional

from elfie.brain.activity.context import ActivityContext
from elfie.brain.consolidation.contracts import CognitiveConsolidationSnapshot
from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.context_types import (
    BrainContext,
    ConversationContext,
    EffectiveCapabilities,
)
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import UTCDateTime

logger = logging.getLogger("elfie.brain.reasoning.context_builder")


class ContextAssembler:
    """Build immutable BrainContext only from sealed typed inputs."""

    def assemble(
        self,
        *,
        frame: TurnFrame,
        emotion: EmotionSnapshot,
        homeostasis: EnergySnapshot,
        motivation: Optional[MotivationSnapshot] = None,
        consolidation: Optional[CognitiveConsolidationSnapshot] = None,
        conversation: ConversationContext,
        memory: MemoryContext,
        capabilities: EffectiveCapabilities,
        activities: Optional[ActivityContext] = None,
        orientation: Optional[OrientationSnapshot] = None,
        selfhood: Optional[SelfhoodPromptProjection] = None,
        constitution_version: int = 1,
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
            constitution_version=constitution_version,
            captured_at=context_captured_at,
            frame=frame,
            emotion=emotion,
            homeostasis=homeostasis,
            motivation=motivation
            if motivation is not None
            else MotivationSnapshot.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
            consolidation=consolidation
            if consolidation is not None
            else CognitiveConsolidationSnapshot.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
            conversation=conversation,
            memory=memory,
            activities=activities
            if activities is not None
            else ActivityContext.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
            capabilities=capabilities,
            orientation=orientation
            if orientation is not None
            else OrientationSnapshot.unknown().model_copy(
                update={"captured_at": context_captured_at}
            ),
            selfhood=(
                selfhood.model_copy(update={"captured_at": context_captured_at})
                if selfhood is not None
                else SelfhoodPromptProjection.unknown(captured_at=context_captured_at)
            ),
        )
