"""Collect a replayable, data-only trace of the production Brain chain.

The collector deliberately owns no Brain semantics.  It selects an isolated
Elfie snapshot, injects either the real or deterministic edge implementations,
and records typed owner boundaries while the existing Brain runtime executes.
Analysis and evaluation stay outside this package.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime
from datetime import time as datetime_time
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from devtools.elfie_lab.model_execution_adapters import redact_text, redact_value
from devtools.elfie_lab.model_execution_foods import (
    ElfieLabModelEnvironment,
    load_model_execution_food_catalog,
    model_execution_food_catalog_store,
)
from devtools.elfie_lab.schemas import StimulusBundle, new_id, utc_now
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie.brain.memory.contracts import MemoryStateSnapshot
from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    EvidenceInput,
    MediaReference,
    NodeInput,
    SourceReference,
)
from elfie.brain.observation import BrainObservation
from elfie.brain.state_lifecycle import StateCheckpoint
from elfie.diagnostics import ElfieDiagnostics
from infrastructure.models.model_execution_observations import (
    get_model_execution_observer,
)
from infrastructure.persistence.brain_journal import SQLiteBrainJournalAdapter
from infrastructure.persistence.layout.data_home import resolve_elfie_home
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


class BrainTraceValidationError(ValueError):
    """Raised for an invalid collector mode, source or artifact request."""


def _jsonable(value: Any, seen: Optional[set[int]] = None) -> Any:
    """Convert typed Brain values to JSON without using repr as a fact source."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if seen is None:
        seen = set()
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _jsonable(value.value, seen)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {
            "sha256": hashlib.sha256(value).hexdigest(),
            "size_bytes": len(value),
            "encoding": "binary_digest",
        }
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump(mode="json"), seen)
        except TypeError:
            return _jsonable(value.model_dump(), seen)
    if is_dataclass(value):
        return _jsonable(asdict(cast(Any, value)), seen)
    if isinstance(value, Mapping):
        return _jsonable_container(value, seen)
    if isinstance(value, (list, tuple, set, frozenset)):
        return _jsonable_container(value, seen)
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value), seen)
    return str(value)


def _jsonable_container(value: Any, seen: set[int]) -> Any:
    """Expand a visited container while guarding against reference cycles."""
    container_id = id(value)
    if container_id in seen:
        return "<cyclic-ref>"
    seen.add(container_id)
    try:
        if isinstance(value, Mapping):
            return {str(key): _jsonable(item, seen) for key, item in value.items()}
        return [_jsonable(item, seen) for item in value]
    finally:
        seen.discard(container_id)


