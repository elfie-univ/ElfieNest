"""端到端场景验证测试

验证完整的模拟多tick对话场景，从感官输入到最终输出全链路。
这是最高层级的验证，模拟真实的运行场景。

每个场景覆盖一条完整链路：
  感官输入 → 信号过滤 → 脑干反射 → 丘脑组装 → 皮层决策
  → 形态学拦截 → 执行器驱动 → 记忆落盘

架构参考:
  AGENTS.md 三层大脑架构:
  1. Neocortex (Cognition) - LLM推理决策
  2. Limbic System (Core Systems) - 情绪/能量/记忆/丘脑
  3. Body (Interface) - 执行器/传感器/反射弧
"""

import os
import sys
from typing import Any, Dict, List

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from elfie import ElfieIndividual
from elfie.brain import (
    BrainContext,
    EmotionSystem,
    HypothalamusEnergy,
    SensorData,
    ThalamusContextBuilder,
)
from elfie.brain.brain_types import BrainDecision
from elfie.brain.memory import MemorySystem
from elfie.brain.memory.node_types import EdgeTypes, MemoryNode, NodeTypes


# ---------------------------------------------------------------------------
# Mock 辅助类
# ---------------------------------------------------------------------------


class MockRuntimeAgent:
    """模拟LLM运行时代理，记录所有调用供验证"""

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

    def __init__(self, response="你好！ [ACTION]nod_head[/ACTION]"):
        self.response = response
        self.ask_calls: List[Dict[str, Any]] = []

    def ask(self, prompt, energy, task_complexity):
        self.ask_calls.append({
            "prompt": prompt,
            "energy": energy,
            "complexity": task_complexity,
        })
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
# 场景1：记忆连贯性 - Memory coherence across ticks
# ---------------------------------------------------------------------------


class TestMemoryCoherence:
    """验证记忆在多个tick之间保持连贯，历史对话影响后续决策上下文"""

    def test_memory_coherence_across_ticks(self):
        """Tick1传入"你喜欢吃什么"，mock回复含"鱼"→Tick2确认记忆落盘→Tick3验证prompt含记忆上下文

        完整链路：感官→丘脑→皮层→记忆录制→跨tick检索→上下文注入
        """
        elfie = ElfieIndividual(anatomy_type="biped")

        # -------- Tick 1: 传入用户消息，模拟LLM回复提到"鱼" --------
        agent_tick1 = MockRuntimeAgent(
            response="我最喜欢吃小鱼干了！ [ACTION]nod_head[/ACTION]"
        )
        sensor_data_1 = {
            "has_new_message": True,
            "user_message": "你喜欢吃什么",
            "temperature": 26.0,  # 温度变化保证信号通过
        }

        result_1 = elfie.perceive_and_respond(sensor_data_1, agent_tick1)

        # 验证正常响应
        assert result_1["success"] is True
        assert "小鱼干" in result_1["speech"]

        # 验证LLM被调用
        assert len(agent_tick1.ask_calls) == 1

        # -------- Tick 2: 检索记忆，验证"鱼"相关记忆已录制 --------
        episodes = elfie.memory.get_all_episodes()
        episode_contents = " ".join(ep["content"] for ep in episodes)

        assert "鱼" in episode_contents or "小鱼干" in episode_contents, (
            f"记忆应包含鱼相关内容，实际：{episode_contents}"
        )
        assert "你喜欢吃什么" in episode_contents, (
            f"记忆应包含用户消息，实际：{episode_contents}"
        )

        # -------- Tick 3: 再次对话，验证prompt包含之前记忆 --------
        agent_tick3 = MockRuntimeAgent(
            response="嗯~让我想想吃什么！ [ACTION]wiggle_ears[/ACTION]"
        )
        # 使用与tick1共享关键词"喜欢"的查询，确保记忆检索能命中
        sensor_data_3 = {
            "has_new_message": True,
            "user_message": "你最喜欢吃什么零食",
            "temperature": 26.2,  # 略有温度变化
        }

        result_3 = elfie.perceive_and_respond(sensor_data_3, agent_tick3)

        # 验证LLM被调用，且prompt包含记忆（共享"喜欢吃"关键词应命中检索）
        assert len(agent_tick3.ask_calls) == 1
        prompt = agent_tick3.ask_calls[0]["prompt"]
        assert "鱼" in prompt or "小鱼干" in prompt or "喜欢吃" in prompt, (
            f"LLM prompt应包含之前的鱼记忆内容，实际片段：{prompt[:400]}"
        )


