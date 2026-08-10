"""Strict HTTP DTOs for administrator Elfie projections."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.interfaces.api.v1.elfies.models import (
    ElfiePermissionsResponse,
    ElfieProfileResponse,
)


class _StrictAdminModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ElfieOwnerResponse(_StrictAdminModel):
    user_id: int
    account_id: str
    display_name: Optional[str]


class AdminElfieResponse(_StrictAdminModel):
    owner: ElfieOwnerResponse
    permissions: ElfiePermissionsResponse
    profile: ElfieProfileResponse


class AdminElfiesResponse(_StrictAdminModel):
    items: tuple[AdminElfieResponse, ...]


__all__ = ("AdminElfieResponse", "AdminElfiesResponse", "ElfieOwnerResponse")
