# -*- coding: utf-8 -*-
"""
引擎模块测试
测试 ElfieNestEngine, ElfieNestRoom, ElfieNestCoordinator
"""
import pytest
from unittest.mock import MagicMock, patch

from elfie import ElfieIndividual
from elfienest.engine import ElfieNestEngine, ElfieNestCoordinator
from elfienest.room import ElfieNestRoom


class TestElfieNestEngine:
    """ElfieNestEngine 单元测试"""

    @pytest.fixture
    def mock_elfie(self):
        """创建模拟精灵"""
        elfie = MagicMock(spec=ElfieIndividual)
        elfie.perceive_and_respond.return_value = {
            "success": True,
            "speech": "你好！",
            "action": "",
            "mutter": ""
        }
        elfie.amygdala = MagicMock()
        elfie.amygdala.get_dominant_mood.return_value = "happy"
        elfie.tick = MagicMock()
        return elfie

    @pytest.fixture
    def engine(self):
        """创建引擎实例"""
        with patch("elfienest.engine.GodotAPIServer"):
            eng = ElfieNestEngine(ws_port=18765, http_port=18000)
            return eng

    def test_engine_initialization(self, engine):
        """测试引擎初始化"""
        assert engine.room is not None
        assert engine.api_server is not None
        assert engine.coordinator is not None
        assert engine.http_port == 18000

    def test_coordinator_register_elfie(self, engine, mock_elfie):
        """测试 Coordinator 注册精灵"""
        engine.coordinator.register_elfie("测试精灵", mock_elfie)
        assert "测试精灵" in engine.room.elfies

    def test_coordinator_trigger_interaction(self, engine):
        """测试物理碰撞触发"""
        engine.coordinator.trigger_elfie_interaction("A", "B", "collision")
        tactile = engine.coordinator.consume_tactile("B")
        assert tactile["gentle_stroke"] == 1.0
        assert tactile["impact_force"] == 1.5

    def test_room_tick_updates_elfies(self, engine, mock_elfie):
        """测试 Tick 循环更新精灵"""
        engine.room.register_elfie("elf1", mock_elfie)
        engine.room.tick(1.0)
        mock_elfie.tick.assert_called_once_with(1.0)


class TestElfieNestRoom:
    """ElfieNestRoom 单元测试"""

    @pytest.fixture
    def room(self):
        return ElfieNestRoom()

    @pytest.fixture
    def mock_elfie(self):
        elfie = MagicMock(spec=ElfieIndividual)
        elfie.tick = MagicMock()
        return elfie

    def test_register_elfie(self, room, mock_elfie):
        """测试注册精灵"""
        room.register_elfie("elf1", mock_elfie)
        assert "elf1" in room.elfies
        assert "elf1" in room.room_state["elfies_status"]

    def test_broadcast_speech_excludes_sender(self, room, mock_elfie):
        """测试广播排除发送者"""
        room.register_elfie("elf1", mock_elfie)
        room.register_elfie("elf2", MagicMock(spec=ElfieIndividual))
        
        room.broadcast_speech("elf1", "Hello")
        
        assert len(room.sensory_buffers["elf1"]) == 0
        assert len(room.sensory_buffers["elf2"]) == 1

    def test_consume_pending_sensory_input(self, room, mock_elfie):
        """测试消费感官输入"""
        room.register_elfie("elf1", mock_elfie)
        room.broadcast_speech("elf2", "消息1")
        room.broadcast_speech("elf3", "消息2")
        
        result = room.consume_pending_sensory_input("elf1")
        
        assert "消息1" in result
        assert "消息2" in result
        assert len(room.sensory_buffers["elf1"]) == 0

    def test_update_elfie_posture_furniture_binding(self, room, mock_elfie):
        """测试姿态更新和家具绑定"""
        room.register_elfie("elf1", mock_elfie)
        room.register_scene_furniture(["bed_1", "chair_1"])
        
        room.update_elfie_posture("elf1", "lying", "bed_1")
        
        assert room.room_state["furniture"]["bed_1"]["occupant"] == "elf1"
        
        room.update_elfie_posture("elf1", "sitting", "chair_1")
        
        assert room.room_state["furniture"]["bed_1"]["occupant"] is None
        assert room.room_state["furniture"]["chair_1"]["occupant"] == "elf1"

    def test_tick_skips_inactive_elfies(self, room, mock_elfie):
        """测试 Tick 跳过非活跃精灵"""
        room.register_elfie("elf1", mock_elfie)
        room.room_state["elfies_status"]["elf1"]["active"] = False
        
        room.tick(1.0)
        
        mock_elfie.tick.assert_not_called()

    def test_tick_skips_away_elfies(self, room, mock_elfie):
        """测试 Tick 跳过离开的精灵"""
        room.register_elfie("elf1", mock_elfie)
        room.room_state["elfies_status"]["elf1"]["posture"] = "away"
        
        room.tick(1.0)
        
        mock_elfie.tick.assert_not_called()


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_speech_broadcast(self):
        """测试空消息广播"""
        room = ElfieNestRoom()
        room.register_elfie("elf1", MagicMock(spec=ElfieIndividual))
        room.register_elfie("elf2", MagicMock(spec=ElfieIndividual))
        
        room.broadcast_speech("elf1", "")
        
        assert len(room.sensory_buffers["elf2"]) == 0

    def test_update_nonexistent_elfie_posture(self):
        """测试更新不存在的精灵姿态"""
        room = ElfieNestRoom()
        room.update_elfie_posture("ghost", "lying", "bed_1")
        
        assert "ghost" not in room.room_state["elfies_status"]

    def test_consume_tactile_default(self):
        """测试消费默认触觉"""
        coordinator = ElfieNestCoordinator(
            MagicMock(),
            MagicMock()
        )
        tactile = coordinator.consume_tactile("unknown")
        
        assert tactile["gentle_stroke"] == 0.0
        assert tactile["impact_force"] == 0.0
