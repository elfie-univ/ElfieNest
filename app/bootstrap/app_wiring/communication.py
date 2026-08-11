"""Production composition for product conversations and message delivery."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountsService
from app.features.communication import CommunicationFacade
from app.features.elfies import ElfiesService
from app.orchestration.message_delivery import MessageDeliveryFacade
from infrastructure.communication import (
    ElfieMessageDeliveryAdapter,
    OwnerMessageSession,
    SameOriginMessagePublisher,
)
from infrastructure.persistence.elfie_workspace.communication import (
    SQLiteConversationHistoryAdapter,
)


@dataclass(frozen=True)
class CommunicationServices:
    communication: CommunicationFacade
    message_delivery: MessageDeliveryFacade
    realtime: SameOriginMessagePublisher


def build_communication_services(
    db_path: str,
    *,
    accounts: AccountsService,
    elfies: ElfiesService,
    session: OwnerMessageSession | None,
) -> CommunicationServices:
    history = SQLiteConversationHistoryAdapter(db_path)
    communication = CommunicationFacade(history, elfies)
    realtime = SameOriginMessagePublisher(
        lambda token, user_id: (
            (principal := accounts.authenticate_session(token)) is not None
            and principal.user_id == user_id
        )
    )
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
