"""情绪自适应加权模块的单元测试。"""


from elfie.brain.memory.emotion_weighting import EmotionWeighting
from elfie.brain.memory.node_types import NodeTypes


class TestEmotionWeighting:
    """EmotionWeighting 类的全部测试"""

    def setup_method(self):
        self.ew = EmotionWeighting()

    # ── get_weights ──────────────────────────────────────────────

    def test_get_weights_known_emotion(self):
        """5种已知情绪应返回各自预定义的权重配置"""
        for emotion, expected in EmotionWeighting.EMOTION_WEIGHTS.items():
            weights = self.ew.get_weights(emotion)
            assert weights == expected, (
                f"情绪 '{emotion}' 的权重应为 {expected}，实际为 {weights}"
            )

    def test_get_weights_unknown_emotion(self):
        """未知情绪应返回默认权重"""
        weights = self.ew.get_weights("nonexistent_emotion")
        assert weights == EmotionWeighting.DEFAULT_WEIGHTS, (
            f"未知情绪应返回默认权重 {EmotionWeighting.DEFAULT_WEIGHTS}，"
            f"实际为 {weights}"
        )

    # ── compute_score ────────────────────────────────────────────

    def test_compute_score(self):
        """综合得分应根据权重、记忆强度和类型增强正确计算"""
        score = self.ew.compute_score(
            semantic_score=0.8,
            mood_score=0.5,
            recency_score=0.6,
            spread_score=0.4,
            memory_strength=1.0,
            node_type=NodeTypes.EPISODIC,
            emotion="calm",
        )
        # calm: 0.55*0.8 + 0.15*0.5 + 0.20*0.6 + 0.10*0.4 = 0.44+0.075+0.12+0.04 = 0.675
        # episodic boost = 1.0
        # 0.675 * 1.0 * 1.0 = 0.675
        expected = 0.675
        assert abs(score - expected) < 1e-10, (
            f"calm 情绪下计算得分应约为 {expected}，实际为 {score}"
        )

    def test_compute_score_with_type_boost(self):
        """类型增强系数应影响最终得分"""
        # 相同输入，不同节点类型 → 得分不同
        episodic_score = self.ew.compute_score(
            semantic_score=0.5, mood_score=0.5, recency_score=0.5,
            spread_score=0.5, memory_strength=1.0,
            node_type=NodeTypes.EPISODIC, emotion="happy",
        )
        pattern_score = self.ew.compute_score(
            semantic_score=0.5, mood_score=0.5, recency_score=0.5,
            spread_score=0.5, memory_strength=1.0,
            node_type=NodeTypes.PATTERN, emotion="happy",
        )
        # episodic boost=1.0, pattern boost=1.5
        # 所以 pattern_score 应为 episodic_score 的 1.5 倍
        assert abs(pattern_score - episodic_score * 1.5) < 1e-10, (
            f"PATTERN 类型得分 ({pattern_score}) 应为 "
            f"EPISODIC 得分 ({episodic_score}) 的 1.5 倍"
        )

    # ── compute_mood_score ───────────────────────────────────────

    def test_compute_mood_score_same(self):
        """同情绪应返回 1.0 × intensity"""
        score = self.ew.compute_mood_score(
            memory_emotion="happy", current_emotion="happy",
            memory_intensity=0.8,
        )
        assert abs(score - 0.8) < 1e-10, (
            f"同情绪得分应为 0.8，实际为 {score}"
        )

    def test_compute_mood_score_different(self):
        """不同情绪应返回 0.3 × intensity"""
        score = self.ew.compute_mood_score(
            memory_emotion="sadness", current_emotion="happy",
            memory_intensity=0.8,
        )
        assert abs(score - 0.24) < 1e-10, (
            f"不同情绪得分应为 0.24（= 0.3×0.8），实际为 {score}"
        )

    # ── compute_recency_score ────────────────────────────────────

    def test_compute_recency_score(self):
        """时间近度得分应按实际时间差正确计算"""
        # 1小时内 → 1.0
        score_1h = self.ew.compute_recency_score(
            "2026-06-06T08:00:00", "2026-06-06T08:30:00",
        )
        assert abs(score_1h - 1.0) < 1e-10

        # 1天内 → 0.8
        score_1d = self.ew.compute_recency_score(
            "2026-06-05T10:00:00", "2026-06-06T08:00:00",
        )
        assert abs(score_1d - 0.8) < 1e-10

        # 7天内 → 0.5
        score_7d = self.ew.compute_recency_score(
            "2026-05-31T10:00:00", "2026-06-06T08:00:00",
        )
        assert abs(score_7d - 0.5) < 1e-10

        # 30天内 → 0.3
        score_30d = self.ew.compute_recency_score(
            "2026-05-10T10:00:00", "2026-06-06T08:00:00",
        )
        assert abs(score_30d - 0.3) < 1e-10

        # 更早 → 0.1
        score_old = self.ew.compute_recency_score(
            "2026-01-01T10:00:00", "2026-06-06T08:00:00",
        )
        assert abs(score_old - 0.1) < 1e-10

    # ── get_type_boost ───────────────────────────────────────────

    def test_get_type_boost(self):
        """各节点类型应返回正确的增强系数"""
        assert self.ew.get_type_boost(NodeTypes.EPISODIC) == 1.0
        assert self.ew.get_type_boost(NodeTypes.ENTITY) == 1.1
        assert self.ew.get_type_boost(NodeTypes.KNOWLEDGE) == 1.3
        assert self.ew.get_type_boost(NodeTypes.PATTERN) == 1.5
        # 未知类型应返回 1.0
        assert self.ew.get_type_boost("unknown_type") == 1.0
