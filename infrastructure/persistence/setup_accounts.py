"""Setup-owned account Port Adapter over the public Accounts Facade."""

from __future__ import annotations

from app.features.accounts import (
    AccountConflict,
    AccountsService,
    AccountsUnavailable,
    AccountValidationFailed,
    CreateFirstOwnerCommand,
    HasOwnerQuery,
)
from app.features.setup import SetupPortError, StoredSetupDraft
from app.orchestration.setup_installation import (
    CreatedSetupOwner,
    SetupInstallationConflict,
    SetupInstallationPortError,
)


class SetupAccountsAdapter:
    def __init__(self, accounts: AccountsService) -> None:
        self._accounts = accounts

    def has_owner(self) -> bool:
        try:
            return self._accounts.has_owner(HasOwnerQuery())
        except AccountsUnavailable as error:
            raise SetupPortError("unable to read Owner status") from error

    def create_first_owner(self, draft: StoredSetupDraft) -> CreatedSetupOwner:
        if draft.owner_account_id is None or draft.password_hash is None:
            raise SetupInstallationConflict("Setup Owner 草稿不完整")
        try:
            owner = self._accounts.create_first_owner(
                CreateFirstOwnerCommand(
                    account_id=draft.owner_account_id,
                    display_name=draft.display_name,
                    password_hash=draft.password_hash,
                )
            )
        except (AccountConflict, AccountValidationFailed) as error:
            raise SetupInstallationConflict(str(error)) from error
        except AccountsUnavailable as error:
            raise SetupInstallationPortError("unable to create first Owner") from error
        return CreatedSetupOwner(
            user_id=owner.user_id,
            account_id=owner.account_id,
            display_name=owner.display_name,
        )

    def issue_session(self, user_id: int) -> tuple[str, int]:
        try:
            return (
                self._accounts.create_session(user_id),
                self._accounts.session_ttl_seconds(),
            )
        except AccountsUnavailable as error:
            raise SetupInstallationPortError("unable to issue Owner session") from error


__all__ = ("SetupAccountsAdapter",)
