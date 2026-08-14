"""Stable public facade for Adoption."""

from .errors import (
    AdoptionCandidateNotAccepted,
    AdoptionCandidateSetExpired,
    AdoptionCapacityReached,
    AdoptionError,
    AdoptionInvalid,
    AdoptionOwnerNotFound,
    AdoptionUnavailable,
)
from .facade import AdoptionService
from .models import (
    AcceptedAdoptionReservation,
    AdoptionOptionsResult,
    AdoptionQuota,
    AdoptionSpecies,
    CandidateAppearance,
    CandidateRepliesResult,
    CandidateReplyResult,
    CandidateResult,
    CandidateSetResult,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    ReplyToCandidatesCommand,
    ReserveAcceptedAdoptionCommand,
    SpeciesId,
)
from .port_models import (
    AdoptionPolicyRecord,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
)
from .ports import (
    AdoptionPersistencePort,
    AdoptionPolicyPort,
    AdoptionPortCapacityReached,
    AdoptionPortError,
    AdoptionPortOwnerNotFound,
)

__all__ = (
    "AcceptedAdoptionReservation",
    "AdoptionSpecies",
    "AdoptionCandidateNotAccepted",
    "AdoptionCandidateSetExpired",
    "AdoptionCapacityReached",
    "AdoptionError",
    "AdoptionInvalid",
    "AdoptionOptionsResult",
    "AdoptionOwnerNotFound",
    "AdoptionPersistencePort",
    "AdoptionPolicyPort",
    "AdoptionPolicyRecord",
    "AdoptionPortCapacityReached",
    "AdoptionPortError",
    "AdoptionPortOwnerNotFound",
    "AdoptionQuota",
    "AdoptionQuotaRecord",
    "AdoptionReservationRecord",
    "AdoptionService",
    "AdoptionUnavailable",
    "CandidateAppearance",
    "CandidateRepliesResult",
    "CandidateReplyResult",
    "CandidateResult",
    "CandidateSetResult",
    "CreateCandidateSetCommand",
    "GetAdoptionOptionsQuery",
    "ReplyToCandidatesCommand",
    "ReserveAcceptedAdoptionCommand",
    "SpeciesId",
)
