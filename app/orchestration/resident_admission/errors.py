"""Stable errors raised by the Resident Admission workflow."""


class ResidentAdmissionError(Exception):
    """Base class for live admission failures."""


class ResidentAdmissionUnavailable(ResidentAdmissionError):
    """The accepted adoption could not be constructed or admitted."""


class ResidentAdmissionCompensationFailed(ResidentAdmissionUnavailable):
    """At least one existing compensation action could not complete."""


__all__ = (
    "ResidentAdmissionCompensationFailed",
    "ResidentAdmissionError",
    "ResidentAdmissionUnavailable",
)