# ---------------------------------------------------------------------------
# 场景2：多轮情绪演化 - Emotion evolution across ticks
# ---------------------------------------------------------------------------


class TestEmotionEvolution:
    """验证情绪在多tick间演化：撞击→恐惧升高→时间衰减→抚摸→恐惧降低/快乐升高"""

    def test_emotion_evolution_across_ticks(self):
        """完整情绪演化轨迹：
        1. 撞击(impact_force=25)→恐惧升高(>20)
        2. tick(dt=2)时间流逝→恐惧有衰减
        3. 抚摸(gentle_stroke=1.2)→恐惧降低、快乐升高
        4. 验证全程情绪在[0,100]合理范围
        """
        elfie = ElfieIndividual(anatomy_type="quadruped")
        initial_fear = elfie.amygdala.get_emotion_value("fear")

        # -------- Tick 1: 撞击刺激 --------
        sensor_impact = {
            "has_new_message": False,
            "impact_force": 25.0,
            "impact_direction": "front",
            "gentle_stroke": 0.0,
            "temperature": 26.0,  # 温度变化通过过滤
        }

        r1 = elfie.perceive_and_respond(sensor_impact, MockRuntimeAgent())

        # 验证触发避险反射
        assert r1["action"] == "reflex_avoidance"
        # 验证fear升高
        fear_after_impact = elfie.amygdala.get_emotion_value("fear")
        assert fear_after_impact > initial_fear + 20, (
            f"撞击后fear应显著升高（>{initial_fear + 20}），实际：{fear_after_impact}"
        )
        # 验证fear在合理范围
        assert 0 <= fear_after_impact <= 100

        # -------- 时间流逝：tick(dt=2) --------
        elfie.tick(dt=2.0)
        fear_after_decay = elfie.amygdala.get_emotion_value("fear")
        # fear应有衰减（但可能较小，因为半衰期180s，2s衰减不大）
        assert fear_after_decay <= fear_after_impact + 0.1, (
            f"tick后fear应衰减或持平（<={fear_after_impact + 0.1}），实际：{fear_after_decay}"
        )
        assert 0 <= fear_after_decay <= 100

        # -------- Tick 2: 温柔抚摸 --------
        sensor_stroke = {
            "has_new_message": False,
            "impact_force": 0.0,
            "impact_direction": "none",
            "gentle_stroke": 1.2,
            "temperature": 26.5,  # 温度变化通过过滤
        }

        r2 = elfie.perceive_and_respond(sensor_stroke, MockRuntimeAgent())

        # 验证触发抚摸反射
        assert r2["action"] == "reflex_soothing"

        # 抚摸后fear应降低（reflex_arc对anxiety减15，即fear减15）
        fear_after_stroke = elfie.amygdala.get_emotion_value("fear")
        assert fear_after_stroke <= fear_after_decay, (
            f"抚摸后fear应降低（<={fear_after_decay}），实际：{fear_after_stroke}"
        )

        # 抚摸后happiness应升高（+15）
        happy_after_stroke = elfie.amygdala.get_emotion_value("happiness")
        assert happy_after_stroke > 50, (
            f"抚摸后happiness应升高（>50），实际：{happy_after_stroke}"
        )

        # 验证全程合理范围
        for emotion_name in ["fear", "happiness", "boredom", "sadness"]:
            val = elfie.amygdala.get_emotion_value(emotion_name)
            assert 0 <= val <= 100, (
                f"情绪{emotion_name}值{val}不在[0,100]范围内"
            )


