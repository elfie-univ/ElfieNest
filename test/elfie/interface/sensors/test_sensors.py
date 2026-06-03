# -*- coding: utf-8 -*-
"""测试传感器模块 (AudioSensor 和 VisionSensor)"""
import pytest
import sys
import os

sys.path.insert(0, "/Users/zhenli/git-code/ElfieNest")

from elfie.interface.sensors.audio import AudioSensor
from elfie.interface.sensors.vision import VisionSensor


class TestAudioSensor:
    """AudioSensor 单元测试"""

    def test_init(self):
        """测试 AudioSensor 初始化"""
        sensor = AudioSensor()
        assert sensor is not None
        assert sensor.last_heard_audio == ""
        assert sensor.last_audio_source == "ambient"

    def test_receive_virtual_audio_with_text(self):
        """测试正常音频输入"""
        sensor = AudioSensor()
        audio_event = "你好，我是小精灵"
        result = sensor.receive_virtual_audio(audio_event)
        
        assert result == audio_event
        assert sensor.last_heard_audio == audio_event

    def test_receive_virtual_audio_with_source(self):
        """测试带声源的音频输入"""
        sensor = AudioSensor()
        audio_event = "小精灵，过来吃饭啦！"
        source = "user_voice_message"
        
        result = sensor.receive_virtual_audio(audio_event, source)
        
        assert result == audio_event
        assert sensor.last_heard_audio == audio_event
        assert sensor.last_audio_source == source

    def test_receive_virtual_audio_strips_whitespace(self):
        """测试音频输入去除空格"""
        sensor = AudioSensor()
        audio_event = "  轰隆隆！窗外打雷了哒！  "
        
        result = sensor.receive_virtual_audio(audio_event)
        
        assert result == "轰隆隆！窗外打雷了哒！"
        assert sensor.last_heard_audio == "轰隆隆！窗外打雷了哒！"

    def test_receive_virtual_audio_empty_string(self):
        """测试空字符串音频输入"""
        sensor = AudioSensor()
        
        result = sensor.receive_virtual_audio("")
        
        assert result == ""
        assert sensor.last_heard_audio == ""

    def test_receive_virtual_audio_different_sources(self):
        """测试不同声源"""
        sensor = AudioSensor()
        
        # spatial_audio_broadcaster
        sensor.receive_virtual_audio("打雷声", "spatial_audio_broadcaster")
        assert sensor.last_audio_source == "spatial_audio_broadcaster"
        
        # user_voice_message
        sensor.receive_virtual_audio("主人呼唤", "user_voice_message")
        assert sensor.last_audio_source == "user_voice_message"
        
        # elfie_buddy
        sensor.receive_virtual_audio("伙伴呼叫", "elfie_buddy")
        assert sensor.last_audio_source == "elfie_buddy"

    def test_get_last_heard(self):
        """测试获取最后听到的音频"""
        sensor = AudioSensor()
        
        # 初始为空
        assert sensor.get_last_heard() == ""
        
        # 设置后返回值
        sensor.receive_virtual_audio("测试音频")
        assert sensor.get_last_heard() == "测试音频"

    def test_get_last_source(self):
        """测试获取最后音频源"""
        sensor = AudioSensor()
        
        # 初始为 ambient
        assert sensor.get_last_source() == "ambient"
        
        # 设置后返回值
        sensor.receive_virtual_audio("测试", "user_voice_message")
        assert sensor.get_last_source() == "user_voice_message"

    def test_multiple_audio_events(self):
        """测试多次音频输入"""
        sensor = AudioSensor()
        
        sensor.receive_virtual_audio("第一条消息")
        assert sensor.get_last_heard() == "第一条消息"
        
        sensor.receive_virtual_audio("第二条消息")
        assert sensor.get_last_heard() == "第二条消息"
        
        sensor.receive_virtual_audio("第三条消息")
        assert sensor.get_last_heard() == "第三条消息"


