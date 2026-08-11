"""Machine-readable links between architecture contracts and their enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ContractRegistration:
    """One logical bilingual contract and the artifacts that enforce it."""

    contract_id: str
    version: str
    english_path: str
    chinese_path: str
    decision_paths: Tuple[str, ...]
    agent_paths: Tuple[str, ...]
    scanner_paths: Tuple[str, ...]
    test_paths: Tuple[str, ...]
    conformance_paths: Tuple[str, ...] = ()
    baseline_path: Optional[str] = None


CONTRACT_REGISTRY: Tuple[ContractRegistration, ...] = (
    ContractRegistration(
        contract_id="repository-governance",
        version="1.4",
        english_path="docs/developer/contracts/repository-governance.md",
        chinese_path="docs/zh/developer/contracts/repository-governance.md",
        decision_paths=(
            "docs/developer/decisions/0003-architecture-governance-ratchet.md",
            "docs/zh/developer/decisions/0003-architecture-governance-ratchet.md",
        ),
        agent_paths=(
            "AGENTS.md",
            "docs/AGENTS.md",
            "scripts/architecture/AGENTS.md",
            "test/architecture/AGENTS.md",
        ),
        scanner_paths=("scripts/architecture/check_governance_change.py",),
        test_paths=(
            "test/architecture/test_architecture_governance.py",
            "test/architecture/test_app_layer_boundaries.py",
            "test/architecture/test_system_layer_boundaries.py",
        ),
    ),
    ContractRegistration(
        contract_id="system-architecture",
        version="1.3",
        english_path="docs/developer/contracts/system.md",
        chinese_path="docs/zh/developer/contracts/system.md",
        decision_paths=(
            "docs/developer/decisions/0002-system-ports-adapters.md",
            "docs/zh/developer/decisions/0002-system-ports-adapters.md",
        ),
        agent_paths=(
            "elfie/AGENTS.md",
            "nest/AGENTS.md",
            "infrastructure/AGENTS.md",
            "infrastructure/persistence/AGENTS.md",
            "infrastructure/godot/AGENTS.md",
            "godot_project/AGENTS.md",
        ),
        scanner_paths=("scripts/architecture/system_layer_scan.py",),
        test_paths=(
            "test/architecture/test_system_layer_boundaries.py",
            "test/architecture/test_project_structure.py",
            "test/architecture/test_elfie_cognitive_contracts.py",
            "test/architecture/test_gateway_runtime_boundaries.py",
            "test/architecture/test_runtime_import_boundaries.py",
            "test/architecture/test_runtime_observer_contracts.py",
            "test/architecture/test_storage_boundaries.py",
        ),
        conformance_paths=(
            "docs/developer/conformance/system.md",
            "docs/zh/developer/conformance/system.md",
        ),
        baseline_path="test/architecture/baselines/system_layer.py",
    ),
    ContractRegistration(
        contract_id="elfie-internal-architecture",
        version="1.0",
        english_path="docs/developer/contracts/elfie.md",
        chinese_path="docs/zh/developer/contracts/elfie.md",
        decision_paths=(
            "docs/developer/decisions/0005-elfie-internal-ports-adapters.md",
            "docs/zh/developer/decisions/0005-elfie-internal-ports-adapters.md",
        ),
        agent_paths=(
            "elfie/AGENTS.md",
            "elfie/brain/AGENTS.md",
            "elfie/brain/memory/AGENTS.md",
            "elfie/body/AGENTS.md",
            "elfie/communication/AGENTS.md",
            "elfie/nervous_system/AGENTS.md",
            "elfie/profile/AGENTS.md",
        ),
        scanner_paths=("scripts/architecture/system_layer_scan.py",),
        test_paths=("test/architecture/test_elfie_cognitive_contracts.py",),
        conformance_paths=(
            "docs/developer/conformance/elfie.md",
            "docs/zh/developer/conformance/elfie.md",
        ),
    ),
    ContractRegistration(
        contract_id="application-architecture",
        version="1.5",
        english_path="docs/developer/contracts/application.md",
        chinese_path="docs/zh/developer/contracts/application.md",
        decision_paths=(
            "docs/developer/decisions/0001-lightweight-ports-adapters.md",
            "docs/zh/developer/decisions/0001-lightweight-ports-adapters.md",
            "docs/developer/decisions/0004-app-domain-slices.md",
            "docs/zh/developer/decisions/0004-app-domain-slices.md",
        ),
        agent_paths=(
            "app/AGENTS.md",
            "app/bootstrap/AGENTS.md",
            "app/features/AGENTS.md",
            "app/features/accounts/AGENTS.md",
            "app/features/configuration/AGENTS.md",
            "app/features/setup/AGENTS.md",
            "infrastructure/AGENTS.md",
            "infrastructure/devices/AGENTS.md",
            "infrastructure/persistence/AGENTS.md",
            "app/interfaces/AGENTS.md",
            "app/interfaces/api/AGENTS.md",
            "app/interfaces/cli/AGENTS.md",
            "app/interfaces/desktop/AGENTS.md",
            "app/interfaces/web/frontend/AGENTS.md",
            "app/orchestration/AGENTS.md",
            "app/orchestration/embodiment/AGENTS.md",
            "app/orchestration/lifecycle/AGENTS.md",
        ),
        scanner_paths=("scripts/architecture/app_layer_scan.py",),
        test_paths=(
            "test/architecture/test_app_layer_boundaries.py",
            "test/architecture/test_bootstrap_wiring_boundaries.py",
            "test/architecture/test_runtime_import_boundaries.py",
            "test/architecture/test_storage_boundaries.py",
        ),
        conformance_paths=(
            "docs/developer/conformance/application.md",
            "docs/zh/developer/conformance/application.md",
        ),
        baseline_path="test/architecture/baselines/app_layer.py",
    ),
    ContractRegistration(
        contract_id="model-food-tool-behavior",
        version="1.5",
        english_path="docs/developer/contracts/ai-runtime.md",
        chinese_path="docs/zh/developer/contracts/ai-runtime.md",
        decision_paths=(
            "docs/developer/decisions/0002-system-ports-adapters.md",
            "docs/zh/developer/decisions/0002-system-ports-adapters.md",
            "docs/developer/decisions/0005-elfie-internal-ports-adapters.md",
            "docs/zh/developer/decisions/0005-elfie-internal-ports-adapters.md",
        ),
        agent_paths=(
            "app/features/configuration/AGENTS.md",
            "elfie/AGENTS.md",
            "infrastructure/AGENTS.md",
        ),
        scanner_paths=(),
        test_paths=("test/architecture/test_ai_runtime_contract.py",),
        conformance_paths=(
            "docs/developer/conformance/ai-runtime.md",
            "docs/zh/developer/conformance/ai-runtime.md",
        ),
    ),
)


def registration_by_id(contract_id: str) -> ContractRegistration:
    """Return one registered logical contract."""

    for registration in CONTRACT_REGISTRY:
        if registration.contract_id == contract_id:
            return registration
    raise KeyError(contract_id)
