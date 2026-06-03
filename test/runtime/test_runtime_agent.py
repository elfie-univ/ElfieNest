"""RuntimeAgent Unit Tests

Test LLMRuntimeAgent class: initialization, model routing, tool calling, and edge cases.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.agent import RuntimeAgent, UnsupportedModalError
from runtime.config import LLMRuntimeConfig


class TestRuntimeAgentInit:
    """RuntimeAgent 初始化测试"""

    def test_init_default_config(self):
        """默认配置初始化"""
        agent = RuntimeAgent()
        assert agent.config is not None
        assert agent.registry is not None
        assert agent.ollama_manager is not None
        assert agent.permission_manager is not None
        assert agent.router is not None

    def test_init_with_custom_config(self):
        """自定义配置初始化"""
        config = LLMRuntimeConfig(temperature=0.5, max_tokens=2000)
        agent = RuntimeAgent(config)
        assert agent.config.temperature == 0.5
        assert agent.config.max_tokens == 2000

    def test_plugins_mounted(self):
        """插件挂载测试"""
        agent = RuntimeAgent()
        assert agent.search_plugin is not None
        assert agent.sandbox_plugin is not None
        assert agent.skills_evolution_plugin is not None


class TestModelRouting:
    """模型路由测试"""

    def test_ask_local_routing_high_energy_simple_task(self):
        """高精力简单任务走本地模型"""
        agent = RuntimeAgent()
        with patch.object(agent.router, "route_request") as mock_route:
            mock_route.return_value = ("local", {"mode": "local", "reason": "test"})
            with patch.object(agent, "generate") as mock_gen:
                mock_gen.return_value = "Hello"
                result = agent.ask("Hello", energy=80.0, task_complexity=1)
                assert result == "Hello"
                mock_gen.assert_called_once()
                # 验证路由为 local 时使用 local_fast
                call_kwargs = mock_gen.call_args[1]
                assert call_kwargs["model_key"] == "local_fast"

    def test_ask_remote_routing_low_energy(self):
        """低精力触发远程路由"""
        agent = RuntimeAgent()
        with patch.object(agent.router, "route_request") as mock_route:
            mock_route.return_value = ("remote", {"mode": "remote", "reason": "test"})
            with patch.object(agent, "generate") as mock_gen:
                mock_gen.return_value = "Response"
                result = agent.ask("Search for info", energy=20.0, task_complexity=1)
                assert result == "Response"
                call_kwargs = mock_gen.call_args[1]
                assert call_kwargs["model_key"] == "remote_deep"

    def test_ask_complexity_threshold(self):
        """复杂度达到阈值触发深度模型"""
        agent = RuntimeAgent()
        with patch.object(agent.router, "route_request") as mock_route:
            mock_route.return_value = ("remote", {"mode": "remote"})
            with patch.object(agent, "generate") as mock_gen:
                mock_gen.return_value = "Complex result"
                agent.ask("Calculate 123*456", energy=100.0, task_complexity=4)
                call_kwargs = mock_gen.call_args[1]
                assert call_kwargs["model_key"] == "remote_deep"

    def test_ask_default_skills(self):
        """测试默认技能注入"""
        agent = RuntimeAgent()
        with patch.object(agent.router, "route_request") as mock_route:
            mock_route.return_value = ("local", {"mode": "local"})
            with patch.object(agent, "generate") as mock_gen:
                mock_gen.return_value = "Result"
                agent.ask("Hello")
                # 验证默认允许三个技能
                call_kwargs = mock_gen.call_args[1]
                assert "web_search" in call_kwargs["allowed_skills"]
                assert "code_sandbox" in call_kwargs["allowed_skills"]
                assert "skills_evolution" in call_kwargs["allowed_skills"]


class TestGenerate:
    """generate 方法测试"""

    def test_generate_inactive_model_raises(self):
        """非激活模型抛出异常"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "test",
                "is_vision": False,
                "is_audio": False,
                "active": False,
            }
            with pytest.raises(ValueError) as exc_info:
                agent.generate("local_fast", [{"role": "user", "content": "test"}])
            assert "未激活" in str(exc_info.value)

    def test_generate_vision_model_without_support(self):
        """视觉模型不支持时抛出异常"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "ollama",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with pytest.raises(UnsupportedModalError) as exc_info:
                agent.generate(
                    "local_fast",
                    [{"role": "user", "content": "test"}],
                    images=["test.jpg"],
                )
            assert "不支持处理视觉" in str(exc_info.value)

    def test_generate_audio_model_without_support(self):
        """音频模型不支持时抛出异常"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "ollama",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with pytest.raises(UnsupportedModalError) as exc_info:
                agent.generate(
                    "local_fast",
                    [{"role": "user", "content": "test"}],
                    audio="test.mp3",
                )
            assert "不支持原生处理音频" in str(exc_info.value)

    def test_generate_ollama_ensures_service(self):
        """Ollama 模型确保服务启动"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "qwen3.5:0.8b",
                "provider": "ollama",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent.ollama_manager, "ensure_service_started"):
                with patch.object(agent, "_call_llm_api", return_value="test"):
                    result = agent.generate(
                        "local_fast", [{"role": "user", "content": "test"}]
                    )
                    assert result == "test"


class TestSkillInjection:
    """技能注入测试"""

    def test_inject_skills_system_prompt(self):
        """技能系统提示注入"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Hello"}]
        allowed_skills = ["web_search", "code_sandbox"]

        result = agent._inject_skills_system_prompt(messages, allowed_skills)

        # 验证提示被注入到第一条消息
        assert "[SEARCH]" in result[0]["content"]
        assert "[CODE]" in result[0]["content"]

    def test_inject_skills_none_allowed(self):
        """无技能时不添加技能规则"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Hello"}]

        result = agent._inject_skills_system_prompt(messages, [])

        # 无技能时不添加搜索/代码/技能规则关键词
        assert "[SEARCH]" not in result[0]["content"]
        assert "[CODE]" not in result[0]["content"]
        assert "[WRITE_SKILL]" not in result[0]["content"]

    def test_inject_skills_with_existing_system(self):
        """已有 system message 时的注入"""
        agent = RuntimeAgent()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        allowed_skills = ["web_search"]

        result = agent._inject_skills_system_prompt(messages, allowed_skills)

        # system message 应该被扩展
        assert "You are a helpful assistant" in result[0]["content"]
        assert "[SEARCH]" in result[0]["content"]


class TestToolCalling:
    """工具调用测试"""

    def test_web_search_interception(self):
        """联网搜索拦截"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent, "_call_llm_api") as mock_api:
                # 模拟 LLM 返回带搜索标签的响应
                mock_api.side_effect = [
                    "I need to [SEARCH]latest news[/SEARCH] about AI",
                    "Here is the final answer based on search results.",
                ]
                with patch.object(agent.search_plugin, "search") as mock_search:
                    mock_search.return_value = "Search result: AI is great"

                    result = agent.generate(
                        "remote_deep",
                        [{"role": "user", "content": "What's new in AI?"}],
                        allowed_skills=["web_search"],
                        max_loops=2,
                    )

                    assert mock_search.called
                    assert "final answer" in result

    def test_code_sandbox_interception(self):
        """代码沙箱拦截"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent, "_call_llm_api") as mock_api:
                mock_api.side_effect = [
                    "Let me calculate [CODE]print(123*456)[/CODE] for you",
                    "The result is 56088.",
                ]
                with patch.object(agent.sandbox_plugin, "execute") as mock_exec:
                    mock_exec.return_value = {"stdout": "56088", "stderr": ""}

                    _ = agent.generate(
                        "remote_deep",
                        [{"role": "user", "content": "Calculate 123*456"}],
                        allowed_skills=["code_sandbox"],
                        max_loops=2,
                    )

                    assert mock_exec.called

    def test_skills_evolution_write(self):
        """技能自进化沉淀拦截"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent, "_call_llm_api") as mock_api:
                mock_api.side_effect = [
                    "I'll create a skill [WRITE_SKILL]my_math|def add(a,b): return a+b[/WRITE_SKILL]",
                    "Skill created successfully.",
                ]
                with patch.object(
                    agent.skills_evolution_plugin, "write_skill"
                ) as mock_write:
                    mock_write.return_value = "Skill my_math created!"

                    _ = agent.generate(
                        "remote_deep",
                        [{"role": "user", "content": "Create a math skill"}],
                        allowed_skills=["skills_evolution"],
                        max_loops=2,
                    )

                    assert mock_write.called

    def test_skills_evolution_run(self):
        """技能运行拦截"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent, "_call_llm_api") as mock_api:
                mock_api.side_effect = [
                    "Running skill [RUN_SKILL]my_math|1,2[/RUN_SKILL]",
                    "The result is 3.",
                ]
                with patch.object(
                    agent.skills_evolution_plugin, "run_skill"
                ) as mock_run:
                    mock_run.return_value = {
                        "exit_code": 0,
                        "stdout": "3",
                        "stderr": "",
                    }

                    _ = agent.generate(
                        "remote_deep",
                        [{"role": "user", "content": "Run my_math with 1,2"}],
                        allowed_skills=["skills_evolution"],
                        max_loops=2,
                    )

                    assert mock_run.called

    def test_list_skills_interception(self):
        """技能列表拦截"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent, "_call_llm_api") as mock_api:
                mock_api.side_effect = [
                    "Let me [LIST_SKILLS]list all skills[/LIST_SKILLS]",
                    "Here are your skills.",
                ]
                with patch.object(
                    agent.skills_evolution_plugin, "list_skills"
                ) as mock_list:
                    mock_list.return_value = "Skill1, Skill2"

                    _ = agent.generate(
                        "remote_deep",
                        [{"role": "user", "content": "List skills"}],
                        allowed_skills=["skills_evolution"],
                        max_loops=2,
                    )

                    assert mock_list.called


