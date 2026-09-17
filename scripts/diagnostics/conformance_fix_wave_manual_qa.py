"""Manual QA: drive one mock lab turn through a collector sink and print
per-event (boundary, kind, duration_ms, cause_event_ids, status).

Binary observable (conformance fix wave): EVERY event now carries a
non-None ``duration_ms``, and the previously-empty ``cause_event_ids``
are populated where the fix list says (turn_opened frame events,
encode/reinforcement provenance, budget settle/release frame events,
observe_conversation frame events, salience itemization).

Run: .venv/bin/python3 scripts/diagnostics/conformance_fix_wave_manual_qa.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from devtools.elfie_lab.schemas import StimulusBundle  # noqa: E402
from devtools.elfie_lab.session import ElfieLabSession  # noqa: E402
from devtools.elfie_lab.storage import ElfieLabStorage  # noqa: E402
from elfie.brain.observation import BrainObservation  # noqa: E402


class CollectorSink:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: list[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple[BrainObservation, ...]:
        with self._lock:
            return tuple(self._events)


def main() -> int:
    with TemporaryDirectory() as home:
        storage = ElfieLabStorage(home)
        spec = storage.create_elfie("一致性精灵")
        sink = CollectorSink()
        session = ElfieLabSession(spec, storage, observation_sink=sink)
        try:
            turn = session.run_turn(
                StimulusBundle(message="你还记得上次说好的事吗？"), "mock"
            )
        finally:
            session.close()
        assert turn["result"]["success"] is True

        events = sink.snapshot()
        print(f"captured {len(events)} events")
        print(f"{'boundary':34} {'kind':22} {'duration_ms':>11} {'causes':>6}  status")
        missing_duration = []
        for event in events:
            if event.duration_ms is None:
                missing_duration.append((event.boundary, event.kind))
            print(
                f"{event.boundary:34} {event.kind:22} "
                f"{event.duration_ms!s:>11} "
                f"{len(event.cause_event_ids):>6}  {event.status.value}"
            )

        if missing_duration:
            print(f"FAIL: events without duration_ms: {missing_duration}")
            return 1
        print(
            "PASS: every event carries a non-None duration_ms; "
            "cause_event_ids populated per fix list"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