def _safe_value(value: Any) -> Any:
    """Serialize and recursively redact a trace value."""
    return redact_value(_jsonable(value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _git_provenance(project_root: Path) -> Dict[str, Any]:
    def run(*args: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(project_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    revision = run("rev-parse", "HEAD")
    dirty = run("status", "--porcelain")
    return {
        "revision": revision,
        "dirty": bool(dirty),
    }


def _assert_developer_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    production = resolve_elfie_home().expanduser().resolve(strict=False)
    if resolved == production or production in resolved.parents:
        raise BrainTraceValidationError(
            f"Brain trace {label} cannot use production ELFIE_HOME"
        )
    return resolved


def _omit_mock_memory_snapshot(
    runtime_storage: ElfieLabStorage,
    elfie_id: str,
) -> None:
    """Keep source memory out of a mock-memory artifact and execution path."""
    memory_root = runtime_storage.elfie_dir(elfie_id) / "memory"
    for path in memory_root.glob("knowledge.sqlite*"):
        if path.is_file() or path.is_symlink():
            path.unlink()


def _reset_mock_memory_checkpoint(
    runtime_storage: ElfieLabStorage,
    elfie_id: str,
    memory_store: TracingMemoryStore,
) -> None:
    """Align the cloned Brain checkpoint with the selected mock Memory state."""
    journal = SQLiteBrainJournalAdapter(runtime_storage.journal_path(elfie_id))
    try:
        checkpoint = journal.load_checkpoint()
        if checkpoint is None:
            return
        episodic_count = memory_store.count_episodes()
        total_count = memory_store.count_memory_records()
        memory_state = MemoryStateSnapshot(
            revision=0,
            captured_at=checkpoint.memory.value.captured_at,
            episodic_count=episodic_count,
            total_count=total_count,
            source_event_ids=(),
            snapshot_freshness="current" if total_count else "unknown",
        )
        memory_checkpoint = StateCheckpoint(
            revision=0,
            committed_at=checkpoint.memory.committed_at,
            source_event_ids=(),
            causation_id=None,
            value=memory_state,
            committed_candidate_ids=(),
        )
        journal.save_checkpoint(replace(checkpoint, memory=memory_checkpoint))
    finally:
        journal.close()


# Temporary W3 shim: map observation boundaries onto the recorder's legacy
# internal event kinds so the existing artifact pipeline stays intact.  W4
# converges the collector onto native envelopes and removes this mapping.
_RECORD_KIND_BY_BOUNDARY = {
    "reasoning.memory_bridge": "memory_bridge",
    "reasoning.context_engine": "context",
}


class TraceRecorder:
    """Thread-safe ``BrainObservationSink`` for the trace collector.

    Incoming ``BrainObservation`` envelopes are converted into the recorder's
    legacy dict event shape at the ``emit`` boundary (temporary W3 shim);
    the dict pipeline and this conversion are removed when W4 converges the
    collector onto native envelopes.  ``emit`` never raises and all shared
    state is guarded by one lock because the Brain emits from the cognitive
    worker and coordinator threads concurrently.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._events: List[Dict[str, Any]] = []
        self._envelopes: List[BrainObservation] = []
        self._local = threading.local()
        self._frame_to_turn: Dict[str, str] = {}

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    @property
    def events(self) -> Tuple[Dict[str, Any], ...]:
        with self._lock:
            return tuple(self._events)

    def current_scope(self) -> Dict[str, Optional[str]]:
        return {
            "turn_id": getattr(self._local, "turn_id", None),
            "frame_id": getattr(self._local, "frame_id", None),
        }

    def emit(self, event: BrainObservation) -> None:
        """Record one observation without ever affecting Brain behavior."""
        try:
            self._record_observation(event)
        except Exception:  # noqa: BLE001 - sink contract absorbs own failures
            pass

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        """Return the recorded observation envelopes in emit order."""
        with self._lock:
            return tuple(self._envelopes)

    def _record_observation(self, event: BrainObservation) -> None:
        frame_id = event.frame_id
        turn_id = event.turn_id
        with self._lock:
            self._envelopes.append(event)
            if frame_id:
                self._local.frame_id = str(frame_id)
            if turn_id:
                self._local.turn_id = str(turn_id)
                if frame_id:
                    self._frame_to_turn[str(frame_id)] = str(turn_id)
            elif frame_id:
                mapped = self._frame_to_turn.get(str(frame_id))
                if mapped:
                    self._local.turn_id = mapped
            self.record(
                _RECORD_KIND_BY_BOUNDARY.get(event.boundary, event.boundary),
                self._observation_payload(event),
            )

    @staticmethod
    def _observation_payload(event: BrainObservation) -> Dict[str, Any]:
        """Flatten one envelope into the legacy payload dict for artifacts."""
        return {
            "boundary": event.boundary,
            "kind": event.kind,
            "turn_id": event.turn_id,
            "frame_id": event.frame_id,
            "cause_event_ids": tuple(event.cause_event_ids),
            "duration_ms": event.duration_ms,
            "status": event.status.value,
            "error": event.error.model_dump() if event.error is not None else None,
            "payload": event.payload.model_dump(),
        }

    def record(self, kind: str, payload: Any) -> None:
        with self._lock:
            self._sequence += 1
            scope = self.current_scope()
            self._events.append(
                {
                    "sequence": self._sequence,
                    "captured_at": utc_now(),
                    "kind": kind,
                    "scope": scope,
                    "payload": payload,
                }
            )


class TracingMemoryStore:
    """Semantic MemoryStore proxy that records calls without reimplementing SQL."""

    def __init__(self, inner: Any, recorder: TraceRecorder):
        self._inner = inner
        self._recorder = recorder

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            if name.startswith("bind_"):
                # Wiring methods are not memory semantics; call through unrecorded.
                return attribute(*args, **kwargs)
            started = time.perf_counter()
            payload: Dict[str, Any] = {
                "method": name,
                "args": args,
                "kwargs": kwargs,
            }
            try:
                result = attribute(*args, **kwargs)
                payload["result"] = result
                return result
            except Exception as error:
                payload["error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
                raise
            finally:
                payload["duration_ms"] = round(
                    (time.perf_counter() - started) * 1000,
                    2,
                )
                self._recorder.record("memory_store", payload)

        return invoke


def _normalise_episode(data: Mapping[str, Any]) -> ClosedEpisode:
    values = dict(data)
    for key in ("source_event_ids",):
        if key in values:
            values[key] = tuple(str(item) for item in values[key])
    values["source_refs"] = tuple(
        item if isinstance(item, SourceReference) else SourceReference(**dict(item))
        for item in values.get("source_refs", ())
    )
    values["media_refs"] = tuple(
        item if isinstance(item, MediaReference) else MediaReference(**dict(item))
        for item in values.get("media_refs", ())
    )
    values["sensory"] = tuple(
        tuple(str(part) for part in item) for item in values.get("sensory", ())
    )
    values["metadata"] = dict(values.get("metadata") or {})
    return ClosedEpisode(**values)


def _normalise_node(data: Mapping[str, Any]) -> NodeInput:
    values = dict(data)
    values["properties"] = dict(values.get("properties") or {})
    return NodeInput(**values)


def _normalise_evidence(data: Mapping[str, Any]) -> EvidenceInput:
    return EvidenceInput(**dict(data))


def _normalise_assertion(data: Mapping[str, Any]) -> AssertionInput:
    values = dict(data)
    values["evidence_ids"] = tuple(str(item) for item in values.get("evidence_ids", ()))
    return AssertionInput(**values)


def _fixture_items(
    data: Mapping[str, Any],
    key: str,
) -> Tuple[Mapping[str, Any], ...]:
    raw = data.get(key, ())
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise BrainTraceValidationError(f"memory fixture field must be a list: {key}")
    if not all(isinstance(item, Mapping) for item in raw):
        raise BrainTraceValidationError(f"memory fixture items must be objects: {key}")
    return tuple(cast(Mapping[str, Any], item) for item in raw)


def _seed_memory_fixture(
    store: TracingMemoryStore,
    fixture_path: Path,
) -> Dict[str, Any]:
    try:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BrainTraceValidationError(
            f"invalid memory fixture: {fixture_path}"
        ) from error
    if not isinstance(data, Mapping):
        raise BrainTraceValidationError("memory fixture must be a JSON object")
    episodes = tuple(
        _normalise_episode(item) for item in _fixture_items(data, "episodes")
    )
    nodes = tuple(_normalise_node(item) for item in _fixture_items(data, "nodes"))
    evidence = tuple(
        _normalise_evidence(item) for item in _fixture_items(data, "evidence")
    )
    assertions = tuple(
        _normalise_assertion(item) for item in _fixture_items(data, "assertions")
    )
    for episode in episodes:
        store.record_episode(episode)
    for node in nodes:
        store.upsert_node_record(node)
    evidence_by_id = {item.evidence_id: item for item in evidence}
    for assertion in assertions:
        selected = next(
            (
                evidence_by_id[item]
                for item in assertion.evidence_ids
                if item in evidence_by_id
            ),
            None,
        )
        if selected is None:
            raise BrainTraceValidationError(
                f"fixture assertion has no matching evidence: {assertion.assertion_id}"
            )
        store.record_sourced_assertion(assertion, selected)
    return {
        "path": str(fixture_path),
        "sha256": _sha256_file(fixture_path),
        "episodes": len(episodes),
        "nodes": len(nodes),
        "evidence": len(evidence),
        "assertions": len(assertions),
    }


def load_messages_file(path: str | Path) -> Tuple[StimulusBundle, ...]:
    """Load a JSON array/object or JSONL sequence of typed stimuli."""
    message_path = Path(path).expanduser().resolve()
    try:
        raw_text = message_path.read_text(encoding="utf-8")
    except OSError as error:
        raise BrainTraceValidationError(
            f"messages file is unreadable: {message_path}"
        ) from error
    try:
        if message_path.suffix.casefold() == ".jsonl":
            values = [
                json.loads(line) for line in raw_text.splitlines() if line.strip()
            ]
        else:
            parsed = json.loads(raw_text)
            values = (
                parsed.get("messages", ()) if isinstance(parsed, Mapping) else parsed
            )
    except ValueError as error:
        raise BrainTraceValidationError(
            f"invalid messages file: {message_path}"
        ) from error
    if not isinstance(values, (list, tuple)) or not values:
        raise BrainTraceValidationError(
            "messages file must contain at least one message"
        )
    result: List[StimulusBundle] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise BrainTraceValidationError("each message must be a JSON object")
        try:
            result.append(StimulusBundle(**dict(item)))
        except (TypeError, ValueError) as error:
            raise BrainTraceValidationError(
                "message does not match StimulusBundle"
            ) from error
    return tuple(result)


@dataclass(frozen=True)
class BrainTraceRun:
    """Machine-readable result of one collection run."""

    run_id: str
    artifact_dir: Path
    status: str
    turns: int
    failed_turns: int
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "artifact_dir": str(self.artifact_dir),
            "status": self.status,
            "turns": self.turns,
            "failed_turns": self.failed_turns,
            "error": self.error,
        }


class _ArtifactWriter:
    def __init__(self, artifact_dir: Path):
        self.root = artifact_dir
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self._manifest = self.root / "manifest.json"
        self._events = self.root / "events.jsonl"
        self._turns = self.root / "turns.jsonl"

    def write_manifest(self, manifest: Mapping[str, Any]) -> None:
        temporary = self.root / ".manifest.tmp"
        temporary.write_text(
            json.dumps(_safe_value(manifest), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._manifest)

    def append(self, name: str, value: Any) -> None:
        path = self._events if name == "events" else self._turns
        with path.open("a", encoding="utf-8") as handle:
            values = (
                value
                if name == "events" and isinstance(value, (list, tuple))
                else (value,)
            )
            for item in values:
                handle.write(json.dumps(_safe_value(item), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _turn_events(
    events: Iterable[Mapping[str, Any]],
    *,
    turn_id: str,
    model_call_count: int,
) -> Dict[str, Any]:
    selected: List[Mapping[str, Any]] = []
    frame_ids: set[str] = set()
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("turn_id", "")) == turn_id:
            selected.append(event)
            if payload.get("frame_id"):
                frame_ids.add(str(payload["frame_id"]))
    for event in events:
        payload = event.get("payload")
        scope = event.get("scope")
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("frame_id", "")) in frame_ids:
            if event not in selected:
                selected.append(event)
            continue
        if isinstance(scope, Mapping) and str(scope.get("frame_id", "")) in frame_ids:
            if event not in selected:
                selected.append(event)
    return {
        "turn_id": turn_id,
        "frame_ids": sorted(frame_ids),
        "events": selected,
        "model_call_count": model_call_count,
    }


def _memory_snapshot(session: ElfieLabSession) -> Any:
    try:
        return ElfieDiagnostics(session.elfie).memory.memory_inspection_snapshot()
    except Exception as error:  # noqa: BLE001 - trace records unavailable owners
        return {"error": type(error).__name__, "message": str(error)}


def _journal_snapshot(session: ElfieLabSession) -> Tuple[Any, ...]:
    try:
        return session.elfie.brain_journal()
    except Exception as error:  # noqa: BLE001 - trace records unavailable owners
        return ({"error": type(error).__name__, "message": str(error)},)


def _model_execution_events_since(
    before: Tuple[Any, ...],
) -> Tuple[Dict[str, Any], ...]:
    """Project existing model-execution observer facts produced since a turn.

    The observer is a shared in-process projection, so the collector snapshots
    its current length rather than changing or flushing the singleton.  A
    separately launched Developer Tool therefore remains isolated while an
    embedded collector does not erase unrelated observations.
    """
    after = get_model_execution_observer().snapshot()
    if len(after) >= len(before) and after[: len(before)] == before:
        delta = after[len(before) :]
    else:
        # A concurrent owner may have flushed the shared projection.  Preserve
        # what is observable instead of claiming an incomplete delta.
        delta = after
    projected: List[Dict[str, Any]] = []
    for event in delta:
        try:
            value: Any = event.to_dict()
        except AttributeError:
            value = event
        projected.append(cast(Dict[str, Any], _jsonable(value)))
    return tuple(projected)


def _persistence_evidence(session: ElfieLabSession) -> Dict[str, Any]:
    """Report the durable files observed after a turn without reading SQL."""
    paths = (
        session.storage.session_path(session.spec.elfie_id, session.session_id),
        session.storage.memory_path(session.spec.elfie_id),
        session.storage.activity_path(session.spec.elfie_id),
        session.storage.journal_path(session.spec.elfie_id),
    )
    return {
        "files": [
            {
                "path": str(path),
                "exists": path.is_file(),
                "sha256": _sha256_file(path) if path.is_file() else None,
                "size_bytes": path.stat().st_size if path.is_file() else 0,
            }
            for path in paths
        ]
    }


def _quiesce(session: ElfieLabSession, *, seconds: float = 0.2) -> None:
    """Give queued receipt/housekeeping work a short, bounded drain window."""
    deadline = time.monotonic() + seconds
    previous = None
    stable = 0
    while time.monotonic() < deadline:
        current = (
            len(session.elfie.turn_outcomes()),
            len(session.elfie.brain_journal()),
        )
        if current == previous:
            stable += 1
            if stable >= 3:
                return
        else:
            stable = 0
            previous = current
        time.sleep(0.02)


def list_brain_trace_sources(
    data_dir: str | Path,
    *,
    model_execution_config_dir: str | Path | None = None,
) -> Dict[str, Any]:
    """List selectable isolated Elfies and saved model foods without secrets."""
    storage = ElfieLabStorage(
        str(_assert_developer_path(Path(data_dir), label="data directory"))
    )
    config_dir = Path(model_execution_config_dir or storage.root / "runtime")
    config_dir = _assert_developer_path(config_dir, label="model configuration")
    environment = ElfieLabModelEnvironment(config_dir)
    catalog = load_model_execution_food_catalog(
        environment,
        model_execution_food_catalog_store(environment),
    )
    foods = []
    for key, package in sorted(catalog.packages.items()):
        if package.archived or not package.enabled:
            continue
        foods.append(
            {
                "food_key": key,
                "display_name": package.display_name,
                "primary_model": package.primary.model if package.primary else None,
            }
        )
    return {
        "data_dir": str(storage.root),
        "elfies": [spec.to_dict() for spec in storage.list_elfies()],
        "foods": foods,
    }


def collect_brain_trace(
    *,
    elfie_id: str,
    messages: Sequence[StimulusBundle],
    memory_mode: str,
    model_mode: str,
    food_key: str | None = None,
    data_dir: str | Path,
    output_root: str | Path,
    memory_fixture: str | Path | None = None,
    model_execution_config_dir: str | Path | None = None,
) -> BrainTraceRun:
    """Run the actual Brain chain and write a data-only trace artifact."""
    if memory_mode not in {"real", "mock"}:
        raise BrainTraceValidationError("memory_mode must be real or mock")
    if model_mode not in {"real", "mock"}:
        raise BrainTraceValidationError("model_mode must be real or mock")
    if not messages:
        raise BrainTraceValidationError("at least one message is required")
    if model_mode == "real" and (not food_key or food_key.strip().casefold() == "mock"):
        raise BrainTraceValidationError("real model mode requires a saved food_key")
    if memory_mode == "real" and memory_fixture is not None:
        raise BrainTraceValidationError(
            "memory_fixture is only valid when memory_mode is mock"
        )
    selected_food = "mock" if model_mode == "mock" else str(food_key).strip()
    source_root = _assert_developer_path(Path(data_dir), label="data directory")
    output_parent = _assert_developer_path(Path(output_root), label="output directory")
    source_storage = ElfieLabStorage(str(source_root))
    # Select from the read-only listing.  ``get_elfie`` intentionally repairs
    # older Lab records when their compiled workspace is missing; that repair
    # is appropriate for normal Lab use but would violate this collector's
    # source-snapshot immutability boundary.
    spec = next(
        (item for item in source_storage.list_elfies() if item.elfie_id == elfie_id),
        None,
    )
    if spec is None:
        raise BrainTraceValidationError(f"unknown Elfie: {elfie_id}")
    run_id = new_id("brain-trace")
    artifact_dir = output_parent / run_id
    writer = _ArtifactWriter(artifact_dir)
    project_root = Path(__file__).resolve().parents[2]
    recorder = TraceRecorder()
    started_at = utc_now()
    manifest: Dict[str, Any] = {
        "schema_version": "brain-trace.v1",
        "run_id": run_id,
        "status": "running",
        "started_at": started_at,
        "elfie": {
            "elfie_id": spec.elfie_id,
            "name": spec.name,
            "source_data_dir": str(source_root),
        },
        "memory": {"mode": memory_mode},
        "model": {"mode": model_mode, "food_key": selected_food},
        "provenance": {
            "code": _git_provenance(project_root),
            "source_snapshot_sha256": None,
            "config_fingerprint": None,
        },
        "input_count": len(messages),
        "completed_turns": 0,
        "failed_turns": 0,
    }
    writer.write_manifest(manifest)
    runtime_root = artifact_dir / "runtime"
    session: ElfieLabSession | None = None
    failed_turns = 0
    completed_turns = 0
    event_cursor = 0
    fatal_error: Optional[str] = None
    try:
        source_storage.export_elfie_snapshot(spec.elfie_id, runtime_root)
        runtime_storage = ElfieLabStorage(str(runtime_root))
        if memory_mode == "mock":
            _omit_mock_memory_snapshot(runtime_storage, spec.elfie_id)
        manifest["provenance"]["source_snapshot_sha256"] = _tree_digest(
            runtime_storage.elfie_dir(spec.elfie_id)
        )
        config_dir = Path(model_execution_config_dir or source_root / "runtime")
        config_dir = _assert_developer_path(config_dir, label="model configuration")
        model_environment = ElfieLabModelEnvironment(config_dir)
        manifest["provenance"]["config_fingerprint"] = {
            str(path.name): _sha256_file(path)
            for path in (
                model_environment.layout.runtime_config,
                model_environment.layout.providers_config,
            )
            if path.is_file()
        }
        fixture_path = (
            _assert_developer_path(Path(memory_fixture), label="memory fixture")
            if memory_fixture is not None
            else None
        )

        if memory_mode == "real":
            inner_memory = SQLiteMemoryStoreAdapter(
                runtime_storage.memory_path(spec.elfie_id),
                elfie_id=spec.elfie_id,
            )
        else:
            inner_memory = SQLiteMemoryStoreAdapter.in_memory(elfie_id=spec.elfie_id)
        memory_store = TracingMemoryStore(inner_memory, recorder)
        if memory_mode == "mock":
            manifest["memory"]["source_snapshot"] = "omitted"
            if fixture_path is not None:
                fixture_info = _seed_memory_fixture(memory_store, fixture_path)
                manifest["memory"]["fixture"] = fixture_info
                recorder.record("memory_fixture", fixture_info)
            _reset_mock_memory_checkpoint(
                runtime_storage,
                spec.elfie_id,
                memory_store,
            )

        session = ElfieLabSession(
            runtime_storage.get_elfie(spec.elfie_id),
            runtime_storage,
            model_execution_config_dir=str(config_dir),
            memory_store=memory_store,
            observation_sink=recorder,
        )
        model_observer = get_model_execution_observer()
        for index, stimulus in enumerate(messages):
            before_event_count = recorder.event_count
            before_journal = _journal_snapshot(session)
            before_memory = _memory_snapshot(session)
            model_events_before = model_observer.snapshot()
            started = time.perf_counter()
            try:
                turn = session.run_turn(stimulus, selected_food)
                _quiesce(session)
                submitted_turn_id = str(turn.get("turn_id"))
                brain_turn_id = str(
                    turn.get("result", {}).get("turn_id") or submitted_turn_id
                )
                model_execution = session.last_model_execution
                calls = list(getattr(model_execution, "calls", ()))
                model_execution_events = _model_execution_events_since(
                    model_events_before
                )
                for model_event in model_execution_events:
                    recorder.record(
                        "model_execution",
                        {"turn_id": brain_turn_id, "event": model_event},
                    )
                if calls:
                    first_call = calls[0]
                    manifest["model"].update(
                        {
                            "provider": first_call.get("provider"),
                            "model": first_call.get("model"),
                        }
                    )
                after_journal = _journal_snapshot(session)
                after_memory = _memory_snapshot(session)
                event_values = recorder.events
                turn_payload = {
                    "schema_version": "brain-trace.turn.v1",
                    "input_index": index,
                    "turn_id": submitted_turn_id,
                    "brain_turn_id": brain_turn_id,
                    "submitted_input": stimulus,
                    "session_turn": turn,
                    "state_before": turn.get("state_before"),
                    "state_after": turn.get("state_after"),
                    "state_diff": turn.get("state_diff"),
                    "memory_before": before_memory,
                    "memory_after": after_memory,
                    "memory_events": _turn_events(
                        event_values[before_event_count:],
                        turn_id=brain_turn_id,
                        model_call_count=len(calls),
                    ),
                    "context_events": [
                        event
                        for event in event_values[before_event_count:]
                        if event.get("kind") == "context"
                        and str(event.get("payload", {}).get("turn_id", ""))
                        == brain_turn_id
                    ],
                    "model_execution_events": model_execution_events,
                    "model_calls": calls,
                    "journal_delta": after_journal[len(before_journal) :],
                    "persistence": _persistence_evidence(session),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "related_turns": [
                        outcome.model_dump(mode="json")
                        for outcome in session.elfie.turn_outcomes()
                        if str(outcome.turn_id) != brain_turn_id
                    ],
                    "status": "completed"
                    if turn.get("result", {}).get("success")
                    else "failed",
                }
                writer.append("events", event_values[event_cursor:])
                event_cursor = len(event_values)
                writer.append("turns", turn_payload)
                if turn_payload["status"] == "completed":
                    completed_turns += 1
                else:
                    failed_turns += 1
            except Exception as error:  # noqa: BLE001 - preserve partial traces
                failed_turns += 1
                model_execution_events = _model_execution_events_since(
                    model_events_before
                )
                for model_event in model_execution_events:
                    recorder.record(
                        "model_execution",
                        {"input_index": index, "event": model_event},
                    )
                recorder.record(
                    "collector_error",
                    {
                        "input_index": index,
                        "type": type(error).__name__,
                        "message": redact_text(str(error)),
                        "model_execution_events": model_execution_events,
                    },
                )
                event_values = recorder.events
                writer.append("events", event_values[event_cursor:])
                event_cursor = len(event_values)
                model_execution = session.last_model_execution
                writer.append(
                    "turns",
                    {
                        "schema_version": "brain-trace.turn.v1",
                        "input_index": index,
                        "turn_id": None,
                        "brain_turn_id": None,
                        "submitted_input": stimulus,
                        "session_turn": None,
                        "state_before": None,
                        "state_after": None,
                        "state_diff": None,
                        "memory_before": before_memory,
                        "memory_after": _memory_snapshot(session),
                        "memory_events": _turn_events(
                            recorder.events[before_event_count:],
                            turn_id="",
                            model_call_count=len(getattr(model_execution, "calls", ())),
                        ),
                        "context_events": [],
                        "model_execution_events": model_execution_events,
                        "model_calls": list(getattr(model_execution, "calls", ())),
                        "journal_delta": _journal_snapshot(session)[
                            len(before_journal) :
                        ],
                        "persistence": _persistence_evidence(session),
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000,
                            2,
                        ),
                        "related_turns": [],
                        "status": "failed",
                        "error": {
                            "type": type(error).__name__,
                            "message": redact_text(str(error)),
                        },
                    },
                )
        manifest["completed_turns"] = completed_turns
        manifest["failed_turns"] = failed_turns
        manifest["provenance"]["runtime_snapshot_sha256"] = _tree_digest(runtime_root)
        manifest["status"] = "completed" if failed_turns == 0 else "partial"
    except Exception as error:  # noqa: BLE001 - setup/runtime failure is an artifact
        fatal_error = f"{type(error).__name__}: {redact_text(str(error))}"
        manifest["status"] = "failed"
        manifest["error"] = fatal_error
        recorder.record(
            "collector_error",
            {
                "type": type(error).__name__,
                "message": redact_text(str(error)),
            },
        )
        event_values = recorder.events
        writer.append("events", event_values[event_cursor:])
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as error:  # noqa: BLE001 - retain final manifest
                manifest.setdefault("cleanup_errors", []).append(type(error).__name__)
            try:
                store = ElfieDiagnostics(session.elfie).memory.storage
                close_store = getattr(store, "close", None)
                if callable(close_store):
                    close_store()
            except Exception as error:  # noqa: BLE001 - retain final manifest
                manifest.setdefault("cleanup_errors", []).append(type(error).__name__)
        event_values = recorder.events
        if len(event_values) > event_cursor:
            writer.append("events", event_values[event_cursor:])
            event_cursor = len(event_values)
        if runtime_root.exists():
            manifest["provenance"]["runtime_snapshot_sha256"] = _tree_digest(
                runtime_root
            )
        manifest["event_count"] = event_cursor
        manifest["turn_count"] = completed_turns + failed_turns
        manifest["artifact_files"] = {
            name: {
                "sha256": _sha256_file(writer.root / name)
                if (writer.root / name).is_file()
                else None,
                "size_bytes": (writer.root / name).stat().st_size
                if (writer.root / name).is_file()
                else 0,
            }
            for name in ("events.jsonl", "turns.jsonl")
        }
        manifest["finished_at"] = utc_now()
        manifest["status"] = (
            "failed" if fatal_error else manifest.get("status", "partial")
        )
        writer.write_manifest(manifest)
    return BrainTraceRun(
        run_id=run_id,
        artifact_dir=artifact_dir,
        status=str(manifest["status"]),
        turns=completed_turns + failed_turns,
        failed_turns=failed_turns,
        error=fatal_error,
    )


__all__ = (
    "BrainTraceRun",
    "BrainTraceValidationError",
    "collect_brain_trace",
    "list_brain_trace_sources",
    "load_messages_file",
)
