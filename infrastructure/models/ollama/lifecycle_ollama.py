"""Lifecycle ownership for the shared local Ollama service."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Mapping, Optional

from app.features.configuration.providers import (
    ProviderLocalTechnologyPort,
    ProviderPortError,
    StoredLocalProviderBinding,
)
from app.orchestration.lifecycle.ports import ProcessIdentityReaderPort
from infrastructure.models.ollama.ollama_platform import (
    OllamaProcessIdentity,
)

if os.name == "nt":
    import msvcrt
else:
    import fcntl


OllamaLeaseOrigin = Literal["EXTERNAL", "ELFIENEST_OWNED"]
_SCHEMA_VERSION = 1
_STATE_FILENAME = "services.json"
_LOCK_FILENAME = "services.lock"
BindingLoader = Callable[[Path], Optional[StoredLocalProviderBinding]]


class OllamaLeaseError(ProviderPortError):
    """The shared Ollama lease could not be reconciled safely."""


class OllamaRuntimeLease:
    """One generation's reference to a shared Ollama service."""

    def __init__(
        self,
        *,
        origin: OllamaLeaseOrigin,
        service_key: str,
        release_callback: Callable[[], None],
    ) -> None:
        self.origin = origin
        self.service_key = service_key
        self._release_callback = release_callback
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._release_callback()

    def __enter__(self) -> OllamaRuntimeLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class OllamaLifecycleAdapter:
    """Coordinate the two allowed Ollama origins across Runtime data roots.

    The state is user-scoped rather than data-root-scoped. A healthy service
    observed before an ElfieNest lease is acquired is recorded as ``EXTERNAL``;
    only a process with exact PID, executable and birth identity evidence may
    be recorded as ``ELFIENEST_OWNED`` or stopped.
    """

    def __init__(
        self,
        technology: ProviderLocalTechnologyPort,
        *,
        process_identity_reader: ProcessIdentityReaderPort,
        runtime_root: Optional[Path] = None,
        binding_loader: Optional[BindingLoader] = None,
    ) -> None:
        self._technology = technology
        self._process_identity_reader = process_identity_reader
        self._runtime_root = runtime_root
        self._binding_loader = binding_loader

    def ready(self) -> bool:
        try:
            binding = self._technology.default_binding()
            return self._technology.probe(binding).state == "healthy"
        except ProviderPortError:
            return False

    def prepare(self) -> None:
        """Best-effort compatibility path for explicit Provider preparation."""
        try:
            binding = self._technology.default_binding()
            if self._technology.probe(binding).state != "healthy":
                self._technology.start(binding)
        except ProviderPortError:
            return

    def reconcile_orphaned_services(
        self, *, elfie_home: Optional[Path] = None
    ) -> tuple[str, ...]:
        """Converge owned services whose Runtime holders all disappeared.

        This is deliberately a Doctor-only repair surface.  External Ollama
        processes are never stopped, and an owned receipt with a changed PID
        birth identity is demoted or discarded rather than signalled.
        """
        if self._binding_loader is not None:
            if elfie_home is None:
                return ()
            try:
                if self._binding_loader(elfie_home) is None:
                    return ()
            except (OSError, ProviderPortError, RuntimeError, ValueError) as error:
                raise OllamaLeaseError(f"无法读取本地 Ollama 配置: {error}") from error
        repaired: list[str] = []
        dirty = False
        with self._locked_state() as (state_path, services):
            for service_key, raw_state in tuple(services.items()):
                if raw_state.get("origin") != "ELFIENEST_OWNED":
                    continue
                state = self._prune_holders(raw_state)
                if state.get("holders"):
                    if state != raw_state:
                        services[service_key] = state
                        dirty = True
                    continue

                identity = _state_process_identity(state)
                if identity is None or not self._identity_is_current(identity):
                    if self._probe_state(state) == "healthy":
                        services[service_key] = _external_state(state)
                        repaired.append(
                            f"preserved external Ollama at {state.get('endpoint', service_key)}"
                        )
                    else:
                        services.pop(service_key, None)
                        repaired.append(f"removed stale Ollama ownership {service_key}")
                    dirty = True
                    continue

                stopper = getattr(self._technology, "stop_owned", None)
                if not callable(stopper):
                    raise OllamaLeaseError(
                        "当前 Ollama Adapter 无法安全回收 orphaned owned 进程"
                    )
                try:
                    stopper(identity)
                except (
                    ProviderPortError,
                    OSError,
                    RuntimeError,
                    TimeoutError,
                    ValueError,
                ) as error:
                    raise OllamaLeaseError(str(error)) from error
                services.pop(service_key, None)
                repaired.append(f"stopped orphaned owned Ollama {service_key}")
                dirty = True

            if dirty:
                _write_services(state_path, services)
        return tuple(repaired)

    def acquire(
        self,
        *,
        owner_id: str,
        instance_id: str,
        generation: int,
        elfie_home: Optional[Path] = None,
    ) -> Optional[OllamaRuntimeLease]:
        """Acquire one generation holder without creating a third ownership mode."""
        if not owner_id or not instance_id or generation < 1:
            raise ValueError("Ollama lease identity is incomplete")
        binding, may_start = self._binding_for(elfie_home)
        service_key = _service_key(binding.api_base)
        if not may_start and self._technology.probe(binding).state != "healthy":
            return None
        holder_identity = self._read_identity(os.getpid())
        if holder_identity is None:
            if may_start:
                raise OllamaLeaseError("无法取得 Core holder 的精确进程身份")
            holder_id = f"{instance_id}:{generation}:external"
        else:
            holder_id = _holder_id(owner_id, instance_id, generation, holder_identity)
        with self._locked_state() as (state_path, services):
            state = services.get(service_key)
            if state is not None:
                state = self._prune_holders(state)
                origin = state.get("origin")
                if origin == "ELFIENEST_OWNED":
                    if holder_identity is None:
                        raise OllamaLeaseError(
                            "无法取得当前 Core holder 的精确进程身份"
                        )
                    owned_identity = _state_process_identity(state)
                    if owned_identity is not None and self._identity_is_current(
                        owned_identity
                    ):
                        state["holders"] = _add_holder(
                            state.get("holders"),
                            holder_id,
                            owner_id,
                            instance_id,
                            generation,
                            holder_identity,
                        )
                        services[service_key] = state
                        _write_services(state_path, services)
                        return self._lease(
                            "ELFIENEST_OWNED",
                            service_key,
                            holder_id,
                        )
                    if self._probe_state(state) == "healthy":
                        services[service_key] = _external_state(state)
                        _write_services(state_path, services)
                        return self._lease("EXTERNAL", service_key, holder_id)
                    services.pop(service_key, None)
                elif origin == "EXTERNAL":
                    if self._probe_state(state) == "healthy":
                        _write_services(state_path, services)
                        return self._lease("EXTERNAL", service_key, holder_id)
                    services.pop(service_key, None)
                else:
                    raise OllamaLeaseError("未知的 Ollama ownership origin")

            if self._technology.probe(binding).state == "healthy":
                services[service_key] = _external_state(_binding_state(binding))
                _write_services(state_path, services)
                return self._lease("EXTERNAL", service_key, holder_id)

            if holder_identity is None:
                raise OllamaLeaseError("无法取得当前 Core holder 的精确进程身份")
            process = self._start_owned(binding)
            state = _binding_state(binding)
            state.update(
                {
                    "origin": "ELFIENEST_OWNED",
                    "process": _process_state(process),
                    "holders": _add_holder(
                        {},
                        holder_id,
                        owner_id,
                        instance_id,
                        generation,
                        holder_identity,
                    ),
                }
            )
            services[service_key] = state
            _write_services(state_path, services)
            return self._lease("ELFIENEST_OWNED", service_key, holder_id)

    def _binding_for(
        self, elfie_home: Optional[Path]
    ) -> tuple[StoredLocalProviderBinding, bool]:
        """Resolve the configured binding and whether this Runtime may start it."""
        if self._binding_loader is None:
            return self._technology.default_binding(), True
        configured = None
        if elfie_home is not None:
            try:
                configured = self._binding_loader(elfie_home)
            except (OSError, ProviderPortError, RuntimeError, ValueError) as error:
                raise OllamaLeaseError(f"无法读取本地 Ollama 配置: {error}") from error
        if configured is not None:
            return configured, True
        # No local Ollama was configured for this data root. We may recognize
        # an already healthy default service as EXTERNAL, but never start one.
        return self._technology.default_binding(), False

    def _start_owned(
        self, binding: StoredLocalProviderBinding
    ) -> OllamaProcessIdentity:
        starter = getattr(self._technology, "start_owned", None)
        if not callable(starter):
            raise OllamaLeaseError("当前 Ollama Adapter 无法证明启动进程的所有权")
        try:
            process = starter(binding)
        except ProviderPortError:
            raise
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            raise OllamaLeaseError(str(error)) from error
        if not isinstance(process, OllamaProcessIdentity):
            raise OllamaLeaseError("Ollama 启动未返回精确进程身份")
        if not self._identity_is_current(process):
            raise OllamaLeaseError("Ollama 启动进程身份校验失败")
        return process

    def _probe_state(self, state: Mapping[str, Any]) -> str:
        try:
            return self._technology.probe(_binding_from_state(state)).state
        except (ProviderPortError, KeyError, TypeError, ValueError):
            return "unavailable"

    def _lease(
        self,
        origin: OllamaLeaseOrigin,
        service_key: str,
        holder_id: str,
    ) -> OllamaRuntimeLease:
        return OllamaRuntimeLease(
            origin=origin,
            service_key=service_key,
            release_callback=lambda: self._release(service_key, holder_id),
        )

    def _release(self, service_key: str, holder_id: str) -> None:
        with self._locked_state() as (state_path, services):
            state = services.get(service_key)
            if state is None or state.get("origin") != "ELFIENEST_OWNED":
                return
            holders = state.get("holders")
            if not isinstance(holders, dict) or holder_id not in holders:
                return
            holders.pop(holder_id, None)
            state["holders"] = holders
            if holders:
                services[service_key] = state
                _write_services(state_path, services)
                return

            owned_identity = _state_process_identity(state)
            if owned_identity is None or not self._identity_is_current(owned_identity):
                if self._probe_state(state) == "healthy":
                    services[service_key] = _external_state(state)
                else:
                    services.pop(service_key, None)
                _write_services(state_path, services)
                return

            stopper = getattr(self._technology, "stop_owned", None)
            if not callable(stopper):
                _write_services(state_path, services)
                raise OllamaLeaseError("当前 Ollama Adapter 无法安全释放 owned 进程")
            try:
                stopper(owned_identity)
            except (
                ProviderPortError,
                OSError,
                RuntimeError,
                TimeoutError,
                ValueError,
            ) as error:
                _write_services(state_path, services)
                raise OllamaLeaseError(str(error)) from error
            services.pop(service_key, None)
            _write_services(state_path, services)

    def _read_identity(self, pid: int) -> OllamaProcessIdentity | None:
        evidence = self._process_identity_reader.read(pid)
        if evidence is None:
            return None
        return OllamaProcessIdentity(
            evidence.pid,
            evidence.executable,
            evidence.birth_identity,
        )

    def _identity_is_current(self, identity: OllamaProcessIdentity) -> bool:
        current = self._read_identity(identity.pid)
        return current is not None and current == identity

    def _prune_holders(self, state: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(state)
        raw_holders = state.get("holders")
        holders: dict[str, dict[str, Any]] = {}
        if isinstance(raw_holders, Mapping):
            for key, raw in raw_holders.items():
                if not isinstance(key, str) or not isinstance(raw, Mapping):
                    continue
                identity = _state_process_identity({"process": raw})
                if identity is not None and self._identity_is_current(identity):
                    holders[key] = dict(raw)
        result["holders"] = holders
        return result

    @contextmanager
    def _locked_state(self) -> Iterator[tuple[Path, dict[str, dict[str, Any]]]]:
        root = self._state_root()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                root.chmod(0o700)
            except PermissionError:
                # Some macOS sandboxes deny chmod on an already private
                # directory.  Preserve the security invariant: continue only
                # when the existing mode is already private to this user.
                try:
                    mode = root.stat().st_mode & 0o777
                except OSError:
                    raise
                if mode & 0o077:
                    raise
        lock_path = root / _LOCK_FILENAME
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            _lock_descriptor(descriptor)
            state_path = root / _STATE_FILENAME
            yield state_path, _read_services(state_path)
        finally:
            _unlock_descriptor(descriptor)
            os.close(descriptor)

    def _state_root(self) -> Path:
        if self._runtime_root is not None:
            return self._runtime_root.expanduser().resolve()
        configured = os.environ.get("ELFIENEST_OLLAMA_RUNTIME_HOME")
        if configured:
            return Path(configured).expanduser().resolve()
        return (Path.home() / ".elfienest" / "runtime" / "ollama").resolve()


def _service_key(endpoint: str) -> str:
    return f"ollama:{endpoint.rstrip('/').lower()}"


def _holder_id(
    owner_id: str,
    instance_id: str,
    generation: int,
    identity: OllamaProcessIdentity,
) -> str:
    return f"{instance_id}:{generation}:{identity.pid}:{owner_id}"


def _binding_state(binding: StoredLocalProviderBinding) -> dict[str, Any]:
    return {
        "origin": "EXTERNAL",
        "endpoint": binding.api_base,
        "platform": binding.platform,
        "install_kind": binding.install_kind,
        "launch_target": binding.launch_target,
        "version": binding.version,
        "installer_source_url": binding.installer_source_url,
        "installer_sha256": binding.installer_sha256,
        "holders": {},
    }


def _external_state(state: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(state)
    result["origin"] = "EXTERNAL"
    result["process"] = None
    result["holders"] = {}
    return result


def _process_state(identity: OllamaProcessIdentity) -> dict[str, Any]:
    return {
        "pid": identity.pid,
        "executable": identity.executable,
        "birth_identity": identity.birth_identity,
    }


def _state_process_identity(state: Mapping[str, Any]) -> OllamaProcessIdentity | None:
    raw = state.get("process")
    if not isinstance(raw, Mapping):
        return None
    pid = raw.get("pid")
    executable = raw.get("executable")
    birth_identity = raw.get("birth_identity")
    if (
        not isinstance(pid, int)
        or pid <= 0
        or not isinstance(executable, str)
        or not executable
        or not isinstance(birth_identity, str)
        or not birth_identity
    ):
        return None
    return OllamaProcessIdentity(pid, executable, birth_identity)


def _add_holder(
    raw_holders: object,
    holder_id: str,
    owner_id: str,
    instance_id: str,
    generation: int,
    identity: OllamaProcessIdentity,
) -> dict[str, dict[str, Any]]:
    holders = dict(raw_holders) if isinstance(raw_holders, Mapping) else {}
    holders[holder_id] = {
        "owner_id": owner_id,
        "instance_id": instance_id,
        "generation": generation,
        "pid": identity.pid,
        "executable": identity.executable,
        "birth_identity": identity.birth_identity,
    }
    return holders


def _binding_from_state(state: Mapping[str, Any]) -> StoredLocalProviderBinding:
    return StoredLocalProviderBinding(
        api_base=_required_string(state, "endpoint"),
        platform=_required_string(state, "platform"),  # type: ignore[arg-type]
        install_kind=_required_string(state, "install_kind"),
        launch_target=_required_string(state, "launch_target"),
        version=str(state.get("version", "")),
        installer_source_url=str(state.get("installer_source_url", "")),
        installer_sha256=str(state.get("installer_sha256", "")),
    )


def _required_string(state: Mapping[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Ollama lease field {key!r} is invalid")
    return value


def _read_services(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OllamaLeaseError(f"Ollama lease state is unreadable: {error}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _SCHEMA_VERSION
    ):
        raise OllamaLeaseError("Ollama lease state schema is invalid")
    services = payload.get("services", {})
    if not isinstance(services, dict):
        raise OllamaLeaseError("Ollama lease services are invalid")
    return {
        str(key): dict(value)
        for key, value in services.items()
        if isinstance(key, str) and isinstance(value, dict)
    }


def _write_services(path: Path, services: Mapping[str, Mapping[str, Any]]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".services.", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
            json.dump(
                {"schema_version": _SCHEMA_VERSION, "services": services},
                receipt,
                ensure_ascii=False,
                sort_keys=True,
            )
            receipt.write("\n")
        temporary_path.replace(path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def _lock_descriptor(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        getattr(msvcrt, "locking")(  # noqa: B009
            descriptor,
            getattr(msvcrt, "LK_LOCK"),  # noqa: B009
            1,  # noqa: B009
        )
        return
    fcntl.flock(descriptor, fcntl.LOCK_EX)


def _unlock_descriptor(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        getattr(msvcrt, "locking")(  # noqa: B009
            descriptor,
            getattr(msvcrt, "LK_UNLCK"),  # noqa: B009
            1,  # noqa: B009
        )
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)


__all__ = (
    "OllamaLeaseError",
    "OllamaLeaseOrigin",
    "OllamaLifecycleAdapter",
    "OllamaRuntimeLease",
)