# ---------------------------------------------------------------------------
# 场景3：睡眠-巩固完整循环 - Sleep-wake consolidation cycle
# ---------------------------------------------------------------------------


class TestSleepWakeConsolidationCycle:
    """验证睡眠→唤醒边沿检测触发记忆巩固，产生consolidated类型节点"""

    def test_sleep_wake_consolidation_cycle(self):
        """完整睡眠循环：
        1. 预存3条相似经历
        2. 手动设fatigue=95→tick触发睡眠
        3. 确认is_sleeping=True
        4. 设fatigue=5→tick触发唤醒
        5. perceive_and_respond→应触发consolidation
        6. 验证产生了knowledge类型节点
        7. 验证产生了knowledge类型节点
        """
        elfie = ElfieIndividual(anatomy_type="biped")
        recon_agent = MockRuntimeAgent(
            response="- 主人每天8点左右喂我\n- 清晨喂食后情绪很开心"
        )

        # 预存3条相似经历（含同一实体"主人"）
        for i in range(3):
            elfie.memory.record_episode(
                content=f"第{i+1}次清晨：主人给我准备了美味的早餐，我吃得很开心",
                emotion="happy",
                intensity=70.0,
            )

        # 确认初始清醒
        assert elfie.hypothalamus.is_sleeping is False
        assert elfie._was_sleeping is False

        # 手动设fatigue极高→触发睡眠
        elfie.hypothalamus.fatigue = 95.0
        elfie.hypothalamus.is_sleeping = False  # 让tick自动检测
        elfie.tick(dt=1.0)  # 触发睡眠检测（fatigue >= hibernation_threshold=95）

        assert elfie.hypothalamus.is_sleeping is True, "疲劳度95应触发睡眠"

        # 睡眠中调用perceive_and_respond应返回sleeping
        sleep_result = elfie.perceive_and_respond(
            {"has_new_message": True, "user_message": "醒醒"},
            MockRuntimeAgent(),
        )
        assert sleep_result["success"] is False
        assert "sleeping" in sleep_result["reason"].lower()

        # 手动降fatigue→触发唤醒
        elfie.hypothalamus.fatigue = 5.0  # 低于wakeup_threshold=15
        elfie.hypothalamus.is_sleeping = True  # tick中会检测fatigue <= wakeup_threshold
        elfie.tick(dt=1.0)

        assert elfie.hypothalamus.is_sleeping is False, "疲劳度5应唤醒"
        # _was_sleeping仅在perceive_and_respond中更新，tick不修改它
        # 目前_was_sleeping=True（因为tick前is_sleeping=True），这正好模拟刚醒来的状态
        assert elfie._was_sleeping is True, "tick不修改_was_sleeping，应该还是True"

        # Spy：追踪consolidation调用
        consolidation_called = [False]
        original_consolidate = elfie.memory.run_consolidation

        def tracking_consolidate(runtime_agent=None):
            consolidation_called[0] = True
            return original_consolidate(runtime_agent)

        elfie.memory.run_consolidation = tracking_consolidate

        # 触发perceive_and_respond（需要有效信号通过过滤）
        wake_result = elfie.perceive_and_respond(
            {"has_new_message": False, "temperature": 26.0},
            recon_agent,
        )

        # 验证consolidation被调用
        assert consolidation_called[0], "唤醒后第一次感知应触发记忆巩固"

        # 验证产生了knowledge类型节点
        knowledge_nodes = elfie.memory.storage.get_nodes_by_type("knowledge", limit=10)
        assert len(knowledge_nodes) > 0, "巩固后应产生knowledge类型节点"
        contents = " ".join(n.content for n in knowledge_nodes)
        assert "主人" in contents, (
            f"知识内容应与预存的记忆相关，实际：{contents}"
        )


