"""Command and result models owned by Resident Admission."""

from dataclasses import dataclass

from app.features.adoption.models import SpeciesId


@dataclass(frozen=True)
class AdmitAcceptedAdoptionCommand:
    candidate_set_id: str
    candidate_id: str
    name: str


@dataclass(frozen=True)
class ResidentAdmissionResult:
    elfie_id: str
    name: str
    species_id: SpeciesId


__all__ = ("AdmitAcceptedAdoptionCommand", "ResidentAdmissionResult")
