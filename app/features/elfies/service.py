"""Authorized read use-cases for Elfie directory and profile projections."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal, is_manager
from elfie.profile import SpeciesCatalog, current_species_catalog

from .cognition import project_cognition
from .errors import ElfieNotFound, ElfiesForbidden, ElfiesUnavailable
from .models import (
    AdminElfieResult,
    BigFiveResult,
    ElfieAppearanceResult,
    ElfieOwnerResult,
    ElfiePermissionsResult,
    ElfiePortraitResult,
    ElfieProfileDetailResult,
    ElfieProfileResult,
    ElfieSpeciesPresentation,
    GetElfiePortraitQuery,
    GetElfieProfileQuery,
    ListAdminElfiesQuery,
    ListVisibleElfiesQuery,
    VisibleElfieResult,
)
from .ports import (
    ElfieDirectoryRecord,
    ElfieProfileRecord,
    ElfiesPortError,
    ElfiesQueryPort,
)

_OWNED_PERMISSIONS = ElfiePermissionsResult(
    can_view_profile=True,
    can_view_cognition=True,
)
_ADMIN_PERMISSIONS = ElfiePermissionsResult(
    can_view_profile=True,
    can_view_cognition=False,
)
_VISITOR_PERMISSIONS = ElfiePermissionsResult(
    can_view_profile=True,
    can_view_cognition=False,
)


class ElfiesService:
    def __init__(
        self,
        queries: ElfiesQueryPort,
        *,
        catalog: SpeciesCatalog | None = None,
    ) -> None:
        self._queries = queries
        self._catalog = catalog or current_species_catalog()

    def list_visible(
        self,
        principal: AccountPrincipal,
        query: ListVisibleElfiesQuery,
    ) -> tuple[VisibleElfieResult, ...]:
        try:
            records = self._queries.list_directory(
                owner_user_id=(
                    principal.user_id if query.relationship == "owned" else None
                ),
            )
            return tuple(
                VisibleElfieResult(
                    relationship=(
                        "owned"
                        if record.owner_user_id == principal.user_id
                        else "other"
                    ),
                    permissions=(
                        _OWNED_PERMISSIONS
                        if record.owner_user_id == principal.user_id
                        else _VISITOR_PERMISSIONS
                    ),
                    profile=self._profile(record),
                )
                for record in records
            )
        except ElfiesPortError as error:
            raise ElfiesUnavailable("Elfie directory unavailable") from error

    def get_profile(
        self,
        principal: AccountPrincipal,
        query: GetElfieProfileQuery,
    ) -> ElfieProfileDetailResult:
        if not query.elfie_id.strip():
            raise ElfieNotFound("Elfie not found")
        try:
            record = self._queries.get_directory(query.elfie_id)
            if record is None:
                raise ElfieNotFound("Elfie not found")
            profile = self._profile(record)
            owned = record.owner_user_id == principal.user_id
            cognition = (
                project_cognition(
                    self._queries.load_cognition(record.elfie_id),
                    elfie_name=record.name,
                )
                if owned
                else None
            )
        except ElfiesPortError as error:
            raise ElfiesUnavailable("Elfie profile unavailable") from error
        return ElfieProfileDetailResult(
            relationship="owned" if owned else "other",
            permissions=_OWNED_PERMISSIONS if owned else _VISITOR_PERMISSIONS,
            profile=profile,
            private_cognition=cognition,
        )

    def get_portrait(
        self,
        principal: AccountPrincipal,
        query: GetElfiePortraitQuery,
    ) -> ElfiePortraitResult:
        if not query.elfie_id.strip() or query.kind not in ("headshot", "full_body"):
            raise ElfieNotFound("Elfie not found")
        try:
            record = self._queries.get_directory(query.elfie_id)
            if record is None:
                raise ElfieNotFound("Elfie not found")
            content = self._queries.load_portrait(query.elfie_id, kind=query.kind)
        except ElfiesPortError as error:
            raise ElfiesUnavailable("Elfie portrait unavailable") from error
        if content is None:
            raise ElfieNotFound("Elfie portrait not found")
        return ElfiePortraitResult(content=content)

    def list_admin(
        self,
        principal: AccountPrincipal,
        query: ListAdminElfiesQuery,
    ) -> tuple[AdminElfieResult, ...]:
        if not is_manager(principal.role):
            raise ElfiesForbidden("Elfie administration requires a manager")
        species_id = query.species_id.strip() if query.species_id else None
        try:
            records = self._queries.list_directory(
                owner_user_id=query.owner_user_id,
                species_id=species_id,
            )
            return tuple(
                AdminElfieResult(
                    owner=ElfieOwnerResult(
                        user_id=record.owner_user_id,
                        account_id=record.owner_account_id,
                        display_name=record.owner_display_name,
                    ),
                    permissions=_ADMIN_PERMISSIONS,
                    profile=self._profile(record),
                )
                for record in records
            )
        except ElfiesPortError as error:
            raise ElfiesUnavailable("Elfie administration unavailable") from error

    def _profile(self, record: ElfieDirectoryRecord) -> ElfieProfileResult:
        source = self._queries.load_profile(record.elfie_id)
        big_five = _big_five(source)
        return ElfieProfileResult(
            elfie_id=record.elfie_id,
            name=record.name,
            species_id=record.species_id,
            species=_species_presentation(self._catalog, record.species_id),
            gender=record.gender,
            birth_date=record.birth_date,
            summary=record.summary,
            adopted_at=record.adopted_at,
            profile_status=source.status,
            big_five=big_five,
            personality_tags=_personality_tags(record.summary, big_five),
            portrait_url=source.portrait_url,
            appearance=(
                None
                if source.appearance is None
                else ElfieAppearanceResult(
                    species_id=source.appearance.species_id,
                    profile_version=source.appearance.profile_version,
                    height_scale=source.appearance.height_scale,
                    build_scale=source.appearance.build_scale,
                    height_label=source.appearance.height_label,
                    build_label=source.appearance.build_label,
                    bone_scales=source.appearance.bone_scales,
                    blend_shapes=source.appearance.blend_shapes,
                    material_parameters=source.appearance.material_parameters,
                    species_traits=source.appearance.species_traits,
                )
            ),
        )


def _species_presentation(
    catalog: SpeciesCatalog,
    species_id: str,
) -> ElfieSpeciesPresentation | None:
    try:
        definition = catalog.definition(species_id)
    except ValueError:
        return None
    return ElfieSpeciesPresentation(
        species_id=definition.species_id,
        canon_id=definition.canon_id,
        display_name=definition.display_name,
        display_name_zh=definition.display_name_zh,
        earth_shape_label=definition.earth_shape_label,
        status=definition.status,
    )


def _big_five(source: ElfieProfileRecord) -> BigFiveResult | None:
    if source.status != "ready":
        return None
    return BigFiveResult(
        openness=source.openness,
        conscientiousness=source.conscientiousness,
        extraversion=source.extraversion,
        agreeableness=source.agreeableness,
        neuroticism=source.neuroticism,
    )


def _personality_tags(
    summary: str | None,
    big_five: BigFiveResult | None,
) -> tuple[str, ...]:
    tags = [summary] if summary else []
    if big_five is None:
        return tuple(tags)
    ranked = sorted(
        (
            (name, value)
            for name, value in (
                ("openness", big_five.openness),
                ("conscientiousness", big_five.conscientiousness),
                ("extraversion", big_five.extraversion),
                ("agreeableness", big_five.agreeableness),
                ("neuroticism", big_five.neuroticism),
            )
            if value is not None
        ),
        key=lambda item: (-item[1], item[0]),
    )
    tags.extend(name for name, _ in ranked[:2])
    return tuple(tags)


__all__ = ("ElfiesService",)
