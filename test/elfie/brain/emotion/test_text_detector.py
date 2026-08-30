"""Focused tests for the model-free multilingual first-pass detector."""

from __future__ import annotations

import pytest

from elfie.brain.emotion.detector.text_detector import TextEmotionDetector


@pytest.mark.parametrize(
    ("text", "emotion", "language"),
    (
        ("I am furious about this", "anger", "en"),
        ("I'm not happy with the result", "sadness", "en"),
        ("This is not bad at all", "happiness", "en"),
        ("I am scared of the dark", "fear", "en"),
        ("I trust you", "attachment", "en"),
        ("This is terrifying", "fear", "en"),
        ("I'm shocked by the news", "surprise", "en"),
        ("#depression is real", "sadness", "en"),
        ("What an F'ing liar", "anger", "en"),
        ("#happy #birthday, best day ever", "happiness", "en"),
        ("我听到好消息，开心得跳了起来", "happiness", "zh"),
        ("他走后我心里空落落的", "sadness", "zh"),
        ("气炸了，别再敷衍我", "anger", "zh"),
        ("我下意识往后退，手一直在抖", "fear", "zh"),
        ("眼睛一下睁大了，啊？？", "surprise", "zh"),
        ("我今天特别开心", "happiness", "zh"),
        ("我真的很难过", "sadness", "zh"),
        ("这个味道让我恶心", "disgust", "zh"),
        ("今天好无聊", "boredom", "zh"),
    ),
)
def test_detects_explicit_chinese_and_english_emotion(
    text: str,
    emotion: str,
    language: str,
) -> None:
    assessment = TextEmotionDetector().assess(text)

    assert assessment.emotion is not None
    assert assessment.emotion.value == emotion
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

    assert assessment.emotion is not None
    assert assessment.emotion.value == "fear"


def test_behavioral_cues_do_not_use_broad_footstep_false_positive() -> None:
    assessment = TextEmotionDetector().assess("我一路哼着歌回家，脚步都轻了")

    assert assessment.emotion is not None
    assert assessment.emotion.value == "happiness"


def test_conflicting_emotions_abstain_with_alternatives() -> None:
    assessment = TextEmotionDetector().assess("I am happy and angry at the same time")

    assert assessment.emotion is None
    assert {emotion.value for emotion, _score in assessment.alternatives} >= {
        "happiness",
        "anger",
    }


def test_same_polarity_emotions_do_not_suppress_a_clear_positive_signal() -> None:
    assessment = TextEmotionDetector().assess("I am happy and I love this so much")

    assert assessment.emotion is not None
    assert assessment.emotion.value == "happiness"


def test_mixed_language_is_scored_by_both_lexicons() -> None:
    assessment = TextEmotionDetector().assess("我很 happy，但也 worried")

    assert assessment.language == "mixed"
    assert assessment.emotion is None
    assert assessment.alternatives