class TestMultimodalPayload:
    """多模态载荷测试"""

    def test_assemble_multimodal_ollama(self):
        """Ollama 多模态载荷组装"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Describe this image"}]

        # 创建临时图片文件
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_img = f.name

        try:
            result = agent._assemble_multimodal_payload(
                messages, [temp_img], None, "ollama"
            )
            assert "images" in result[-1]
            assert len(result[-1]["images"]) == 1
        finally:
            os.unlink(temp_img)

    def test_assemble_multimodal_cloud(self):
        """云端多模态载荷组装"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Describe this image"}]

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake image data")
            temp_img = f.name

        try:
            result = agent._assemble_multimodal_payload(
                messages, [temp_img], None, "openai"
            )
            # 云端格式为 list
            assert isinstance(result[-1]["content"], list)
        finally:
            os.unlink(temp_img)

    def test_assemble_multimodal_missing_file(self):
        """缺失文件抛出异常"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Describe"}]

        with pytest.raises(FileNotFoundError):
            agent._assemble_multimodal_payload(
                messages, ["nonexistent.jpg"], None, "ollama"
            )

    def test_assemble_audio_payload(self):
        """音频载荷组装"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Transcribe this"}]

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"fake audio data")
            temp_audio = f.name

        try:
            result = agent._assemble_multimodal_payload(
                messages, None, temp_audio, "openai"
            )
            content = result[-1]["content"]
            assert isinstance(content, list)
            # 验证有音频内容
            has_audio = any(
                isinstance(c, dict) and c.get("type") == "input_audio" for c in content
            )
            assert has_audio
        finally:
            os.unlink(temp_audio)


