from __future__ import annotations

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.elfies import (
    CognitionEdgeRecord,
    CognitionEntityRecord,
    CognitionEventRecord,
    CognitionSnapshotRecord,
    CognitionTopicRecord,
    ElfieDirectoryRecord,
    ElfiePortraitInvalid,
    ElfieProfileRecord,
    ElfiesForbidden,
    ElfiesService,
    GetElfieProfileQuery,
    ListAdminElfiesQuery,
    ListVisibleElfiesQuery,
    UpdateElfiePortraitCommand,
)


class FakeElfiesPort:
    def __init__(self) -> None:
        self.saved_portraits: dict[str, bytes] = {}
        self.records = (
            _record("00000001", owner_user_id=1, owner_account_id="alice"),
            _record("00000002", owner_user_id=2, owner_account_id="bob"),
        )

    def list_directory(
        self,
        *,
        owner_user_id: int | None = None,
        species_id: str | None = None,
    ) -> tuple[ElfieDirectoryRecord, ...]:
        return tuple(
            record
            for record in self.records
            if (owner_user_id is None or record.owner_user_id == owner_user_id)
            and (species_id is None or record.species_id == species_id)
        )

    def get_directory(self, elfie_id: str) -> ElfieDirectoryRecord | None:
        return next(
            (record for record in self.records if record.elfie_id == elfie_id),
            None,
        )

    def save_portrait(self, elfie_id: str, content: bytes) -> None:
        self.saved_portraits[elfie_id] = content

    def load_profile(self, elfie_id: str) -> ElfieProfileRecord:
        del elfie_id
        return ElfieProfileRecord(
            status="ready",
            openness=0.9,
            conscientiousness=0.5,
            extraversion=0.8,
            agreeableness=0.7,
            neuroticism=0.2,
        )

    def load_cognition(self, elfie_id: str) -> CognitionSnapshotRecord:
        return CognitionSnapshotRecord(
            status="ready",
            entities=(
                CognitionEntityRecord(
                    id="self-db",
                    entity_type="elfie",
                    name=elfie_id,
                    summary="",
                    relationship_label="",
                    relation_key="",
                    weight=1.0,
                    closeness=1.0,
                    is_self=True,
                    world_ring=None,
                    concept_kind=None,
                    core_key=None,
                ),
                CognitionEntityRecord(
                    id="owner",
                    entity_type="person",
                    name="Alice",
                    summary="",
                    relationship_label="主人",
                    relation_key="owner",
                    weight=0.9,
                    closeness=0.95,
                    is_self=False,
                    world_ring="family",
                    concept_kind=None,
                    core_key=None,
                ),
                CognitionEntityRecord(
                    id="source",
                    entity_type="concept",
                    name="观察",
                    summary="",
                    relationship_label="",
                    relation_key="",
                    weight=0.8,
                    closeness=0.0,
                    is_self=False,
                    world_ring=None,
                    concept_kind="source",
                    core_key=None,
                ),
                CognitionEntityRecord(
                    id="belief",
                    entity_type="concept",
                    name="家是安全的",
                    summary="",
                    relationship_label="",
                    relation_key="",
                    weight=0.7,
                    closeness=0.0,
                    is_self=False,
                    world_ring="self",
                    concept_kind="belief",
                    core_key="world",
                ),
            ),
            events=(
                CognitionEventRecord(
                    id="event-adoption",
                    occurred_at="2026-08-01T00:00:00Z",
                    event_type="adoption",
                    description="被 Alice 领养",
                    importance=0.95,
                    topics=(CognitionTopicRecord("Alice", "person"),),
                    major_event=True,
                    lifecycle_event="adoption",
                    title="被领养",
                    changed="有了家",
                    people=("Alice",),
                ),
            ),
            edges=(
                CognitionEdgeRecord(
                    source="source",
                    target="belief",
                    relation_type="supports",
                    summary="支持",
                    weight=0.8,
                ),
            ),
            core_world="世界可以被理解",
        )


def _record(
    elfie_id: str,
    *,
    owner_user_id: int,
    owner_account_id: str,
) -> ElfieDirectoryRecord:
    return ElfieDirectoryRecord(
        elfie_id=elfie_id,
        name=f"Elfie {elfie_id}",
        owner_user_id=owner_user_id,
        owner_account_id=owner_account_id,
        owner_display_name=owner_account_id.title(),
        species_id="fox",
        gender=None,
        birth_date=None,
        adopted_at="2026-08-01T00:00:00Z",
        summary="好奇探索",
    )


