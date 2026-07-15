from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PINNED_PYTHON_VERSION = "3.9.25"


def test_python_version_file_pins_exact_runtime() -> None:
    # Given
    version_file = PROJECT_ROOT / ".python-version"

    # When
    pinned_version = version_file.read_text(encoding="utf-8").strip()

    # Then
    assert pinned_version == PINNED_PYTHON_VERSION


def test_project_metadata_requires_exact_pinned_runtime() -> None:
    # Given
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # When
    required_version = f'requires-python = "=={PINNED_PYTHON_VERSION}"'

    # Then
    assert required_version in pyproject


def test_uv_lock_is_committed_as_dependency_contract() -> None:
    # Given
    lock_file = PROJECT_ROOT / "uv.lock"

    # When
    lock_exists = lock_file.is_file()

    # Then
    assert lock_exists


def test_build_backend_is_constrained_to_an_exact_version() -> None:
    # Given
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # When
    exact_build_backend = 'requires = ["setuptools==80.9.0"]'
    exact_build_constraint = 'build-constraint-dependencies = ["setuptools==80.9.0"]'

    # Then
    assert exact_build_backend in pyproject
    assert exact_build_constraint in pyproject
