"""Focused tests for the model-free multilingual first-pass detector."""

from __future__ import annotations

import pytest

from elfie.brain.emotion.detector import (
    EmotionDetector,
    NoEmotionDetectedError,
    UnsupportedEmotionModalityError,
)
from elfie.brain.emotion.detector.text_detector import TextEmotionDetector
from elfie.brain.emotion.emotion_types import EmotionType


@pytest.mark.parametrize(
    ("text", "emotion", "language"),
    (
        ("I am furious about this", EmotionType.ANGER, "en"),
        ("I'm not happy with the result", EmotionType.SADNESS, "en"),
        ("This is not bad at all", EmotionType.HAPPINESS, "en"),
        ("I am scared of the dark", EmotionType.FEAR, "en"),
        ("I trust you", EmotionType.ATTACHMENT, "en"),
        ("This is terrifying", EmotionType.FEAR, "en"),
        ("I'm shocked by the news", EmotionType.SURPRISE, "en"),
        ("#depression is real", EmotionType.SADNESS, "en"),
        ("What an F'ing liar", EmotionType.ANGER, "en"),
        ("#happy #birthday, best day ever", EmotionType.HAPPINESS, "en"),
        ("我听到好消息，开心得跳了起来", EmotionType.HAPPINESS, "zh"),
        ("他走后我心里空落落的", EmotionType.SADNESS, "zh"),
        ("气炸了，别再敷衍我", EmotionType.ANGER, "zh"),
        ("我下意识往后退，手一直在抖", EmotionType.FEAR, "zh"),
        ("眼睛一下睁大了，啊？？", EmotionType.SURPRISE, "zh"),
        ("我今天特别开心", EmotionType.HAPPINESS, "zh"),
        ("我真的很难过", EmotionType.SADNESS, "zh"),
        ("这个味道让我恶心", EmotionType.DISGUST, "zh"),
        ("今天好无聊", EmotionType.BOREDOM, "zh"),
    ),
)
def test_detects_explicit_chinese_and_english_emotion(
    text: str,
    emotion: EmotionType,
    language: str,
) -> None:
    assessment = TextEmotionDetector().assess(text)

    assert assessment.emotion is emotion
    assert assessment.language == language
    assert assessment.confidence >= TextEmotionDetector.MIN_CONFIDENCE


@pytest.mark.parametrize(
    "text",
    (
        "Don't worry, I'm fine",
        "I am not angry, just tired",
        "我没有生气，只是有点累",
        "我真的没事，别担心",
        "The train leaves at six.",
    ),
)
def test_neutral_or_negated_text_does_not_create_a_stimulus(text: str) -> None:
    assessment = TextEmotionDetector().assess(text)

    assert assessment.emotion is None
    assert assessment.confidence == 0.0


def test_english_word_boundaries_prevent_substring_false_positive() -> None:
    assessment = TextEmotionDetector().assess("I am scared")

    assert assessment.emotion is EmotionType.FEAR
    assert assessment.emotion is not EmotionType.ATTACHMENT


def test_behavioral_cues_do_not_use_broad_footstep_false_positive() -> None:
    assessment = TextEmotionDetector().assess("我一路哼着歌回家，脚步都轻了")

    assert assessment.emotion is EmotionType.HAPPINESS


def test_conflicting_emotions_abstain_with_alternatives() -> None:
    assessment = TextEmotionDetector().assess("I am happy and angry at the same time")

    assert assessment.emotion is None
    assert {emotion for emotion, _score in assessment.alternatives} >= {
        EmotionType.HAPPINESS,
        EmotionType.ANGER,
    }


def test_same_polarity_emotions_do_not_suppress_a_clear_positive_signal() -> None:
    assessment = TextEmotionDetector().assess("I am happy and I love this so much")

    assert assessment.emotion is EmotionType.HAPPINESS


def test_mixed_language_is_scored_by_both_lexicons() -> None:
    assessment = TextEmotionDetector().assess("我很 happy，但也 worried")

    assert assessment.language == "mixed"
    assert assessment.emotion is None
    assert assessment.alternatives


@pytest.mark.parametrize("modality", ("audio", "image"))
def test_version_one_unified_detector_rejects_unsupported_media(
    modality: str,
) -> None:
    with pytest.raises(UnsupportedEmotionModalityError):
        EmotionDetector().detect(
            {"type": modality, "path": "unused", "event_id": "media-1"}
        )


def test_version_one_unified_detector_does_not_encode_abstention_as_calm() -> None:
    with pytest.raises(NoEmotionDetectedError):
        EmotionDetector().detect(
            {
                "type": "text",
                "content": "The train leaves at six.",
                "event_id": "text-1",
            }
        )
