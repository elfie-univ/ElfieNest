"""Production composition for product conversations and message delivery."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.communication import CommunicationFacade
from app.features.elfies import ElfiesService
from app.orchestration.message_delivery import MessageDeliveryFacade
from infrastructure.communication import (
    ElfieMessageDeliveryAdapter,
    OwnerMessageSession,
    SameOriginMessagePublisher,
)
from infrastructure.persistence.communication import SQLiteConversationHistoryAdapter


@dataclass(frozen=True)
class CommunicationServices:
    communication: CommunicationFacade
    message_delivery: MessageDeliveryFacade
    realtime: SameOriginMessagePublisher


def build_communication_services(
    db_path: str,
    *,
    elfies: ElfiesService,
    session: OwnerMessageSession | None,
) -> CommunicationServices:
    history = SQLiteConversationHistoryAdapter(db_path)
    communication = CommunicationFacade(history, elfies)
    realtime = SameOriginMessagePublisher()
    return CommunicationServices(
        communication=communication,
        message_delivery=MessageDeliveryFacade(
            communication,
            ElfieMessageDeliveryAdapter(session),
            realtime,
        ),
        realtime=realtime,
    )


__all__ = ("CommunicationServices", "build_communication_services")
