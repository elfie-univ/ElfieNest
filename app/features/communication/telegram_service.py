"""Owner authorization, token setup, pairing, and inbound identity mapping."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Optional, Tuple
from urllib.parse import urlencode

from app.features.accounts import AccountPrincipal

from .avatar_ports import ElfiePortraitPort
from .telegram_errors import (
    TelegramAccountConflict,
    TelegramAccountInvalid,
    TelegramAccountNotFound,
    TelegramAccountUnavailable,
)
from .telegram_models import (
    AuthorizedTelegramMessage,
    ConfigureTelegramAccountCommand,
    CreateTelegramPairingSessionCommand,
    DisconnectTelegramAccountCommand,
    GetTelegramAccountQuery,
    TelegramAccountResult,
    TelegramAccountState,
    TelegramPairingCompletion,
    TelegramPairingSessionResult,
)
from .telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
    TelegramPrivateUpdate,
    TelegramRuntimeAccount,
)
from .telegram_ports import (
    AccountPrincipalLookupPort,
    TelegramAccountPortError,
    TelegramAccountStoreConflict,
    TelegramAccountStorePort,
    TelegramBotAvatarPort,
    TelegramBotInspectionPort,
    TelegramBotTokenRejected,
    TelegramBotTransportError,
    TelegramTokenPort,
)

_PAIRING_TTL = timedelta(minutes=10)
_TOKEN_MAX_LENGTH = 256
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PairingSession:
    elfie_id: str
    bot_id: str
    local_owner_user_id: int
    local_owner_account_id: str
    expires_at: datetime


class TelegramAccountsService:
    """Single product authority for one Elfie's Telegram bot connection."""

    def __init__(
        self,
        store: TelegramAccountStorePort,
        tokens: TelegramTokenPort,
        inspection: TelegramBotInspectionPort,
        principals: AccountPrincipalLookupPort,
        *,
        now: Optional[Callable[[], datetime]] = None,
        pairing_token: Optional[Callable[[], str]] = None,
        portrait_source: Optional[ElfiePortraitPort] = None,
        avatar_sync: Optional[TelegramBotAvatarPort] = None,
    ) -> None:
        self._store = store
        self._tokens = tokens
        self._inspection = inspection
        self._principals = principals
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._pairing_token = pairing_token or (lambda: secrets.token_urlsafe(32))
        self._portrait_source = portrait_source
        self._avatar_sync = avatar_sync
        self._pairing_sessions: dict[str, _PairingSession] = {}
        self._pairing_lock = RLock()

    def get_account(
        self,
        principal: AccountPrincipal,
        query: GetTelegramAccountQuery,
    ) -> TelegramAccountResult:
        elfie_id = self._require_owned(principal, query.elfie_id)
        try:
            account = self._store.get_account(elfie_id)
            binding = self._store.get_binding(elfie_id) if account is not None else None
        except TelegramAccountPortError as error:
            raise TelegramAccountUnavailable(
                "Telegram account is temporarily unavailable"
            ) from error
        return self._result(elfie_id, account, binding, principal.user_id)

    def configure_account(
        self,
        principal: AccountPrincipal,
        command: ConfigureTelegramAccountCommand,
    ) -> TelegramAccountResult:
        elfie_id = self._require_owned(principal, command.elfie_id)
        token = _validate_bot_token(command.bot_token)
        try:
            inspected = self._inspection.inspect_bot(token)
        except TelegramBotTokenRejected as error:
            raise TelegramAccountInvalid("Telegram Bot Token 无效") from error
        except TelegramBotTransportError as error:
            raise TelegramAccountUnavailable("暂时无法连接 Telegram") from error
        if inspected.webhook_url:
            raise TelegramAccountConflict(
                "这个机器人已配置 Webhook；请先在原系统中移除 Webhook"
            )
        if not inspected.username:
            raise TelegramAccountInvalid("Telegram 机器人缺少 username")

        checked_at = _iso(self._now())
        credential_ref = self._tokens.credential_ref(elfie_id)
        previous_token = self._tokens.load(credential_ref)
        account = StoredTelegramAccount(
            elfie_id=elfie_id,
            bot_id=inspected.bot_id,
            bot_username=inspected.username,
            display_name=inspected.display_name,
            credential_ref=credential_ref,
            configured_owner_user_id=principal.user_id,
            status="active",
            last_checked_at=checked_at,
            issue=None,
        )
        try:
            actual_reference = self._tokens.replace(elfie_id, token)
            if actual_reference != credential_ref:
                raise ValueError("Telegram credential reference changed unexpectedly")
            self._store.save_account(account)
        except TelegramAccountStoreConflict as error:
            self._restore_token(elfie_id, previous_token)
            raise TelegramAccountConflict(str(error)) from error
        except (OSError, ValueError, TelegramAccountPortError) as error:
            self._restore_token(elfie_id, previous_token)
            raise TelegramAccountUnavailable(
                "Telegram account could not be saved"
            ) from error
        self._invalidate_pairing_sessions(elfie_id)
        self._sync_avatar(elfie_id, token)
        binding = self._store.get_binding(elfie_id)
        return self._result(elfie_id, account, binding, principal.user_id)

    def disconnect_account(
        self,
        principal: AccountPrincipal,
        command: DisconnectTelegramAccountCommand,
    ) -> TelegramAccountResult:
        elfie_id = self._require_owned(principal, command.elfie_id)
        disconnected_at = _iso(self._now())
        try:
            self._store.disconnect_account(elfie_id, disconnected_at=disconnected_at)
            self._tokens.delete(elfie_id)
        except (OSError, ValueError, TelegramAccountPortError) as error:
            raise TelegramAccountUnavailable(
                "Telegram account could not be disconnected"
            ) from error
        self._invalidate_pairing_sessions(elfie_id)
        return self._result(elfie_id, None, None, principal.user_id)

    def create_pairing_session(
        self,
        principal: AccountPrincipal,
        command: CreateTelegramPairingSessionCommand,
    ) -> TelegramPairingSessionResult:
        elfie_id = self._require_owned(principal, command.elfie_id)
        try:
            account = self._store.get_account(elfie_id)
        except TelegramAccountPortError as error:
            raise TelegramAccountUnavailable(
                "Telegram account is temporarily unavailable"
            ) from error
        if account is None:
            raise TelegramAccountInvalid("请先配置 Telegram 机器人")
        if account.status != "active":
            raise TelegramAccountInvalid("请先重新配置 Telegram 机器人")
        code = self._pairing_token()
        if not code or len(code) > 64:
            raise TelegramAccountUnavailable("Unable to generate pairing code")
        expires_at = self._now() + _PAIRING_TTL
        digest = _pairing_digest(code)
        with self._pairing_lock:
            self._prune_pairing_sessions(self._now())
            self._invalidate_pairing_sessions_locked(elfie_id)
            self._pairing_sessions[digest] = _PairingSession(
                elfie_id=elfie_id,
                bot_id=account.bot_id,
                local_owner_user_id=principal.user_id,
                local_owner_account_id=principal.account_id,
                expires_at=expires_at,
            )
        query = urlencode({"start": code})
        return TelegramPairingSessionResult(
            deep_link=f"https://t.me/{account.bot_username}?{query}",
            expires_at=_iso(expires_at),
        )

    def runtime_accounts(self) -> Tuple[TelegramRuntimeAccount, ...]:
        now = _iso(self._now())
        try:
            stored = self._store.list_active_accounts()
        except TelegramAccountPortError:
            return ()
        runtime: list[TelegramRuntimeAccount] = []
        for account in stored:
            if account.status != "active":
                continue
            owner_user_id = self._store.owner_user_id(account.elfie_id)
            if owner_user_id != account.configured_owner_user_id:
                self._safe_mark_attention(account.elfie_id, now, "owner_changed")
                continue
            token = self._tokens.load(account.credential_ref)
            if not token:
                self._safe_mark_attention(account.elfie_id, now, "credential_missing")
                continue
            runtime.append(
                TelegramRuntimeAccount(
                    account=account,
                    bot_token=token,
                    next_update_id=self._store.next_update_id(account.elfie_id),
                    binding=self._store.get_binding(account.elfie_id),
                )
            )
        return tuple(runtime)

    def complete_pairing(
        self,
        account: StoredTelegramAccount,
        update: TelegramPrivateUpdate,
        code: str,
    ) -> TelegramPairingCompletion:
        if update.chat_type != "private" or update.sender_is_bot:
            return TelegramPairingCompletion(False, "private_human_required")
        now = self._now()
        digest = _pairing_digest(code)
        with self._pairing_lock:
            self._prune_pairing_sessions(now)
            session = self._pairing_sessions.get(digest)
            if session is None:
                return TelegramPairingCompletion(False, "pairing_expired")
            if (
                session.elfie_id != account.elfie_id
                or session.bot_id != account.bot_id
                or session.expires_at < now
            ):
                self._pairing_sessions.pop(digest, None)
                return TelegramPairingCompletion(False, "pairing_expired")
            if (
                self._store.owner_user_id(account.elfie_id)
                != session.local_owner_user_id
            ):
                self._pairing_sessions.pop(digest, None)
                return TelegramPairingCompletion(False, "owner_changed")
            principal = self._principals.find_principal(session.local_owner_user_id)
            if principal is None:
                self._pairing_sessions.pop(digest, None)
                return TelegramPairingCompletion(False, "owner_unavailable")
            bound_at = _iso(now)
            try:
                self._store.replace_binding(
                    StoredTelegramBinding(
                        elfie_id=account.elfie_id,
                        telegram_user_id=update.telegram_user_id,
                        telegram_chat_id=update.chat_id,
                        telegram_username=update.telegram_username,
                        display_name=update.display_name,
                        local_owner_user_id=principal.user_id,
                        local_owner_account_id=principal.account_id,
                        conversation_id=f"telegram:{update.chat_id}",
                        bound_at=bound_at,
                    )
                )
            except TelegramAccountPortError:
                return TelegramPairingCompletion(False, "binding_unavailable")
            self._pairing_sessions.pop(digest, None)
        return TelegramPairingCompletion(True)

    def authorize_inbound(
        self,
        account: StoredTelegramAccount,
        update: TelegramPrivateUpdate,
    ) -> Optional[AuthorizedTelegramMessage]:
        if update.chat_type != "private" or update.sender_is_bot:
            return None
        try:
            binding = self._store.get_binding(account.elfie_id)
            owner_user_id = self._store.owner_user_id(account.elfie_id)
        except TelegramAccountPortError:
            return None
        if (
            binding is None
            or binding.telegram_user_id != update.telegram_user_id
            or binding.telegram_chat_id != update.chat_id
            or binding.local_owner_user_id != owner_user_id
            or account.configured_owner_user_id != owner_user_id
        ):
            return None
        principal = self._principals.find_principal(binding.local_owner_user_id)
        if principal is None or principal.user_id != owner_user_id:
            return None
        return AuthorizedTelegramMessage(
            elfie_id=account.elfie_id,
            principal=principal,
            conversation_id=binding.conversation_id,
            external_actor_id=update.telegram_user_id,
            external_actor_display_name=update.display_name,
        )

    def mark_runtime_health(
        self, elfie_id: str, *, healthy: bool, issue: Optional[str] = None
    ) -> None:
        try:
            self._store.mark_account_health(
                elfie_id,
                status="active" if healthy else "attention",
                checked_at=_iso(self._now()),
                issue=None if healthy else (issue or "telegram_unavailable"),
            )
        except TelegramAccountPortError:
            return

    def save_next_update_id(self, elfie_id: str, next_update_id: int) -> None:
        self._store.save_next_update_id(
            elfie_id,
            next_update_id=next_update_id,
            synced_at=_iso(self._now()),
        )

    def _require_owned(self, principal: AccountPrincipal, raw_elfie_id: str) -> str:
        elfie_id = raw_elfie_id.strip()
        if not elfie_id:
            raise TelegramAccountNotFound("精灵不存在")
        try:
            owner_user_id = self._store.owner_user_id(elfie_id)
        except TelegramAccountPortError as error:
            raise TelegramAccountUnavailable(
                "Telegram account is temporarily unavailable"
            ) from error
        if owner_user_id is None or owner_user_id != principal.user_id:
            raise TelegramAccountNotFound("精灵不存在或不属于当前用户")
        return elfie_id

    @staticmethod
    def _result(
        elfie_id: str,
        account: Optional[StoredTelegramAccount],
        binding: Optional[StoredTelegramBinding],
        current_owner_user_id: int,
    ) -> TelegramAccountResult:
        if account is None:
            return TelegramAccountResult(
                elfie_id=elfie_id,
                state="unconfigured",
                bot_username=None,
                bot_display_name=None,
                bound_telegram_username=None,
                bound_display_name=None,
                last_checked_at=None,
                issue=None,
            )
        binding_current = (
            binding is not None
            and binding.local_owner_user_id == current_owner_user_id
            and account.configured_owner_user_id == current_owner_user_id
        )
        current_binding = binding if binding_current else None
        state: TelegramAccountState
        if account.status == "attention" or (
            account.configured_owner_user_id != current_owner_user_id
        ):
            state = "attention"
        elif binding_current:
            state = "active"
        else:
            state = "waiting_pairing"
        return TelegramAccountResult(
            elfie_id=elfie_id,
            state=state,
            bot_username=account.bot_username,
            bot_display_name=account.display_name,
            bound_telegram_username=(
                None if current_binding is None else current_binding.telegram_username
            ),
            bound_display_name=(
                None if current_binding is None else current_binding.display_name
            ),
            last_checked_at=account.last_checked_at,
            issue=account.issue,
        )

    def _restore_token(self, elfie_id: str, previous_token: str) -> None:
        try:
            if previous_token:
                self._tokens.replace(elfie_id, previous_token)
            else:
                self._tokens.delete(elfie_id)
        except (OSError, ValueError):
            pass

    def _sync_avatar(self, elfie_id: str, bot_token: str) -> None:
        source = self._portrait_source
        sync = self._avatar_sync
        if source is None or sync is None:
            return
        try:
            content = source.load_portrait(elfie_id, kind="headshot")
            if not content:
                return
            sync.sync_avatar(bot_token, content, "image/png")
        except Exception:
            # Profile polish must never turn a valid connection into a failed setup.
            # Adapters own transport/error sanitization; this boundary also keeps
            # unexpected avatar failures from affecting the saved account.
            _logger.warning("Telegram avatar sync skipped for Elfie %s", elfie_id)

    def _safe_mark_attention(self, elfie_id: str, checked_at: str, issue: str) -> None:
        try:
            self._store.mark_account_health(
                elfie_id,
                status="attention",
                checked_at=checked_at,
                issue=issue,
            )
        except TelegramAccountPortError:
            pass

    def _invalidate_pairing_sessions(self, elfie_id: str) -> None:
        with self._pairing_lock:
            self._invalidate_pairing_sessions_locked(elfie_id)

    def _invalidate_pairing_sessions_locked(self, elfie_id: str) -> None:
        expired = [
            digest
            for digest, session in self._pairing_sessions.items()
            if session.elfie_id == elfie_id
        ]
        for digest in expired:
            self._pairing_sessions.pop(digest, None)

    def _prune_pairing_sessions(self, now: datetime) -> None:
        expired = [
            digest
            for digest, session in self._pairing_sessions.items()
            if session.expires_at < now
        ]
        for digest in expired:
            self._pairing_sessions.pop(digest, None)


def _validate_bot_token(raw: str) -> str:
    token = raw.strip()
    if (
        not token
        or len(token) > _TOKEN_MAX_LENGTH
        or ":" not in token
        or any(character.isspace() for character in token)
    ):
        raise TelegramAccountInvalid("Telegram Bot Token 格式无效")
    return token


def _pairing_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


__all__ = ("TelegramAccountsService",)