class TestEdgeCases:
    """边界情况测试"""

    def test_generate_max_loops_timeout(self):
        """超过最大循环次数抛出超时异常"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            # 持续返回带搜索标签，触发循环直到超时
            with patch.object(agent, "_call_llm_api") as mock_api:
                mock_api.return_value = "I need to [SEARCH]query[/SEARCH]"
                with patch.object(agent.search_plugin, "search", return_value="result"):
                    with pytest.raises(TimeoutError) as exc_info:
                        agent.generate(
                            "remote_deep",
                            [{"role": "user", "content": "test"}],
                            allowed_skills=["web_search"],
                            max_loops=2,
                        )
                    assert "超出了迭代轮数上限" in str(exc_info.value)

    def test_generate_no_user_message(self):
        """无 user message 时的处理"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.return_value = {
                "name": "test-model",
                "provider": "openai",
                "is_vision": False,
                "is_audio": False,
                "active": True,
            }
            with patch.object(agent, "_call_llm_api", return_value="response"):
                result = agent.generate(
                    "remote_deep",
                    [{"role": "assistant", "content": "previous"}],
                    allowed_skills=[],
                )
                assert result == "response"

    def test_model_key_not_in_catalog(self):
        """无效模型 key 抛出 KeyError"""
        agent = RuntimeAgent()
        with patch.object(agent.registry, "get_model_info") as mock_info:
            mock_info.side_effect = KeyError("invalid_key")

            with pytest.raises(KeyError):
                agent.generate("invalid_key", [{"role": "user", "content": "test"}])

    def test_empty_allowed_skills(self):
        """空技能列表只保留通用说明"""
        agent = RuntimeAgent()
        messages = [{"role": "user", "content": "Hello"}]

        result = agent._inject_skills_system_prompt(messages, [])

        # 空技能不添加具体规则但保留通用说明
        assert "[SEARCH]" not in result[0]["content"]
        assert "[CODE]" not in result[0]["content"]


class TestCallLLMApi:
    """底层 API 调用测试"""

    def test_ollama_api_call(self):
        """Ollama API 调用"""
        agent = RuntimeAgent()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = (
                b'{"message": {"content": "test response"}}'
            )
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = agent._call_llm_api(
                "ollama",
                "qwen3.5:0.8b",
                [{"role": "user", "content": "hello"}],
                0.7,
                1500,
            )

            assert result == "test response"

    def test_cloud_api_call(self):
        """云端 API 调用"""
        agent = RuntimeAgent()
        agent.config.providers["deepseek"]["api_key"] = "test-key"
        agent.config.providers["deepseek"]["api_base"] = "https://api.test.com"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = (
                b'{"choices": [{"message": {"content": "cloud response"}}]}'
            )
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = agent._call_llm_api(
                "deepseek",
                "deepseek-chat",
                [{"role": "user", "content": "hello"}],
                0.7,
                1500,
            )

            assert result == "cloud response"

    def test_api_missing_base_url(self):
        """缺少 API Base 时抛出异常"""
        agent = RuntimeAgent()
        agent.config.providers["test"] = {"api_key": "test-key", "api_base": ""}

        with pytest.raises(ValueError) as exc_info:
            agent._call_llm_api(
                "test", "test-model", [{"role": "user", "content": "hello"}], 0.7, 1500
            )

        assert "未找到" in str(exc_info.value)
        assert "API Base" in str(exc_info.value)
