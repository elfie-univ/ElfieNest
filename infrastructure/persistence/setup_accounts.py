"""Setup-owned account Port Adapter over the public Accounts Facade."""

from __future__ import annotations

from app.features.accounts import (
    AccountConflict,
    AccountNotFound,
    AccountPrincipal,
    AccountsService,
    AccountsUnavailable,
    AccountValidationFailed,
    CreateFirstOwnerCommand,
    GetOwnerAccountQuery,
    HasOwnerQuery,
    UpdateLandingPageCommand,
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

    def find_owner(self) -> CreatedSetupOwner | None:
        try:
            owner = self._accounts.get_owner_account(GetOwnerAccountQuery())
        except AccountNotFound:
            return None
        except AccountsUnavailable as error:
            raise SetupInstallationPortError("unable to read Owner") from error
        return CreatedSetupOwner(
            user_id=owner.user_id,
            account_id=owner.account_id,
            display_name=owner.display_name,
        )

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

    def set_default_landing_page(self, user_id: int, page: str) -> None:
        try:
            owner = self.find_owner()
            if owner is None or owner.user_id != user_id:
                raise SetupInstallationPortError("unable to read Setup Owner")
            self._accounts.update_default_landing_page(
                AccountPrincipal(
                    user_id=owner.user_id,
                    account_id=owner.account_id,
                    role="owner",
                ),
                UpdateLandingPageCommand(default_landing_page=page),
            )
        except SetupInstallationPortError:
            raise
        except AccountsUnavailable as error:
            raise SetupInstallationPortError(
                "unable to set Owner default landing page"
            ) from error


__all__ = ("SetupAccountsAdapter",)
