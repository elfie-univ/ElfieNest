from __future__ import annotations

import pytest

from app.orchestration.embodiment.state_machine import (
    EmbodimentState,
    EmbodimentTransitionError,
)


def test_state_machine_accepts_the_existing_nest_host_return_path() -> None:
    state = EmbodimentState.AT_NEST
    state = state.transition_to(EmbodimentState.SWITCHING_TO_HOSTED)
    state = state.transition_to(EmbodimentState.HOSTED)
    state = state.transition_to(EmbodimentState.RETURNING_TO_NEST)
    state = state.transition_to(EmbodimentState.AT_NEST)

    assert state is EmbodimentState.AT_NEST


def test_state_machine_rejects_skipped_transition() -> None:
    with pytest.raises(EmbodimentTransitionError):
        EmbodimentState.AT_NEST.transition_to(EmbodimentState.HOSTED)


def test_offline_state_can_only_recover_to_nest() -> None:
    state = EmbodimentState.HOSTED.transition_to(EmbodimentState.OFFLINE)

    assert state.transition_to(EmbodimentState.AT_NEST) is EmbodimentState.AT_NEST
