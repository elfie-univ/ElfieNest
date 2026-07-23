"""Elfie Lab 进程内会话所有权与查找。"""

from __future__ import annotations

from threading import Lock
from typing import Callable, Dict, TypeVar

from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage

ResultT = TypeVar("ResultT")


class SessionBusyError(RuntimeError):
    __slots__ = ("elfie_id",)

    def __init__(self, elfie_id: str) -> None:
        super().__init__(elfie_id)
        self.elfie_id = elfie_id

    def __str__(self) -> str:
        return f"精灵正在执行调试回合，暂时不能删除: {self.elfie_id}"


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

    def remove(self, elfie_id: str, remove_data: Callable[[], ResultT]) -> ResultT:
        """Remove an idle session and its data without allowing a concurrent get."""
        with self._lock:
            session = self._sessions.get(elfie_id)
            if session is not None and not session.close_if_idle():
                raise SessionBusyError(elfie_id)
            self._sessions.pop(elfie_id, None)
            return remove_data()

    def reload(
        self,
        elfie_id: str,
        update_data: Callable[[], Callable[[], None]],
    ) -> ElfieLabSession:
        """在精灵空闲时更新稳定档案并重建唯一会话实例。"""
        with self._lock:
            session = self._sessions.get(elfie_id)

            def create_replacement() -> ElfieLabSession:
                return ElfieLabSession(
                    self.storage.get_elfie(elfie_id),
                    self.storage,
                    self.runtime_config_dir,
                )

            if session is not None:
                replacement = session.replace_if_idle(update_data, create_replacement)
                if replacement is None:
                    raise SessionBusyError(elfie_id)
            else:
                rollback = update_data()
                replacement_created = False
                try:
                    replacement = create_replacement()
                    replacement_created = True
                finally:
                    if not replacement_created:
                        rollback()
            self._sessions[elfie_id] = replacement
            return replacement

    def close(self) -> None:
        """Close every session created by this registry exactly once."""
        with self._lock:
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()
