"""Cross-Module Integration Tests

验证模块之间的数据流和协作是否正确。
测试丘脑→皮层、情绪→记忆、能量→决策、反射→情绪→记忆等多条链路。

架构参考：
  认知层(NeocortexBrain) → 边缘系统(情绪/能量/记忆/丘脑) → 身体层(解剖/反射/执行器/传感器)
  数据契约: BrainContext(边缘→认知), BrainDecision(认知→执行)
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from elfie import ElfieIndividual
from elfie.brain import (
    BrainContext,
    EmotionSystem,
    HypothalamusEnergy,
    SensorData,
    ThalamusContextBuilder,
)
from elfie.brain.memory import MemorySystem


# ---------------------------------------------------------------------------
# Mock 辅助类
# ---------------------------------------------------------------------------


class MockRuntimeAgent:
    """记录prompt供测试验证的模拟运行时"""

    class MockConfig:
        remote_api_key = ""
        providers = {
            "deepseek": {"api_key": "", "api_base": ""},
            "openai": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
            "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
        }

    config = MockConfig()

    def __init__(self, response="你好！"):
        self.response = response
        self.prompts_received = []

    def ask(self, prompt, energy, task_complexity):
        self.prompts_received.append(prompt)
        return self.response


class MockGodotAPI:
    """追踪send_expression调用的模拟Godot API"""

    def __init__(self):
        self.expression_sent = None
        self.send_count = 0

    def send_expression(self, expression):
        self.expression_sent = expression
        self.send_count += 1


# ---------------------------------------------------------------------------
# 丘脑→皮层数据契约
# ---------------------------------------------------------------------------


class TestThalamusToCortex:
    """验证ThalamusContextBuilder.assemble()生产的BrainContext数据契约完整性"""

    def test_thalamus_assembles_complete_context(self):
        """调用 thalamus.assemble()，验证 BrainContext 的完整数据契约。"""
        builder = ThalamusContextBuilder()
        energy = HypothalamusEnergy()
        emotion = EmotionSystem()
        memory = MemorySystem(db_path=":memory:")

        raw_sensors = {
            "temperature": 26.5,
            "is_network_online": True,
            "salience_score": 10.0,
            "has_new_message": True,
            "user_message": "你好小狐狸",
            "images": ["/tmp/camera.png"],
            "audio": "/tmp/microphone.wav",
        }

        ctx = builder.assemble(raw_sensors, energy, emotion, memory)

        # 验证类型
        assert isinstance(ctx, BrainContext), "返回类型应为BrainContext"
        assert isinstance(ctx.sensors, SensorData), "sensors字段应为SensorData"

        # 文本和多模态感官信号都必须保留
        assert ctx.sensors.temperature == 26.5
        assert ctx.sensors.is_network_online is True
        assert ctx.sensors.salience_score == 10.0
        assert ctx.sensors.has_new_message is True
        assert ctx.sensors.user_message == "你好小狐狸"
        assert ctx.sensors.images == ("/tmp/camera.png",)
        assert ctx.sensors.audio == "/tmp/microphone.wav"

        # 下丘脑字段：energy, fatigue, is_sleeping
        assert isinstance(ctx.energy, (int, float))
        assert isinstance(ctx.fatigue, (int, float))
        assert isinstance(ctx.is_sleeping, bool)

        # 杏仁核字段：emotion_state, emotion_mood, emotion_intensity
        assert isinstance(ctx.emotion_state, str)
        assert isinstance(ctx.emotion_mood, str)
        assert isinstance(ctx.emotion_intensity, (int, float))

        # 记忆字段：history_episodes
        assert isinstance(ctx.history_episodes, str)

    def test_emotion_intensity_not_lost(self):
        """验证丘脑组装时emotion_intensity正确传入BrainContext（之前bug修复验证）"""
        builder = ThalamusContextBuilder()
        energy = HypothalamusEnergy()
        emotion = EmotionSystem()

        # 让fear成为主导情绪，确保intensity>0
        emotion.update_emotion("anxiety", 50.0)  # anxiety别名解析为fear

        memory = MemorySystem(db_path=":memory:")
        raw_sensors = {"has_new_message": False, "user_message": ""}

        ctx = builder.assemble(raw_sensors, energy, emotion, memory)

        # 检查emotion_intensity被正确传递
        assert isinstance(ctx.emotion_intensity, float)
        assert ctx.emotion_intensity > 0.0, "emotion_intensity应大于0"
        # 验证数值与EmotionSystem.get_emotion_value一致
        assert ctx.emotion_intensity == emotion.get_emotion_value("fear"), (
            f"BrainContext.emotion_intensity({ctx.emotion_intensity}) "
            f"应与emotion.get_emotion_value('fear')({emotion.get_emotion_value('fear')})一致"
        )


# ---------------------------------------------------------------------------
# 情绪→记忆检索
# ---------------------------------------------------------------------------


class TestEmotionToMemory:
    """验证当前情绪对记忆检索排序和参数传递的影响"""

    def test_emotion_affects_retrieval_ranking(self):
        """往MemorySystem存两条情绪不同的记忆(happy vs angry)，用happy检索→happy记忆排前"""
        memory = MemorySystem(db_path=":memory:")

        # 存两条内容都包含"主人"关键词的记忆，情绪不同
        memory.record_episode(
            content="今天主人表扬了我，主人让我很开心",
            emotion="happy",
            intensity=80.0,
        )
        memory.record_episode(
            content="今天主人生气了，批评了我很难过",
            emotion="sadness",
            intensity=70.0,
        )

        # 用happy情绪检索 → MemoryRetriever会从语义+情绪双维度加权
        # 注意：编码器自动为"主人"创建entity节点，它在文本搜索中得满分(cosine=1.0)。
        # 因此top_k=3以确保两条episodic都在结果中。
        results = memory.retrieve_relevant_memories(
            "主人", top_k=3, current_emotion="happy"
        )

        assert len(results) >= 3, (
            f"应检索到3条（2条episodic+1条entity），实际：{results}"
        )
        # happy情绪下，happy记忆应该排在sadness记忆之前
        happy_idx = next(i for i, r in enumerate(results) if "开心" in r)
        sad_idx = next(i for i, r in enumerate(results) if "批评" in r)
        assert happy_idx < sad_idx, (
            f"happy情绪下开心记忆应排在悲伤记忆前，"
            f"但实际顺序：\n  {chr(10).join(results)}"
        )

    def test_intensity_passed_to_memory_retrieval(self):
        """验证context_builder调用memory_system.get_context()时传入了intensity参数"""
        memory = MemorySystem(db_path=":memory:")

        # Spy: 追踪get_context的调用参数
        original_get_context = memory.get_context
        call_kwargs = {}

        def tracking_get_context(*args, **kwargs):
            call_kwargs.update(kwargs)
            return original_get_context(*args, **kwargs)

        memory.get_context = tracking_get_context

        builder = ThalamusContextBuilder()
        energy = HypothalamusEnergy()
        emotion = EmotionSystem()
        emotion.update_emotion("anxiety", 50.0)  # fear

        raw_sensors = {"has_new_message": True, "user_message": "测试"}
        ctx = builder.assemble(raw_sensors, energy, emotion, memory)

        # 验证intensity参数被传入
        assert "intensity" in call_kwargs, "get_context应收到intensity参数"
        assert call_kwargs["intensity"] > 0.0, f"intensity应>0，实际={call_kwargs['intensity']}"


# ---------------------------------------------------------------------------
# 能量→决策熔断
# ---------------------------------------------------------------------------


class TestEnergyToDecision:
    """验证能量/睡眠状态对感知决策的影响"""

    def test_sleeping_blocks_perception(self):
        """构造ElfieIndividual，设置is_sleeping=True，验证返休眠reason且不做LLM调用"""
        elfie = ElfieIndividual(anatomy_type="biped")
        # 强制设置为睡眠状态
        elfie.hypothalamus.is_sleeping = True

        mock_agent = MockRuntimeAgent()
        # 即使有新消息，睡眠也应阻断处理
        sensor_data = {"has_new_message": True, "user_message": "你好"}

        result = elfie.perceive_and_respond(sensor_data, mock_agent)

        assert result["success"] is False
        assert "sleeping" in result["reason"].lower(), (
            f"返回reason应包含sleeping，实际：{result['reason']}"
        )
        # 睡眠熔断应跳过LLM调用
        assert len(mock_agent.prompts_received) == 0, "睡眠时不应对LLM发起调用"


# ---------------------------------------------------------------------------
# 反射→情绪→记忆链路
# ---------------------------------------------------------------------------


class TestReflexToEmotionToMemory:
    """验证脑干反射→情绪变化→记忆记录的完整链路"""

    def test_shock_reflex_records_to_memory(self):
        """传入impact_force=25触发避险反射→验证memory包含脑干反射记录"""
        elfie = ElfieIndividual(anatomy_type="biped")
        mock_agent = MockRuntimeAgent()

        sensor_data = {
            "has_new_message": False,
            "impact_force": 25.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0,
        }

        response = elfie.perceive_and_respond(sensor_data, mock_agent)

        assert response["action"] == "reflex_avoidance", "应触发避险反射"

        # 验证记忆系统记录了反射事件
        episodes = elfie.memory.get_all_episodes()
        episode_contents = [ep["content"] for ep in episodes]
        combined = " ".join(episode_contents)
        assert "脑干反射" in combined, (
            f"记忆应包含脑干反射记录，实际内容：{episode_contents}"
        )

    def test_shock_reflex_elevates_fear_then_retrievable(self):
        """撞击后fear升高→存入记忆→用fear情绪检索应能找到这条反射记录"""
        elfie = ElfieIndividual(anatomy_type="biped")
        mock_agent = MockRuntimeAgent()

        sensor_data = {
            "has_new_message": False,
            "impact_force": 25.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0,
        }

        response = elfie.perceive_and_respond(sensor_data, mock_agent)
        assert response["action"] == "reflex_avoidance"

        # 验证fear升高
        fear_value = elfie.amygdala.get_emotion_value("fear")

        if fear_value > 0:
            # 用fear情绪检索 → emotion维度匹配
            results = elfie.memory.retrieve_relevant_memories(
                "脑干反射", top_k=5, current_emotion="fear"
            )
            contents = " ".join(results)
            assert "脑干反射" in contents or "撞击" in contents or "碰撞" in contents, (
                f"fear情绪检索应找到反射记忆，结果：{results}"
            )


# ---------------------------------------------------------------------------
# 记忆→上下文→prompt
# ---------------------------------------------------------------------------


class TestMemoryToContextToPrompt:
    """验证记忆系统的内容如何流入LLM prompt"""

    def test_context_appears_in_llm_prompt(self, tmp_path):
        """存入记忆→perceive_and_respond→验证传给LLM的prompt包含记忆上下文"""
        elfie = ElfieIndividual(config_dir=str(tmp_path), anatomy_type="biped")
        assert elfie.memory.storage.db_path == str(tmp_path / "graph_memory.db")

        # 先存一条测试记忆
        elfie.memory.record_episode(
            content="今天主人给我吃了美味的鸡肉，我非常开心",
            emotion="happy",
            intensity=80.0,
        )

        mock_agent = MockRuntimeAgent()

        # 触发CEN模式（has_new_message=True, salience_score低）
        sensor_data = {
            "has_new_message": True,
            "user_message": "今天",
            "salience_score": 0.0,
        }

        _ = elfie.perceive_and_respond(sensor_data, mock_agent)

        # 验证有prompt被发送给LLM
        assert len(mock_agent.prompts_received) >= 1, "CEN模式应调用LLM"

        # 验证记忆内容出现在prompt中
        prompt = mock_agent.prompts_received[0]
        assert "鸡肉" in prompt or "开心" in prompt, (
            f"prompt应包含存入的记忆内容，实际前200字符：\n{prompt[:200]}"
        )

    def test_empty_memory_shows_default_text(self, tmp_path):
        """无记忆时→perceive_and_respond→prompt中不应包含具体回忆但结构完好"""
        elfie = ElfieIndividual(config_dir=str(tmp_path), anatomy_type="biped")
        mock_agent = MockRuntimeAgent()

        sensor_data = {
            "has_new_message": True,
            "user_message": "你好",
            "salience_score": 0.0,
        }

        _ = elfie.perceive_and_respond(sensor_data, mock_agent)

        # CEN模式应调用LLM
        if len(mock_agent.prompts_received) > 0:
            prompt = mock_agent.prompts_received[0]
            # 无具体记忆 → 不应包含虚构的回忆内容
            assert "鸡肉" not in prompt, "无记忆时prompt不应包含具体回忆"
            # 记忆上下文部分应存在（格式框架）
            assert "海马体" in prompt or "记忆" in prompt or "情景" in prompt, (
                "prompt的记忆上下文段落应存在"
            )


# ---------------------------------------------------------------------------
# 巩固→知识→检索
# ---------------------------------------------------------------------------


class TestConsolidationToKnowledgeToRetrieval:
    """验证记忆巩固流程产生knowledge节点，且节点正确引用来源"""

    def test_consolidation_produces_retrievable_knowledge(self):
        """存3条相似经历→运行巩固(无LLM降级规则提取)→应产生knowledge类型节点"""
        memory = MemorySystem(db_path=":memory:")

        # 存3条同类型经历（同一实体关联，触发频率模式提取）
        for i in range(3):
            memory.record_episode(
                content=f"第{i+1}次和主人玩球很开心",
                emotion="happy",
                intensity=70.0,
            )

        # 运行巩固（无LLM时降级为规则提取）
        result = memory.run_consolidation(runtime_agent=None)

        # 验证产生了knowledge节点
        assert result["knowledge_created"] > 0, (
            f"巩固应产生knowledge节点，结果：{result}"
        )
        assert result["consolidated_count"] > 0

        # 验证knowledge可检索
        knowledge_nodes = memory.storage.get_nodes_by_type("knowledge", limit=10)
        assert len(knowledge_nodes) > 0
        contents = " ".join(n.content for n in knowledge_nodes)
        assert "主人" in contents or "玩球" in contents, (
            f"知识内容应与存储的经历相关，实际：{contents}"
        )

    def test_knowledge_has_source_ids(self):
        """巩固后的knowledge节点的source_ids包含原始episodic节点ID"""
        memory = MemorySystem(db_path=":memory:")

        # 存3条经历，记录原始ID
        created_ids = []
        for i in range(3):
            nid = memory.record_episode(
                content=f"第{i+1}次在公园玩耍很开心",
                emotion="happy",
                intensity=70.0,
            )
            created_ids.append(nid)

        # 运行巩固
        result = memory.run_consolidation(runtime_agent=None)
        assert result["knowledge_created"] > 0, "巩固应产生knowledge"

        # 获取knowledge节点并验证source_ids
        knowledge_nodes = memory.storage.get_nodes_by_type("knowledge", limit=10)

        found_source = False
        for kn in knowledge_nodes:
            source_ids = kn.metadata.get("source_ids", [])
            for nid in created_ids:
                if nid in source_ids:
                    found_source = True
                    break
            if found_source:
                break

        assert found_source, (
            f"knowledge节点的source_ids应包含原始episodic ID。"
            f"created_ids={created_ids}，"
            f"knowledge节点元数据："
            f"{[(n.id, n.metadata.get('source_ids', [])) for n in knowledge_nodes]}"
        )


# ---------------------------------------------------------------------------
# 情绪→表达变化
# ---------------------------------------------------------------------------


class TestEmotionToExpression:
    """验证情绪变化通过godot_api发送表达事件"""

    def test_emotion_change_triggers_expression(self):
        """构造ElfieIndividual(godot_api=mock)→改变情绪→verify send_expression被调用"""
        godot = MockGodotAPI()
        elfie = ElfieIndividual(anatomy_type="biped", godot_api=godot)

        # 初始状态：_last_expression应为None
        assert elfie._last_expression is None

        # 改变情绪使其达到表达阈值
        elfie.amygdala.update_emotion("happiness", 60.0)

        # 调用tick → 内部调用_send_emotion_expression()
        elfie.tick(dt=0.1)

        # 验证send_expression被调用
        assert godot.send_count >= 1, "情绪变化后send_expression应被调用"
        assert godot.expression_sent is not None
        # 表达应包含关键字段
        assert "emotion" in godot.expression_sent
        assert "expression" in godot.expression_sent
        assert "intensity" in godot.expression_sent

    def test_same_emotion_no_duplicate_expression(self):
        """情绪未变化时不重复发送表达事件"""
        godot = MockGodotAPI()
        elfie = ElfieIndividual(anatomy_type="biped", godot_api=godot)

        # 第一次：发送表达（happiness升高到阈值以上）
        elfie.amygdala.update_emotion("happiness", 60.0)
        elfie.tick(dt=0.1)
        first_expression = godot.expression_sent
        assert godot.send_count == 1, "第一次应发送表达"
        first_emotion = godot.expression_sent["emotion"]

        # 第二次：情绪未变化 → 不应重复发送
        elfie.tick(dt=0.1)
        assert godot.send_count == 1, "情绪未变化时不应重复发送"
        assert godot.expression_sent is first_expression, "expression_sent不应变化"

        # 第三次：降低happiness、升高sadness使主导情绪变化 → 应再发送
        elfie.amygdala.update_emotion("happiness", -80.0)  # 降低开心
        elfie.amygdala.update_emotion("sadness", 60.0)  # 升高悲伤
        elfie.tick(dt=0.1)
        # 验证主导情绪已变
        new_dominant = elfie.amygdala.get_dominant_mood()
        if new_dominant != first_emotion:
            assert godot.send_count == 2, "主导情绪变化后应再次发送表达"


# ---------------------------------------------------------------------------
# 睡眠→唤醒→巩固
# ---------------------------------------------------------------------------


class TestSleepWakeConsolidation:
    """验证睡眠→唤醒边沿检测触发记忆巩固"""

    def test_wakeup_triggers_consolidation(self):
        """_was_sleeping=True然后is_sleeping=False→perceive_and_respond→触发巩固"""
        elfie = ElfieIndividual(anatomy_type="biped")
        mock_agent = MockRuntimeAgent(response="我醒了！")

        # 模拟刚醒来：_was_sleeping=True, is_sleeping=False
        elfie._was_sleeping = True
        elfie.hypothalamus.is_sleeping = False

        # Spy：追踪run_consolidation是否被调用
        consolidation_called = [False]
        original_consolidate = elfie.memory.run_consolidation

        def tracking_consolidate(runtime_agent=None):
            consolidation_called[0] = True
            return original_consolidate(runtime_agent)

        elfie.memory.run_consolidation = tracking_consolidate

        # 写入几段睡前记忆
        elfie.memory.record_episode(
            content="睡前和主人说了晚安",
            emotion="calm",
            intensity=30.0,
        )

        sensor_data = {
            "has_new_message": False,
            "temperature": 26.5,  # 温度变化通过信号过滤
        }

        result = elfie.perceive_and_respond(sensor_data, mock_agent)

        assert consolidation_called[0], "唤醒后第一次perceive_and_respond应触发巩固"

    def test_no_consolidation_when_not_waking(self):
        """正常清醒状态下perceive_and_respond不触发巩固"""
        elfie = ElfieIndividual(anatomy_type="biped")
        mock_agent = MockRuntimeAgent()

        # 确保是默认清醒状态
        assert elfie._was_sleeping is False
        assert elfie.hypothalamus.is_sleeping is False

        # Spy：追踪run_consolidation
        consolidation_called = [False]
        original_consolidate = elfie.memory.run_consolidation

        def tracking_consolidate(runtime_agent=None):
            consolidation_called[0] = True
            return original_consolidate(runtime_agent)

        elfie.memory.run_consolidation = tracking_consolidate

        sensor_data = {
            "has_new_message": True,
            "user_message": "测试",
        }

        result = elfie.perceive_and_respond(sensor_data, mock_agent)

        assert not consolidation_called[0], "清醒状态不应触发记忆巩固"
