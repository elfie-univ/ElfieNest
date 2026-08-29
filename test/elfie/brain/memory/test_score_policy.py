from elfie.brain.memory.score_policy import MemoryScorePolicy


def test_supporting_evidence_increases_importance_and_confidence() -> None:
    update = MemoryScorePolicy.evidence_update(
        confidence=0.5,
        importance=0.4,
        stance="supports",
    )

    assert update.confidence > 0.5
    assert update.importance > 0.4
    assert update.confidence <= 1.0
    assert update.importance <= 1.0


def test_contradiction_lowers_confidence_but_keeps_importance() -> None:
    update = MemoryScorePolicy.evidence_update(
        confidence=0.8,
        importance=0.7,
        stance="contradicts",
    )

    assert update.confidence < 0.8
    assert update.importance == 0.7


def test_context_evidence_does_not_change_semantic_scores() -> None:
    update = MemoryScorePolicy.evidence_update(
        confidence=0.8,
        importance=0.7,
        stance="context",
    )

    assert update.confidence == 0.8
    assert update.importance == 0.7
