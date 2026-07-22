"""Elfie Lab 进程内会话所有权与查找。"""

from __future__ import annotations

from threading import Lock
from typing import Dict

from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage


class SessionRegistry:
    """Own lazily created sessions and close them at application shutdown."""

    def __init__(
        self,
        storage: ElfieLabStorage,
        runtime_config_dir: str | None = None,
    ) -> None:
        self.storage = storage
        self.runtime_config_dir = runtime_config_dir
        self._sessions: Dict[str, ElfieLabSession] = {}
        self._lock = Lock()

    def get(self, elfie_id: str) -> ElfieLabSession:
        with self._lock:
            if elfie_id not in self._sessions:
                self._sessions[elfie_id] = ElfieLabSession(
                    self.storage.get_elfie(elfie_id),
                    self.storage,
                    self.runtime_config_dir,
                )
            return self._sessions[elfie_id]

    def close(self) -> None:
        """Close every session created by this registry exactly once."""
        with self._lock:
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()
