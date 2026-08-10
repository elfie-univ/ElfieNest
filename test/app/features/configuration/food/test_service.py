from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import cast

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.configuration.food import (
    ChangeFoodLifecycleCommand,
    CreateFoodPackageCommand,
    DeleteFoodPackageCommand,
    FoodConflict,
    FoodNotFound,
    FoodRolesInput,
    FoodService,
    FoodValidationError,
    GetMainFoodPolicyQuery,
    ListFoodPackagesQuery,
    PreviewFoodGenerationCommand,
    StoredElfieFoodAssignment,
    StoredFoodChange,
    StoredFoodDefaults,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
    UpdateMainFoodPolicyCommand,
)


class MemoryCatalog:
    def __init__(self, packages: tuple[StoredFoodPackage, ...]) -> None:
        self.packages = {item.food_id: item for item in packages}

    def list_packages(self) -> tuple[StoredFoodPackage, ...]:
        ordered = ("food_emergency", "food_common")
        return tuple(
            self.packages[key]
            for key in (*ordered, *sorted(set(self.packages) - set(ordered)))
            if key in self.packages
        )

    def get_package(self, food_id: str) -> StoredFoodPackage | None:
        return self.packages.get(food_id)

    def create_package(self, package: StoredFoodPackage) -> StoredFoodPackage:
        self.packages[package.food_id] = package
        return package

    def update_package(self, package: StoredFoodPackage) -> StoredFoodPackage:
        self.packages[package.food_id] = package
        return package

    def delete_package(self, food_id: str) -> None:
        self.packages.pop(food_id)


class MemoryAssignments:
    def __init__(self) -> None:
        self.assignments = {
            "elfie-1": StoredElfieFoodAssignment("elfie-1", 7, None),
        }

    def get_assignment(self, elfie_id: str) -> StoredElfieFoodAssignment | None:
        return self.assignments.get(elfie_id)

    def set_main_food(self, elfie_id: str, food_id: str) -> None:
        assignment = self.assignments[elfie_id]
        self.assignments[elfie_id] = replace(assignment, main_food_id=food_id)


