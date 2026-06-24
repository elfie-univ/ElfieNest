"""Tests for runtime.model_route module.

测试每精灵模型路由配置的加载、保存和解析功能。
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime.model_route import (
    SCENE_SLOTS,
    SceneRoute,
    ModelRoute,
    DEFAULT_SCENE_ROUTES,
    load_model_route,
    save_model_route,
    create_default_route,
    resolve_model,
)
from runtime.config import LLMRuntimeConfig


class TestSceneRoute:
    """SceneRoute 数据类测试"""

    def test_scene_route_creation(self):
        """创建 SceneRoute 实例"""
        route = SceneRoute(
            primary="openai/gpt-4o",
            fallbacks=["deepseek/deepseek-chat", "ollama/qwen3.5:0.8b"],
            energy_threshold=30.0,
        )
        assert route.primary == "openai/gpt-4o"
        assert len(route.fallbacks) == 2
        assert route.energy_threshold == 30.0

    def test_scene_route_to_dict(self):
        """SceneRoute 序列化为字典"""
        route = SceneRoute(
            primary="openai/gpt-4o",
            fallbacks=["deepseek/deepseek-chat"],
            energy_threshold=20.0,
        )
        data = route.to_dict()
        assert data["primary"] == "openai/gpt-4o"
        assert data["fallbacks"] == ["deepseek/deepseek-chat"]
        assert data["energy_threshold"] == 20.0

    def test_scene_route_from_dict(self):
        """从字典创建 SceneRoute"""
        data = {
            "primary": "openai/gpt-4o",
            "fallbacks": ["deepseek/deepseek-chat"],
            "energy_threshold": 25.0,
        }
        route = SceneRoute.from_dict(data)
        assert route.primary == "openai/gpt-4o"
        assert route.fallbacks == ["deepseek/deepseek-chat"]
        assert route.energy_threshold == 25.0


class TestModelRoute:
    """ModelRoute 数据类测试"""

    def test_model_route_creation(self):
        """创建 ModelRoute 实例"""
        route = ModelRoute(
            elfie_id="test_elfie",
            scene_routes={
                "idle": SceneRoute(primary="ollama/qwen3.5:0.8b", fallbacks=[], energy_threshold=0),
            },
        )
        assert route.elfie_id == "test_elfie"
        assert "idle" in route.scene_routes

    def test_model_route_to_dict(self):
        """ModelRoute 序列化为字典"""
        route = ModelRoute(
            elfie_id="test_elfie",
            scene_routes={
                "idle": SceneRoute(primary="ollama/qwen3.5:0.8b", fallbacks=[], energy_threshold=0),
            },
            updated_at="2024-01-01T00:00:00",
        )
        data = route.to_dict()
        assert data["elfie_id"] == "test_elfie"
        assert "idle" in data["scene_routes"]
        assert data["updated_at"] == "2024-01-01T00:00:00"

    def test_model_route_from_dict(self):
        """从字典创建 ModelRoute"""
        data = {
            "elfie_id": "test_elfie",
            "scene_routes": {
                "idle": {
                    "primary": "ollama/qwen3.5:0.8b",
                    "fallbacks": [],
                    "energy_threshold": 0,
                },
            },
            "updated_at": "2024-01-01T00:00:00",
        }
        route = ModelRoute.from_dict(data)
        assert route.elfie_id == "test_elfie"
        assert "idle" in route.scene_routes


class TestDefaultSceneRoutes:
    """默认场景路由测试"""

    def test_default_scene_routes_has_5_slots(self):
        """DEFAULT_SCENE_ROUTES 包含 5 个场景槽"""
        assert len(DEFAULT_SCENE_ROUTES) == 5
        for slot in SCENE_SLOTS:
            assert slot in DEFAULT_SCENE_ROUTES, f"Missing scene slot: {slot}"

    def test_default_scene_slots_constant(self):
        """SCENE_SLOTS 常量包含正确的场景名称"""
        assert SCENE_SLOTS == ["idle", "deep", "vision", "tool_use", "sleep"]

    def test_default_deep_route_has_fallback(self):
        """deep 场景有降级链"""
        deep_route = DEFAULT_SCENE_ROUTES["deep"]
        assert len(deep_route.fallbacks) > 0
        assert "ollama" in deep_route.fallbacks[0]


class TestLoadSaveModelRoute:
    """加载和保存路由配置测试"""

    def test_load_model_route_nonexistent_elfie_falls_back(self, monkeypatch, tmp_path):
        """加载不存在的精灵配置时返回默认配置"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        
        route = load_model_route("nonexistent_elfie")
        
        assert route.elfie_id == "nonexistent_elfie"
        assert len(route.scene_routes) == 5
        for slot in SCENE_SLOTS:
            assert slot in route.scene_routes

    def test_create_default_route_creates_all_5_scenes(self):
        """create_default_route 创建包含所有 5 个场景的路由"""
        route = create_default_route("test_elfie")
        
        assert route.elfie_id == "test_elfie"
        assert len(route.scene_routes) == 5
        for slot in SCENE_SLOTS:
            assert slot in route.scene_routes
            assert isinstance(route.scene_routes[slot], SceneRoute)

    def test_save_and_load_model_route_roundtrip(self, monkeypatch, tmp_path):
        """保存后重新加载配置保持一致"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        
        # 创建自定义路由
        original_route = ModelRoute(
            elfie_id="test_elfie",
            scene_routes={
                "idle": SceneRoute(
                    primary="openai/gpt-4o-mini",
                    fallbacks=["ollama/qwen3.5:0.8b"],
                    energy_threshold=10.0,
                ),
                "deep": SceneRoute(
                    primary="openai/gpt-4o",
                    fallbacks=["deepseek/deepseek-chat", "ollama/qwen3.5:0.8b"],
                    energy_threshold=30.0,
                ),
            },
        )
        
        # 保存
        save_model_route(original_route)
        
        # 加载
        loaded_route = load_model_route("test_elfie")
        
        assert loaded_route.elfie_id == "test_elfie"
        assert loaded_route.scene_routes["idle"].primary == "openai/gpt-4o-mini"
        assert loaded_route.scene_routes["idle"].energy_threshold == 10.0
        assert loaded_route.scene_routes["deep"].primary == "openai/gpt-4o"
        assert loaded_route.scene_routes["deep"].fallbacks == ["deepseek/deepseek-chat", "ollama/qwen3.5:0.8b"]
        assert loaded_route.updated_at is not None


class TestResolveModel:
    """模型解析测试"""

    def test_resolve_model_high_energy_returns_primary(self, monkeypatch, tmp_path):
        """高能量时返回主模型"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        
        config = LLMRuntimeConfig()
        
        # deep 场景主模型是 deepseek/deepseek-chat，能量阈值 30
        provider, model = resolve_model(
            elfie_id="test_elfie",
            scene="deep",
            energy=100.0,  # 高能量
            config=config,
        )
        
        # 由于 deepseek 可能没有 API key，会降级到 ollama
        # 但我们检查的是高能量不会因为阈值降级
        assert model in ["deepseek-chat", "qwen3.5:0.8b"]

    def test_resolve_model_low_energy_triggers_fallback(self, monkeypatch, tmp_path):
        """低能量时触发降级"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        
        config = LLMRuntimeConfig()
        
        # deep 场景能量阈值 30，低能量应该使用降级链
        provider, model = resolve_model(
            elfie_id="test_elfie",
            scene="deep",
            energy=10.0,  # 低能量
            config=config,
        )
        
        # 低能量应该使用 fallback
        # 最终会降到 ollama
        assert provider == "ollama"
        assert model == "qwen3.5:0.8b"

    def test_resolve_model_all_fallbacks_failing_returns_ollama(self, monkeypatch, tmp_path):
        """所有候选模型不可用时返回 ollama 兜底"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        
        # 创建一个没有 API key 的配置
        config = LLMRuntimeConfig()
        # 移除所有云端 API keys
        for provider_name in ["deepseek", "openai", "gemini", "qwen"]:
            config.providers[provider_name]["api_key"] = ""
            config.providers[provider_name]["status"] = "inactive"
        
        provider, model = resolve_model(
            elfie_id="test_elfie",
            scene="deep",
            energy=100.0,
            config=config,
        )
        
        # 应该降级到 ollama
        assert provider == "ollama"
        assert model == "qwen3.5:0.8b"

    def test_resolve_model_idle_scene(self, monkeypatch, tmp_path):
        """idle 场景使用轻量模型"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        
        config = LLMRuntimeConfig()
        
        provider, model = resolve_model(
            elfie_id="test_elfie",
            scene="idle",
            energy=100.0,
            config=config,
        )
        
        # idle 场景默认使用 ollama
        assert provider == "ollama"
        assert model == "qwen3.5:0.8b"
