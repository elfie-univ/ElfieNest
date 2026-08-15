from pathlib import Path
from unittest.mock import Mock

from app.features.configuration.providers import (
    StoredLocalProviderBinding,
    StoredLocalProviderProbe,
)
from infrastructure.models.ollama.lifecycle_ollama import OllamaLifecycleAdapter
from infrastructure.models.ollama.ollama_platform import OllamaProcessIdentity


def test_lifecycle_ollama_only_starts_an_unhealthy_existing_binding() -> None:
    technology = Mock()
    binding = StoredLocalProviderBinding(
        api_base="http://localhost:11434",
        platform="darwin",
        install_kind="existing-public",
        launch_target="/Applications/Ollama.app",
    )
    technology.default_binding.return_value = binding
    technology.probe.side_effect = (
        StoredLocalProviderProbe("unavailable", binding.api_base),
        StoredLocalProviderProbe("unavailable", binding.api_base),
    )
    adapter = OllamaLifecycleAdapter(technology)

    assert adapter.ready() is False
    adapter.prepare()

    technology.start.assert_called_once_with(binding)


def test_shared_owned_ollama_is_reused_until_the_last_holder_releases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: two Runtime roots share one directly manageable local service.
    binding = StoredLocalProviderBinding(
        api_base="http://127.0.0.1:11434",
        platform="linux",
        install_kind="binary",
        launch_target="/usr/local/bin/ollama",
    )
    holder_identity = OllamaProcessIdentity(501, "/usr/local/bin/python", "holder")
    owned_identity = OllamaProcessIdentity(900, "/usr/local/bin/ollama", "owned")
    live = {501: holder_identity}

    def current_identity(pid: int):
        return live.get(pid)

    monkeypatch.setattr(
        "infrastructure.models.ollama.lifecycle_ollama.process_identity",
        current_identity,
    )
    monkeypatch.setattr(
        "infrastructure.models.ollama.lifecycle_ollama.os.getpid",
        lambda: 501,
    )

    class Technology:
        def __init__(self) -> None:
            self.started = False
            self.start_calls = 0
            self.stop_calls = 0

        def default_binding(self):
            return binding

        def probe(self, _binding):
            return StoredLocalProviderProbe(
                "healthy" if self.started else "unavailable",
                binding.api_base,
            )

        def start_owned(self, _binding):
            self.started = True
            self.start_calls += 1
            live[owned_identity.pid] = owned_identity
            return owned_identity

        def stop_owned(self, _identity):
            self.stop_calls += 1
            self.started = False
            live.pop(owned_identity.pid, None)

    technology = Technology()
    first = OllamaLifecycleAdapter(technology, runtime_root=tmp_path / "shared").acquire(
        owner_id="cli-a", instance_id="one", generation=1
    )
    second = OllamaLifecycleAdapter(technology, runtime_root=tmp_path / "shared").acquire(
        owner_id="cli-b", instance_id="two", generation=1
    )

    # When: the first Core exits before the second.
    first.release()

    # Then: the shared service remains available until the final holder exits.
    assert first.origin == "ELFIENEST_OWNED"
    assert second.origin == "ELFIENEST_OWNED"
    assert technology.start_calls == 1
    assert technology.stop_calls == 0

    second.release()
    assert technology.stop_calls == 1


def test_healthy_preexisting_ollama_is_external_and_never_stopped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: Ollama was already healthy before ElfieNest requested a lease.
    binding = StoredLocalProviderBinding(
        api_base="http://127.0.0.1:11434",
        platform="linux",
        install_kind="binary",
        launch_target="/usr/local/bin/ollama",
    )
    holder = OllamaProcessIdentity(501, "/usr/local/bin/python", "holder")
    monkeypatch.setattr(
        "infrastructure.models.ollama.lifecycle_ollama.process_identity",
        lambda pid: holder if pid == 501 else None,
    )
    monkeypatch.setattr(
        "infrastructure.models.ollama.lifecycle_ollama.os.getpid",
        lambda: 501,
    )
    technology = Mock()
    technology.default_binding.return_value = binding
    technology.probe.return_value = StoredLocalProviderProbe("healthy", binding.api_base)

    lease = OllamaLifecycleAdapter(technology, runtime_root=tmp_path / "shared").acquire(
        owner_id="cli", instance_id="one", generation=1
    )

    assert lease.origin == "EXTERNAL"
    technology.start_owned.assert_not_called()
    lease.release()
    technology.stop_owned.assert_not_called()


def test_unconfigured_data_root_does_not_start_default_ollama(
    tmp_path: Path,
) -> None:
    binding = StoredLocalProviderBinding(
        api_base="http://127.0.0.1:11434",
        platform="linux",
        install_kind="existing-public",
        launch_target="/usr/local/bin/ollama",
    )
    technology = Mock()
    technology.default_binding.return_value = binding
    technology.probe.return_value = StoredLocalProviderProbe(
        "unavailable", binding.api_base
    )
    adapter = OllamaLifecycleAdapter(
        technology,
        runtime_root=tmp_path / "shared",
        binding_loader=lambda _home: None,
    )

    lease = adapter.acquire(
        owner_id="core",
        instance_id="one",
        generation=1,
        elfie_home=tmp_path / "data",
    )

    assert lease is None
    technology.start_owned.assert_not_called()
