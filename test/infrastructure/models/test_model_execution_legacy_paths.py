from pathlib import Path


def test_legacy_generation_fallback_modules_are_removed():
    project_root = Path(__file__).resolve().parents[3]
    assert not (project_root / "ai_runtime").exists()


def test_model_execution_layer_does_not_restore_runtime_named_modules():
    project_root = Path(__file__).resolve().parents[3]
    retired_paths = (
        "app/bootstrap/runtime.py",
        "app/bootstrap/runtime_food.py",
        "app/bootstrap/system_wiring/runtime.py",
        "devtools/elfie_lab/runtime_adapters.py",
        "devtools/elfie_lab/runtime_foods.py",
        "elfie/brain/memory/runtime_food.py",
        "infrastructure/models/fallback_runtime.py",
        "infrastructure/models/runtime_adapter.py",
        "infrastructure/models/runtime_agent.py",
        "infrastructure/models/runtime_config.py",
        "infrastructure/models/runtime_contracts.py",
        "infrastructure/models/runtime_observations.py",
        "infrastructure/models/runtime_observer.py",
        "infrastructure/models/runtime_overview.py",
        "infrastructure/models/runtime_ports.py",
        "infrastructure/models/validation/provider_validation_runtime.py",
        "infrastructure/persistence/runtime_config.py",
        "infrastructure/persistence/runtime_overview.py",
    )

    restored = [path for path in retired_paths if (project_root / path).exists()]
    assert restored == []
