"""Shared test composition for the injected RuntimeAgent capabilities."""

import os

from infrastructure.models.runtime_ports import RuntimeAgentPorts
from infrastructure.persistence.food_evidence import query_model_evidence
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository


def runtime_agent_ports() -> RuntimeAgentPorts:
    """Use the production tool composition without creating a user data DB."""
    from app.bootstrap.system_wiring.runtime import build_runtime_agent_ports

    report_writer = (
        ReportStorageAdapter(ReportRepository())
        if os.environ.get("ELFIE_HOME")
        else None
    )
    return build_runtime_agent_ports(
        model_evidence_source=query_model_evidence,
        report_writer=report_writer,
    )


__all__ = ("runtime_agent_ports",)
