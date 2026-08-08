"""Shared Setup test helpers that exercise the current draft-based flow."""

from __future__ import annotations

from app.features.setup.service import OwnerAccount, create_first_owner_from_hash
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import hash_password


def create_test_owner(
    db_path: str,
    *,
    account_id: str = "owner",
    password: str = "secret123",
    display_name: str | None = None,
) -> OwnerAccount:
    """Create an Owner through the persisted Setup draft handoff."""
    repository = SetupInstallRepository(db_path)
    repository.save_owner_draft(
        account_id=account_id,
        display_name=display_name,
        password_hash=hash_password(password),
    )
    return create_first_owner_from_hash(db_path, repository.get_draft())
