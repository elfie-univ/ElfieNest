"""Authorized conversation directory and user-visible history use-cases."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal
from app.features.elfies import (
    ElfiesService,
    ElfiesUnavailable,
    ListVisibleElfiesQuery,
)

from .errors import CommunicationUnavailable, ConversationNotFound, MessageInvalid
from .models import (
    ConversationAccessResult,
    ConversationResult,
    ConversationsResult,
    GetConversationQuery,
    ListConversationsQuery,
    ListMessagesQuery,
    MessageResult,
    MessagesResult,
    PreparedUserMessageResult,
    RecordedElfieMessageResult,
    RecordElfieMessageCommand,
    RecordUserMessageCommand,
)
from .port_models import ConversationMessageWrite, StoredConversationMessage
from .ports import CommunicationPortError, ConversationHistoryPort

_MESSAGE_LIMIT = 4000


class CommunicationFacade:
    """Single product entry point for conversation relations and history."""

    def __init__(
        self,
        history: ConversationHistoryPort,
        elfies: ElfiesService,
    ) -> None:
        self._history = history
        self._elfies = elfies

    def list_conversations(
        self,
        principal: AccountPrincipal,
        query: ListConversationsQuery,
    ) -> ConversationsResult:
        del query
        try:
            visible = self._elfies.list_visible(
                principal,
                ListVisibleElfiesQuery(relationship="owned"),
            )
            items = []
            for item in visible:
                elfie_id = item.profile.elfie_id
                history = self._history.list_messages(
                    elfie_id,
                    conversation_id=_owner_conversation_id(principal.user_id),
                    user_id=principal.user_id,
                )
                latest = history[-1] if history else None
                items.append(
                    ConversationResult(
                        elfie_id=elfie_id,
                        name=item.profile.name,
                        portrait_url=item.profile.portrait_url,
                        last_message_preview="" if latest is None else latest.text,
                        last_message_at=None if latest is None else latest.created_at,
                    )
                )
        except (CommunicationPortError, ElfiesUnavailable) as error:
            raise CommunicationUnavailable(
                "Conversation directory unavailable"
            ) from error
        return ConversationsResult(items=tuple(items))

    def get_conversation(
        self,
        principal: AccountPrincipal,
        query: GetConversationQuery,
    ) -> ConversationAccessResult:
        elfie_id = query.elfie_id.strip()
        if not elfie_id:
            raise ConversationNotFound("精灵不存在")
        try:
            visible = self._elfies.list_visible(
                principal,
                ListVisibleElfiesQuery(relationship="owned"),
            )
        except ElfiesUnavailable as error:
            raise CommunicationUnavailable(
                "Conversation directory unavailable"
            ) from error
        matched = next(
            (item for item in visible if item.profile.elfie_id == elfie_id),
            None,
        )
        if matched is None:
            raise ConversationNotFound("精灵不存在")
        return ConversationAccessResult(
            elfie_id=matched.profile.elfie_id,
            owner_user_id=principal.user_id,
            owner_account_id=principal.account_id,
        )

    def list_messages(
        self,
        principal: AccountPrincipal,
        query: ListMessagesQuery,
    ) -> MessagesResult:
        access = self.get_conversation(
            principal,
            GetConversationQuery(elfie_id=query.elfie_id),
        )
        try:
            stored = self._history.list_messages(
                access.elfie_id,
                conversation_id=_owner_conversation_id(access.owner_user_id),
                user_id=access.owner_user_id,
            )
        except CommunicationPortError as error:
            raise CommunicationUnavailable(
                "Conversation history unavailable"
            ) from error
        return MessagesResult(
            items=tuple(_message_result(access.elfie_id, item) for item in stored)
        )

    def prepare_user_message(
        self,
        principal: AccountPrincipal,
        command: RecordUserMessageCommand,
    ) -> PreparedUserMessageResult:
        access = self.get_conversation(
            principal,
            GetConversationQuery(elfie_id=command.elfie_id),
        )
        return PreparedUserMessageResult(
            access=access,
            text=_message_text(command.text),
            channel=command.channel,
            message_id=command.message_id,
        )

    def record_user_message(
        self,
        principal: AccountPrincipal,
        command: RecordUserMessageCommand,
    ) -> MessageResult:
        prepared = self.prepare_user_message(principal, command)
        return self.record_prepared_user_message(prepared)

    def record_prepared_user_message(
        self,
        prepared: PreparedUserMessageResult,
    ) -> MessageResult:
        access = prepared.access
        try:
            stored = self._history.append_message(
                ConversationMessageWrite(
                    elfie_id=access.elfie_id,
                    conversation_id=_owner_conversation_id(access.owner_user_id),
                    sender="user",
                    text=prepared.text,
                    channel=prepared.channel,
                    user_id=access.owner_user_id,
                    message_id=prepared.message_id,
                    meta="已投递到下一次 tick",
                )
            )
        except CommunicationPortError as error:
            raise CommunicationUnavailable(
                "Unable to record conversation message"
            ) from error
        return _message_result(access.elfie_id, stored)

    def record_elfie_message(
        self,
        command: RecordElfieMessageCommand,
    ) -> RecordedElfieMessageResult:
        elfie_id = command.elfie_id.strip()
        text = _message_text(command.text)
        try:
            owner_user_id = self._history.owner_user_id(elfie_id)
            if owner_user_id is None:
                raise ConversationNotFound("精灵不存在")
            stored = self._history.append_message(
                ConversationMessageWrite(
                    elfie_id=elfie_id,
                    conversation_id=_owner_conversation_id(owner_user_id),
                    sender="elfie",
                    text=text,
                    channel=command.channel,
                    user_id=owner_user_id,
                    meta=command.meta,
                )
            )
        except CommunicationPortError as error:
            raise CommunicationUnavailable("Unable to record Elfie reply") from error
        return RecordedElfieMessageResult(
            owner_user_id=owner_user_id,
            message=_message_result(elfie_id, stored),
        )


def _owner_conversation_id(user_id: int) -> str:
    return f"owner:{user_id}"


def _message_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise MessageInvalid("消息不能为空")
    if len(normalized) > _MESSAGE_LIMIT:
        raise MessageInvalid("聊天字段无效")
    return normalized


def _message_result(elfie_id: str, stored: StoredConversationMessage) -> MessageResult:
    return MessageResult(
        id=stored.id,
        elfie_id=elfie_id,
        sender=stored.sender,
        text=stored.text,
        created_at=stored.created_at,
    )


__all__ = ("CommunicationFacade",)