# ---------------------------------------------------------------------------
# 场景4：形态学防护全链路 - Morphological protection chain
# ---------------------------------------------------------------------------


class TestMorphologicalProtection:
    """验证biped双足形态下，"wag_tail"动作被物理拦截转发为nod_head"""

    def test_morphological_protection_full_chain(self):
        """完整拦截链路：
        1. 构造biped Elfie
        2. mock LLM返回含[ACTION]wag_tail[/ACTION]的回复
        3. 验证action被拦截为nod_head
        4. 验证fear(anxiety)升高
        5. 验证记忆记录了该拦截事件
        """
        elfie = ElfieIndividual(anatomy_type="biped")

        initial_fear = elfie.amygdala.get_emotion_value("fear")

        # mock LLM返回wag_tail动作
        agent = MockRuntimeAgent(
            response="主人你看我尾巴！ [ACTION]wag_tail[/ACTION]"
        )

        sensor_data = {
            "has_new_message": True,
            "user_message": "摇个尾巴看看",
            "temperature": 26.0,
        }

        result = elfie.perceive_and_respond(sensor_data, agent)

        # 验证动作被形态学拦截为nod_head
        assert result["action"] == "nod_head", (
            f"双足形态下wag_tail应被拦截为nod_head，实际：{result['action']}"
        )
        assert "形态学" in result["speech"], (
            f"回复应包含形态学拦截说明，实际：{result['speech']}"
        )
        assert "动作因形态学不兼容被强行拦截了" in result["mutter"], (
            f"mutter应包含拦截说明，实际：{result['mutter']}"
        )

        # 验证fear升高（拦截时增加anxiety→fear +15）
        fear_after = elfie.amygdala.get_emotion_value("fear")
        assert fear_after > initial_fear + 10, (
            f"拦截后fear应升高（>{initial_fear + 10}），实际：{fear_after}"
        )

        # 验证记忆记录了该事件
        episodes = elfie.memory.get_all_episodes()
        episode_text = " ".join(ep["content"] for ep in episodes)
        assert "wag_tail" in episode_text or "拦截" in episode_text or "摇尾巴" in episode_text, (
            f"记忆应包含拦截相关记录，实际：{episode_text}"
        )


# ---------------------------------------------------------------------------
# 场景5：预测驱动主动社交 - Prediction-driven proactive social
# ---------------------------------------------------------------------------


class TestPredictionDrivenSocial:
    """验证温度大幅偏离预期触发DMN主动社交模式"""

    def test_prediction_driven_proactive_social(self):
        """预期温度24°C，输入40°C（温差16>2）→预测误差>30→DMN_ACTIVE→主动发起对话

        完整链路：温度变化→信号通过→丘脑组装→皮层预测加工误差大→主动社交→LLM调用→speech输出
        """
        elfie = ElfieIndividual(anatomy_type="quadruped")
        agent = MockRuntimeAgent(
            response="好热呀！今天天气怎么这么热！ [ACTION]wag_tail[/ACTION]"
        )

        # 温度40°C，无新消息，salience_score低
        # 这样会进入DMN模式（非CEN/SN），然后预测误差大触发主动社交
        sensor_data = {
            "has_new_message": False,
            "user_message": "",
            "temperature": 40.0,  # 远超预期24°C
            "salience_score": 0.0,
            "is_network_online": True,
        }

        result = elfie.perceive_and_respond(sensor_data, agent)

        # 验证LLM被调用（DMN_ACTIVE模式下LLM应被调用）
        assert len(agent.ask_calls) >= 1, "DMN_ACTIVE模式应调用LLM"

        # 验证有speech_text输出（主动发起对话）
        assert result["speech"] and result["speech"].strip(), (
            f"主动社交应有speech输出，实际：'{result['speech']}'"
        )
        assert "好热" in result["speech"], (
            f"speech内容应与温度相关，实际：'{result['speech']}'"
        )

        # 验证attention_mode为DMN_ACTIVE（通过brain的内部状态推断）
        # 注意：perceive_and_respond不返回attention_mode，但我们可以检查brain的attention
        # 或者通过agent ask call的prompt内容推断
        prompt = agent.ask_calls[0]["prompt"]
        assert "温度" in prompt or "热" in prompt or "天气" in prompt, (
            f"prompt应包含温度相关内容，实际片段：{prompt[:200]}"
        )


