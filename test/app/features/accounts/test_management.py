from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.features.accounts import (
    AccountConflict,
    AccountForbidden,
    AccountPrincipal,
    AccountProfileRecord,
    AccountProfileWrite,
    AccountsService,
    ChangePasswordCommand,
    CreateManagedAccountCommand,
    CurrentPasswordIncorrect,
    DeleteManagedAccountCommand,
    GetCurrentAccountQuery,
    ListManagedAccountsQuery,
    ManagedAccountHasElfies,
    ManagedAccountRecord,
    ManagedAccountRecords,
    OwnerAccountRecord,
    RecordAccountHeartbeatCommand,
    RecoverOwnerAccountCommand,
    SeedInitialOwnerCommand,
    StoredAvatar,
    UpdateAccountProfileCommand,
    UpdateManagedAccountQuotaCommand,
    UploadAvatarCommand,
    hash_password,
)
from app.features.accounts.ports import AccountPersistenceConflict


class ManagementStub:
    def __init__(self) -> None:
        self.profile = AccountProfileRecord(
            user_id=1,
            account_id="owner",
            password_hash=hash_password("old-password"),
            display_name="Owner",
            gender="male",
            birth_date=None,
            role="owner",
            avatar_path=None,
            avatar_color=0,
            avatar_kind="initials",
            theme_key="warm-paper",
            default_landing_page="manage",
            created_at="2026-08-01T00:00:00+00:00",
            updated_at="2026-08-01T00:00:00+00:00",
            elfie_count=0,
        )
        self.users = {
            1: ManagedAccountRecord(
                user_id=1,
                account_id="owner",
                display_name="Owner",
                role="owner",
                gender="male",
                birth_date=None,
                presence="online",
                last_seen_at=None,
                language="zh-CN",
                created_at="2026-08-01T00:00:00+00:00",
                elfie_count=0,
                elfie_quota_override=None,
                avatar_path=None,
            ),
            2: ManagedAccountRecord(
                user_id=2,
                account_id="member",
                display_name=None,
                role="user",
                gender="female",
                birth_date=None,
                presence="offline",
                last_seen_at=None,
                language="zh-CN",
                created_at="2026-08-02T00:00:00+00:00",
                elfie_count=0,
                elfie_quota_override=None,
                avatar_path=None,
            ),
        }
        self.owner = OwnerAccountRecord(
            user_id=1,
            account_id="owner",
            display_name="Owner",
            created_at="2026-08-01T00:00:00+00:00",
            updated_at="2026-08-01T00:00:00+00:00",
        )
        self.password_change: tuple[int, str, str] | None = None
        self.last_heartbeat: tuple[int, str] | None = None

    def find_profile(self, user_id: int) -> AccountProfileRecord | None:
        return self.profile if user_id == self.profile.user_id else None

    def record_heartbeat(self, user_id: int, last_seen_at: str) -> bool:
        self.last_heartbeat = (user_id, last_seen_at)
        return user_id in self.users

    def update_profile(
        self, user_id: int, profile: AccountProfileWrite
    ) -> AccountProfileRecord | None:
        if profile.account_id == "duplicate":
            raise AccountPersistenceConflict
        self.profile = replace(
            self.profile,
            account_id=profile.account_id,
            display_name=profile.display_name,
            gender=profile.gender,
            birth_date=profile.birth_date,
            avatar_color=profile.avatar_color,
            avatar_kind=profile.avatar_kind,
        )
        return self.profile

    def change_password(
        self, user_id: int, password_hash: str, current_session_token: str
    ) -> None:
        self.password_change = (user_id, password_hash, current_session_token)

    def update_avatar_path(self, user_id: int, relative_path: str) -> None:
        if user_id == self.profile.user_id:
            self.profile = replace(self.profile, avatar_path=relative_path)

    def list_managed_accounts(self) -> ManagedAccountRecords:
        return ManagedAccountRecords(items=tuple(self.users.values()))

    def get_managed_account(self, user_id: int) -> ManagedAccountRecord | None:
        return self.users.get(user_id)

    def create_managed_account(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str,
        role: str,
    ) -> int:
        _ = password_hash
        user_id = max(self.users) + 1
        self.users[user_id] = replace(
            self.users[2],
            user_id=user_id,
            account_id=account_id,
            display_name=display_name,
            role=role,
        )
        return user_id

    def update_managed_quota(self, user_id: int, quota: int | None) -> bool:
        record = self.users.get(user_id)
        if record is None or record.role == "owner":
            return False
        self.users[user_id] = replace(record, elfie_quota_override=quota)
        return True

    def delete_managed_account(self, user_id: int) -> bool:
        return self.users.pop(user_id, None) is not None

    def find_owner_account(self) -> OwnerAccountRecord | None:
        return self.owner

    def recover_owner_account(
        self, user_id: int, account_id: str, password_hash: str
    ) -> OwnerAccountRecord | None:
        _ = password_hash
        self.owner = replace(self.owner, account_id=account_id)
        return self.owner


