"""Adapter from App message delivery to the existing typed Elfie boundary."""

from __future__ import annotations

from typing import Optional, Protocol

from app.orchestration.message_delivery import (
    DeliveryAdmission,
    MessageDeliveryPortError,
    UserMessageDeliveryAttempt,
)
from elfie.communication import InboundDisposition, InboundDispositionStatus


class OwnerMessageSession(Protocol):
    def send_user_message(
        self,
        elfie_id: str,
        message: str,
        *,
        owner_id: str,
        conversation_id: Optional[str],
        external_message_id: Optional[str],
        account_id: str,
        channel_id: str,
    ) -> Optional[InboundDisposition]: ...


class ElfieMessageDeliveryAdapter:
    """Delegate one message attempt without taking Runtime lifecycle ownership."""

    def __init__(self, session: Optional[OwnerMessageSession]) -> None:
        self._session = session

    def deliver_user_message(
        self, attempt: UserMessageDeliveryAttempt
    ) -> DeliveryAdmission:
        if self._session is None:
            return DeliveryAdmission(
                status="unavailable",
                error_code="elfie_runtime_unavailable",
            )
        try:
            disposition = self._session.send_user_message(
                attempt.elfie_id,
                attempt.text,
                owner_id=str(attempt.owner_user_id),
                conversation_id=attempt.conversation_id,
                external_message_id=attempt.external_message_id,
                account_id=attempt.owner_account_id,
                channel_id=attempt.channel_id,
            )
        except RuntimeError as error:
            raise MessageDeliveryPortError("Unable to deliver message to Elfie") from error
        if disposition is None:
            return DeliveryAdmission(
                status="unavailable",
                error_code="elfie_runtime_unavailable",
            )
        if disposition.status is InboundDispositionStatus.ACCEPTED:
            return DeliveryAdmission(status="accepted")
        if disposition.status is InboundDispositionStatus.DUPLICATE:
            return DeliveryAdmission(status="duplicate", error_code="duplicate_message")
        disposition_error = disposition.error
        return DeliveryAdmission(
            status="rejected",
            error_code=(
                "message_rejected"
                if disposition_error is None
                else disposition_error.code
            ),
            retryable=(
                False if disposition_error is None else disposition_error.retryable
            ),
        )


__all__ = ("ElfieMessageDeliveryAdapter", "OwnerMessageSession")
