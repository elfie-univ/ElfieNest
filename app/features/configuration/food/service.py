"""Authorized Food package, preview and Elfie-selection use-cases."""

from __future__ import annotations

import secrets
from dataclasses import replace

from app.features.accounts import AccountPrincipal, is_manager

from .errors import (
    FoodConflict,
    FoodForbidden,
    FoodNotFound,
    FoodUnavailable,
    FoodValidationError,
)
from .models import (
    ChangeFoodLifecycleCommand,
    CreateFoodPackageCommand,
    DeleteFoodPackageCommand,
    ElfieFoodOptionResult,
    EligibleFoodModelResult,
    FoodCatalogResult,
    FoodGenerationChangeResult,
    FoodGenerationPreviewResult,
    FoodPackageMutationResult,
    FoodPackageResult,
    FoodRoleAssignmentResult,
    FoodRolesInput,
    FoodRolesResult,
    GetMainFoodPolicyQuery,
    ListFoodPackagesQuery,
    MainFoodPolicyResult,
    PreviewFoodGenerationCommand,
    ResolvedElfieFoodResult,
    ResolveElfieFoodQuery,
    UpdateFoodPackageCommand,
    UpdateMainFoodPolicyCommand,
)
from .port_models import (
    FoodSystemRole,
    FoodVisibilityMode,
    StoredElfieFoodAssignment,
    StoredFoodDefaults,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredModelEvidence,
)
from .ports import (
    ElfieFoodAssignmentPort,
    FoodCatalogPort,
    FoodPortConflict,
    FoodPortError,
    FoodPortInvalid,
    FoodPortNotFound,
    FoodTechnologyPort,
)


