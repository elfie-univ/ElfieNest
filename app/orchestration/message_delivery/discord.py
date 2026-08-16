"""Application workflow for one authorized Discord DM and outbound history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.features.communication import (
    CommunicationError,
    CommunicationFacade,
    DiscordAccountsService,
    DiscordPrivateUpdate,
    MessageInvalid,
    RecordElfieMessageCommand,
    RecordUserMessageCommand,
    StoredDiscordAccount,
)

from .errors import DuplicateMessage, MessageDeliveryUnavailable, MessageRejected
from .models import SubmitUserMessageCommand
from .service import MessageDeliveryFacade


@dataclass(frozen=True)
class DiscordUpdateOutcome:
    terminal: bool
    reply_text: Optional[str] = None


class DiscordUpdateHandler:
    """Keep Discord syntax outside Brain and reuse canonical delivery."""

    def __init__(
        self,
        accounts: DiscordAccountsService,
        delivery: MessageDeliveryFacade,
        communication: CommunicationFacade,
    ) -> None:
        self._accounts = accounts
        self._delivery = delivery
        self._communication = communication

    def handle(
        self,
        account: StoredDiscordAccount,
        update: DiscordPrivateUpdate,
        *,
        pairing_code: Optional[str] = None,
    ) -> DiscordUpdateOutcome:
        if pairing_code is not None:
            result = self._accounts.complete_pairing(account, update, pairing_code)
            if result.completed:
                return DiscordUpdateOutcome(True, "配对成功，现在可以和精灵聊天了。")
            if result.reason == "binding_unavailable":
                return DiscordUpdateOutcome(False)
            return DiscordUpdateOutcome(
                True,
                "配对码无效或已过期，请回 ElfieNest 重新生成。",
            )

        authorized = self._accounts.authorize_inbound(account, update)
        if authorized is None:
            return DiscordUpdateOutcome(True)
        if update.text is None or not update.text.strip():
            return DiscordUpdateOutcome(True, "目前只支持文字消息。")

        external_message_id = f"discord:{account.bot_id}:message:{update.message_id}"
        command = SubmitUserMessageCommand(
            elfie_id=authorized.elfie_id,
            text=update.text,
            channel="discord",
            external_message_id=external_message_id,
            conversation_id=authorized.conversation_id,
            external_actor_id=authorized.external_actor_id,
            external_actor_display_name=authorized.external_actor_display_name,
        )
        try:
            self._delivery.submit_user_message(authorized.principal, command)
        except DuplicateMessage:
            try:
                self._communication.record_user_message(
                    authorized.principal,
                    RecordUserMessageCommand(
                        elfie_id=authorized.elfie_id,
                        text=update.text,
                        channel="discord",
                        message_id=external_message_id,
                        conversation_id=authorized.conversation_id,
                        external_actor_id=authorized.external_actor_id,
                        external_actor_display_name=(
                            authorized.external_actor_display_name
                        ),
                    ),
                )
            except CommunicationError:
                return DiscordUpdateOutcome(False)
        except MessageDeliveryUnavailable:
            return DiscordUpdateOutcome(False)
        except (MessageInvalid, MessageRejected):
            return DiscordUpdateOutcome(True, "这条消息暂时无法处理，请缩短后重试。")
        except CommunicationError:
            return DiscordUpdateOutcome(False)
        return DiscordUpdateOutcome(True)


class DiscordReplyRecorder:
    """Persist an externally delivered Elfie reply in the same history store."""

    def __init__(self, communication: CommunicationFacade) -> None:
        self._communication = communication

    def record_reply(
        self,
        *,
        elfie_id: str,
        conversation_id: str,
        text: str,
        source_message_key: str,
    ) -> None:
        self._communication.record_elfie_message(
            RecordElfieMessageCommand(
                elfie_id=elfie_id,
                text=text,
                channel="discord",
                meta="Discord 回复",
                conversation_id=conversation_id,
                message_id=source_message_key,
            )
        )


__all__ = ("DiscordReplyRecorder", "DiscordUpdateHandler", "DiscordUpdateOutcome")