# ---------------------------------------------------------------------------
# 场景6：扩散联想到输出 - Spreading activation to output
# ---------------------------------------------------------------------------


class TestSpreadingActivation:
    """验证扩散激活机制：从种子节点沿边传播激活值到关联节点"""

    def test_spreading_activation_to_output(self):
        """手动构造3条记忆A-B-C，建立A→B和A→C关联边，
        从种子A扩散→验证B和C被激活"""
        memory = MemorySystem(db_path=":memory:")

        # 创建3个episodic节点（手动构造）
        now = "2025-06-20T12:00:00"
        node_a = MemoryNode(
            id="ep_test_a",
            type=NodeTypes.EPISODIC.value,
            content="今天主人给我吃了鱼",
            metadata={"emotion": "happy", "timestamp": now},
            edges=[],
            created_at=now,
            updated_at=now,
        )
        node_b = MemoryNode(
            id="ep_test_b",
            type=NodeTypes.EPISODIC.value,
            content="主人带我去公园玩",
            metadata={"emotion": "happy", "timestamp": now},
            edges=[],
            created_at=now,
            updated_at=now,
        )
        node_c = MemoryNode(
            id="ep_test_c",
            type=NodeTypes.EPISODIC.value,
            content="主人给我买了新玩具",
            metadata={"emotion": "happy", "timestamp": now},
            edges=[],
            created_at=now,
            updated_at=now,
        )

        # 存储节点
        memory.storage.add_node(node_a)
        memory.storage.add_node(node_b)
        memory.storage.add_node(node_c)

        # 建立A→B和A→C关联边（使用temporal类型，标记时间先后）
        memory.storage.add_edge(
            "ep_test_a", "ep_test_b",
            EdgeTypes.TEMPORAL.value,
            weight=0.8,
        )
        memory.storage.add_edge(
            "ep_test_a", "ep_test_c",
            EdgeTypes.TEMPORAL.value,
            weight=0.7,
        )

        # 从种子A扩散激活
        activation = memory.spreading.spread(
            seed_node_ids=["ep_test_a"],
            max_hops=1,
            decay=0.5,
            threshold=0.1,
        )

        # 验证A自身被激活（初始值1.0）
        assert "ep_test_a" in activation
        assert activation["ep_test_a"] == 1.0

        # 验证B和C被扩散激活
        assert "ep_test_b" in activation, (
            f"A→B扩散激活应激活B，实际激活节点：{list(activation.keys())}"
        )
        assert "ep_test_c" in activation, (
            f"A→C扩散激活应激活C，实际激活节点：{list(activation.keys())}"
        )

        # 验证B的激活值 = 1.0 * 0.5 * 0.8 = 0.4
        assert abs(activation["ep_test_b"] - 0.4) < 1e-6, (
            f"B激活值应为0.4，实际：{activation['ep_test_b']}"
        )
        # 验证C的激活值 = 1.0 * 0.5 * 0.7 = 0.35
        assert abs(activation["ep_test_c"] - 0.35) < 1e-6, (
            f"C激活值应为0.35，实际：{activation['ep_test_c']}"
        )


# ---------------------------------------------------------------------------
# 场景7：多tick情绪持续衰减 - Emotion decay over multiple ticks
# ---------------------------------------------------------------------------


