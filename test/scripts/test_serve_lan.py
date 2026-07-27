from scripts.serve import prepare_godot_web_runtime, service_host


def test_service_host_binds_loopback_unless_lan_is_explicit() -> None:
    # Given: the developer CLI defaults and its explicit LAN option.
    # When: each mode resolves a bind host.
    # Then: only LAN chooses all IPv4 interfaces.
    assert service_host(lan=False) == "127.0.0.1"
    assert service_host(lan=True) == "0.0.0.0"


def test_prepare_godot_web_runtime_uses_ensure_for_development() -> None:
    # Given: a development launch and a successful exporter process.
    commands: list[list[str]] = []

    class Result:
        returncode = 0

    def run(command: list[str]) -> Result:
        commands.append(command)
        return Result()

    # When: preparation runs.
    # Then: it requests an incremental ensure build.
    assert prepare_godot_web_runtime("development", run) is True
    assert commands[0][-1] == "--ensure"


def test_prepare_godot_web_runtime_checks_only_in_release() -> None:
    # Given: a release launch with a missing staged bundle.
    commands: list[list[str]] = []

    class Result:
        returncode = 1

    def run(command: list[str]) -> Result:
        commands.append(command)
        return Result()

    # When: preparation runs.
    # Then: it only validates the staged runtime and fails closed.
    assert prepare_godot_web_runtime("release", run) is False
    assert commands[0][-1] == "--check"


def test_frozen_release_core_does_not_try_to_reexecute_the_godot_build_script() -> None:
    # Given: an installed Core whose staged Godot resources have already passed package validation.
    class Result:
        returncode = 1

    def run(_command: list[str]) -> Result:
        raise AssertionError("the frozen Core must not run build_godot_web.py")

    # When: the installed release runtime starts.
    # Then: it trusts the already-validated staged bundle instead of treating itself as Python.
    assert prepare_godot_web_runtime("release", run, is_frozen=True) is True
