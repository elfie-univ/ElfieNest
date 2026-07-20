import os

# 确保 Python 能够正确寻址父目录
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from elfie import Elfie
from elfienest import ElfieNestEngine
from elfienest.core.room import ElfieNestRoom


class TestElfieNestSimulation(unittest.TestCase):
    """
    针对精灵仓 3D 宿舍宿舍物理容器进行的高阶链路冒烟测试。
    测试群聊广播路由、家具动态注册、脑干碰撞反射与 Godot 姿态状态反馈合拢。
    """

    def setUp(self):
        self._old_elfie_home = os.environ.get("ELFIE_HOME")
        self._elfie_home = tempfile.TemporaryDirectory()
        os.environ["ELFIE_HOME"] = self._elfie_home.name

    def tearDown(self):
        if self._old_elfie_home is None:
            os.environ.pop("ELFIE_HOME", None)
        else:
            os.environ["ELFIE_HOME"] = self._old_elfie_home
        self._elfie_home.cleanup()

    def test_room_logic_and_broadcast(self):
        """测试 ElfieNestRoom 本身的核心逻辑、动态注册和广播路由"""
        room = ElfieNestRoom()

        # 1. 注册多只精灵
        elfie_1 = Elfie()
        elfie_2 = Elfie()
        room.register_elfie("艾菲", elfie_1)
        room.register_elfie("雪球", elfie_2)

        self.assertIn("艾菲", room.elfies)
        self.assertIn("雪球", room.elfies)
        self.assertEqual(elfie_1.brain.elfie_id, "艾菲")
        self.assertEqual(elfie_1.memory.encoder.elfie_id, "艾菲")

        # 2. 动态家具注册
        furniture_list = ["bed_1", "bed_2", "chair_1", "chair_2", "wormhole_door"]
        room.register_scene_furniture(furniture_list)

        self.assertIn("bed_1", room.room_state["furniture"])
        self.assertEqual(room.room_state["furniture"]["bed_1"]["occupant"], None)

        # 3. 室内广播路由机制测试
        room.broadcast_speech("艾菲", "我们一起去玩滑梯吧哒！")

        # 艾菲自己不应该收到自己说的话
        self.assertEqual(len(room.sensory_buffers["艾菲"]), 0)
        # 雪球应该把听到的话存入待处理的感官缓冲
        self.assertEqual(len(room.sensory_buffers["雪球"]), 1)
        self.assertIn("艾菲 说道", room.sensory_buffers["雪球"][0])

        # 消费消息
        sensory_input = room.consume_pending_sensory_input("雪球")
        self.assertIn("我们一起去玩滑梯吧哒", sensory_input)
        self.assertEqual(len(room.sensory_buffers["雪球"]), 0)  # 消费后自动清空

        # 4. 物理姿态与家具占用联动
        room.update_elfie_posture("艾菲", "lying", "bed_1")
        self.assertEqual(room.room_state["elfies_status"]["艾菲"]["posture"], "lying")
        self.assertEqual(
            room.room_state["elfies_status"]["艾菲"]["target_furniture"], "bed_1"
        )
        self.assertEqual(room.room_state["furniture"]["bed_1"]["occupant"], "艾菲")

        # 精灵艾菲搬去 chair_1
        room.update_elfie_posture("艾菲", "sitting", "chair_1")
        self.assertEqual(
            room.room_state["furniture"]["bed_1"]["occupant"], None
        )  # 原床位自动释放
        self.assertEqual(
            room.room_state["furniture"]["chair_1"]["occupant"], "艾菲"
        )  # 新椅子被占用

    def test_engine_coordinator_reflex_and_main_compatibility(self):
        """测试 ElfieNestEngine 和 Coordinator 配合时的反射以及对 main.py 调用的完美兼容"""
        engine = ElfieNestEngine(ws_port=8899, http_port=8080)

        # 注册精灵
        elfie = Elfie()
        engine.coordinator.register_elfie("艾菲", elfie)

        # 模拟触觉碰撞 (揉尾巴)
        engine.coordinator.trigger_elfie_interaction(
            "艾菲", "艾菲", event_type="collision"
        )

        # 消费触觉
        tactile = engine.coordinator.consume_tactile("艾菲")
        self.assertEqual(tactile["gentle_stroke"], 1.0)
        self.assertEqual(tactile["impact_force"], 1.5)

        # 模拟 Godot 握手上报
        engine.api_server._trigger_callbacks(
            "register_scene",
            {"furniture": ["bed_1", "chair_1"], "cameras": ["overview"]},
        )
        self.assertIn("bed_1", engine.room.room_state["furniture"])

        # 模拟 Godot 模型寻路到达反馈
        engine.api_server._trigger_callbacks(
            "arrived_at", {"elfie_id": "艾菲", "target": "bed_1"}
        )
        self.assertEqual(
            engine.room.room_state["elfies_status"]["艾菲"]["posture"], "lying"
        )
        self.assertEqual(
            engine.room.room_state["furniture"]["bed_1"]["occupant"], "艾菲"
        )


if __name__ == "__main__":
    unittest.main()
