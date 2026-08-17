"""Owner authorization, token setup, pairing, and Discord identity mapping."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Optional, Tuple
from urllib.parse import quote

from app.features.accounts import AccountPrincipal

from .avatar_ports import ElfiePortraitPort
from .discord_errors import (
    DiscordAccountConflict,
    DiscordAccountInvalid,
    DiscordAccountNotFound,
    DiscordAccountUnavailable,
)
from .discord_models import (
    AuthorizedDiscordMessage,
    ConfigureDiscordAccountCommand,
    CreateDiscordPairingSessionCommand,
    DisconnectDiscordAccountCommand,
    DiscordAccountResult,
    DiscordAccountState,
    DiscordPairingCompletion,
    DiscordPairingSessionResult,
    GetDiscordAccountQuery,
)
from .discord_port_models import (
    DiscordPrivateUpdate,
    DiscordRuntimeAccount,
    StoredDiscordAccount,
    StoredDiscordBinding,
)
from .discord_ports import (
    DiscordAccountPortError,
    DiscordAccountPrincipalLookupPort,
    DiscordAccountStoreConflict,
    DiscordAccountStorePort,
    DiscordBotAvatarPort,
    DiscordBotInspectionPort,
    DiscordBotTokenRejected,
    DiscordBotTransportError,
    DiscordTokenPort,
)

_PAIRING_TTL = timedelta(minutes=10)
_TOKEN_MAX_LENGTH = 512
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PairingSession:
    elfie_id: str
    bot_id: str
    local_owner_user_id: int
    local_owner_account_id: str
    expires_at: datetime


class DiscordAccountsService:
    """Single product authority for one Elfie's Discord Bot connection."""

    def __init__(
        self,
        store: DiscordAccountStorePort,
        tokens: DiscordTokenPort,
        inspection: DiscordBotInspectionPort,
        principals: DiscordAccountPrincipalLookupPort,
        *,
        now: Optional[Callable[[], datetime]] = None,
        pairing_token: Optional[Callable[[], str]] = None,
        portrait_source: Optional[ElfiePortraitPort] = None,
        avatar_sync: Optional[DiscordBotAvatarPort] = None,
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
        query: GetDiscordAccountQuery,
    ) -> DiscordAccountResult:
        elfie_id = self._require_owned(principal, query.elfie_id)
        try:
            account = self._store.get_account(elfie_id)
            binding = self._store.get_binding(elfie_id) if account is not None else None
        except DiscordAccountPortError as error:
            raise DiscordAccountUnavailable(
                "Discord account is temporarily unavailable"
            ) from error
        return self._result(elfie_id, account, binding, principal.user_id)

    def configure_account(
        self,
        principal: AccountPrincipal,
        command: ConfigureDiscordAccountCommand,
    ) -> DiscordAccountResult:
        elfie_id = self._require_owned(principal, command.elfie_id)
        token = _validate_bot_token(command.bot_token)
        try:
            inspected = self._inspection.inspect_bot(token)
        except DiscordBotTokenRejected as error:
            raise DiscordAccountInvalid("Discord Bot Token 无效") from error
        except DiscordBotTransportError as error:
            raise DiscordAccountUnavailable("暂时无法连接 Discord") from error

        checked_at = _iso(self._now())
        credential_ref = self._tokens.credential_ref(elfie_id)
        previous_token = self._tokens.load(credential_ref)
        account = StoredDiscordAccount(
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
                raise ValueError("Discord credential reference changed unexpectedly")
            self._store.save_account(account)
        except DiscordAccountStoreConflict as error:
            self._restore_token(elfie_id, previous_token)
            raise DiscordAccountConflict(str(error)) from error
        except (OSError, ValueError, DiscordAccountPortError) as error:
            self._restore_token(elfie_id, previous_token)
            raise DiscordAccountUnavailable(
                "Discord account could not be saved"
            ) from error
        self._invalidate_pairing_sessions(elfie_id)
        self._sync_avatar(elfie_id, token)
        binding = self._store.get_binding(elfie_id)
        return self._result(elfie_id, account, binding, principal.user_id)

    def disconnect_account(
        self,
        principal: AccountPrincipal,
        command: DisconnectDiscordAccountCommand,
    ) -> DiscordAccountResult:
        elfie_id = self._require_owned(principal, command.elfie_id)
        disconnected_at = _iso(self._now())
        try:
            self._store.disconnect_account(elfie_id, disconnected_at=disconnected_at)
            self._tokens.delete(elfie_id)
        except (OSError, ValueError, DiscordAccountPortError) as error:
            raise DiscordAccountUnavailable(
                "Discord account could not be disconnected"
            ) from error
        self._invalidate_pairing_sessions(elfie_id)
        return self._result(elfie_id, None, None, principal.user_id)

    def create_pairing_session(
        self,
        principal: AccountPrincipal,
        command: CreateDiscordPairingSessionCommand,
    ) -> DiscordPairingSessionResult:
        elfie_id = self._require_owned(principal, command.elfie_id)
        try:
            account = self._store.get_account(elfie_id)
        except DiscordAccountPortError as error:
            raise DiscordAccountUnavailable(
                "Discord account is temporarily unavailable"
            ) from error
        if account is None:
            raise DiscordAccountInvalid("请先配置 Discord 机器人")
        if account.status != "active":
            raise DiscordAccountInvalid("请先重新配置 Discord 机器人")
        code = self._pairing_token()
        if not code or len(code) > 64:
            raise DiscordAccountUnavailable("Unable to generate pairing code")
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
        scope = quote("bot applications.commands", safe="")
        invite_url = (
            "https://discord.com/oauth2/authorize?"
            f"client_id={quote(account.bot_id, safe='')}&scope={scope}&permissions=0"
        )
        return DiscordPairingSessionResult(
            invite_url=invite_url,
            bot_profile_url=f"https://discord.com/users/{account.bot_id}",
            pairing_code=code,
            expires_at=_iso(expires_at),
        )

    def runtime_accounts(self) -> Tuple[DiscordRuntimeAccount, ...]:
        now = _iso(self._now())
        try:
            stored = self._store.list_active_accounts()
        except DiscordAccountPortError:
            return ()
        runtime: list[DiscordRuntimeAccount] = []
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
                DiscordRuntimeAccount(
                    account=account,
                    bot_token=token,
                    binding=self._store.get_binding(account.elfie_id),
                )
            )
        return tuple(runtime)

    def complete_pairing(
        self,
        account: StoredDiscordAccount,
        update: DiscordPrivateUpdate,
        code: str,
    ) -> DiscordPairingCompletion:
        if not update.is_dm or update.sender_is_bot:
            return DiscordPairingCompletion(False, "private_human_required")
        now = self._now()
        digest = _pairing_digest(code)
        with self._pairing_lock:
            self._prune_pairing_sessions(now)
            session = self._pairing_sessions.get(digest)
            if session is None:
                return DiscordPairingCompletion(False, "pairing_expired")
            if (
                session.elfie_id != account.elfie_id
                or session.bot_id != account.bot_id
                or session.expires_at < now
            ):
                self._pairing_sessions.pop(digest, None)
                return DiscordPairingCompletion(False, "pairing_expired")
            if (
                self._store.owner_user_id(account.elfie_id)
                != session.local_owner_user_id
            ):
                self._pairing_sessions.pop(digest, None)
                return DiscordPairingCompletion(False, "owner_changed")
            principal = self._principals.find_principal(session.local_owner_user_id)
            if principal is None:
                self._pairing_sessions.pop(digest, None)
                return DiscordPairingCompletion(False, "owner_unavailable")
            bound_at = _iso(now)
            try:
                self._store.replace_binding(
                    StoredDiscordBinding(
                        elfie_id=account.elfie_id,
                        discord_user_id=update.discord_user_id,
                        discord_channel_id=update.channel_id,
                        discord_username=update.discord_username,
                        display_name=update.display_name,
                        local_owner_user_id=principal.user_id,
                        local_owner_account_id=principal.account_id,
                        conversation_id=f"discord:{update.channel_id}",
                        bound_at=bound_at,
                    )
                )
            except DiscordAccountPortError:
                return DiscordPairingCompletion(False, "binding_unavailable")
            self._pairing_sessions.pop(digest, None)
        return DiscordPairingCompletion(True)

    def authorize_inbound(
        self,
        account: StoredDiscordAccount,
        update: DiscordPrivateUpdate,
    ) -> Optional[AuthorizedDiscordMessage]:
        if not update.is_dm or update.sender_is_bot:
            return None
        try:
            binding = self._store.get_binding(account.elfie_id)
            owner_user_id = self._store.owner_user_id(account.elfie_id)
        except DiscordAccountPortError:
            return None
        if (
            binding is None
            or binding.discord_user_id != update.discord_user_id
            or binding.discord_channel_id != update.channel_id
            or binding.local_owner_user_id != owner_user_id
            or account.configured_owner_user_id != owner_user_id
        ):
            return None
        principal = self._principals.find_principal(binding.local_owner_user_id)
        if principal is None or principal.user_id != owner_user_id:
            return None
        return AuthorizedDiscordMessage(
            elfie_id=account.elfie_id,
            principal=principal,
            conversation_id=binding.conversation_id,
            external_actor_id=update.discord_user_id,
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
                issue=None if healthy else (issue or "discord_unavailable"),
            )
        except DiscordAccountPortError:
            return

    def _require_owned(self, principal: AccountPrincipal, raw_elfie_id: str) -> str:
        elfie_id = raw_elfie_id.strip()
        if not elfie_id:
            raise DiscordAccountNotFound("精灵不存在")
        try:
            owner_user_id = self._store.owner_user_id(elfie_id)
        except DiscordAccountPortError as error:
            raise DiscordAccountUnavailable(
                "Discord account is temporarily unavailable"
            ) from error
        if owner_user_id is None or owner_user_id != principal.user_id:
            raise DiscordAccountNotFound("精灵不存在或不属于当前用户")
        return elfie_id

    @staticmethod
    def _result(
        elfie_id: str,
        account: Optional[StoredDiscordAccount],
        binding: Optional[StoredDiscordBinding],
        current_owner_user_id: int,
    ) -> DiscordAccountResult:
        if account is None:
            return DiscordAccountResult(
                elfie_id=elfie_id,
                state="unconfigured",
                bot_username=None,
                bot_display_name=None,
                bound_discord_username=None,
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
        state: DiscordAccountState
        if account.status == "attention" or (
            account.configured_owner_user_id != current_owner_user_id
        ):
            state = "attention"
        elif binding_current:
            state = "active"
        else:
            state = "waiting_pairing"
        return DiscordAccountResult(
            elfie_id=elfie_id,
            state=state,
            bot_username=account.bot_username,
            bot_display_name=account.display_name,
            bound_discord_username=(
                None if current_binding is None else current_binding.discord_username
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
            _logger.warning("Discord avatar sync skipped for Elfie %s", elfie_id)

    def _safe_mark_attention(self, elfie_id: str, checked_at: str, issue: str) -> None:
        try:
            self._store.mark_account_health(
                elfie_id,
                status="attention",
                checked_at=checked_at,
                issue=issue,
            )
        except DiscordAccountPortError:
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
        or any(character.isspace() for character in token)
    ):
        raise DiscordAccountInvalid("Discord Bot Token 格式无效")
    return token


def _pairing_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


__all__ = ("DiscordAccountsService",)
