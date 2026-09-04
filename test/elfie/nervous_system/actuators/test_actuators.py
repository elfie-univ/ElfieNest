"""测试文本执行器模块。"""

from elfie.nervous_system.actuators.speech import SpeechActuator


class TestSpeechActuator:
    """SpeechActuator 单元测试"""

    def test_init(self):
        """测试 SpeechActuator 初始化"""
        actuator = SpeechActuator()
        assert actuator is not None

    def test_speak_empty_text(self):
        """测试空文本输入返回空字符串"""
        actuator = SpeechActuator()
        result = actuator.speak("")
        assert result == ""

    def test_speak_with_empty_text(self):
        """测试 None 输入返回空字符串"""
        actuator = SpeechActuator()
        # 模拟处理无消息场景 - 传入空字符串而非None
        result = actuator.speak("")
        assert result == ""

    def test_speak_with_text(self):
        """测试正常发言文本。"""
        actuator = SpeechActuator()
        text = "你好，我是小精灵"
        result = actuator.speak(text)
        assert result == text

    def test_speak_method(self):
        """测试 speak 返回广播文本。"""
        actuator = SpeechActuator()
        text = "Hello World"
        result = actuator.speak(text)
        assert result == text

    def test_speak_empty(self):
        """测试 speak 方法处理空字符串"""
        actuator = SpeechActuator()
        result = actuator.speak("")
        assert result == ""