class FoodService:
    """The single public Facade for Food configuration and selection."""

    def __init__(
        self,
        *,
        catalog: FoodCatalogPort,
        technology: FoodTechnologyPort,
        assignments: ElfieFoodAssignmentPort,
    ) -> None:
        self._catalog = catalog
        self._technology = technology
        self._assignments = assignments

    def list_packages(
        self,
        principal: AccountPrincipal,
        query: ListFoodPackagesQuery,
    ) -> FoodCatalogResult:
        _ = query
        self._require_manager(principal)
        packages, evidence = self._load_catalog()
        return self._catalog_result(packages, evidence)

    def create_package(
        self,
        principal: AccountPrincipal,
        command: CreateFoodPackageCommand,
    ) -> FoodPackageMutationResult:
        self._require_manager(principal)
        evidence = self._load_evidence()
        package = self._package_from_input(
            food_id=self._new_food_id(),
            display_name=command.display_name,
            enabled=command.enabled,
            roles=command.roles,
            visibility_mode=command.visibility_mode,
            visible_user_ids=command.visible_user_ids,
            required_roles=command.required_roles,
        )
        self._validate_references(package, evidence)
        try:
            saved = self._catalog.create_package(package)
            packages = self._catalog.list_packages()
        except FoodPortInvalid as error:
            raise FoodValidationError(str(error)) from error
        except FoodPortConflict as error:
            raise FoodConflict(str(error)) from error
        except FoodPortError as error:
            raise FoodUnavailable("Food package could not be created") from error
        return FoodPackageMutationResult(
            food=self._package_result(saved, evidence),
            catalog=self._catalog_result(packages, evidence),
        )

    def update_package(
        self,
        principal: AccountPrincipal,
        command: UpdateFoodPackageCommand,
    ) -> FoodPackageMutationResult:
        self._require_manager(principal)
        existing = self._require_package(command.food_id)
        evidence = self._load_evidence()
        package = self._package_from_input(
            food_id=existing.food_id,
            display_name=command.display_name,
            enabled=command.enabled,
            roles=command.roles,
            visibility_mode=command.visibility_mode,
            visible_user_ids=command.visible_user_ids,
            system_role=existing.system_role,
            archived=existing.archived,
            required_roles=(
                existing.required_roles
                if command.required_roles is None
                else command.required_roles
            ),
        )
        self._validate_references(package, evidence)
        try:
            saved = self._catalog.update_package(package)
        except FoodPortNotFound as error:
            raise FoodNotFound("Food package not found") from error
        except FoodPortInvalid as error:
            raise FoodValidationError(str(error)) from error
        except FoodPortConflict as error:
            raise FoodConflict(str(error)) from error
        except FoodPortError as error:
            raise FoodUnavailable("Food package could not be updated") from error
        return FoodPackageMutationResult(food=self._package_result(saved, evidence))

    def preview_generation(
        self,
        principal: AccountPrincipal,
        command: PreviewFoodGenerationCommand,
    ) -> FoodGenerationPreviewResult:
        self._require_manager(principal)
        if not command.connection_ids or any(
            not connection_id.strip() for connection_id in command.connection_ids
        ):
            raise FoodValidationError("At least one generation source is required")
        evidence = self._load_evidence()
        if command.food_id is None:
            package = StoredFoodPackage(
                food_id="food_preview",
                display_name=self._normalize_display_name(command.display_name or ""),
                enabled=False,
                visibility_mode=command.visibility_mode,
                visible_user_ids=self._normalize_visibility(
                    command.visibility_mode,
                    command.visible_user_ids,
                    system=False,
                ),
            )
        else:
            existing = self._require_package(command.food_id)
            package = replace(
                existing,
                visibility_mode=command.visibility_mode,
                visible_user_ids=self._normalize_visibility(
                    command.visibility_mode,
                    command.visible_user_ids,
                    system=existing.system_role is not None,
                ),
            )
        try:
            proposal = self._technology.propose_package(
                package,
                evidence,
                connection_ids=command.connection_ids,
                local_first=command.local_first,
                allow_remote=command.allow_remote,
            )
        except FoodPortError as error:
            raise FoodUnavailable("Food generation preview unavailable") from error
        changes = tuple(
            FoodGenerationChangeResult(item.role, item.old_model, item.new_model)
            for item in proposal.changes
        )
        return FoodGenerationPreviewResult(
            food_id=command.food_id,
            candidate=self._package_result(proposal.package, evidence),
            changes=changes,
            warnings=proposal.warnings,
            has_changes=any(item.old_model != item.new_model for item in changes),
        )

    def change_lifecycle(
        self,
        principal: AccountPrincipal,
        command: ChangeFoodLifecycleCommand,
    ) -> FoodPackageResult:
        self._require_manager(principal)
        package = self._require_package(command.food_id)
        if command.action == "enable":
            if package.archived:
                raise FoodConflict("An archived Food package must be restored first")
            if package.primary_model is None:
                raise FoodValidationError("A primary model is required")
            updated = replace(package, enabled=True)
        elif command.action == "disable":
            updated = replace(package, enabled=False)
        elif command.action == "archive":
            if package.food_id in self._defaults().system_food_ids:
                raise FoodConflict("System Food packages cannot be archived")
            updated = replace(package, enabled=False, archived=True)
        else:
            if package.food_id in self._defaults().system_food_ids:
                raise FoodConflict("System Food packages cannot be restored")
            updated = replace(package, enabled=False, archived=False)
        evidence = self._load_evidence()
        if updated.enabled:
            self._validate_references(updated, evidence)
        try:
            saved = self._catalog.update_package(updated)
        except FoodPortNotFound as error:
            raise FoodNotFound("Food package not found") from error
        except FoodPortInvalid as error:
            raise FoodValidationError(str(error)) from error
        except FoodPortConflict as error:
            raise FoodConflict(str(error)) from error
        except FoodPortError as error:
            raise FoodUnavailable("Food lifecycle could not be changed") from error
        return self._package_result(saved, evidence)

    def delete_package(
        self,
        principal: AccountPrincipal,
        command: DeleteFoodPackageCommand,
    ) -> FoodCatalogResult:
        self._require_manager(principal)
        if command.food_id in self._defaults().system_food_ids:
            raise FoodConflict("System Food packages cannot be deleted")
        try:
            self._catalog.delete_package(command.food_id)
            packages = self._catalog.list_packages()
        except FoodPortNotFound as error:
            raise FoodNotFound("Food package not found") from error
        except FoodPortConflict as error:
            raise FoodConflict(str(error)) from error
        except FoodPortInvalid as error:
            raise FoodValidationError(str(error)) from error
        except FoodPortError as error:
            raise FoodUnavailable("Food package could not be deleted") from error
        return self._catalog_result(packages, self._load_evidence())

    def get_elfie_policy(
        self,
        principal: AccountPrincipal,
        query: GetMainFoodPolicyQuery,
    ) -> MainFoodPolicyResult:
        return self._policy_result(
            self._accessible_assignment(principal, query.elfie_id)
        )

    def update_elfie_policy(
        self,
        principal: AccountPrincipal,
        command: UpdateMainFoodPolicyCommand,
    ) -> MainFoodPolicyResult:
        assignment = self._accessible_assignment(principal, command.elfie_id)
        selected = command.main_food_id.strip()
        policy = self._policy_result(assignment)
        if selected not in {item.food_id for item in policy.main_food_options}:
            raise FoodValidationError("The selected main Food is unavailable")
        try:
            self._assignments.set_main_food(assignment.elfie_id, selected)
        except FoodPortNotFound as error:
            raise FoodNotFound("Elfie not found") from error
        except FoodPortError as error:
            raise FoodUnavailable("Elfie Food policy could not be updated") from error
        return self._policy_result(replace(assignment, main_food_id=selected))

    def resolve_elfie_food(
        self,
        query: ResolveElfieFoodQuery,
    ) -> ResolvedElfieFoodResult:
        try:
            assignment = self._assignments.get_assignment(query.elfie_id)
        except FoodPortError as error:
            raise FoodUnavailable("Elfie Food policy unavailable") from error
        if assignment is None:
            return ResolvedElfieFoodResult(food_id=None, unavailable=True)
        policy = self._policy_result(assignment)
        return ResolvedElfieFoodResult(
            food_id=assignment.main_food_id,
            unavailable=policy.main_food_unavailable,
        )

    def _accessible_assignment(
        self,
        principal: AccountPrincipal,
        elfie_id: str,
    ) -> StoredElfieFoodAssignment:
        try:
            assignment = self._assignments.get_assignment(elfie_id)
        except FoodPortError as error:
            raise FoodUnavailable("Elfie Food policy unavailable") from error
        if assignment is None or (
            not is_manager(principal.role)
            and assignment.owner_user_id != principal.user_id
        ):
            raise FoodNotFound("Elfie not found or inaccessible")
        return assignment

    def _policy_result(
        self,
        assignment: StoredElfieFoodAssignment,
    ) -> MainFoodPolicyResult:
        packages, evidence = self._load_catalog()
        defaults = self._defaults()
        options = tuple(
            ElfieFoodOptionResult(item.food_id, item.display_name)
            for item in packages
            if item.food_id != defaults.emergency_food_id
            and not item.archived
            and (
                item.visibility_mode == "global"
                or assignment.owner_user_id in item.visible_user_ids
            )
            and item.enabled
            and self._project_health(item, evidence).status in {"healthy", "degraded"}
        )
        option_ids = {item.food_id for item in options}
        configured = assignment.main_food_id or ""
        effective = (
            configured
            if configured in option_ids
            else defaults.default_food_id
            if not configured and defaults.default_food_id in option_ids
            else ""
        )
        return MainFoodPolicyResult(
            main_food_id=configured,
            effective_main_food_id=effective,
            main_food_options=options,
            main_food_unavailable=bool(configured and configured not in option_ids),
        )

    def _load_catalog(
        self,
    ) -> tuple[tuple[StoredFoodPackage, ...], tuple[StoredModelEvidence, ...]]:
        try:
            return (
                self._catalog.list_packages(),
                self._technology.list_model_evidence(),
            )
        except FoodPortError as error:
            raise FoodUnavailable("Food catalog unavailable") from error

    def _load_evidence(self) -> tuple[StoredModelEvidence, ...]:
        try:
            return self._technology.list_model_evidence()
        except FoodPortError as error:
            raise FoodUnavailable("Food model evidence unavailable") from error

    def _defaults(self) -> StoredFoodDefaults:
        try:
            return self._technology.food_defaults()
        except FoodPortError as error:
            raise FoodUnavailable("Food defaults unavailable") from error

    def _require_package(self, food_id: str) -> StoredFoodPackage:
        try:
            package = self._catalog.get_package(food_id)
        except FoodPortError as error:
            raise FoodUnavailable("Food package unavailable") from error
        if package is None:
            raise FoodNotFound("Food package not found")
        return package

    def _new_food_id(self) -> str:
        for _ in range(32):
            food_id = f"food_{secrets.token_hex(4)}"
            try:
                if self._catalog.get_package(food_id) is None:
                    return food_id
            except FoodPortError as error:
                raise FoodUnavailable("Food package ID unavailable") from error
        raise FoodUnavailable("Food package ID unavailable")

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if not is_manager(principal.role):
            raise FoodForbidden("Food administration requires a manager")

    @classmethod
    def _package_from_input(
        cls,
        *,
        food_id: str,
        display_name: str,
        enabled: bool,
        roles: FoodRolesInput,
        visibility_mode: FoodVisibilityMode,
        visible_user_ids: tuple[int, ...],
        required_roles: tuple[str, ...] | frozenset[str] = (),
        system_role: FoodSystemRole | None = None,
        archived: bool = False,
    ) -> StoredFoodPackage:
        normalized_ids = cls._normalize_visibility(
            visibility_mode,
            visible_user_ids,
            system=system_role is not None,
        )
        package = StoredFoodPackage(
            food_id=food_id,
            display_name=cls._normalize_display_name(display_name),
            system_role=system_role,
            enabled=enabled,
            archived=archived,
            primary_model=cls._normalize_model(roles.primary),
            reasoning_model=cls._normalize_model(roles.reasoning),
            vision_model=cls._normalize_model(roles.vision),
            tool_model=cls._normalize_model(roles.tool),
            fallback_model=cls._normalize_model(roles.fallback),
            visibility_mode=visibility_mode,
            visible_user_ids=normalized_ids,
            required_roles=cls._normalize_required_roles(required_roles),
        )
        if package.archived and package.enabled:
            raise FoodValidationError("An archived Food package cannot be enabled")
        if package.system_role is not None and package.archived:
            raise FoodValidationError("A system Food package cannot be archived")
        if package.enabled and package.primary_model is None:
            raise FoodValidationError("A primary model is required")
        return package

    @staticmethod
    def _normalize_display_name(display_name: str) -> str:
        normalized = display_name.strip()
        if not normalized:
            raise FoodValidationError("Food display name is required")
        return normalized

    @staticmethod
    def _normalize_required_roles(
        required_roles: tuple[str, ...] | frozenset[str],
    ) -> frozenset[str]:
        allowed = {"reasoning", "vision", "tool"}
        normalized = frozenset(
            role.strip() for role in required_roles if role.strip()
        )
        if normalized - allowed:
            raise FoodValidationError("Required Food roles are invalid")
        return normalized

    @staticmethod
    def _normalize_model(reference: str | None) -> str | None:
        if reference is None:
            return None
        normalized = reference.strip()
        return normalized or None

    @staticmethod
    def _normalize_visibility(
        visibility_mode: FoodVisibilityMode,
        visible_user_ids: tuple[int, ...],
        *,
        system: bool,
    ) -> tuple[int, ...]:
        normalized = tuple(sorted(set(visible_user_ids)))
        if any(user_id <= 0 for user_id in normalized):
            raise FoodValidationError("Visible user IDs must be positive")
        if system and (visibility_mode != "global" or normalized):
            raise FoodValidationError(
                "System Food packages must remain globally visible"
            )
        if visibility_mode == "global" and normalized:
            raise FoodValidationError(
                "Globally visible Food cannot target specific users"
            )
        if visibility_mode == "users" and not normalized:
            raise FoodValidationError("User-visible Food requires at least one user")
        return normalized

    def _validate_references(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> None:
        by_reference = {item.reference: item for item in evidence}
        for reference in package.model_references:
            item = by_reference.get(reference)
            if item is None or not item.fresh:
                raise FoodValidationError(
                    f"Model {reference} has no recent successful validation"
                )
        try:
            self._technology.validate_package(package)
        except FoodPortInvalid as error:
            raise FoodValidationError(str(error)) from error
        except FoodPortError as error:
            raise FoodUnavailable("Food model validation unavailable") from error

    def _catalog_result(
        self,
        packages: tuple[StoredFoodPackage, ...],
        evidence: tuple[StoredModelEvidence, ...],
    ) -> FoodCatalogResult:
        defaults = self._defaults()
        return FoodCatalogResult(
            version=defaults.catalog_version,
            global_default_food_id=defaults.default_food_id,
            global_emergency_food_id=defaults.emergency_food_id,
            packages=tuple(self._package_result(item, evidence) for item in packages),
            eligible_models=tuple(
                EligibleFoodModelResult(
                    reference=item.reference,
                    display_name=item.display_name or item.reference,
                    local=item.local,
                    capabilities=tuple(sorted(item.capabilities)),
                )
                for item in evidence
                if item.fresh
            ),
        )

    def _package_result(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> FoodPackageResult:
        health = self._project_health(package, evidence)
        return FoodPackageResult(
            food_id=package.food_id,
            display_name=package.display_name,
            system_role=package.system_role,
            enabled=package.enabled,
            archived=package.archived,
            visibility_mode=package.visibility_mode,
            visible_user_ids=package.visible_user_ids,
            roles=FoodRolesResult(
                primary=self._assignment_result(package.primary_model),
                reasoning=self._assignment_result(package.reasoning_model),
                vision=self._assignment_result(package.vision_model),
                tool=self._assignment_result(package.tool_model),
                fallback=self._assignment_result(package.fallback_model),
            ),
            health=health.status,
            locality=health.locality,
            latest_evidence_at=health.latest_evidence_at,
            required_roles=tuple(sorted(package.required_roles)),
        )

    @staticmethod
    def _assignment_result(reference: str | None) -> FoodRoleAssignmentResult | None:
        return None if reference is None else FoodRoleAssignmentResult(reference)

    def _project_health(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> StoredFoodHealth:
        try:
            return self._technology.project_health(package, evidence)
        except FoodPortError as error:
            raise FoodUnavailable("Food health projection unavailable") from error


__all__ = ("FoodService",)
