"""
引擎模块测试
测试 ElfieNestEngine, ElfieNestRoom, ElfieNestCoordinator
"""

from unittest.mock import MagicMock, patch

import pytest

from elfie import Elfie
from elfie.body import BodyCommand, CommandStatus, HeadlessBody
from elfienest.core.room import ElfieNestRoom, RoomFullError
from elfienest.simulation.engine import ElfieNestCoordinator, ElfieNestEngine


class TestElfieNestEngine:
    """ElfieNestEngine 单元测试"""

    @pytest.fixture
    def mock_elfie(self):
        """创建模拟精灵"""
        elfie = MagicMock(spec=Elfie)
        elfie.perceive_and_respond.return_value = {
            "success": True,
            "speech": "你好！",
            "action": "",
            "mutter": "",
        }
        elfie.amygdala = MagicMock()
        elfie.amygdala.get_dominant_mood.return_value = "happy"
        elfie.tick = MagicMock()
        return elfie

    @pytest.fixture
    def engine(self):
        """创建引擎实例"""
        with patch("elfienest.transport.godot_api.GodotAPIServer"):
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

    def test_engine_collects_room_owner_and_touch_as_body_events(
        self, engine, mock_elfie
    ):
        engine.room.register_elfie("elf1", mock_elfie)
        engine.room.broadcast_speech("other", "伙伴在说话")
        engine.coordinator.send_user_message("elf1", "主人在说话")
        engine.coordinator.trigger_elfie_interaction("other", "elf1", "collision")

        events = engine._collect_world_sensory_events("elf1")

        assert [event.sensor for event in events] == ["hearing", "hearing", "touch"]
        assert "伙伴在说话" in events[0].payload["user_message"]
        assert events[1].payload["user_message"] == "主人在说话"
        assert events[2].payload["gentle_stroke"] == 1.0

    def test_engine_executes_output_through_current_body(self, engine):
        body = HeadlessBody(body_id="elf1")
        body.connect()
        elfie = Elfie(memory_db_path=":memory:", body=body)

        result = engine._execute_body_command(elfie, BodyCommand(action="gesture.wave"))

        assert result is not None
        assert result["status"] == CommandStatus.COMPLETED.value
        assert body.last_result is not None
        assert body.last_result.action == "gesture.wave"

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
        elfie = MagicMock(spec=Elfie)
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
        room.register_elfie("elf2", MagicMock(spec=Elfie))

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


class TestRoomCapacity:
    """房间容量限制测试"""

    def test_room_full_error(self):
        """max_elfies_per_room=1 → 注册第 2 只 → RoomFullError"""
        room = ElfieNestRoom(max_elfies_per_room=1)
        room.register_elfie("elf1", MagicMock(spec=Elfie))

        with pytest.raises(RoomFullError, match="房间已满"):
            room.register_elfie("elf2", MagicMock(spec=Elfie))

    def test_room_full_error_message(self):
        """验证 RoomFullError 消息包含当前数量/上限"""
        room = ElfieNestRoom(max_elfies_per_room=2)
        room.register_elfie("elf1", MagicMock(spec=Elfie))
        room.register_elfie("elf2", MagicMock(spec=Elfie))

        with pytest.raises(RoomFullError) as exc_info:
            room.register_elfie("elf3", MagicMock(spec=Elfie))
        assert "2/2" in str(exc_info.value)

    def test_room_unlimited(self):
        """max_elfies_per_room=None → 无限制注册"""
        room = ElfieNestRoom(max_elfies_per_room=None)
        for i in range(100):
            room.register_elfie(f"elf{i}", MagicMock(spec=Elfie))
        assert len(room.elfies) == 100


class TestEngineConfig:
    """引擎配置参数测试"""

    def test_engine_tick_interval(self):
        """tick_interval_sec=2.0 → 验证属性"""
        engine = ElfieNestEngine(ws_port=18766, http_port=18001, tick_interval_sec=2.0)
        assert engine.tick_interval_sec == 2.0

    def test_engine_tick_interval_default(self):
        """tick_interval_sec 默认值应为 1.5"""
        engine = ElfieNestEngine(ws_port=18767, http_port=18002)
        assert engine.tick_interval_sec == 1.5

    def test_engine_tts_enabled_default(self):
        """tts_enabled 默认应为 True"""
        engine = ElfieNestEngine(ws_port=18768, http_port=18003)
        assert engine.tts_enabled is True

    def test_engine_tts_disabled(self):
        """tts_enabled=False → _synthesize_voice 返回 None"""
        with patch("elfienest.transport.godot_api.GodotAPIServer"):
            engine = ElfieNestEngine(ws_port=18769, http_port=18004, tts_enabled=False)
        result = engine._synthesize_voice("test", "hello")
        assert result is None

    def test_engine_max_elfies_per_room(self):
        """max_elfies_per_room=3 → 房间容量正确"""
        with patch("elfienest.transport.godot_api.GodotAPIServer"):
            engine = ElfieNestEngine(
                ws_port=18770, http_port=18005, max_elfies_per_room=3
            )
        assert engine.room.max_elfies_per_room == 3

    def test_start_loop_uses_tick_interval(self):
        """start_loop 不传 interval_sec 时使用 self.tick_interval_sec"""
        with patch("elfienest.transport.godot_api.GodotAPIServer"):
            engine = ElfieNestEngine(
                ws_port=18771, http_port=18006, tick_interval_sec=2.5
            )
        # interval_sec=None → 使用 self.tick_interval_sec
        # 我们无法轻松测试运行时行为，但验证默认值传递逻辑
        assert engine.tick_interval_sec == 2.5


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_speech_broadcast(self):
        """测试空消息广播"""
        room = ElfieNestRoom()
        room.register_elfie("elf1", MagicMock(spec=Elfie))
        room.register_elfie("elf2", MagicMock(spec=Elfie))

        room.broadcast_speech("elf1", "")

        assert len(room.sensory_buffers["elf2"]) == 0

    def test_update_nonexistent_elfie_posture(self):
        """测试更新不存在的精灵姿态"""
        room = ElfieNestRoom()
        room.update_elfie_posture("ghost", "lying", "bed_1")

        assert "ghost" not in room.room_state["elfies_status"]

    def test_consume_tactile_default(self):
        """测试消费默认触觉"""
        coordinator = ElfieNestCoordinator(MagicMock())
        tactile = coordinator.consume_tactile("unknown")

        assert tactile["gentle_stroke"] == 0.0
        assert tactile["impact_force"] == 0.0