def _principal(
    user_id: int = 1,
    role: AccountRole = "user",
) -> AccountPrincipal:
    return AccountPrincipal(
        user_id=user_id,
        account_id="alice",
        role=role,
        default_landing_page="/chat",
    )


def _service(
    port: FakeElfiesPort | None = None,
    *,
    catalog=None,
) -> ElfiesService:
    source = port or FakeElfiesPort()
    return ElfiesService(source, source, catalog=catalog)


def test_member_directory_exposes_visible_elfies_with_bounded_permissions() -> None:
    service = _service()

    results = service.list_visible(_principal(), ListVisibleElfiesQuery())

    assert [item.profile.elfie_id for item in results] == ["00000001", "00000002"]
    assert [item.relationship for item in results] == ["owned", "other"]
    assert results[0].permissions.can_view_profile is True
    assert results[0].permissions.can_view_cognition is True
    assert results[0].profile.personality_tags == (
        "好奇探索",
        "openness",
        "extraversion",
    )
    assert results[0].profile.species is not None
    assert results[0].profile.species.display_name_zh == "灵狐"
    assert results[1].permissions.can_view_profile is True
    assert results[1].permissions.can_view_cognition is False

    owned = service.list_visible(
        _principal(), ListVisibleElfiesQuery(relationship="owned")
    )
    assert [item.profile.elfie_id for item in owned] == ["00000001"]


def test_member_profile_of_another_member_is_public_without_cognition() -> None:
    service = _service()

    result = service.get_profile(
        _principal(),
        GetElfieProfileQuery(elfie_id="00000002"),
    )

    assert result.relationship == "other"
    assert result.private_cognition is None


def test_owner_portrait_update_writes_the_supplied_png() -> None:
    port = FakeElfiesPort()
    service = _service(port)
    payload = b"\x89PNG\r\n\x1a\nupdated"

    result = service.update_portrait(
        _principal(),
        UpdateElfiePortraitCommand(
            elfie_id="00000001",
            content_type="image/png",
            content=payload,
        ),
    )

    assert result.content == payload
    assert port.saved_portraits == {"00000001": payload}


def test_portrait_update_rejects_non_owner_and_invalid_content() -> None:
    port = FakeElfiesPort()
    service = _service(port)

    with pytest.raises(ElfiesForbidden):
        service.update_portrait(
            _principal(),
            UpdateElfiePortraitCommand(
                elfie_id="00000002",
                content_type="image/png",
                content=b"\x89PNG\r\n\x1a\nother",
            ),
        )
    with pytest.raises(ElfiePortraitInvalid):
        service.update_portrait(
            _principal(),
            UpdateElfiePortraitCommand(
                elfie_id="00000001",
                content_type="image/jpeg",
                content=b"not a png",
            ),
        )
    assert port.saved_portraits == {}


def test_retired_species_can_still_be_presented_when_catalog_contains_it() -> None:
    from dataclasses import replace

    from elfie.profile import current_species_catalog

    catalog = current_species_catalog()
    fox = catalog.definition("fox")
    retired = replace(fox, canon_id="old-fox", status="retired")
    retired_catalog = replace(
        catalog,
        definitions=tuple(
            retired if definition.species_id == "fox" else definition
            for definition in catalog.definitions
        ),
    )
    service = _service(catalog=retired_catalog)

    result = service.list_visible(_principal(), ListVisibleElfiesQuery())[0]

    assert result.profile.species is not None
    assert result.profile.species.status == "retired"


def test_profile_preserves_the_five_existing_cognition_modules() -> None:
    service = _service()

    result = service.get_profile(
        _principal(),
        GetElfieProfileQuery(elfie_id="00000001"),
    )

    cognition = result.private_cognition
    assert cognition is not None
    assert cognition.recent_focus.topics[0].label == "Alice"
    assert cognition.important_experiences.entries[0].id == "event-adoption"
    assert cognition.relationship_world.nodes[1].kind == "human"
    assert cognition.world_understanding.rings[1].key == "family"
    assert cognition.knowledge_beliefs.edges[0].relation_key == "supports"


def test_admin_directory_requires_manager_and_does_not_grant_cognition() -> None:
    service = _service()

    with pytest.raises(ElfiesForbidden):
        service.list_admin(_principal(), ListAdminElfiesQuery())

    results = service.list_admin(
        _principal(role="admin"),
        ListAdminElfiesQuery(owner_user_id=2),
    )
    assert [item.profile.elfie_id for item in results] == ["00000002"]
    assert results[0].owner.account_id == "bob"
    assert results[0].permissions.can_view_cognition is False
