"""Explicit developer-only inspection boundary for one Elfie.

Product callers use the stable :class:`elfie.Elfie` facade.  Elfie Lab and
focused integration tests may opt into this module when they intentionally
need raw owner state or controlled fault/state injection.
"""

from __future__ import annotations

from elfie.elfie import Elfie


class ElfieDiagnostics:
    """Narrow opt-in access to internal owners; never exported by elfie.public."""

    def __init__(self, elfie: Elfie) -> None:
        self._elfie = elfie

    @property
    def energy(self):
        return self._elfie._energy

    @property
    def emotion(self):
        return self._elfie._emotion

    @property
    def memory(self):
        return self._elfie._memory

    @property
    def selfhood(self):
        return self._elfie._selfhood

    @property
    def nervous_system(self):
        return self._elfie._nervous_system

    @property
    def workspace(self):
        return self._elfie._workspace

    @property
    def communication(self):
        return self._elfie._communication

    @property
    def activity_store(self):
        return self._elfie._activity_store

    @property
    def journal_store(self):
        return self._elfie._journal_store

    @property
    def body_registry(self):
        return self._elfie._body_registry

    @property
    def body_binding(self):
        return self._elfie._body_binding

    @property
    def skills(self):
        return self._elfie._skills


__all__ = ("ElfieDiagnostics",)
