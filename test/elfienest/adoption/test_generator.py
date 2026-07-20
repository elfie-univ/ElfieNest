"""测试 adoption.py — ElfieGenerator 领养生成器

测试 Big Five 范围、YAML 文件结构、ElfieProfile 解析兼容性。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

from elfienest.adoption.config import get_allowed_species_ids
from elfienest.adoption.generator import (
    PERSONALITY_PRESETS,
    VALID_BUILDS,
    VALID_HEIGHTS,
    ElfieGenerator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def generator() -> ElfieGenerator:
    return ElfieGenerator()


@pytest.fixture
def config_dir(tmp_path: Path) -> str:
    d = tmp_path / "elfies" / "test_elfie"
    d.mkdir(parents=True)
    return str(d)


def _generate(generator: ElfieGenerator, config_dir: str, **kwargs) -> dict:
    """辅助：用默认值调用 generate，允许覆盖参数。"""
    params = {
        "name": "小白",
        "anatomy_type": "biped",
        "personality_style": "好奇探索",
        "height": "standard",
        "build": "standard",
        "config_dir": config_dir,
        "elfie_id": "test_elfie",
    }
    params.update(kwargs)
    return generator.generate(**params)


# ===================================================================
# Big Five 范围测试
# ===================================================================


class TestBigFiveRanges:
    def test_all_six_styles_in_range(self, generator: ElfieGenerator, tmp_path: Path) -> None:
        """6 种风格各生成 1 个 → big_five 5 个维度都在 [0, 1]。"""
        for style in PERSONALITY_PRESETS:
            cfg = str(tmp_path / f"elfie_{style}")
            result = _generate(generator, cfg, personality_style=style, elfie_id=f"test_{style}")
            # 读取 personality.yaml 验证
            with open(Path(result["config_dir"]) / "personality.yaml") as f:
                data = yaml.safe_load(f)
            bf = data["big_five"]
            for trait in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
                val = bf[trait]
                assert 0.0 <= val <= 1.0, f"{style}/{trait} = {val} out of [0,1]"

    def test_random_style_high_variance(self, generator: ElfieGenerator, tmp_path: Path) -> None:
        """完全随机风格生成 10 次 → 每个维度有较大方差。"""
        traits = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
        values: Dict[str, List[float]] = {t: [] for t in traits}

        for i in range(10):
            cfg = str(tmp_path / f"random_{i}")
            result = _generate(generator, cfg, personality_style="完全随机", elfie_id=f"r{i}")
            with open(Path(result["config_dir"]) / "personality.yaml") as f:
                data = yaml.safe_load(f)
            bf = data["big_five"]
            for t in traits:
                values[t].append(bf[t])

        for t in traits:
            vals = values[t]
            # 至少 5 个不同值 或 标准差 > 0.1
            distinct = len({round(v, 4) for v in vals})
            std = math.sqrt(sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals))
            assert distinct >= 5 or std > 0.1, (
                f"{t}: distinct={distinct}, std={std:.4f} — not enough variance"
            )


# ===================================================================
# YAML 文件结构
# ===================================================================


class TestYamlStructure:
    def test_three_yaml_files_exist(self, generator: ElfieGenerator, config_dir: str) -> None:
        """生成的 YAML 文件存在。"""
        result = _generate(generator, config_dir)
        base = Path(result["config_dir"])
        assert (base / "personality.yaml").exists()
        assert (base / "capabilities.yaml").exists()
        assert (base / "system_limits.yaml").exists()

    def test_personality_has_big_five(self, generator: ElfieGenerator, config_dir: str) -> None:
        """personality.yaml 包含 big_five 节。"""
        _generate(generator, config_dir)
        with open(Path(config_dir) / "personality.yaml") as f:
            data = yaml.safe_load(f)
        assert "big_five" in data
        bf = data["big_five"]
        assert set(bf.keys()) == {
            "openness", "conscientiousness", "extraversion",
            "agreeableness", "neuroticism",
        }

    def test_capabilities_has_actuators(self, generator: ElfieGenerator, config_dir: str) -> None:
        """capabilities.yaml 包含 actuators 节。"""
        _generate(generator, config_dir)
        with open(Path(config_dir) / "capabilities.yaml") as f:
            data = yaml.safe_load(f)
        assert "actuators" in data

    def test_system_limits_has_limits(self, generator: ElfieGenerator, config_dir: str) -> None:
        """system_limits.yaml 包含 limits 节。"""
        _generate(generator, config_dir)
        with open(Path(config_dir) / "system_limits.yaml") as f:
            data = yaml.safe_load(f)
        assert "limits" in data
        assert "energy" in data["limits"]
        assert "runtime_usage" in data["limits"]
        assert data["limits"]["runtime_usage"]["observe_only"] is True
        assert "lingbi" not in data["limits"]


# ===================================================================
# ElfieProfile 兼容性
# ===================================================================


class TestElfieProfileCompatibility:
    def test_elfie_profile_loads(self, generator: ElfieGenerator, config_dir: str) -> None:
        """ElfieProfile(config_dir) 能成功加载。"""
        _generate(generator, config_dir)
        # 动态导入避免类加载顺序问题
        from elfie.brain.cognition.profile import ElfieProfile
        profile = ElfieProfile(config_dir=config_dir)
        assert profile is not None
        # 验证能读取 big_five
        assert profile.personality is not None

    def test_canonical_profile_contains_legacy_config_sections(
        self, generator: ElfieGenerator, config_dir: str
    ) -> None:
        _generate(generator, config_dir)
        from elfie.profile import ElfieProfileRepository

        profile = ElfieProfileRepository(config_dir).load()
        assert "big_five" in profile.personality
        assert "actuators" in profile.capabilities
        assert "limits" in profile.system_limits

    def test_supported_actions_contains_mandatory(self, generator: ElfieGenerator, config_dir: str) -> None:
        """supported_actions 包含 nod_head + blink_eyes。"""
        # 需要读取 capabilities.yaml 中的 supported_actions
        # 因为 generate 内部调用 _pick_supported_actions，我们直接测试该方法
        for _ in range(20):
            actions = generator._pick_supported_actions()
            assert "nod_head" in actions
            assert "blink_eyes" in actions
            assert 3 <= len(actions) <= 5


# ===================================================================
# height/build 对 energy 影响
# ===================================================================


class TestHeightBuildEffects:
    def test_tall_depletion_greater_than_short(self) -> None:
        """height=tall 时 depletion_rate > short 的对应值。"""
        base_rate = 0.005
        tall_rate = ElfieGenerator._compute_depletion_rate(base_rate, "tall", "standard")
        short_rate = ElfieGenerator._compute_depletion_rate(base_rate, "short", "standard")
        standard_rate = ElfieGenerator._compute_depletion_rate(base_rate, "standard", "standard")
        assert tall_rate > standard_rate > short_rate
        assert abs(tall_rate - 0.0055) < 0.0001  # 0.005 * 1.1
        assert abs(short_rate - 0.0045) < 0.0001  # 0.005 * 0.9

    def test_plump_depletion_greater_than_slim(self) -> None:
        """build=plump 时 depletion_rate > slim 的对应值。"""
        base_rate = 0.005
        plump_rate = ElfieGenerator._compute_depletion_rate(base_rate, "standard", "plump")
        slim_rate = ElfieGenerator._compute_depletion_rate(base_rate, "standard", "slim")
        standard_rate = ElfieGenerator._compute_depletion_rate(base_rate, "standard", "standard")
        assert plump_rate > standard_rate > slim_rate
        assert abs(plump_rate - 0.00525) < 0.0001  # 0.005 * 1.05
        assert abs(slim_rate - 0.00475) < 0.0001  # 0.005 * 0.95

    def test_tall_plump_compounds(self) -> None:
        """tall + plump 叠加。"""
        base_rate = 0.005
        rate = ElfieGenerator._compute_depletion_rate(base_rate, "tall", "plump")
        expected = 0.005 * 1.1 * 1.05
        assert abs(rate - expected) < 0.0001


# ===================================================================
# 参数校验
# ===================================================================


class TestValidation:
    def test_unknown_personality_style_raises(self, generator: ElfieGenerator, config_dir: str) -> None:
        """未知 personality_style → ValueError。"""
        with pytest.raises(ValueError, match="未知"):
            _generate(generator, config_dir, personality_style="nonexistent")

    def test_unknown_anatomy_type_raises(self, generator: ElfieGenerator, config_dir: str) -> None:
        """未知 anatomy_type → ValueError。"""
        with pytest.raises(ValueError, match="无效 anatomy_type"):
            _generate(generator, config_dir, anatomy_type="tripled")

    def test_unknown_height_raises(self, generator: ElfieGenerator, config_dir: str) -> None:
        """未知 height → ValueError。"""
        with pytest.raises(ValueError, match="无效 height"):
            _generate(generator, config_dir, height="super_tall")

    def test_unknown_build_raises(self, generator: ElfieGenerator, config_dir: str) -> None:
        """未知 build → ValueError。"""
        with pytest.raises(ValueError, match="无效 build"):
            _generate(generator, config_dir, build="extra_wide")


# ===================================================================
# 类常量暴露
# ===================================================================


class TestConstants:
    def test_personality_presets_exposed(self) -> None:
        """PERSONALITY_PRESETS 是类属性并可访问。"""
        assert len(ElfieGenerator.PERSONALITY_PRESETS) == 6
        assert "完全随机" in ElfieGenerator.PERSONALITY_PRESETS

    def test_action_pool_exposed(self) -> None:
        """ACTION_POOL 是类属性。"""
        assert len(ElfieGenerator.ACTION_POOL) >= 6
        assert "nod_head" in ElfieGenerator.ACTION_POOL

    def test_valid_values_constants(self) -> None:
        """VALID 常量定义正确，正式领养配置提供物种而非运动形态。"""
        assert VALID_HEIGHTS == ("short", "standard", "tall")
        assert VALID_BUILDS == ("slim", "standard", "plump")
        assert get_allowed_species_ids() == ("dog", "fox")
