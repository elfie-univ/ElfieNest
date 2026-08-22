from __future__ import annotations

from devtools.brain_eval.gates import evaluate_p0_gates
from devtools.brain_eval.projection import episode_from_lab_turn_records


def test_lab_projection_uses_typed_decisions_and_receipts_not_model_claims() -> None:
    records = (
        {
            "turn_id": "turn-1",
            "stimulus_bundle": {"source_domain": "communication"},
            "trace": {
                "stages": {
                    "turn_boundary": {
                        "source_domain": "communication",
                        "interaction_scope": {
                            "channel_id": "elfie-lab",
                            "conversation_id": "conversation-owner",
                        },
                    },
                    "output_receipts": [
                        {
                            "receipt_id": "receipt-1",
                            "intent_id": "message-1",
                            "executor": "communication",
                            "status": "completed",
                        }
                    ],
                }
            },
            "decision": {
                "message_texts": ["我记得你喜欢蓝莓派。"],
                "spoken_texts": [],
                "message_intents": [
                    {
                        "intent_id": "message-1",
                        "conversation_id": "conversation-owner",
                        "status": "completed",
                    }
                ],
                "speech_intents": [],
                "motion_intents": [],
                "expression_intents": [],
            },
            "result": {"success": True},
            "model_call": {
                "food_key": "mock",
                "provider": "mock",
                "model": "elfie-mock",
                "output_tokens": 12,
                "input_tokens": 30,
            },
            "duration_ms": 25.0,
        },
    )

    episode = episode_from_lab_turn_records(
        candidate_id="candidate",
        candidate_spec_sha256="d" * 64,
        scenario_family_id="q3-memory-precision",
        scenario_version="1.0.0",
        variant_id="favorite-food",
        fixture_id="anchor-elfie",
        seed=3,
        hidden=False,
        records=records,
    )

    assert episode.execution_success is True
    assert episode.candidate_spec_sha256 == "d" * 64
    assert episode.scenario_verdict is None
    assert episode.turns[0].source_scope_id == "conversation-owner"
    assert episode.effects[0].receipt_id == "receipt-1"
    assert episode.public_outputs == ("我记得你喜欢蓝莓派。",)
    assert episode.resources.model_calls == 1
    assert episode.model_executions[0].provider == "mock"
    assert episode.model_executions[0].model_id == "elfie-mock"
    assert evaluate_p0_gates((episode,)) == ()
