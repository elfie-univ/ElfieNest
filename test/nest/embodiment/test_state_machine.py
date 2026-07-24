"""Persistent embodiment state vocabulary is independent from body transports."""

from __future__ import annotations

import pytest

from nest.embodiment.state_machine import EmbodimentState, EmbodimentTransitionError


def test_hosted_round_trip_uses_only_the_declared_states() -> None:
    state = EmbodimentState.AT_NEST

    state = state.transition_to(EmbodimentState.SWITCHING_TO_HOSTED)
    state = state.transition_to(EmbodimentState.HOSTED)
    state = state.transition_to(EmbodimentState.RETURNING_TO_NEST)
    state = state.transition_to(EmbodimentState.AT_NEST)

    assert state is EmbodimentState.AT_NEST


def test_invalid_transition_is_rejected_instead_of_creating_a_second_body() -> None:
    with pytest.raises(EmbodimentTransitionError):
        EmbodimentState.AT_NEST.transition_to(EmbodimentState.HOSTED)


def test_any_active_transition_can_record_offline_and_recover_to_nest() -> None:
    state = EmbodimentState.HOSTED.transition_to(EmbodimentState.OFFLINE)

    assert state.transition_to(EmbodimentState.AT_NEST) is EmbodimentState.AT_NEST
