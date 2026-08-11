"""Shared test composition for the injected RuntimeAgent capabilities."""

from infrastructure.models.runtime_ports import RuntimeAgentPorts


def runtime_agent_ports() -> RuntimeAgentPorts:
    """Use the production Bootstrap wiring in RuntimeAgent-focused tests."""
    from app.bootstrap.system_wiring.runtime import build_runtime_agent_ports

    return build_runtime_agent_ports()


__all__ = ("runtime_agent_ports",)
