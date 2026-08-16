"""Runtime artifact handoff contract tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from infrastructure.godot.artifacts.artifact_manifest import (
    RuntimeArtifactContractError,
    RuntimeArtifactFile,
    RuntimeArtifactMode,
    RuntimeComponentKind,
    RuntimeTarget,
    build_runtime_artifact_manifest,
    load_runtime_artifact_manifest,
    validate_runtime_artifact_manifest,
    write_runtime_artifact_manifest,
)


def _write_component_file(directory: Path, name: str, payload: bytes) -> None:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_godot_manifest(directory: Path, entry: str, version: str) -> None:
    files = {
        path.name: {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in directory.iterdir()
        if path.is_file()
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(
            {
                "entry": entry,
                "files": files,
                "godot_version": version,
                "species_catalog_digest": hashlib.sha256(
                    b"species-catalog-fixture"
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def _runtime_component_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "components"
    web = root / "godot-web"
    dedicated = root / "godot-linux-dedicated"
    desktop = root / "desktop-interface"
    web.mkdir(parents=True)
    dedicated.mkdir(parents=True)
    desktop.mkdir(parents=True)
    for name in ("elfienest.html", "elfienest.js", "elfienest.wasm", "elfienest.pck"):
        _write_component_file(web, name, f"web:{name}".encode())
    _write_godot_manifest(web, "elfienest.html", "4.7")
    _write_component_file(dedicated, "ElfieNestRuntime", b"dedicated")
    (dedicated / "ElfieNestRuntime").chmod(0o755)
    _write_godot_manifest(dedicated, "ElfieNestRuntime", "4.7")
    _write_component_file(desktop, "main.js", b"observer")
    _write_component_file(desktop, "lifecycle_client.js", b"client")
    _write_component_file(desktop, "lifecycle_client.test.js", b"test-client")
    return root


def test_runtime_contract_requires_web_and_observer_for_every_target(
    tmp_path: Path,
) -> None:
    # Given: export fixtures for the three runtime component roots.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")

    # When: each supported packaging target asks for its required components.
    required = {
        target: manifest.required_components_for(target) for target in RuntimeTarget
    }

    # Then: Web and Observer are universal while Dedicated is Linux-only.
    universal = {
        RuntimeComponentKind.GODOT_WEB,
        RuntimeComponentKind.DESKTOP_OBSERVER,
    }
    for target in RuntimeTarget:
        assert universal.issubset(required[target])
    assert RuntimeComponentKind.LINUX_DEDICATED in required[RuntimeTarget.LINUX_X64]
    assert all(
        RuntimeComponentKind.LINUX_DEDICATED not in required[target]
        for target in RuntimeTarget
        if target is not RuntimeTarget.LINUX_X64
    )
    assert validate_runtime_artifact_manifest(manifest, component_root) == ()


def test_runtime_contract_rejects_missing_mode_entry_and_invalid_hash(
    tmp_path: Path,
) -> None:
    # Given: a valid contract and component fixture.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")
    web = manifest.component(RuntimeComponentKind.GODOT_WEB)
    wasm = next(file for file in web.files if file.path == "elfienest.wasm")

    # When: the mode entry and a content hash are each corrupted in the handoff.
    missing_entry = replace(web, entrypoint="missing.html")
    bad_hash = replace(wasm, sha256="0" * 64)
    corrupted_hash = replace(
        web,
        files=tuple(bad_hash if file.path == wasm.path else file for file in web.files),
    )
    missing_entry_manifest = manifest.with_component(missing_entry)
    bad_hash_manifest = manifest.with_component(corrupted_hash)

    # Then: packaging is stopped before it can copy an invalid runtime.
    assert (
        "godot-web: mode entry missing.html is not declared"
        in validate_runtime_artifact_manifest(missing_entry_manifest, component_root)
    )
    assert any(
        "godot-web: elfienest.wasm sha256 mismatch" == error
        for error in validate_runtime_artifact_manifest(
            bad_hash_manifest, component_root
        )
    )


def test_runtime_contract_rejects_tampered_wasm_and_pck_payloads(
    tmp_path: Path,
) -> None:
    # Given: a valid runtime contract generated from exported component files.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")

    # When: either browser runtime payload changes after contract generation.
    wasm = component_root / "godot-web" / "elfienest.wasm"
    wasm.write_bytes(b"tampered-wasm")
    wasm_errors = validate_runtime_artifact_manifest(manifest, component_root)
    pck = component_root / "godot-web" / "elfienest.pck"
    pck.write_bytes(b"tampered-pck")
    pck_errors = validate_runtime_artifact_manifest(manifest, component_root)

    # Then: each content-addressed payload blocks package assembly.
    assert "godot-web: elfienest.wasm sha256 mismatch" in wasm_errors
    assert "godot-web: elfienest.pck sha256 mismatch" in pck_errors


def test_desktop_observer_contract_excludes_and_rejects_compiled_test_payloads(
    tmp_path: Path,
) -> None:
    # Given: a Desktop output directory containing runtime and compiled test files.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")
    desktop = manifest.component(RuntimeComponentKind.DESKTOP_OBSERVER)

    # When: the generated handoff is inspected or a test output is declared manually.
    payload = (
        component_root / "desktop-interface/lifecycle_client.test.js"
    ).read_bytes()
    declared_test = RuntimeArtifactFile(
        path="lifecycle_client.test.js",
        bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        executable=False,
    )
    invalid_manifest = manifest.with_component(
        replace(desktop, files=(*desktop.files, declared_test))
    )

    # Then: package inputs never contain compiled test payloads.
    assert not any(file.path.endswith(".test.js") for file in desktop.files)
    assert (
        "desktop-observer: lifecycle_client.test.js must not be packaged"
        in validate_runtime_artifact_manifest(invalid_manifest, component_root)
    )


def test_runtime_contract_rejects_wrong_target_applicability_and_linux_gap(
    tmp_path: Path,
) -> None:
    # Given: a valid handoff contract.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")

    # When: Linux loses Dedicated and macOS incorrectly requires it.
    linux_gap = manifest.with_required_components(
        RuntimeTarget.LINUX_X64,
        {
            RuntimeComponentKind.GODOT_WEB,
            RuntimeComponentKind.DESKTOP_OBSERVER,
        },
    )
    macos_dedicated = manifest.with_required_components(
        RuntimeTarget.DARWIN_ARM64,
        {
            RuntimeComponentKind.GODOT_WEB,
            RuntimeComponentKind.DESKTOP_OBSERVER,
            RuntimeComponentKind.LINUX_DEDICATED,
        },
    )

    # Then: both applicability errors are explicit.
    assert (
        "linux-x64: missing required component linux-dedicated"
        in validate_runtime_artifact_manifest(linux_gap, component_root)
    )
    assert (
        "darwin-arm64: linux-dedicated must not be required"
        in validate_runtime_artifact_manifest(macos_dedicated, component_root)
    )


def test_runtime_contract_rejects_a_component_with_the_wrong_runtime_mode(
    tmp_path: Path,
) -> None:
    # Given: an Observer Web component from a valid runtime handoff.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")
    web = manifest.component(RuntimeComponentKind.GODOT_WEB)

    # When: that component claims to host the Dedicated authority mode.
    wrong_mode = manifest.with_component(
        replace(web, mode=RuntimeArtifactMode.DEDICATED_AUTHORITY)
    )

    # Then: package assembly rejects the mode/entry role mismatch.
    assert "godot-web: mode must be observer" in validate_runtime_artifact_manifest(
        wrong_mode, component_root
    )


def test_runtime_contract_serializes_a_packaging_handoff_fixture(
    tmp_path: Path,
) -> None:
    # Given: all runtime component fixture roots are available.
    component_root = _runtime_component_fixture(tmp_path)
    manifest = build_runtime_artifact_manifest(component_root, "0.1.0")
    output = tmp_path / "runtime-components.json"

    # When: the typed contract writes its packaging handoff JSON.
    write_runtime_artifact_manifest(manifest, output)

    # Then: it has one stable versioned payload and no hand-written schema.
    payload = json.loads(output.read_text(encoding="utf-8"))
    reloaded = load_runtime_artifact_manifest(output)
    assert payload["schema_version"] == 1
    assert set(payload["targets"]) == {target.value for target in RuntimeTarget}
    assert payload["components"]["godot-web"]["entrypoint"] == "elfienest.html"
    assert payload["components"]["linux-dedicated"]["files"][0]["executable"] is True
    assert reloaded == manifest


def test_runtime_contract_rejects_invalid_serialized_payload(tmp_path: Path) -> None:
    # Given: an invalid JSON handoff fixture.
    path = tmp_path / "runtime-components.json"
    path.write_text('{"schema_version": 99}', encoding="utf-8")

    # When / Then: the parser rejects it with a typed contract error.
    with pytest.raises(RuntimeArtifactContractError, match="schema_version"):
        load_runtime_artifact_manifest(path)


def test_runtime_contract_fixture_is_the_only_unignored_build_component() -> None:
    # Given: the repository build-output ignore rules.
    ignore_file = Path(__file__).resolve().parents[4] / ".gitignore"

    # When: the runtime contract exception is inspected.
    rules = ignore_file.read_text(encoding="utf-8")

    # Then: only the single handoff file becomes versionable.
    assert "/build/components/*\n" in rules
    assert "/build/components/runtime-contract/*\n" in rules
    assert rules.index("/build/components/*\n") > rules.index("!/build/components/\n")
    assert rules.index("/build/components/runtime-contract/*\n") > rules.index(
        "!/build/components/runtime-contract/\n"
    )
    assert "!/build/components/runtime-contract/runtime-components.json\n" in rules
