"""Machine gates for database ownership, inventory, and final-state safety."""

from pathlib import Path

from scripts.governance.persistence.inventory import (
    DatabaseInventory,
    DatabaseReference,
    collect_inventory,
    database_change_paths,
    sql_boundary_violations,
    transient_final_state_violations,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_database_inventory_covers_the_elfie_dependency_hub() -> None:
    inventory = collect_inventory(PROJECT_ROOT)
    elfie_paths = {
        reference.path
        for reference in inventory.references
        if reference.table == "elfies"
    }

    assert "infrastructure/persistence/nest_db/final_schema.py" in elfie_paths
    assert "infrastructure/persistence/adoption.py" in elfie_paths
    assert "infrastructure/persistence/accounts.py" in elfie_paths
    assert "infrastructure/persistence/operations.py" in elfie_paths
    assert "infrastructure/persistence/nest_db/nest_state.py" in elfie_paths


def test_application_layers_do_not_bypass_the_persistence_boundary() -> None:
    inventory = collect_inventory(PROJECT_ROOT)
    assert sql_boundary_violations(inventory) == ()


def test_final_elfie_table_contains_only_durable_final_state() -> None:
    assert transient_final_state_violations(PROJECT_ROOT) == ()


def test_database_change_path_filter_excludes_local_agent_rules() -> None:
    assert database_change_paths(
        (
            "infrastructure/persistence/AGENTS.md",
            "infrastructure/persistence/adoption.py",
            "infrastructure/persistence/nest_db/final_schema.py",
            "elfie/brain/memory/schema.py",
            "app/features/adoption/facade.py",
        )
    ) == (
        "elfie/brain/memory/schema.py",
        "infrastructure/persistence/adoption.py",
        "infrastructure/persistence/nest_db/final_schema.py",
    )


def test_sql_boundary_scanner_has_positive_and_violation_fixtures() -> None:
    allowed = DatabaseInventory(
        references=(
            DatabaseReference(
                path="infrastructure/persistence/example.py",
                line=1,
                operation="SELECT",
                table="elfies",
                snippet="SELECT * FROM elfies",
            ),
        ),
        parse_errors=(),
    )
    forbidden = DatabaseInventory(
        references=(
            DatabaseReference(
                path="app/features/example.py",
                line=1,
                operation="SELECT",
                table="elfies",
                snippet="SELECT * FROM elfies",
            ),
        ),
        parse_errors=(),
    )

    assert sql_boundary_violations(allowed) == ()
    assert sql_boundary_violations(forbidden) == (
        "SQL outside persistence boundary: app/features/example.py:1 SELECT elfies",
    )


def test_transient_state_guard_has_positive_and_violation_fixtures(
    tmp_path: Path,
) -> None:
    schema_path = tmp_path / "infrastructure/persistence/nest_db/final_schema.py"
    schema_path.parent.mkdir(parents=True)

    schema_path.write_text(
        """
_TABLE_STATEMENTS = (\"\"\"CREATE TABLE IF NOT EXISTS elfies (
    elfie_id TEXT PRIMARY KEY,
    adopted_at TEXT NOT NULL
)\"\"\", \"\"\"CREATE TABLE IF NOT EXISTS food_packages (\"\"\" )
""",
        encoding="utf-8",
    )
    assert transient_final_state_violations(tmp_path) == ()

    schema_path.write_text(
        """
_TABLE_STATEMENTS = (\"\"\"CREATE TABLE IF NOT EXISTS elfies (
    elfie_id TEXT PRIMARY KEY,
    admission_state TEXT NOT NULL CHECK(admission_state='provisioning')
)\"\"\", \"\"\"CREATE TABLE IF NOT EXISTS food_packages (\"\"\" )
""",
        encoding="utf-8",
    )
    assert transient_final_state_violations(tmp_path) == (
        "final elfies table contains transient state marker: admission_state",
        "final elfies table contains transient state marker: provisioning",
    )