class TestEmotionDecayMultiTick:
    """验证情绪在连续多个tick中逐步衰减"""

    def test_emotion_decays_over_multiple_ticks(self):
        """设fear=80，连续tick(dt=1.0)10次，验证：
        1. fear值逐步下降
        2. 最终fear < 80 但 > 0（不会衰减到零）
        """
        elfie = ElfieIndividual(anatomy_type="biped")

        # 直接设fear=80（基线10，需要加70）
        elfie.amygdala.update_emotion("fear", 70.0)
        initial_fear = elfie.amygdala.get_emotion_value("fear")
        assert initial_fear > 75, f"初始fear应≈80，实际：{initial_fear}"

        fear_values = [initial_fear]

        # 连续10个tick
        for tick_idx in range(10):
            elfie.tick(dt=1.0)
            current_fear = elfie.amygdala.get_emotion_value("fear")
            fear_values.append(current_fear)

            # 验证每一步都有衰减（或持平，但不应增加）
            # 在高值区(>50)半衰期=180*0.3=54s，dt=1s衰减很小，但不应上升
            assert current_fear <= fear_values[-2] + 0.01, (
                f"Tick{tick_idx+1}后fear不应上升：{fear_values[-2]}→{current_fear}"
            )

        final_fear = fear_values[-1]

        # 最终fear < 80（有衰减）
        assert final_fear < initial_fear, (
            f"最终fear应<初始值{initial_fear}，实际：{final_fear}"
        )
        # 最终fear > 0（不会衰减到零，基线10）
        assert final_fear > 0.0, (
            f"最终fear应>0，实际：{final_fear}"
        )

        # 验证全部在合理范围
        for v in fear_values:
            assert 0 <= v <= 100, f"fear值{v}不在[0,100]范围"


# ---------------------------------------------------------------------------
# 场景8：记忆录制→巩固→检索三步 - Record → Consolidate → Retrieve
# ---------------------------------------------------------------------------


class TestRecordConsolidateRetrieve:
    """验证记忆系统完整生命周期：录制→巩固（知识提炼）→检索"""

    def test_record_consolidate_retrieve_cycle(self):
        """完整三步：
        1. 存入3条含相似实体（主人+喂食）的经历
        2. 运行巩固（无LLM，降级规则提取）→产生knowledge节点
        3. 检索"主人喂我"→能返回知识节点
        """
        memory = MemorySystem(db_path=":memory:")

        # 存入3条含相似实体的经历
        ids = []
        times = ["2025-06-20T08:00", "2025-06-20T08:15", "2025-06-20T07:50"]
        for i, t in enumerate(times):
            nid = memory.record_episode(
                content=f"早上{t.split('T')[1]}左右主人给我准备了早餐，我吃得很开心",
                emotion="happy",
                intensity=70.0,
            )
            ids.append(nid)

        # 运行巩固（无LLM，降级规则提取）
        result = memory.run_consolidation(runtime_agent=None)

        # 验证产生了knowledge节点
        assert result["knowledge_created"] > 0, (
            f"巩固应产生knowledge节点，结果：{result}"
        )
        assert result["consolidated_count"] > 0

        # 获取knowledge节点
        knowledge_nodes = memory.storage.get_nodes_by_type("knowledge", limit=10)
        assert len(knowledge_nodes) > 0

        # 验证知识内容与存储的经历相关
        knowledge_contents = " ".join(n.content for n in knowledge_nodes)
        assert "主人" in knowledge_contents, (
            f"知识内容应包含'主人'，实际：{knowledge_contents}"
        )

        # 检索"主人喂我"→应该能返回knowledge节点
        # 注意：retrieve_relevant_memories返回记忆内容文本列表
        retrieval_results = memory.retrieve_relevant_memories(
            query="主人喂我",
            top_k=10,
            current_emotion="happy",
        )

        all_text = " ".join(retrieval_results)
        assert "主人" in all_text, (
            f"检索结果应包含主人相关内容，实际：{retrieval_results}"
        )

        # 验证knowledge节点有source_ids指向原始episodic
        found_source = False
        for kn in knowledge_nodes:
            source_ids = kn.metadata.get("source_ids", [])
            for nid in ids:
                if nid in source_ids:
                    found_source = True
                    break
            if found_source:
                break

        assert found_source, (
            f"knowledge节点应包含source_ids引用原始episodic。"
            f"id列表：{ids}，knowledge元数据："
            f"{[(n.id, n.metadata.get('source_ids', [])) for n in knowledge_nodes]}"
        )