class AvatarStub:
    def __init__(self) -> None:
        self.stored: StoredAvatar | None = None

    def store(self, user_id: int, content_type: str, content: bytes) -> StoredAvatar:
        self.stored = StoredAvatar(
            relative_path=f"users/{user_id}/assets/avatar.png",
            content_type=content_type,
            content=content,
        )
        return self.stored


class QuotaPolicyStub:
    def default_elfie_limit(self) -> int:
        return 3


OWNER = AccountPrincipal(1, "owner", "owner", "manage")
ADMIN = AccountPrincipal(3, "admin", "admin", "manage")


def _service() -> tuple[AccountsService, ManagementStub, AvatarStub]:
    management = ManagementStub()
    avatars = AvatarStub()
    service = AccountsService(
        management=management,
        avatars=avatars,
        quota_policy=QuotaPolicyStub(),
    )
    return service, management, avatars


def test_profile_and_password_use_cases_stay_inside_accounts_facade() -> None:
    service, management, _ = _service()

    updated = service.update_profile(
        OWNER,
        UpdateAccountProfileCommand(
            fields=frozenset({"account_id", "display_name", "gender"}),
            account_id="owner-new",
            display_name=" Owner New ",
            gender="female",
        ),
    )
    service.change_password(
        OWNER,
        ChangePasswordCommand("old-password", "new-password", "current-token"),
    )

    assert updated.account_id == "owner-new"
    assert updated.display_name == "Owner New"
    assert updated.gender == "female"
    assert management.password_change is not None
    assert management.password_change[2] == "current-token"


def test_initial_owner_seed_is_an_explicit_accounts_use_case() -> None:
    class InitialOwnerSeedStub:
        calls = 0

        def seed_initial_owner(self) -> bool:
            self.calls += 1
            return True

    seed = InitialOwnerSeedStub()
    service = AccountsService(initial_owner_seed=seed)

    result = service.seed_initial_owner(SeedInitialOwnerCommand())

    assert result.created is True
    assert seed.calls == 1


def test_heartbeat_records_current_principal_with_injected_utc_clock() -> None:
    management = ManagementStub()
    now = datetime(2026, 8, 11, 8, 0, tzinfo=timezone.utc)
    service = AccountsService(management=management, now=lambda: now)

    result = service.record_heartbeat(OWNER, RecordAccountHeartbeatCommand())

    assert result.last_seen_at == "2026-08-11T08:00:00.000000+00:00"
    assert management.last_heartbeat == (1, result.last_seen_at)


def test_profile_conflict_and_wrong_password_are_stable_business_errors() -> None:
    service, _, _ = _service()

    with pytest.raises(AccountConflict):
        service.update_profile(
            OWNER,
            UpdateAccountProfileCommand(
                fields=frozenset({"account_id"}), account_id="duplicate"
            ),
        )
    with pytest.raises(CurrentPasswordIncorrect):
        service.change_password(
            OWNER,
            ChangePasswordCommand("wrong", "new-password", "current-token"),
        )


def test_manager_rules_and_quota_projection_are_owned_by_accounts() -> None:
    service, _, _ = _service()

    listed = service.list_managed_accounts(OWNER, ListManagedAccountsQuery())
    updated = service.update_managed_quota(
        OWNER, UpdateManagedAccountQuotaCommand(user_id=2, elfie_quota_override=6)
    )

    assert listed.items[1].effective_elfie_limit == 3
    assert updated.effective_elfie_limit == 6
    with pytest.raises(AccountForbidden):
        service.create_managed_account(
            ADMIN,
            CreateManagedAccountCommand(
                account_id="admin02",
                display_name=None,
                password="new-password",
                role="admin",
            ),
        )


def test_account_with_elfies_cannot_be_deleted() -> None:
    service, management, _ = _service()
    management.users[2] = replace(management.users[2], elfie_count=1)

    with pytest.raises(ManagedAccountHasElfies):
        service.delete_managed_account(OWNER, DeleteManagedAccountCommand(user_id=2))


def test_avatar_signature_and_owner_recovery_reuse_accounts_facade() -> None:
    service, management, avatars = _service()
    png = b"\x89PNG\r\n\x1a\ncontent"

    service.upload_avatar(OWNER, UploadAvatarCommand("image/png", png))
    recovered = service.recover_owner_account(
        RecoverOwnerAccountCommand("owner-new", "new-password")
    )

    assert avatars.stored is not None
    assert recovered.account_id == "owner-new"
    assert service.get_current_account(OWNER, GetCurrentAccountQuery()).user_id == 1
    assert management.owner.account_id == "owner-new"
