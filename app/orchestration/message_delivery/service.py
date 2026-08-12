"""Coordinate authorization, Elfie admission, history and realtime delivery."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    CommunicationFacade,
    RecordedElfieMessageResult,
    RecordElfieMessageCommand,
    RecordUserMessageCommand,
)

from .errors import DuplicateMessage, MessageDeliveryUnavailable, MessageRejected
from .models import (
    DeliverElfieReplyCommand,
    SubmittedMessageResult,
    SubmitUserMessageCommand,
)
from .port_models import LiveConversationMessage, UserMessageDeliveryAttempt
from .ports import (
    ElfieMessageDeliveryPort,
    LiveConversationPort,
    MessageDeliveryPortError,
)


class MessageDeliveryFacade:
    """The one workflow for an authorized product message and its receipt."""

    def __init__(
        self,
        communication: CommunicationFacade,
        elfie_delivery: ElfieMessageDeliveryPort,
        live_conversation: LiveConversationPort,
    ) -> None:
        self._communication = communication
        self._elfie_delivery = elfie_delivery
        self._live_conversation = live_conversation

    def submit_user_message(
        self,
        principal: AccountPrincipal,
        command: SubmitUserMessageCommand,
    ) -> SubmittedMessageResult:
        prepared = self._communication.prepare_user_message(
            principal,
            RecordUserMessageCommand(
                elfie_id=command.elfie_id,
                text=command.text,
                channel=command.channel,
                message_id=command.external_message_id,
            ),
        )
        access = prepared.access
        try:
            admission = self._elfie_delivery.deliver_user_message(
                UserMessageDeliveryAttempt(
                    elfie_id=access.elfie_id,
                    text=prepared.text,
                    owner_user_id=access.owner_user_id,
                    owner_account_id=access.owner_account_id,
                    conversation_id=f"owner:{access.owner_user_id}",
                    channel_id="godot-owner",
                    external_message_id=command.external_message_id,
                )
            )
        except MessageDeliveryPortError as error:
            raise MessageDeliveryUnavailable("Elfie delivery unavailable") from error
        if admission.status == "unavailable":
            raise MessageDeliveryUnavailable(
                admission.error_code or "elfie_runtime_unavailable"
            )
        if admission.status == "duplicate":
            raise DuplicateMessage(admission.error_code or "duplicate_message")
        if admission.status == "rejected":
            if admission.retryable:
                raise MessageDeliveryUnavailable(
                    admission.error_code or "message_rejected"
                )
            raise MessageRejected(admission.error_code or "message_rejected")
        message = self._communication.record_prepared_user_message(prepared)
        return SubmittedMessageResult(message=message)

    def deliver_elfie_reply(
        self,
        command: DeliverElfieReplyCommand,
    ) -> RecordedElfieMessageResult:
        recorded = self._communication.record_elfie_message(
            RecordElfieMessageCommand(
                elfie_id=command.elfie_id,
                text=command.text,
                channel=command.channel,
                meta=command.meta,
            )
        )
        try:
            self._live_conversation.publish_message(
                LiveConversationMessage(
                    owner_user_id=recorded.owner_user_id,
                    message=recorded.message,
                )
            )
        except MessageDeliveryPortError as error:
            raise MessageDeliveryUnavailable("Realtime reply unavailable") from error
        return recorded


__all__ = ("MessageDeliveryFacade",)