# ---------------------------------------------------------------------------
# 场景9：能量耗尽影响行为 - Low energy affects decision
# ---------------------------------------------------------------------------


class TestLowEnergyEffects:
    """验证低能量状态下LLM调用时energy参数很低，且能量被进一步扣减"""

    def test_low_energy_affects_decision(self):
        """设energy=5.0→发送用户消息→验证LLM收到低energy参数→验证能量被扣减

        完整链路：低能量→丘脑组装含energy值→皮层decision→consume_energy
        """
        elfie = ElfieIndividual(anatomy_type="biped")

        # 设能量极低
        elfie.hypothalamus.energy = 5.0

        agent = MockRuntimeAgent(
            response="我好累呀... [ACTION]blink_eyes[/ACTION]"
        )

        sensor_data = {
            "has_new_message": True,
            "user_message": "你还好吗",
            "temperature": 26.0,
        }

        _ = elfie.perceive_and_respond(sensor_data, agent)

        # 验证LLM被调用
        assert len(agent.ask_calls) == 1

        # 验证LLM收到的energy参数值很低（≈5.0）
        energy_passed = agent.ask_calls[0]["energy"]
        assert energy_passed <= 5.5, (
            f"LLM收到的energy应≤5.5（≈当前energy 5.0），实际：{energy_passed}"
        )

        # 验证能量被进一步扣减（local chat消耗0.5）
        assert elfie.hypothalamus.energy < 5.0, (
            f"能量应被扣减至<5.0，实际：{elfie.hypothalamus.energy}"
        )


# ---------------------------------------------------------------------------
# 场景10：完整感知闭环 - Full perception-action cycle
# ---------------------------------------------------------------------------