class TestVisionSensor:
    """VisionSensor 单元测试"""

    def test_init(self):
        """测试 VisionSensor 初始化"""
        sensor = VisionSensor()
        assert sensor is not None
        assert sensor.last_viewport_image_path == ""
        assert sensor.last_analysis_results == {}

    def test_receive_viewport_snapshot_basic(self):
        """测试基本视口快照接收"""
        sensor = VisionSensor()
        image_path = "/tmp/elfie_viewport.png"
        
        result = sensor.receive_viewport_snapshot(image_path)
        
        assert result["has_image"] is True
        assert result["path"] == image_path
        assert "detected_objects" in result
        assert "description" in result
        assert result["source"] == "Godot_Camera3D_Viewport"

    def test_receive_viewport_snapshot_door_detection(self):
        """测试门检测"""
        sensor = VisionSensor()
        image_path = "/tmp/door_view.png"
        
        result = sensor.receive_viewport_snapshot(image_path)
        
        assert "door" in result["detected_objects"]
        assert "portal" in result["detected_objects"]
        assert "门" in result["description"]

    def test_receive_viewport_snapshot_elfie_detection(self):
        """测试小精灵同伴检测"""
        sensor = VisionSensor()
        image_path = "/tmp/elfie_buddy.png"
        
        result = sensor.receive_viewport_snapshot(image_path)
        
        assert "elfie_buddy" in result["detected_objects"]
        assert "joint_entity" in result["detected_objects"]
        assert "小精灵" in result["description"]

    def test_receive_viewport_snapshot_desk_detection(self):
        """测试桌椅检测"""
        sensor = VisionSensor()
        image_path = "/tmp/desk_chair.png"
        
        result = sensor.receive_viewport_snapshot(image_path)
        
        assert "desk" in result["detected_objects"]
        assert "chair" in result["detected_objects"]
        assert "obstacle" in result["detected_objects"]

    def test_receive_viewport_snapshot_default(self):
        """测试默认视角"""
        sensor = VisionSensor()
        image_path = "/tmp/random_image.png"
        
        result = sensor.receive_viewport_snapshot(image_path)
        
        assert "dormitory_room" in result["detected_objects"]
        assert "wooden_door" in result["detected_objects"]

    def test_receive_viewport_snapshot_updates_last(self):
        """测试快照更新 last 属性"""
        sensor = VisionSensor()
        
        sensor.receive_viewport_snapshot("/tmp/test.png")
        
        assert sensor.last_viewport_image_path == "/tmp/test.png"
        assert sensor.last_analysis_results != {}

    def test_get_last_seen(self):
        """测试获取最后视野"""
        sensor = VisionSensor()
        
        # 初始为空
        assert sensor.get_last_seen() == {}
        
        # 设置后返回值
        sensor.receive_viewport_snapshot("/tmp/test.png")
        result = sensor.get_last_seen()
        
        assert result["has_image"] is True
        assert result["path"] == "/tmp/test.png"

    def test_receive_viewport_multiple_snapshots(self):
        """测试多次快照"""
        sensor = VisionSensor()
        
        sensor.receive_viewport_snapshot("/tmp/first.png")
        first_result = sensor.get_last_seen()
        
        sensor.receive_viewport_snapshot("/tmp/second.png")
        second_result = sensor.get_last_seen()
        
        assert first_result["path"] == "/tmp/first.png"
        assert second_result["path"] == "/tmp/second.png"

    def test_detected_objects_always_includes_base(self):
        """测试检测结果始终包含基础对象"""
        sensor = VisionSensor()
        
        # 测试各种路径
        paths = [
            "/tmp/door.png",
            "/tmp/elfie.png", 
            "/tmp/desk.png",
            "/tmp/random.png"
        ]
        
        for path in paths:
            sensor.receive_viewport_snapshot(path)
            detected = sensor.last_analysis_results["detected_objects"]
            assert "floor" in detected
            assert "walls" in detected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