class Technology:
    def __init__(self) -> None:
        observed_at = datetime.now(timezone.utc).isoformat()
        self.evidence = (
            StoredModelEvidence(
                reference="cloud/main",
                display_name="Main",
                capabilities=frozenset({"text"}),
                verified=True,
                observed_at=observed_at,
                fresh=True,
            ),
        )
        self.proposal_calls = 0

    def food_defaults(self) -> StoredFoodDefaults:
        return StoredFoodDefaults(
            catalog_version=1,
            default_food_id="food_common",
            emergency_food_id="food_emergency",
            system_food_ids=frozenset({"food_common", "food_emergency"}),
        )

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]:
        return self.evidence

    def validate_package(self, package: StoredFoodPackage) -> None:
        _ = package

    def project_health(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> StoredFoodHealth:
        _ = evidence
        status = (
            "archived"
            if package.archived
            else "healthy"
            if package.enabled
            else "disabled"
        )
        return StoredFoodHealth(status, "remote", self.evidence[0].observed_at)

    def propose_package(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
        *,
        connection_ids: tuple[str, ...],
        local_first: bool,
        allow_remote: bool,
    ) -> StoredFoodProposal:
        _ = evidence, connection_ids, local_first, allow_remote
        self.proposal_calls += 1
        proposed = replace(package, enabled=True, primary_model="cloud/main")
        return StoredFoodProposal(
            package=proposed,
            changes=(StoredFoodChange("primary", package.primary_model, "cloud/main"),),
            warnings=(),
        )


def _principal(user_id: int = 1, role: str = "owner") -> AccountPrincipal:
    return AccountPrincipal(
        user_id=user_id,
        account_id=f"user-{user_id}",
        role=cast(AccountRole, role),
        default_landing_page="/manage" if role == "owner" else "/chat",
    )


def _service() -> tuple[FoodService, MemoryCatalog, MemoryAssignments, Technology]:
    packages = (
        StoredFoodPackage(
            food_id="food_emergency",
            display_name="Emergency",
            system_role="emergency",
            enabled=False,
        ),
        StoredFoodPackage(
            food_id="food_common",
            display_name="Common",
            system_role="common",
            enabled=True,
            primary_model="cloud/main",
        ),
        StoredFoodPackage(
            food_id="food_private",
            display_name="Private",
            enabled=True,
            primary_model="cloud/main",
            visibility_mode="users",
            visible_user_ids=(7,),
        ),
    )
    catalog = MemoryCatalog(packages)
    assignments = MemoryAssignments()
    technology = Technology()
    return (
        FoodService(catalog=catalog, technology=technology, assignments=assignments),
        catalog,
        assignments,
        technology,
    )


def test_manager_crud_lifecycle_and_preview_preserve_current_food_operations() -> None:
    service, catalog, _, technology = _service()
    owner = _principal()

    before = tuple(catalog.packages)
    preview = service.preview_generation(
        owner,
        PreviewFoodGenerationCommand(
            display_name="Preview",
            connection_ids=("cloud",),
            local_first=False,
            allow_remote=True,
            visibility_mode="global",
            visible_user_ids=(),
        ),
    )
    assert preview.food_id is None
    assert preview.candidate.roles.primary is not None
    assert tuple(catalog.packages) == before
    assert technology.proposal_calls == 1

    created = service.create_package(
        owner,
        CreateFoodPackageCommand(
            display_name="Custom",
            enabled=True,
            roles=FoodRolesInput(primary="cloud/main"),
            visibility_mode="global",
            visible_user_ids=(),
        ),
    )
    food_id = created.food.food_id
    assert created.catalog is not None
    assert food_id.startswith("food_")

    disabled = service.change_lifecycle(
        owner,
        ChangeFoodLifecycleCommand(food_id, "disable"),
    )
    assert disabled.enabled is False
    archived = service.change_lifecycle(
        owner,
        ChangeFoodLifecycleCommand(food_id, "archive"),
    )
    assert archived.archived is True
    deleted = service.delete_package(owner, DeleteFoodPackageCommand(food_id))
    assert all(item.food_id != food_id for item in deleted.packages)

    with pytest.raises(FoodConflict):
        service.change_lifecycle(
            owner,
            ChangeFoodLifecycleCommand("food_common", "archive"),
        )
    assert service.list_packages(owner, ListFoodPackagesQuery()).packages


def test_member_policy_is_authorized_and_uses_visible_healthy_packages() -> None:
    service, _, assignments, _ = _service()
    member = _principal(7, "user")

    policy = service.get_elfie_policy(member, GetMainFoodPolicyQuery("elfie-1"))
    assert [item.food_id for item in policy.main_food_options] == [
        "food_common",
        "food_private",
    ]
    assert policy.effective_main_food_id == "food_common"

    updated = service.update_elfie_policy(
        member,
        UpdateMainFoodPolicyCommand("elfie-1", "food_private"),
    )
    assert updated.main_food_id == "food_private"
    assert assignments.assignments["elfie-1"].main_food_id == "food_private"

    with pytest.raises(FoodNotFound):
        service.get_elfie_policy(
            _principal(8, "user"), GetMainFoodPolicyQuery("elfie-1")
        )
    with pytest.raises(FoodValidationError):
        service.update_elfie_policy(
            member,
            UpdateMainFoodPolicyCommand("elfie-1", "food_emergency"),
        )


def test_writes_reject_models_without_fresh_evidence() -> None:
    service, _, _, _ = _service()
    with pytest.raises(FoodValidationError, match="no recent successful validation"):
        service.create_package(
            _principal(),
            CreateFoodPackageCommand(
                display_name="Bad",
                enabled=True,
                roles=FoodRolesInput(primary="cloud/stale"),
                visibility_mode="global",
                visible_user_ids=(),
            ),
        )