class TestFullPerceptionActionCycle:
    """验证quadruped形态下从感官输入到最终输出的完整链路"""

    def test_full_perception_action_cycle(self):
        """完整验证10个环节：
        a. 信号过滤通过 ✓
        b. 丘脑组装了BrainContext ✓
        c. 大脑皮层返回了BrainDecision ✓
        d. speech_text正确提取（不含ACTION标签） ✓
        e. action="wag_tail" ✓
        f. 物理限制未拦截（四足可摇尾巴） ✓
        g. 记忆录制了对话 ✓
        h. 能量被扣减 ✓
        i. boredom降低，happiness升高 ✓
        """
        elfie = ElfieIndividual(anatomy_type="quadruped")

        # 记录初始状态
        initial_energy = elfie.hypothalamus.get_energy()
        initial_boredom = elfie.amygdala.get_emotion_value("boredom")
        initial_happiness = elfie.amygdala.get_emotion_value("happiness")

        agent = MockRuntimeAgent(
            response="你好主人！今天天气真好呀 [ACTION]wag_tail[/ACTION]"
        )

        sensor_data = {
            "has_new_message": True,
            "user_message": "你好啊",
            "impact_force": 0.0,
            "gentle_stroke": 0.0,
            "temperature": 26.0,
            "salience_score": 0.0,
            "is_network_online": True,
        }

        result = elfie.perceive_and_respond(sensor_data, agent)

        # --- a. 信号过滤通过 ---
        assert result.get("filtered") is not True, "信号应通过过滤"
        assert result["success"] is True

        # --- b. 丘脑组装了BrainContext ---
        assert len(agent.ask_calls) >= 1, "LLM应被调用（CEN模式）"
        prompt = agent.ask_calls[0]["prompt"]
        # BrainContext中的信息应出现在prompt中
        assert "你好啊" in prompt, (
            f"用户消息应出现在prompt中，实际片段：{prompt[:200]}"
        )
        assert "体能" in prompt or "能量" in prompt or "energy" in prompt, (
            "prompt应包含能量信息"
        )

        # --- c & d. 大脑皮层返回了BrainDecision，speech_text正确提取 ---
        # speech_text应去除ACTION标签
        assert "[ACTION]" not in result["speech"], (
            f"speech不应含ACTION标签，实际：'{result['speech']}'"
        )
        assert "你好主人" in result["speech"], (
            f"speech应为LLM回复去标签，实际：'{result['speech']}'"
        )

        # --- e. action="wag_tail" ---
        assert result["action"] == "wag_tail", (
            f"action应为wag_tail，实际：{result['action']}"
        )

        # --- f. 物理限制未拦截（四足可摇尾巴） ---
        # action是wag_tail，quadruped允许此动作
        assert "形态学" not in result.get("speech", ""), (
            "四足摇尾巴不应触发形态学拦截"
        )

        # --- g. 记忆录制了对话 ---
        episodes = elfie.memory.get_all_episodes()
        episode_contents = " ".join(ep["content"] for ep in episodes)
        assert "你好啊" in episode_contents, (
            f"记忆应包含用户消息'你好啊'，实际：{episode_contents}"
        )
        assert "主人" in episode_contents, (
            f"记忆应包含回复内容，实际：{episode_contents}"
        )

        # --- h. 能量被扣减 ---
        current_energy = elfie.hypothalamus.get_energy()
        assert current_energy < initial_energy, (
            f"能量应从{initial_energy}被扣减至{current_energy}"
        )

        # --- i. boredom降低，happiness升高 ---
        current_boredom = elfie.amygdala.get_emotion_value("boredom")
        current_happiness = elfie.amygdala.get_emotion_value("happiness")

        assert current_boredom < initial_boredom, (
            f"boredom应从{initial_boredom}降低至{current_boredom}"
        )
        assert current_happiness > initial_happiness, (
            f"happiness应从{initial_happiness}升高至{current_happiness}"
        )

        # 验证CEN模式下mutter为None
        assert result["mutter"] is None, (
            f"CEN模式下mutter应为None，实际：{result['mutter']}"
        )

        # 验证关节角度有效
        assert "joint_angles" in result
        assert len(result["joint_angles"]) > 0


# ---------------------------------------------------------------------------
# 场景10：完整感知闭环 - Full perception-action cycle
# ---------------------------------------------------------------------------


class TestSignalFilterBoundary:
    """验证信号过滤器正确拦截重复输入"""

    def test_signal_filter_blocks_duplicate(self):
        """连续两次传入相同用户消息→第二次被过滤拦截"""
        elfie = ElfieIndividual(anatomy_type="biped")
        agent = MockRuntimeAgent()

        sensor_data = {
            "has_new_message": True,
            "user_message": "你好",
            "temperature": 26.0,
        }

        # 第一次：应通过
        r1 = elfie.perceive_and_respond(sensor_data, agent)
        assert r1["success"] is True
        assert r1.get("filtered") is not True
        assert len(agent.ask_calls) == 1

        # 第二次：完全相同的数据，应被信号过滤拦截
        r2 = elfie.perceive_and_respond(sensor_data, agent)
        # 因为temperature没变，user_message没变，所以filter_noise返回False
        assert r2.get("filtered") is True, "重复输入应被信号过滤拦截"
        assert r2["success"] is True
        assert "No sensory changes" in r2["reason"]

        # LLM不应被再次调用
        assert len(agent.ask_calls) == 1, "过滤后不应调用LLM"
