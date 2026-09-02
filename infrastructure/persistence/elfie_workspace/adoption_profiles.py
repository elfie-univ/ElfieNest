"""Persistence boundary for one-time Genesis workspace publication.

Genesis owns every semantic decision.  This adapter only validates the typed
handoff, writes an unpublished sibling workspace, and atomically publishes it
when Resident Admission tells it to do so.  A final workspace is never used as
an intermediate scratch directory and is never removed as compensation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Mapping, cast

from app.orchestration.resident_admission import (
    AdmissionPublication,
    ResidentAdmissionPortError,
)
from elfie.brain.selfhood.contracts import (
    SelfhoodState,
    normalize_selfhood_mapping,
)
from elfie.genesis import (
    GenesisCompilation,
    GenesisCompileEnvelope,
    GenesisCompileEnvelopeError,
    GenesisMemoryCommitter,
    output_ids_hash,
)
from elfie.profile import ElfieProfile
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import (
    FinalElfieLayout,
    ensure_staging_elfie_layout,
    final_root_layout,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter

_MARKER_FORMAT_VERSION = 1
_MARKER_KEYS = frozenset(
    {
        "format_version",
        "elfie_id",
        "manifest_id",
        "content_hash",
        "output_ids_hash",
        "output_ids",
        "compiler_version",
        "schema_version",
        "idempotency_key_digest",
    }
)


class FinalElfieWorkspaceAdapter:
    """Stage and publish one already-compiled Genesis result."""

    def __init__(
        self,
        data_home: Path | None = None,
        *,
        db_path: str | Path | None = None,
    ) -> None:
        if (data_home is None) == (db_path is None):
            raise ValueError("select exactly one workspace root source")
        self._data_home = data_home
        self._db_path = db_path

    @classmethod
    def from_database_path(cls, db_path: str | Path) -> FinalElfieWorkspaceAdapter:
        """Construct an adapter whose data root follows the Nest database."""

        return cls(db_path=db_path)

    def _selected_data_home(self) -> Path:
        if self._db_path is not None:
            return data_home_from_db_path(self._db_path)
        if self._data_home is None:  # pragma: no cover - constructor invariant
            raise RuntimeError("workspace root source is unavailable")
        return Path(self._data_home).expanduser()

    def stage(self, compilation: GenesisCompilation) -> str:
        """Write one validated compilation below the hidden staging root.

        Repeating an exact stage operation is safe when its marker and all
        three owners already validate.  A different or incomplete staging
        directory is rejected so a caller cannot silently replace a transaction
        belonging to another admission.
        """

        elfie_id = compilation.profile.identity.elfie_id
        data_home = self._selected_data_home()
        root = final_root_layout(data_home)
        final_layout = root.elfie(elfie_id)
        staging_layout = root.staging_elfie(elfie_id)
        _reject_existing_final(final_layout)

        if (
            staging_layout.workspace.exists()
            and staging_layout.genesis_stage_marker.exists()
        ):
            try:
                self._validate_workspace(
                    staging_layout,
                    expected=_compilation_metadata(compilation),
                )
                return str(staging_layout.workspace)
            except Exception as error:  # noqa: BLE001 - preserve exact staging
                if isinstance(error, ResidentAdmissionPortError):
                    raise
                raise ResidentAdmissionPortError(
                    "Genesis staging workspace already exists but is invalid"
                ) from error
        elif (
            staging_layout.workspace.exists()
            and not staging_layout.genesis_compile_envelope.exists()
        ):
            raise ResidentAdmissionPortError(
                "Genesis staging workspace exists without a recovery envelope"
            )

        try:
            compilation.bundle.validate()
            if compilation.energy_limits is None:
                raise ValueError("Genesis compilation lacks Brain energy limits")
            selfhood = compilation.plan.selfhood
            if not selfhood.complete:
                raise ValueError("Genesis compilation lacks complete Selfhood")
            portraits = _decode_portraits(
                compilation.full_body_image_url,
                compilation.headshot_image_url,
            )

            layout = ensure_staging_elfie_layout(data_home, elfie_id)
            YamlProfileStoreAdapter(layout.profile.parent).save(compilation.profile)
            YamlSelfhoodSeedAdapter(layout.brain).save(
                selfhood.model_dump(mode="python")
            )
            YamlEnergyLimitsAdapter(layout.brain).save(compilation.energy_limits)
            if portraits is not None:
                full_body, headshot = portraits
                _write_private_asset(layout.portrait_full_body, full_body)
                _write_private_asset(layout.portrait_headshot, headshot)

            with SQLiteMemoryStoreAdapter(
                layout.knowledge_database,
                elfie_id=elfie_id,
            ) as memory_store:
                GenesisMemoryCommitter().commit(compilation.bundle, memory_store)

            _write_marker(
                layout.genesis_stage_marker, _compilation_metadata(compilation)
            )
            return str(layout.workspace)
        except Exception as error:  # noqa: BLE001 - persistence boundary
            # This path is known to be a newly-created sibling.  Never target
            # the final workspace during compensation.
            _remove_staging_quietly(staging_layout)
            if isinstance(error, ResidentAdmissionPortError):
                raise
            raise ResidentAdmissionPortError(
                "unable to stage compiled Elfie workspace"
            ) from error

    def stage_envelope(self, envelope: GenesisCompileEnvelope) -> str:
        """Persist the private compile input before semantic compilation starts."""

        if not isinstance(envelope, GenesisCompileEnvelope):
            raise ResidentAdmissionPortError("Genesis compile envelope 类型无效")
        elfie_id = envelope.request.elfie_id
        data_home = self._selected_data_home()
        root = final_root_layout(data_home)
        final_layout = root.elfie(elfie_id)
        staging_layout = root.staging_elfie(elfie_id)
        _reject_existing_final(final_layout)
        payload = envelope.to_dict()
        try:
            if staging_layout.workspace.exists():
                if staging_layout.genesis_compile_envelope.exists():
                    current = _read_compile_envelope(
                        staging_layout.genesis_compile_envelope
                    )
                    if current.to_dict() != payload:
                        raise ResidentAdmissionPortError(
                            "Genesis recovery envelope 与当前预约不一致"
                        )
                    return str(staging_layout.genesis_compile_envelope)
                if staging_layout.genesis_stage_marker.exists():
                    raise ResidentAdmissionPortError(
                        "已暂存的 Genesis workspace 缺少 recovery envelope"
                    )
                raise ResidentAdmissionPortError(
                    "Genesis staging workspace already exists but is incomplete"
                )
            layout = ensure_staging_elfie_layout(data_home, elfie_id)
            _write_json_file(layout.genesis_compile_envelope, payload)
            return str(layout.genesis_compile_envelope)
        except ResidentAdmissionPortError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to stage Genesis compile envelope"
            ) from error

    def reopen(
        self,
        elfie_id: str,
        *,
        manifest_id: str | None = None,
        content_hash: str | None = None,
        output_ids_hash: str | None = None,
    ) -> str:
        """Reopen and integrity-check an existing staged or published output."""

        root = final_root_layout(self._selected_data_home())
        staging = root.staging_elfie(elfie_id)
        final = root.elfie(elfie_id)
        expected = {
            key: value
            for key, value in (
                ("manifest_id", manifest_id),
                ("content_hash", content_hash),
                ("output_ids_hash", output_ids_hash),
            )
            if value is not None
        }
        for layout in (staging, final):
            if not layout.workspace.exists():
                continue
            try:
                self._validate_workspace(layout, expected=expected)
            except ResidentAdmissionPortError:
                raise
            except Exception as error:  # noqa: BLE001
                raise ResidentAdmissionPortError(
                    "Genesis workspace integrity validation failed"
                ) from error
            return str(layout.workspace)
        raise ResidentAdmissionPortError(
            "Genesis workspace does not exist in staging or final storage"
        )

    def publish(self, elfie_id: str) -> str:
        """Atomically rename the validated sibling workspace to its final path."""

        root = final_root_layout(self._selected_data_home())
        staging = root.staging_elfie(elfie_id)
        final = root.elfie(elfie_id)
        final_exists = final.workspace.exists() or final.workspace.is_symlink()
        staging_exists = staging.workspace.exists()

        if final_exists:
            if final.workspace.is_symlink() or not final.workspace.is_dir():
                raise ResidentAdmissionPortError(
                    "final Elfie workspace is not a real directory"
                )
            self._validate_workspace(final)
            if staging_exists:
                self._validate_workspace(staging)
                if _read_marker(final.genesis_stage_marker) != _read_marker(
                    staging.genesis_stage_marker
                ):
                    raise ResidentAdmissionPortError(
                        "staging and final Genesis workspaces disagree"
                    )
                _remove_workspace(staging)
            return str(final.workspace)

        if not staging_exists:
            raise ResidentAdmissionPortError(
                "staged Genesis workspace is missing before publication"
            )
        self._validate_workspace(staging)
        _ensure_real_parent(final.workspace.parent)
        try:
            # Both paths are siblings below the same data root, so this rename
            # is one filesystem operation and never exposes a half-written
            # final workspace.
            os.replace(staging.workspace, final.workspace)
            _fsync_directory(final.workspace.parent)
        except (OSError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to publish staged Elfie workspace"
            ) from error
        return str(final.workspace)

    def publication(self, elfie_id: str) -> AdmissionPublication:
        """Return validated publication metadata from staged output."""

        root = final_root_layout(self._selected_data_home())
        for layout in (root.staging_elfie(elfie_id), root.elfie(elfie_id)):
            if not layout.workspace.exists():
                continue
            marker = self._validate_workspace(layout)
            return AdmissionPublication(
                manifest_id=str(marker["manifest_id"]),
                content_hash=str(marker["content_hash"]),
                output_ids_hash=str(marker["output_ids_hash"]),
                compiler_version=str(marker["compiler_version"]),
                schema_version=cast(int, marker["schema_version"]),
            )
        raise ResidentAdmissionPortError(
            "Genesis workspace does not exist in staging or final storage"
        )

    def final_workspace(self, elfie_id: str) -> str:
        """Return the path used by final-owner restoration."""

        layout = final_root_layout(self._selected_data_home()).elfie(elfie_id)
        if layout.workspace.is_symlink() or (
            layout.workspace.exists() and not layout.workspace.is_dir()
        ):
            raise ResidentAdmissionPortError(
                "final Elfie workspace is not a real directory"
            )
        return str(layout.workspace)

    def abort(self, elfie_id: str) -> None:
        """Delete only the exact unpublished workspace for a failed admission."""

        root = final_root_layout(self._selected_data_home())
        final = root.elfie(elfie_id)
        if final.workspace.exists() or final.workspace.is_symlink():
            raise ResidentAdmissionPortError(
                "cannot abort an Elfie after its final workspace was published"
            )
        _remove_workspace(root.staging_elfie(elfie_id))

    def finalize(self, elfie_id: str) -> None:
        """Remove the temporary marker after the durable Admission commit."""

        root = final_root_layout(self._selected_data_home())
        final = root.elfie(elfie_id)
        if final.workspace.exists():
            if final.workspace.is_symlink() or not final.workspace.is_dir():
                raise ResidentAdmissionPortError(
                    "final Elfie workspace is not a real directory"
                )
            marker = final.genesis_stage_marker
            if marker.exists():
                if marker.is_symlink() or not marker.is_file():
                    raise ResidentAdmissionPortError(
                        "Genesis marker is not a regular file"
                    )
                marker.unlink()
                _fsync_directory(final.workspace)
            envelope = final.genesis_compile_envelope
            if envelope.exists():
                if envelope.is_symlink() or not envelope.is_file():
                    raise ResidentAdmissionPortError(
                        "Genesis compile envelope is not a regular file"
                    )
                envelope.unlink()
                _fsync_directory(final.workspace)

    def load_envelope(self, elfie_id: str) -> GenesisCompileEnvelope | None:
        """Load only the exact private envelope for an unfinished reservation."""

        root = final_root_layout(self._selected_data_home())
        for layout in (root.staging_elfie(elfie_id), root.elfie(elfie_id)):
            path = layout.genesis_compile_envelope
            if not path.exists():
                continue
            try:
                envelope = _read_compile_envelope(path)
                if envelope.request.elfie_id != elfie_id:
                    raise ValueError(
                        "Genesis envelope Elfie ID does not match workspace"
                    )
                return envelope
            except (OSError, TypeError, ValueError) as error:
                raise ResidentAdmissionPortError(
                    "Genesis compile envelope is invalid"
                ) from error
        return None

    def clear_envelope(self, elfie_id: str) -> None:
        """Delete the private input after the Admission reaches a terminal owner."""

        root = final_root_layout(self._selected_data_home())
        for layout in (root.staging_elfie(elfie_id), root.elfie(elfie_id)):
            path = layout.genesis_compile_envelope
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise ResidentAdmissionPortError(
                    "Genesis compile envelope is not a regular file"
                )
            path.unlink()
            _fsync_directory(path.parent)

    def load_profile(self, elfie_id: str) -> ElfieProfile:
        """Load the final external dossier for an idempotent admission result."""

        layout = final_root_layout(self._selected_data_home()).elfie(elfie_id)
        try:
            profile = YamlProfileStoreAdapter(layout.profile.parent).load()
            profile.validate()
            if profile.identity.elfie_id != elfie_id:
                raise ValueError("Profile Elfie ID does not match workspace")
            return profile
        except (OSError, ValueError, TypeError) as error:
            raise ResidentAdmissionPortError(
                "unable to load final Elfie Profile"
            ) from error

    def _validate_workspace(
        self,
        layout: FinalElfieLayout,
        *,
        expected: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        _ensure_real_directory(layout.workspace)
        marker = _read_marker(layout.genesis_stage_marker)
        if marker["elfie_id"] != layout.workspace.name:
            raise ValueError("Genesis marker Elfie ID does not match workspace")
        if expected:
            for key, value in expected.items():
                if marker.get(key) != value:
                    raise ValueError(f"Genesis marker {key} does not match Admission")

        profile = YamlProfileStoreAdapter(layout.profile.parent).load()
        profile.validate()
        if profile.identity.elfie_id != str(marker["elfie_id"]):
            raise ValueError("Profile Elfie ID does not match Genesis marker")

        selfhood_raw = YamlSelfhoodSeedAdapter(layout.brain).load()
        # YAML has no tuple type and therefore loads the strict runtime tuple
        # fields as lists.  Normalize only at this persistence boundary; the
        # in-memory Selfhood contract remains strict.
        selfhood = SelfhoodState.model_validate(
            normalize_selfhood_mapping(selfhood_raw)
        )
        if selfhood.identity_core.elfie_id != str(marker["elfie_id"]):
            raise ValueError("Selfhood Elfie ID does not match Genesis marker")
        energy = YamlEnergyLimitsAdapter(layout.brain).load()
        if not isinstance(energy.get("limits"), dict) or not energy["limits"]:
            raise ValueError("Genesis energy seed is incomplete")

        with SQLiteMemoryStoreAdapter(
            layout.knowledge_database,
            elfie_id=str(marker["elfie_id"]),
        ) as memory:
            marker_node = memory.get_graph_node(f"genesis:receipt:{marker['elfie_id']}")
            if marker_node is None:
                raise ValueError("Genesis Memory completion marker is missing")
            properties = marker_node.properties
            for key in (
                "manifest_id",
                "content_hash",
                "output_ids_hash",
                "compiler_version",
                "schema_version",
                "idempotency_key_digest",
            ):
                if properties.get(key) != marker[key]:
                    raise ValueError(f"Memory completion marker {key} is inconsistent")
            memory_output_ids = _string_list(
                properties.get("output_ids"), "Memory output inventory"
            )
            marker_output_ids = _string_list(
                marker.get("output_ids"), "Genesis output inventory"
            )
            if memory_output_ids != marker_output_ids:
                raise ValueError("Memory output inventory is inconsistent")
            missing_outputs = [
                str(identifier)
                for identifier in marker_output_ids
                if memory.get_graph_node(str(identifier)) is None
                and memory.get_episode(str(identifier)) is None
            ]
            if missing_outputs:
                raise ValueError(
                    "Genesis output inventory contains missing records: "
                    + ", ".join(missing_outputs[:8])
                )
            submission = memory.conn.execute(
                """SELECT manifest_id, source_version, content_sha256,
                                  expected_ids_hash
                   FROM memory_genesis_submissions
                   WHERE elfie_id=? AND submission_id=?""",
                (str(marker["elfie_id"]), str(marker["idempotency_key_digest"])),
            ).fetchone()
            if submission is None:
                raise ValueError("Genesis Memory submission receipt is missing")
            if (
                str(submission["manifest_id"]) != str(marker["manifest_id"])
                or str(submission["source_version"]) != str(marker["compiler_version"])
                or str(submission["content_sha256"]) != str(marker["content_hash"])
                or str(submission["expected_ids_hash"])
                != _memory_output_ids_hash(marker["output_ids"])
            ):
                raise ValueError("Genesis Memory submission receipt is inconsistent")
        return marker


def _compilation_metadata(compilation: GenesisCompilation) -> dict[str, object]:
    manifest = compilation.bundle.manifest
    return {
        "format_version": _MARKER_FORMAT_VERSION,
        "elfie_id": compilation.profile.identity.elfie_id,
        "manifest_id": manifest.manifest_id,
        "content_hash": manifest.content_hash,
        "output_ids_hash": output_ids_hash(manifest.output_ids),
        "output_ids": list(manifest.output_ids),
        "compiler_version": manifest.compiler_version,
        "schema_version": manifest.schema_version,
        "idempotency_key_digest": _text_digest(manifest.idempotency_key),
    }


def _read_marker(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Genesis marker must be a regular file")
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as error:
        raise ValueError("Genesis marker is not valid JSON") from error
    if not isinstance(raw, dict) or set(raw) != set(_MARKER_KEYS):
        raise ValueError("Genesis marker has an unsupported shape")
    if raw.get("format_version") != _MARKER_FORMAT_VERSION:
        raise ValueError("Genesis marker format is unsupported")
    for key in (
        "elfie_id",
        "manifest_id",
        "content_hash",
        "output_ids_hash",
        "compiler_version",
        "idempotency_key_digest",
    ):
        if not isinstance(raw.get(key), str) or not str(raw[key]).strip():
            raise ValueError(f"Genesis marker {key} is invalid")
    for key in ("content_hash", "output_ids_hash", "idempotency_key_digest"):
        value = str(raw[key])
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"Genesis marker {key} is invalid")
    if (
        isinstance(raw.get("schema_version"), bool)
        or not isinstance(raw.get("schema_version"), int)
        or int(raw["schema_version"]) < 1
    ):
        raise ValueError("Genesis marker schema_version is invalid")
    output_ids = raw.get("output_ids")
    if (
        not isinstance(output_ids, list)
        or not output_ids
        or any(not isinstance(value, str) or not value.strip() for value in output_ids)
    ):
        raise ValueError("Genesis marker output_ids is invalid")
    if len(set(output_ids)) != len(output_ids):
        raise ValueError("Genesis marker output_ids must be unique")
    if output_ids_hash(output_ids) != raw["output_ids_hash"]:
        raise ValueError("Genesis marker output_ids_hash is inconsistent")
    return dict(raw)


def _read_compile_envelope(path: Path) -> GenesisCompileEnvelope:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Genesis compile envelope must be a regular file")
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as error:
        raise ValueError("Genesis compile envelope is not valid JSON") from error
    try:
        return GenesisCompileEnvelope.from_dict(raw)
    except GenesisCompileEnvelopeError as error:
        raise ValueError(str(error)) from error


def _write_json_file(path: Path, payload: Mapping[str, object]) -> None:
    _ensure_real_parent(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("JSON target is unsafe")
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(
                dict(payload),
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_marker(path: Path, marker: Mapping[str, object]) -> None:
    _ensure_real_parent(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Genesis marker target is unsafe")
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(
                dict(marker),
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _decode_portraits(
    full_body_url: str, headshot_url: str
) -> tuple[bytes, bytes] | None:
    if not full_body_url and not headshot_url:
        return None
    if not full_body_url or not headshot_url:
        raise ValueError("accepted Adoption portraits must contain both views")
    return _decode_png_data_url(full_body_url), _decode_png_data_url(headshot_url)


def _decode_png_data_url(value: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not value.startswith(prefix):
        raise ValueError("accepted Adoption portrait must be a PNG data URL")
    try:
        content = base64.b64decode(value[len(prefix) :], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("accepted Adoption portrait is not valid base64") from error
    if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > 8 * 1024 * 1024:
        raise ValueError("accepted Adoption portrait is not a valid PNG")
    return content


def _write_private_asset(path: Path, content: bytes) -> None:
    _ensure_real_parent(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("asset target is unsafe")
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _text_digest(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Genesis idempotency key must not be blank")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _memory_output_ids_hash(output_ids: object) -> str:
    if not isinstance(output_ids, list):
        raise ValueError("Memory output inventory is invalid")
    encoded = json.dumps(
        sorted(str(value) for value in output_ids),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} is invalid")
    return tuple(cast(str, item) for item in value)


def _ensure_real_directory(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError(f"path is not a real directory: {path}")
    if not path.is_dir():
        raise FileNotFoundError(path)


def _ensure_real_parent(path: Path) -> None:
    _ensure_real_directory(path)


def _reject_existing_final(layout: FinalElfieLayout) -> None:
    if layout.workspace.is_symlink() or (
        layout.workspace.exists() and not layout.workspace.is_dir()
    ):
        raise ResidentAdmissionPortError(
            "final Elfie workspace is not a real directory"
        )
    if layout.workspace.exists():
        raise ResidentAdmissionPortError(
            "Elfie workspace already exists; a new Genesis cannot overwrite it"
        )


def _remove_workspace(layout: FinalElfieLayout) -> None:
    path = layout.workspace
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        raise ResidentAdmissionPortError(
            "refusing to remove a non-directory Elfie workspace"
        )
    shutil.rmtree(path)


def _remove_staging_quietly(layout: FinalElfieLayout) -> None:
    try:
        _remove_workspace(layout)
    except (OSError, ResidentAdmissionPortError):
        # The admission record remains recoverable when cleanup itself fails.
        return


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ("FinalElfieWorkspaceAdapter",)
