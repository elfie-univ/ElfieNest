"""Atomic adapter for the authoritative RuntimeSnapshotV1."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import uuid
from pathlib import Path
from typing import Any, Final, Mapping

from app.orchestration.lifecycle.ports import RuntimeWriterHandoff
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    EndpointSnapshot,
    FailureSnapshot,
    ModelOverallState,
    OwnerLease,
    RuntimeComponent,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
    TimingSnapshot,
)
from app.orchestration.lifecycle.types import SnapshotRecoveryRequiredError

RUNTIME_RECORD_FILENAME: Final = "runtime.json"


class FileRuntimeRecordAdapter:
    """Read and atomically write one strict lifecycle snapshot.

    A missing snapshot is not silently treated as stopped. Only an actually
    empty or explicitly prepared data root can be initialized; an unprepared
    existing root with a missing or malformed snapshot is recovery-required.
    """

    def __init__(
        self,
        elfie_home: Path,
        *,
        writer_token: str | None = None,
    ) -> None:
        self._elfie_home = elfie_home
        self._writer_token = writer_token or self._read_writer_token()
        # Only the lifecycle parent that explicitly issued the handoff may
        # create a new credential. A child may use its inherited token, but it
        # can never mint a replacement after its generation is revoked.
        self._handoff_armed = False

    def begin_writer_handoff(
        self, *, generation: int, owner_id: str
    ) -> RuntimeWriterHandoff:
        token = secrets.token_urlsafe(32)
        self._writer_token = token
        self._handoff_armed = True
        self._write_writer_token(token)
        return RuntimeWriterHandoff(
            token=token,
            digest=_digest(token),
            generation=generation,
            owner_id=owner_id,
        )

    def revoke_writer_handoff(self) -> None:
        self._writer_token = None
        self._handoff_armed = False
        try:
            self._writer_token_path().unlink()
        except FileNotFoundError:
            pass

    def read(self) -> RuntimeSnapshotV1:
        path = self._record_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._recovery_snapshot(
                "SNAPSHOT_MISSING", "Runtime snapshot is missing"
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            return self._recovery_snapshot("SNAPSHOT_CORRUPT", str(error))
        try:
            return self._parse(payload)
        except (KeyError, TypeError, ValueError) as error:
            return self._recovery_snapshot("SNAPSHOT_INVALID", str(error))

    def initialize_if_fresh(
        self, *, allow_existing_root: bool = False
    ) -> RuntimeSnapshotV1:
        existing = self._record_path()
        if existing.exists():
            snapshot = self.read()
            if snapshot.phase is RuntimePhase.RECOVERY_REQUIRED:
                raise SnapshotRecoveryRequiredError(
                    self._elfie_home,
                    snapshot.failures[0].detail
                    if snapshot.failures
                    else "Invalid Runtime snapshot",
                )
            return snapshot
        if not allow_existing_root and not self._root_is_fresh():
            raise SnapshotRecoveryRequiredError(
                self._elfie_home,
                "Existing data root has no authoritative Runtime snapshot",
            )
        snapshot = RuntimeSnapshotV1(instance_id=uuid.uuid4().hex)
        self.write(snapshot)
        return snapshot

    def write(self, snapshot: RuntimeSnapshotV1) -> None:
        if snapshot.schema_version != 1:
            raise ValueError(
                f"Unsupported Runtime snapshot schema: {snapshot.schema_version}"
            )
        if not snapshot.instance_id or snapshot.instance_id == "uninitialized":
            raise ValueError("Runtime snapshot instance_id must be initialized")
        if snapshot.generation < 0 or snapshot.revision < 0:
            raise ValueError(
                "Runtime snapshot generation and revision must be non-negative"
            )
        previous = self._read_valid_for_write()
        self._authorize_write(previous, snapshot)
        if previous is not None:
            if previous.instance_id != snapshot.instance_id:
                raise ValueError("Runtime snapshot instance identity changed")
            if snapshot.revision <= previous.revision:
                raise ValueError(
                    f"Runtime snapshot revision must advance from {previous.revision}"
                )
            if snapshot.generation < previous.generation:
                raise ValueError("Runtime snapshot generation must be monotonic")
        self._elfie_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime_dir = self._elfie_home / "runtime"
        runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".runtime.", dir=str(runtime_dir)
        )
        temporary_path = Path(temporary_name)
        payload = self._serialize(snapshot)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
                json.dump(payload, receipt, ensure_ascii=False, sort_keys=True)
                receipt.write("\n")
            temporary_path.replace(self._record_path())
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise

    def _authorize_write(
        self,
        previous: RuntimeSnapshotV1 | None,
        snapshot: RuntimeSnapshotV1,
    ) -> None:
        """Reject writes from a stale generation or an unarmed writer."""
        current_digest = _digest(self._writer_token) if self._writer_token else None
        previous_digest = (
            None if previous is None else previous.writer_credential_digest
        )
        requested_digest = snapshot.writer_credential_digest

        if previous_digest is not None and current_digest != previous_digest:
            raise PermissionError(
                "Runtime writer credential does not own this generation"
            )
        if requested_digest is not None and current_digest != requested_digest:
            raise PermissionError("Runtime snapshot writer credential is invalid")
        if (
            requested_digest is not None
            and previous_digest is None
            and not self._handoff_armed
        ):
            raise PermissionError("Runtime writer handoff was not issued by the parent")
        if (
            previous is not None
            and previous_digest is None
            and requested_digest is None
            and not self._handoff_armed
        ):
            raise PermissionError("Runtime writer credential has been revoked")

    def _read_valid_for_write(self) -> RuntimeSnapshotV1 | None:
        if not self._record_path().exists():
            return None
        snapshot = self.read()
        if snapshot.phase is RuntimePhase.RECOVERY_REQUIRED:
            raise SnapshotRecoveryRequiredError(
                self._elfie_home,
                snapshot.failures[0].detail
                if snapshot.failures
                else "Invalid Runtime snapshot",
            )
        return snapshot

    def _root_is_fresh(self) -> bool:
        if not self._elfie_home.exists():
            return True
        try:
            children = tuple(self._elfie_home.iterdir())
            if not children:
                return True
            if any(child.name != "runtime" for child in children):
                return False
            runtime_dir = self._elfie_home / "runtime"
            if not runtime_dir.is_dir():
                return False
            allowed = {Path("locks"), Path("locks") / "owner-recovery.lock"}
            for child in runtime_dir.rglob("*"):
                if child.is_dir():
                    continue
                if child.relative_to(runtime_dir) not in allowed:
                    return False
            return True
        except OSError as error:
            raise SnapshotRecoveryRequiredError(self._elfie_home, str(error)) from error

    def _record_path(self) -> Path:
        return self._elfie_home / "runtime" / RUNTIME_RECORD_FILENAME

    @staticmethod
    def _parse(payload: Any) -> RuntimeSnapshotV1:
        if not isinstance(payload, dict):
            raise TypeError("snapshot root must be an object")
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported snapshot schema")
        components = tuple(
            ComponentSnapshot(
                component=RuntimeComponent(item["component"]),
                state=ComponentState(item["state"]),
                detail=_string(item.get("detail", ""), "component.detail"),
                pid=_optional_positive_int(item.get("pid"), "component.pid"),
                executable=_optional_string(
                    item.get("executable"), "component.executable"
                ),
                birth_identity=_optional_string(
                    item.get("birth_identity"), "component.birth_identity"
                ),
            )
            for item in _list_of_dicts(payload.get("components", []), "components")
        )
        endpoints = tuple(
            EndpointSnapshot(
                name=_string(item["name"], "endpoint.name"),
                scheme=_string(item["scheme"], "endpoint.scheme"),
                host=_string(item["host"], "endpoint.host"),
                port=_positive_int(item["port"], "endpoint.port"),
                protocol_version=_string(
                    item.get("protocol_version", ""), "endpoint.protocol_version"
                ),
            )
            for item in _list_of_dicts(payload.get("endpoints", []), "endpoints")
        )
        failures = tuple(
            FailureSnapshot(
                code=_string(item["code"], "failure.code"),
                detail=_string(item["detail"], "failure.detail"),
                phase=_string(item.get("phase", ""), "failure.phase"),
            )
            for item in _list_of_dicts(payload.get("failures", []), "failures")
        )
        timings = tuple(
            TimingSnapshot(
                phase=_string(item["phase"], "timing.phase"),
                duration_ms=_optional_nonnegative_int(
                    item.get("duration_ms"), "timing.duration_ms"
                ),
                elapsed_ms=_optional_nonnegative_int(
                    item.get("elapsed_ms"), "timing.elapsed_ms"
                ),
            )
            for item in _list_of_dicts(payload.get("timings", []), "timings")
        )
        owner = payload.get("owner_lease")
        owner_lease = (
            OwnerLease(
                owner_id=_string(owner["owner_id"], "owner_lease.owner_id"),
                generation=_nonnegative_int(
                    owner["generation"], "owner_lease.generation"
                ),
            )
            if owner is not None
            else None
        )
        startup_owner_id = _optional_string(
            payload.get("startup_owner_id"), "startup_owner_id"
        )
        return RuntimeSnapshotV1(
            schema_version=1,
            instance_id=_string(payload["instance_id"], "instance_id"),
            generation=_nonnegative_int(payload["generation"], "generation"),
            revision=_nonnegative_int(payload["revision"], "revision"),
            tier=BackendTier(payload["tier"]),
            phase=RuntimePhase(payload["phase"]),
            subphase=_string(payload.get("subphase", ""), "subphase"),
            desired_target=RuntimeTarget(payload["desired_target"]),
            reached_target=(
                RuntimeTarget(payload["reached_target"])
                if payload.get("reached_target") is not None
                else None
            ),
            components=components,
            endpoints=endpoints,
            model_state=ModelOverallState(payload.get("model_state", "unconfigured")),
            model_common_state=ModelOverallState(
                payload.get(
                    "model_common_state", payload.get("model_state", "unconfigured")
                )
            ),
            model_emergency_state=ModelOverallState(
                payload.get(
                    "model_emergency_state", payload.get("model_state", "unconfigured")
                )
            ),
            model_revision=_optional_nonnegative_int(
                payload.get("model_revision"), "model_revision"
            ),
            failures=failures,
            correlation_id=_optional_string(
                payload.get("correlation_id"), "correlation_id"
            ),
            timings=timings,
            protocol_versions=tuple(
                _string(item, "protocol_versions.item")
                for item in _list_of_strings(
                    payload.get("protocol_versions", []), "protocol_versions"
                )
            ),
            owner_lease=owner_lease,
            startup_owner_id=startup_owner_id,
            writer_credential_digest=_optional_string(
                payload.get("writer_credential_digest"),
                "writer_credential_digest",
            ),
        )

    @staticmethod
    def _serialize(snapshot: RuntimeSnapshotV1) -> Mapping[str, object]:
        return {
            "schema_version": snapshot.schema_version,
            "instance_id": snapshot.instance_id,
            "generation": snapshot.generation,
            "revision": snapshot.revision,
            "tier": snapshot.tier.value,
            "phase": snapshot.phase.value,
            "subphase": snapshot.subphase,
            "desired_target": snapshot.desired_target.value,
            "reached_target": (
                snapshot.reached_target.value if snapshot.reached_target else None
            ),
            "components": [
                {
                    "component": item.component.value,
                    "state": item.state.value,
                    "detail": item.detail,
                    "pid": item.pid,
                    "executable": item.executable,
                    "birth_identity": item.birth_identity,
                }
                for item in snapshot.components
            ],
            "endpoints": [
                {
                    "name": item.name,
                    "scheme": item.scheme,
                    "host": item.host,
                    "port": item.port,
                    "protocol_version": item.protocol_version,
                }
                for item in snapshot.endpoints
            ],
            "model_state": snapshot.model_state.value,
            "model_common_state": snapshot.model_common_state.value,
            "model_emergency_state": snapshot.model_emergency_state.value,
            "model_revision": snapshot.model_revision,
            "failures": [
                {"code": item.code, "detail": item.detail, "phase": item.phase}
                for item in snapshot.failures
            ],
            "correlation_id": snapshot.correlation_id,
            "timings": [
                {
                    "phase": item.phase,
                    "duration_ms": item.duration_ms,
                    "elapsed_ms": item.elapsed_ms,
                }
                for item in snapshot.timings
            ],
            "protocol_versions": list(snapshot.protocol_versions),
            "owner_lease": (
                {
                    "owner_id": snapshot.owner_lease.owner_id,
                    "generation": snapshot.owner_lease.generation,
                }
                if snapshot.owner_lease is not None
                else None
            ),
            "startup_owner_id": snapshot.startup_owner_id,
            "writer_credential_digest": snapshot.writer_credential_digest,
        }

    def _writer_token_path(self) -> Path:
        return self._elfie_home / "runtime" / "writer.token"

    def _read_writer_token(self) -> str | None:
        try:
            token = self._writer_token_path().read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError, UnicodeError):
            return None
        return token or None

    def _write_writer_token(self, token: str) -> None:
        self._elfie_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime_dir = self._elfie_home / "runtime"
        runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".writer.", dir=str(runtime_dir)
        )
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as secret:
                secret.write(token)
                secret.write("\n")
            temporary_path.replace(self._writer_token_path())
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _recovery_snapshot(code: str, detail: str) -> RuntimeSnapshotV1:
        return RuntimeSnapshotV1(
            phase=RuntimePhase.RECOVERY_REQUIRED,
            failures=(FailureSnapshot(code=code, detail=detail, phase="preflight"),),
        )


def _list_of_dicts(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"{field_name} must be a list of objects")
    return value


def _list_of_strings(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _positive_int(value: Any, field_name: str) -> int:
    result = _nonnegative_int(value, field_name)
    if result <= 0:
        raise ValueError(f"{field_name} must be positive")
    return result


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field_name)


def _nonnegative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _optional_nonnegative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, field_name)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
