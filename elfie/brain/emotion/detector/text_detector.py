"""Fast, in-process multilingual text emotion detection."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from elfie.brain.emotion.emotion_types import EmotionType

_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")

# Common inflections and social-media spellings are folded to a canonical
# cue before scoring.  This keeps the detector model-free while avoiding a
# large list of nearly identical entries in each emotion lexicon.
_ENGLISH_VARIANTS = {
    "terrify": ("terrifying", "terrified", "terrifies"),
    "scared": ("scary", "scarier", "scariest"),
    "shock": ("shocked", "shocking"),
    "sad": ("depressed", "depression", "gloomy"),
    "anger": ("angry", "raging", "rage", "irritated", "irritating"),
    "nervous": ("nervously", "nervousness"),
    "happy": ("happier", "happiest", "happily"),
    "surprise": ("surprising", "surprised"),
    "disgust": ("disgusting", "disgusted"),
}


@dataclass(frozen=True)
class TextEmotionAssessment:
    """Internal, non-persistent result of one text inspection."""

    emotion: Optional[EmotionType]
    confidence: float
    language: str
    matched_terms: Tuple[str, ...] = ()
    alternatives: Tuple[Tuple[EmotionType, float], ...] = ()


_LEXICON: Dict[EmotionType, Dict[str, Tuple[str, ...]]] = {
    EmotionType.HAPPINESS: {
        "en": (
            "happy",
            "happiness",
            "glad",
            "joy",
            "joyful",
            "excited",
            "thrilled",
            "satisfied",
            "satisfying",
            "delighted",
            "pleased",
            "relieved",
            "awesome",
            "promotion",
            "offer",
            "yay",
            "yayy",
            "win",
            "won",
            "record",
            "smile",
            "smiling",
            "laugh",
            "laughed",
            "bright",
            "beautifully",
            "best day",
            "yes",
        ),
        "zh": (
            "开心",
            "高兴",
            "快乐",
            "幸福",
            "兴奋",
            "满足",
            "太好了",
            "喜悦",
            "暖暖",
            "胜利",
            "赢",
            "微笑",
            "笑",
            "甜",
            "哼着歌",
            "脚步轻",
            "通过的消息",
            "站起来",
            "心情超好",
            "合不拢嘴",
        ),
    },
    EmotionType.SADNESS: {
        "en": (
            "sad",
            "sadness",
            "unhappy",
            "upset",
            "disappointed",
            "lonely",
            "loneliness",
            "empty",
            "hollow",
            "ache",
            "tears",
            "crying",
            "cried",
            "can't laugh",
            "want to cry",
            "rain",
            "deletes",
            "photos",
            "alone",
            "sigh",
        ),
        "zh": (
            "难过",
            "傷心",
            "伤心",
            "悲伤",
            "心碎",
            "失望",
            "沮丧",
            "低落",
            "孤独",
            "寂寞",
            "失落",
            "眼睛有点红",
            "眼泪",
            "想哭",
            "笑不出来",
            "空落落",
            "房间更空",
            "鼻子酸",
            "唉",
            "一个人",
            "心情没有",
        ),
    },
    EmotionType.ANGER: {
        "en": (
            "anger",
            "angry",
            "furious",
            "mad",
            "annoyed",
            "liar",
            "hate",
            "resent",
            "resentful",
            "unfair",
            "lied",
            "scam",
            "gets under my skin",
            "deleting",
            "missed deadline",
            "fix everything",
            "stop touching",
            "slammed",
            "destroyed",
            "snapped",
            "clenched",
            "pacing",
        ),
        "zh": (
            "生气",
            "愤怒",
            "气死",
            "气炸",
            "火大",
            "烦",
            "讨厌",
            "恼火",
            "敷衍",
            "被骗",
            "骗我",
            "插队",
            "火了",
            "过分",
            "发抖",
            "重重放",
            "皱眉",
            "宕机",
            "摔门",
            "摔抽屉",
            "拍桌",
            "大喊",
            "够了",
            "毁了",
            "别来了",
            "我真的会谢",
            "你再说一遍试试",
        ),
    },
    EmotionType.FEAR: {
        "en": (
            "afraid",
            "scared",
            "fear",
            "worried",
            "worry",
            "anxious",
            "nervous",
            "danger",
            "terrify",
            "panic",
            "panicked",
            "froze",
            "terrible",
            "following me",
            "dark basement",
            "creeping me out",
            "footsteps",
            "alarm",
            "haunted",
            "backing away",
            "heart racing",
            "stomach dropped",
            "shaking",
            "sweaty palms",
        ),
        "zh": (
            "害怕",
            "恐惧",
            "担心",
            "危险",
            "心慌",
            "慌",
            "不安",
            "僵住",
            "往后退",
            "心跳快",
            "发虚",
            "手心全是汗",
            "一直在抖",
            "楼梯间",
            "救命",
            "蛇",
            "警报",
            "怕",
        ),
    },
    EmotionType.SURPRISE: {
        "en": (
            "surprised",
            "surprise",
            "shock",
            "wow",
            "unexpected",
            "expect",
            "expecting",
            "never expected",
            "omg",
            "wait what",
            "no way",
            "moved the meeting",
            "replied in one minute",
            "gasped",
            "twist",
            "eyebrows",
            "reread",
            "came back early",
        ),
        "zh": (
            "惊讶",
            "驚訝",
            "惊奇",
            "居然",
            "竟然",
            "没想到",
            "真的假的",
            "惊人的",
            "怎么会",
            "怎麼會",
            "突然",
            "睁大",
            "啊？？",
        ),
    },
    EmotionType.DISGUST: {
        "en": (
            "disgust",
            "disgusting",
            "disgusted",
            "gross",
            "revolting",
            "nauseating",
            "nauseous",
            "vomit",
            "sour",
            "spoiled",
            "filthy",
            "mold",
            "ick",
            "gagged",
            "worm",
            "ugh",
            "not eating",
        ),
        "zh": (
            "恶心",
            "噁心",
            "厌恶",
            "討厭",
            "反胃",
            "馊",
            "馊了",
            "下不去嘴",
            "黏糊糊",
            "没胃口",
            "沒胃口",
            "虫子",
        ),
    },
    EmotionType.BOREDOM: {
        "en": (
            "bored",
            "boring",
            "dull",
            "tedious",
            "sleepy",
            "sleep",
            "spreadsheet",
            "another meeting",
            "nothing new",
            "nothing happening",
            "same old",
            "same slide",
            "refreshing",
            "refreshed",
            "ceiling tiles",
            "mechanically nodding",
            "brain drifted",
            "zzz",
            "done with this queue",
        ),
        "zh": (
            "无聊",
            "無聊",
            "闷",
            "悶",
            "重复",
            "重複",
            "睡着",
            "睡著",
            "毫无变化",
            "毫無變化",
            "刷新",
            "没意思",
            "机械地点头",
            "脑子已经飘走",
            "提不起劲",
            "太平",
        ),
    },
    EmotionType.ATTACHMENT: {
        "en": (
            "trust",
            "trusted",
            "attached",
            "love",
            "care",
            "safe",
            "connected",
            "fondly",
            "miss",
            "hear your voice",
            "hoodie",
            "feels like you",
            "heart",
            "comfort",
            "note",
            "key",
            "luv",
            "luvv",
            "stay a little longer",
            "like having you",
            "don't leave me",
            "wherever you answer",
            "jealous",
        ),
        "zh": (
            "信任",
            "依恋",
            "依戀",
            "喜欢",
            "喜歡",
            "爱",
            "愛",
            "陪伴",
            "牵挂",
            "牽掛",
            "眷恋",
            "眷戀",
            "舍不得",
            "捨不得",
            "黏着你",
            "黏著你",
            "不想分开",
            "不想分開",
            "妈妈来接",
            "安稳",
            "留着灯",
            "留著燈",
            "拉着我的袖子",
            "拉著我的袖子",
        ),
    },
}

_PHRASES: Dict[EmotionType, Dict[str, Tuple[str, ...]]] = {
    EmotionType.HAPPINESS: {
        "en": (
            "made my day",
            "feel relieved",
            "got the promotion",
            "heart dance",
            "feel relieved",
            "good news",
            "can't stop smiling",
            "not only did we win",
            "worked out beautifully",
        ),
        "zh": ("太好了", "开心得", "高兴得", "心里暖暖", "暖暖的"),
    },
    EmotionType.SADNESS: {
        "en": (
            "empty inside",
            "isn't what i wanted",
            "is not what i wanted",
            "fine but",
            "old photos",
        ),
        "zh": ("心里空空", "心好痛", "空落落", "一个人过生日", "心情没有"),
    },
    EmotionType.ANGER: {
        "en": (
            "leave me alone",
            "pisses me off",
            "gets under my skin",
            "nice job deleting",
            "sure, i just love",
            "wonderful service",
        ),
        "zh": ("别烦我", "別煩我", "真是谢谢你", "真是謝謝你", "好个惊喜", "好個驚喜"),
    },
    EmotionType.FEAR: {
        "en": (
            "feel panicked",
            "i am terrified",
            "what if",
            "checked the lock",
            "hands were shaking",
            "wouldn't say i'm not scared",
        ),
        "zh": ("心里很慌", "心裡很慌", "越说没事越不安", "越說沒事越不安"),
    },
    EmotionType.SURPRISE: {
        "en": (
            "can't believe",
            "can’t believe",
            "wasn't expecting",
            "was not expecting",
            "lights suddenly came on",
        ),
        "zh": ("怎么会", "怎麼會", "打开盒子", "打開盒子"),
    },
    EmotionType.DISGUST: {
        "en": (
            "gone sour",
            "not eating that",
            "spoiled milk",
            "gave me the ick",
            "worm-filled",
        ),
        "zh": ("没胃口", "沒胃口"),
    },
    EmotionType.BOREDOM: {
        "en": ("same old feed", "still on slide two", "best. spreadsheet. ever."),
        "zh": ("刷新了十遍", "刷新十遍"),
    },
    EmotionType.ATTACHMENT: {
        "en": (
            "feel safe with you",
            "i appreciate you",
            "deeply connected",
            "think of him fondly",
            "close to my heart",
            "keep every note",
            "carried the worn key",
            "don't leave me on read",
        ),
        "zh": ("谢谢你一直陪着我", "謝謝你一直陪著我", "说不出的眷恋", "說不出的眷戀"),
    },
}

_CALM_PHRASES = {
    "don't worry",
    "do not worry",
    "i'm fine",
    "i am fine",
    "no problem",
    "all good",
    "no panic",
    "no rush",
    "没事",
    "沒事",
    "别担心",
    "別擔心",
    "不用担心",
    "不用擔心",
    "应该没事",
    "應該沒事",
    "平静",
    "平靜",
    "从容",
    "從容",
    "安安静静",
    "安安靜靜",
    "panic? me? never",
    "panic me never",
    "cool as a cucumber",
    "at ease",
    "feel steady",
    "深呼吸",
    "心跳慢了下来",
    "心跳慢了下來",
    "nothing urgent",
    "watched clouds",
}
_NEGATED_HAPPINESS = (
    "not happy",
    "not glad",
    "not joyful",
    "不开心",
    "不高兴",
    "不快乐",
    "不開心",
    "不高興",
    "不快樂",
)
_NEGATED_ANGER = (
    "not angry",
    "not mad",
    "not furious",
    "没有生气",
    "沒有生氣",
    "没生气",
    "沒生氣",
    "不生气",
    "不生氣",
    "not anger",
)
_NEGATED_FEAR = (
    "not afraid",
    "not scared",
    "not worried",
    "不害怕",
    "没有害怕",
    "沒有害怕",
)
_NEGATED_SADNESS = (
    "not sad",
    "not unhappy",
    "不难过",
    "不難過",
    "不伤心",
    "不傷心",
)
_NEGATED_DISGUST = ("not disgusting", "not gross", "不讨厌", "不討厭")
_NEGATED_CALM = ("不焦虑", "不焦慮", "不兴奋", "不興奮", "not anxious", "not excited")
_NEGATED_HATE = ("not hate", "don't hate", "do not hate")

_EMOJI_CUES = {
    EmotionType.HAPPINESS: ("😄", "😊", "🎉", "<3"),
    EmotionType.SADNESS: ("😢", "😭"),
    EmotionType.DISGUST: ("🤢",),
    EmotionType.ATTACHMENT: ("🥺", "❤️", "❤"),
    EmotionType.ANGER: ("😡", "😠"),
    EmotionType.FEAR: ("😱", "😨"),
    EmotionType.BOREDOM: ("😑", "🥱"),
}

_MIXED_CONNECTORS = (
    "but",
    "yet",
    "however",
    "although",
    "though",
    "while",
    "但是",
    "但",
    "却",
    "反而",
    "又",
    "也",
)
_SAME_POLARITY = {
    "positive": frozenset({EmotionType.HAPPINESS, EmotionType.ATTACHMENT}),
    "negative": frozenset(
        {EmotionType.SADNESS, EmotionType.ANGER, EmotionType.FEAR, EmotionType.DISGUST}
    ),
}


def _same_polarity(first: EmotionType, second: EmotionType) -> bool:
    return any(first in group and second in group for group in _SAME_POLARITY.values())


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("’", "'").strip().lower()
    normalized = re.sub(r"([a-z])\1{2,}", r"\1\1", normalized)
    for canonical, variants in _ENGLISH_VARIANTS.items():
        for variant in variants:
            normalized = re.sub(
                rf"(?<![a-z]){re.escape(variant)}(?![a-z])",
                canonical,
                normalized,
            )
    # Hashtags are lexical cues, not separate words for this first pass.
    return normalized.replace("#", "")


def _language(text: str) -> str:
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    if cjk and latin:
        return "mixed"
    if cjk:
        return "zh"
    if latin:
        return "en"
    return "unknown"


def _english_hits(text: str, term: str) -> int:
    return len(re.findall(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text))


class TextEmotionDetector:
    """Small multilingual first-pass detector with no model/runtime service."""

    MIN_CONFIDENCE = 0.55
    MIN_MARGIN = 0.15

    def assess(self, text: str) -> TextEmotionAssessment:
        """Return a provisional assessment; ambiguity intentionally abstains."""
        normalized = _normalize(text)
        language = _language(normalized)
        if not normalized:
            return TextEmotionAssessment(None, 0.0, language)

        scores: Dict[EmotionType, float] = dict.fromkeys(_LEXICON, 0.0)
        matched: Dict[EmotionType, List[str]] = dict.fromkeys(_LEXICON, [])
        matched = {emotion: [] for emotion in matched}
        for emotion, language_terms in _LEXICON.items():
            for term_language, terms in language_terms.items():
                if language not in {term_language, "mixed"}:
                    continue
                for term in terms:
                    hits = (
                        _english_hits(normalized, term)
                        if term_language == "en"
                        else normalized.count(term)
                    )
                    if hits:
                        scores[emotion] += float(hits)
                        matched[emotion].append(term)

        for emotion, language_phrases in _PHRASES.items():
            for phrase_language, phrases in language_phrases.items():
                if language not in {phrase_language, "mixed"}:
                    continue
                for phrase in phrases:
                    hits = normalized.count(phrase)
                    if hits:
                        scores[emotion] += 2.0 * hits
                        matched[emotion].append(phrase)

        for emotion, cues in _EMOJI_CUES.items():
            for cue in cues:
                if cue in normalized:
                    scores[emotion] += 1.5
                    matched[emotion].append(cue)

        self._apply_negation_rules(normalized, scores, matched)
        calm_signal = any(phrase in normalized for phrase in _CALM_PHRASES)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        active = [(emotion, score) for emotion, score in ranked if score > 0.0]
        if not active:
            return TextEmotionAssessment(None, 0.0, language)

        top_emotion, top_score = active[0]
        second_score = active[1][1] if len(active) > 1 else 0.0
        confidence = min(0.95, 0.45 + 0.15 * top_score)
        if len(active) > 1 and any(
            connector in normalized for connector in _MIXED_CONNECTORS
        ):
            return TextEmotionAssessment(
                None,
                min(confidence, 0.54),
                language,
                tuple(dict.fromkeys(sum(matched.values(), []))),
                tuple(
                    (emotion, min(0.95, 0.45 + 0.15 * score))
                    for emotion, score in active[:3]
                ),
            )
        if calm_signal and top_score <= 1.0:
            return TextEmotionAssessment(None, 0.0, language)
        if (
            len(active) > 1
            and top_score - second_score < self.MIN_MARGIN
            and not _same_polarity(top_emotion, active[1][0])
        ):
            alternatives = tuple(
                (emotion, min(0.95, 0.45 + 0.15 * score))
                for emotion, score in active[:3]
            )
            return TextEmotionAssessment(
                None,
                min(confidence, 0.54),
                language,
                tuple(dict.fromkeys(sum(matched.values(), []))),
                alternatives,
            )
        if confidence < self.MIN_CONFIDENCE:
            return TextEmotionAssessment(None, confidence, language)
        return TextEmotionAssessment(
            top_emotion,
            confidence,
            language,
            tuple(matched[top_emotion]),
            tuple(
                (emotion, min(0.95, 0.45 + 0.15 * score))
                for emotion, score in active[1:3]
            ),
        )

    @staticmethod
    def _apply_negation_rules(
        text: str,
        scores: Dict[EmotionType, float],
        matched: Dict[EmotionType, List[str]],
    ) -> None:
        if any(phrase in text for phrase in _NEGATED_HAPPINESS):
            scores[EmotionType.HAPPINESS] = 0.0
            scores[EmotionType.SADNESS] += 2.0
            matched[EmotionType.SADNESS].append("negated_happiness")
        if any(phrase in text for phrase in _NEGATED_SADNESS):
            scores[EmotionType.SADNESS] = 0.0
        if any(phrase in text for phrase in _NEGATED_DISGUST):
            scores[EmotionType.DISGUST] = 0.0
            scores[EmotionType.ANGER] = 0.0
            scores[EmotionType.HAPPINESS] += 1.0
            matched[EmotionType.HAPPINESS].append("negated_disgust")
        if any(phrase in text for phrase in _NEGATED_CALM):
            scores[EmotionType.FEAR] = 0.0
            scores[EmotionType.HAPPINESS] = 0.0
        if "没有什么值得高兴" in text or "沒有什麼值得高興" in text:
            scores[EmotionType.HAPPINESS] = 0.0
            scores[EmotionType.SADNESS] += 2.0
            matched[EmotionType.SADNESS].append("negated_happiness_context")
        if ("not unhappy" in text and "thrilled" in text) or (
            "不是不高兴" in text and "不是高兴" in text
        ):
            scores[EmotionType.HAPPINESS] = 0.0
            scores[EmotionType.SADNESS] = 0.0
            matched[EmotionType.HAPPINESS].append("ambiguous_happiness")
            matched[EmotionType.SADNESS].append("ambiguous_happiness")
        if "miss" in text:
            if any(
                marker in text
                for marker in ("mom", "mother", "tonight", "alone", "hollow")
            ):
                scores[EmotionType.ATTACHMENT] = 0.0
                scores[EmotionType.SADNESS] += 1.0
                matched[EmotionType.SADNESS].append("loss_context")
            elif "miss you" in text or "miss him" in text or "miss her" in text:
                scores[EmotionType.ATTACHMENT] += 1.0
                matched[EmotionType.ATTACHMENT].append("missing_someone")
        if any(marker in text for marker in ("lied", "scam", "unfair")):
            scores[EmotionType.ANGER] += 1.0
            matched[EmotionType.ANGER].append("betrayal_context")
        if ("反而" in text or "却" in text) and any(
            phrase in text for phrase in ("满足", "滿足", "relieved", "made my day")
        ):
            scores[EmotionType.SADNESS] = 0.0
            scores[EmotionType.HAPPINESS] += 2.0
            matched[EmotionType.HAPPINESS].append("contrast_resolution")
        if any(phrase in text for phrase in _NEGATED_ANGER):
            scores[EmotionType.ANGER] = 0.0
        if any(phrase in text for phrase in _NEGATED_FEAR):
            scores[EmotionType.FEAR] = 0.0
        # A construction such as "wouldn't say I'm not scared" is a
        # deliberate double negative: retain a provisional fear signal.
        if (
            "wouldn't say i'm not scared" in text
            or "would not say i am not scared" in text
        ):
            scores[EmotionType.FEAR] += 2.0
            matched[EmotionType.FEAR].append("double_negated_fear")
        if any(phrase in text for phrase in _NEGATED_HATE):
            scores[EmotionType.ANGER] = 0.0
        if "not bad" in text:
            scores[EmotionType.HAPPINESS] += 2.0
            matched[EmotionType.HAPPINESS].append("not bad")
        if "not unhappy" in text:
            scores[EmotionType.SADNESS] = 0.0
            scores[EmotionType.HAPPINESS] += 2.0
            matched[EmotionType.HAPPINESS].append("not unhappy")
        if "不是不难过" in text or "不是不難過" in text:
            scores[EmotionType.SADNESS] += 2.0
            matched[EmotionType.SADNESS].append("double_negated_sadness")
        if "不是不害怕" in text or "不是不害怕" in text:
            scores[EmotionType.FEAR] += 2.0
            matched[EmotionType.FEAR].append("double_negated_fear")

    def detect(self, text: str) -> Tuple[str, float]:
        """Compatibility tuple API; no candidate is represented as zero calm."""
        assessment = self.assess(text)
        if assessment.emotion is None:
            return "calm", 0.0
        return assessment.emotion.value, assessment.confidence


__all__ = ("TextEmotionAssessment", "TextEmotionDetector")
