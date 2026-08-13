"""Shared test composition for the injected ModelExecutionAgent capabilities."""

import os

from infrastructure.models.model_execution_ports import ModelExecutionAgentPorts
from infrastructure.persistence.food_evidence import query_model_evidence
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository


def model_execution_agent_ports() -> ModelExecutionAgentPorts:
    """Use the production tool composition without creating a user data DB."""
    from app.bootstrap.system_wiring.model_execution import (
        build_model_execution_agent_ports,
    )

    report_writer = (
        ReportStorageAdapter(ReportRepository())
        if os.environ.get("ELFIE_HOME")
        else None
    )
    return build_model_execution_agent_ports(
        model_evidence_source=query_model_evidence,
        report_writer=report_writer,
    )


__all__ = ("model_execution_agent_ports",)
