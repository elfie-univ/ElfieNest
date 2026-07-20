"""Tests for ai_runtime.policy.scene_classifier module.

测试场景分类器的各种输入组合。
"""

import pytest

from ai_runtime.policy.scene_classifier import (
    SCENE_SLOTS,
    DEEP_KEYWORDS,
    VISION_KEYWORDS,
    TOOL_USE_KEYWORDS,
    classify_scene,
)


class TestSceneSlots:
    """场景槽定义测试"""

    def test_scene_slots_has_5_elements(self):
        """场景槽包含 5 个元素"""
        assert len(SCENE_SLOTS) == 5
        assert "idle" in SCENE_SLOTS
        assert "deep" in SCENE_SLOTS
        assert "vision" in SCENE_SLOTS
        assert "tool_use" in SCENE_SLOTS
        assert "sleep" in SCENE_SLOTS


class TestKeywords:
    """关键词定义测试"""

    def test_deep_keywords_exist(self):
        """deep 关键词列表不为空"""
        assert len(DEEP_KEYWORDS) > 0
        assert "计算" in DEEP_KEYWORDS
        assert "搜索" in DEEP_KEYWORDS

    def test_vision_keywords_exist(self):
        """vision 关键词列表不为空"""
        assert len(VISION_KEYWORDS) > 0
        assert "图片" in VISION_KEYWORDS
        assert "看看" in VISION_KEYWORDS

    def test_tool_use_keywords_exist(self):
        """tool_use 关键词列表不为空"""
        assert len(TOOL_USE_KEYWORDS) > 0
        assert "帮我" in TOOL_USE_KEYWORDS
        assert "执行" in TOOL_USE_KEYWORDS


class TestClassifyScene:
    """场景分类测试"""

    def test_tool_call_pending_returns_tool_use(self):
        """tool_call_pending → tool_use"""
        result = classify_scene(
            prompt="你好",
            tool_call_pending=True,
        )
        assert result == "tool_use"

    def test_has_image_returns_vision(self):
        """has_image=True → vision"""
        result = classify_scene(
            prompt="这是什么",
            has_image=True,
        )
        assert result == "vision"

    def test_has_audio_returns_vision(self):
        """has_audio=True → vision"""
        result = classify_scene(
            prompt="听一下",
            has_audio=True,
        )
        assert result == "vision"

    def test_cen_high_returns_deep(self):
        """CEN 高 → deep"""
        result = classify_scene(
            prompt="帮我分析一下",
            attention_state={"CEN": 80.0},
        )
        assert result == "deep"

    def test_dmn_high_returns_idle(self):
        """DMN 高 → idle"""
        result = classify_scene(
            prompt="随便聊聊",
            attention_state={"DMN": 70.0},
        )
        assert result == "idle"

    def test_sn_high_returns_tool_use(self):
        """SN 高 → tool_use"""
        result = classify_scene(
            prompt="有情况",
            attention_state={"SN": 80.0},
        )
        assert result == "tool_use"

    def test_current_network_string_format(self):
        """支持 current_network 字符串格式"""
        result = classify_scene(
            prompt="你好",
            attention_state={"current_network": "CEN"},
        )
        assert result == "deep"

        result = classify_scene(
            prompt="你好",
            attention_state={"current_network": "DMN"},
        )
        assert result == "idle"

        result = classify_scene(
            prompt="你好",
            attention_state={"current_network": "SN"},
        )
        assert result == "tool_use"


class TestKeywordClassification:
    """关键词分类测试"""

    def test_search_keyword_returns_deep(self):
        """"搜索" 关键词 → deep（不含 tool_use 关键词）"""
        # 注意："搜索一下" 在 TOOL_USE_KEYWORDS 中，所以用 "搜索" 不带 "一下"
        result = classify_scene(prompt="搜索最新的新闻")
        assert result == "deep"

    def test_calculate_keyword_returns_deep(self):
        """"计算" 关键词 → deep（不含 tool_use 关键词）"""
        result = classify_scene(prompt="计算一下 123 + 456")
        assert result == "deep"

    def test_code_keyword_returns_deep(self):
        """"代码" 关键词 → deep（不含 tool_use 关键词）"""
        result = classify_scene(prompt="写一段代码")
        assert result == "deep"

    def test_analyze_keyword_returns_deep(self):
        """"分析" 关键词 → deep"""
        result = classify_scene(prompt="分析这个问题")
        assert result == "deep"

    def test_image_keyword_returns_vision(self):
        """"看看这张图片" → vision"""
        result = classify_scene(prompt="看看这张图片")
        assert result == "vision"

    def test_photo_keyword_returns_vision(self):
        """"照片" 关键词 → vision"""
        result = classify_scene(prompt="这是一张什么照片")
        assert result == "vision"

    def test_help_keyword_returns_tool_use(self):
        """"帮我" 关键词 → tool_use"""
        result = classify_scene(prompt="帮我做这件事")
        assert result == "tool_use"

    def test_execute_keyword_returns_tool_use(self):
        """"执行" 关键词 → tool_use"""
        result = classify_scene(prompt="执行这个命令")
        assert result == "tool_use"

    def test_help_with_search_returns_tool_use(self):
        """"帮我搜索一下" → tool_use（因为"帮我"先匹配）"""
        result = classify_scene(prompt="帮我搜索一下最新的新闻")
        assert result == "tool_use"

    def test_help_keyword_returns_tool_use(self):
        """"帮我" 关键词 → tool_use"""
        result = classify_scene(prompt="帮我做这件事")
        assert result == "tool_use"

    def test_execute_keyword_returns_tool_use(self):
        """"执行" 关键词 → tool_use"""
        result = classify_scene(prompt="执行这个命令")
        assert result == "tool_use"


class TestPriority:
    """优先级测试"""

    def test_tool_call_pending_overrides_vision(self):
        """tool_call_pending 覆盖 has_image"""
        result = classify_scene(
            prompt="看图片",
            tool_call_pending=True,
            has_image=True,
        )
        assert result == "tool_use"

    def test_vision_overrides_attention_state(self):
        """has_image 覆盖注意力状态"""
        result = classify_scene(
            prompt="你好",
            attention_state={"CEN": 90.0},
            has_image=True,
        )
        assert result == "vision"

    def test_tool_call_pending_overrides_all(self):
        """tool_call_pending 是最高优先级"""
        result = classify_scene(
            prompt="帮我搜索计算代码",
            tool_call_pending=True,
            attention_state={"CEN": 100.0},
            has_image=True,
        )
        assert result == "tool_use"


class TestDefaultBehavior:
    """默认行为测试"""

    def test_no_signals_returns_idle(self):
        """无明确信号 → idle（默认）"""
        result = classify_scene(prompt="你好")
        assert result == "idle"

    def test_empty_prompt_returns_idle(self):
        """空 prompt → idle"""
        result = classify_scene(prompt="")
        assert result == "idle"

    def test_unknown_attention_state_returns_idle(self):
        """未知注意力状态 → idle"""
        result = classify_scene(
            prompt="你好",
            attention_state={"UNKNOWN": 100.0},
        )
        assert result == "idle"

    def test_low_attention_scores_returns_idle(self):
        """低注意力分数 → 使用关键词判断或 idle"""
        result = classify_scene(
            prompt="随便聊聊",
            attention_state={"SN": 10.0, "CEN": 20.0, "DMN": 30.0},
        )
        # 低分数，无关键词，应该返回 idle
        assert result == "idle"
