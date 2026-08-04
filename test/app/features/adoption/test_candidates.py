from __future__ import annotations

from pathlib import Path

from app.features.adoption.candidates import (
    create_candidate_set,
    find_candidate,
    reply_to_candidates,
)
from app.infrastructure.persistence.store import get_db, init_db


def _user(db_path: str) -> int:
    with get_db(db_path) as connection:
        user_id = int(connection.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES ('candidate-owner', 'unused', 'owner')",
        ).lastrowid)
        connection.commit()
    return user_id


def test_candidate_set_contains_five_immutable_snapshots(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    user_id = _user(db_path)
    snapshot = create_candidate_set(
        user_id=user_id,
        species_id="fox",
        life_stage="young_adult",
        gender="any",
        appearance={"stature": "tall", "build": "round", "face": "soft", "signature": "warm"},
        answers=["quiet", "research", "plan", "discuss", "steady"],
        db_path=db_path,
    )

    assert len(snapshot.candidates) == 5
    first = snapshot.candidates[0]
    assert first.species_id == "fox"
    assert first.height == "tall"
    assert first.build == "plump"
    assert first.appearance_seed != snapshot.candidates[1].appearance_seed
    assert find_candidate(snapshot.candidate_set_id, user_id=user_id, candidate_id=first.candidate_id) == first


def test_replies_keep_selected_candidate_ids_and_always_offer_one_acceptance(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    user_id = _user(db_path)
    snapshot = create_candidate_set(
        user_id=user_id,
        species_id="dog",
        life_stage="any",
        gender="any",
        appearance={},
        answers=["any"] * 5,
        db_path=db_path,
    )
    ids = [snapshot.candidates[0].candidate_id, snapshot.candidates[1].candidate_id]
    replies = reply_to_candidates(snapshot.candidate_set_id, user_id=user_id, candidate_ids=ids)

    assert [reply["candidate_id"] for reply in replies] == ids
    assert replies[0]["status"] == "accepted"
