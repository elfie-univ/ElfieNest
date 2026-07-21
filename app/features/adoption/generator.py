"""精灵领养生成器：创建稳定外貌档案及现有大脑兼容配置。

Usage::

    from app.features.adoption.generator import ElfieGenerator
    from ai_runtime.storage.data_home import get_elfie_config_dir

    gen = ElfieGenerator()
    result = gen.generate_for_species(
        name="小白",
        species_id="dog",
        personality_style="好奇探索",
        height="tall",
        build="plump",
        config_dir=str(get_elfie_config_dir("elfie_001")),
        elfie_id="elfie_001",
    )
"""

from __future__ import annotations

import logging
import random
import secrets
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from elfie.profile import (
    AppearanceResolver,
    ElfieProfileRepository,
    create_visual_profile,
)

logger = logging.getLogger("app.features.adoption.generator")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PERSONALITY_PRESETS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "活泼好动": {
        "openness": (0.5, 0.8),
        "conscientiousness": (0.3, 0.6),
        "extraversion": (0.75, 0.95),
        "agreeableness": (0.5, 0.8),
        "neuroticism": (0.3, 0.6),
    },
    "安静温顺": {
        "openness": (0.4, 0.7),
        "conscientiousness": (0.6, 0.85),
        "extraversion": (0.2, 0.5),
        "agreeableness": (0.7, 0.95),
        "neuroticism": (0.2, 0.45),
    },
    "好奇探索": {
        "openness": (0.7, 0.95),
        "conscientiousness": (0.4, 0.7),
        "extraversion": (0.6, 0.85),
        "agreeableness": (0.5, 0.8),
        "neuroticism": (0.2, 0.5),
    },
    "胆小害羞": {
        "openness": (0.4, 0.7),
        "conscientiousness": (0.5, 0.8),
        "extraversion": (0.15, 0.4),
        "agreeableness": (0.5, 0.8),
        "neuroticism": (0.6, 0.9),
    },
    "傲娇独立": {
        "openness": (0.5, 0.8),
        "conscientiousness": (0.5, 0.8),
        "extraversion": (0.3, 0.6),
        "agreeableness": (0.3, 0.6),
        "neuroticism": (0.4, 0.7),
    },
    "完全随机": {
        "openness": (0.0, 1.0),
        "conscientiousness": (0.0, 1.0),
        "extraversion": (0.0, 1.0),
        "agreeableness": (0.0, 1.0),
        "neuroticism": (0.0, 1.0),
    },
}

VERBAL_TICKS_POOL: List[str] = ["哒", "喵", "呢", "啦", "呀"]

MUTTER_TEMPLATES_POOL: Dict[str, List[str]] = {
    "bored": [
        "({name}无聊地咬了咬尾巴...)",
        "({name}趴在地上画圈圈...)",
        "(打哈欠) 没人理{name}呀...",
        "({name}盯着窗外发呆...)",
    ],
    "tired": [
        "({name}的耳朵耷拉下来了...)",
        "(揉眼睛) 呼...{name}要睡了...",
        "({name}打了个大大的哈欠...)",
    ],
    "jealous": [
        "哼，主人又忙别的了...",
        "({name}酸溜溜地撇过头...)",
        "({name}小声嘀咕着什么...)",
    ],
}

ACTION_POOL: List[str] = [
    "wag_tail",
    "wiggle_ears",
    "nod_head",
    "shake_head",
    "blink_eyes",
    "mutter",
]

# ---------------------------------------------------------------------------
# 按性格风格的描述 & 招呼语
# ---------------------------------------------------------------------------

DESCRIPTION_TEMPLATES: Dict[str, str] = {
    "活泼好动": "一只活泼好动、精力旺盛的小精灵",
    "安静温顺": "一只安静温顺、乖巧懂事的小精灵",
    "好奇探索": "一只充满好奇心、热爱探索的小精灵",
    "胆小害羞": "一只胆小害羞、容易受惊的小精灵",
    "傲娇独立": "一只傲娇独立、口是心非的小精灵",
    "完全随机": "一只充满了个性、独一无二的小精灵",
}

GREETINGS_POOLS: Dict[str, List[str]] = {
    "活泼好动": [
        "主人好呀！",
        "今天又是元气满满的一天！",
        "嘿嘿，我来啦！",
    ],
    "安静温顺": [
        "主人好...",
        "今天也很安静呢",
        "嗯...我在的",
    ],
    "好奇探索": [
        "咦？这是什么？",
        "主人快来看！",
        "那边好像有什么有趣的东西！",
    ],
    "胆小害羞": [
        "呜...主人好",
        "那个...你、你好...",
        "唔...被发现了",
    ],
    "傲娇独立": [
        "哼，我才不是想你呢！",
        "干嘛呀，人家正忙着呢",
        "哟，你来了啊",
    ],
    "完全随机": [
        "你好呀！",
        "咦，是你啊",
        "嘿嘿，今天天气真不错",
    ],
}

# ---------------------------------------------------------------------------
# 有效值集合
# ---------------------------------------------------------------------------

VALID_HEIGHTS: Tuple[str, ...] = ("short", "standard", "tall")
VALID_BUILDS: Tuple[str, ...] = ("slim", "standard", "plump")
VALID_LEGACY_ANATOMY_TYPES: Tuple[str, ...] = ("biped", "quadruped")


# ===================================================================
# ElfieGenerator
# ===================================================================


class ElfieGenerator:
    """根据领养偏好生成 ``profile.yaml`` 和三个兼容配置文件。

    类属性暴露常量，方便前端 / API 层读取可选值：

    - ``PERSONALITY_PRESETS`` — 6 种性格风格的 Big Five 范围
    - ``VERBAL_TICKS_POOL`` — 口癖池
    - ``MUTTER_TEMPLATES_POOL`` — 碎碎念模板池
    - ``ACTION_POOL`` — 动作池
    """

    PERSONALITY_PRESETS = PERSONALITY_PRESETS
    VERBAL_TICKS_POOL = VERBAL_TICKS_POOL
    MUTTER_TEMPLATES_POOL = MUTTER_TEMPLATES_POOL
    ACTION_POOL = ACTION_POOL

    # ------------------------------------------------------------------
    # 静态辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_big_five(style: str) -> Dict[str, float]:
        """按性格风格随机生成 Big Five 五维分数。"""
        presets = PERSONALITY_PRESETS.get(style)
        if presets is None:
            raise ValueError(f"未知性格风格: {style}")
        return {
            trait: round(random.uniform(lo, hi), 4)
            for trait, (lo, hi) in presets.items()
        }

    @staticmethod
    def _pick_verbal_tick() -> str:
        """随机选一个口癖。"""
        return random.choice(VERBAL_TICKS_POOL)

    @staticmethod
    def _pick_mutter_templates(name: str) -> Dict[str, List[str]]:
        """每个 mood 从池中随机选取 1-2 条，并将 ``{name}`` 替换为精灵名。"""
        result: Dict[str, List[str]] = {}
        for mood, templates in MUTTER_TEMPLATES_POOL.items():
            count = random.randint(1, min(2, len(templates)))
            selected = random.sample(templates, count)
            result[mood] = [t.replace("{name}", name) for t in selected]
        return result

    @staticmethod
    def _pick_greetings(style: str) -> List[str]:
        """按风格返回 2-3 条招呼语。"""
        pool = GREETINGS_POOLS.get(style, GREETINGS_POOLS["完全随机"])
        count = random.randint(2, min(3, len(pool)))
        return random.sample(pool, count)

    @staticmethod
    def _pick_supported_actions() -> List[str]:
        """从动作池中随机选 3-5 个，保证 ``nod_head`` 和 ``blink_eyes`` 必选。"""
        mandatory = ["nod_head", "blink_eyes"]
        optional = [a for a in ACTION_POOL if a not in mandatory]
        count = random.randint(1, 3)  # total = 2 + count => 3..5
        selected = mandatory + random.sample(optional, count)
        random.shuffle(selected)
        return selected

    @staticmethod
    def _compute_depletion_rate(base_rate: float, height: str, build: str) -> float:
        """根据身高/体型计算最终的 depletion rate。

        修改量叠加（先乘 height 因子，再乘 build 因子）：
            tall × 1.1, short × 0.9, plump × 1.05, slim × 0.95
        """
        rate = base_rate
        if height == "tall":
            rate *= 1.1
        elif height == "short":
            rate *= 0.9
        if build == "plump":
            rate *= 1.05
        elif build == "slim":
            rate *= 0.95
        return rate

    # ------------------------------------------------------------------
    # YAML 字典构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_personality_yaml(
        name: str,
        style: str,
        height: str,
        build: str,
        appearance_summary: Dict[str, Any],
        big_five: Dict[str, float],
        verbal_tick: str,
        mutter_templates: Dict[str, List[str]],
        greetings: List[str],
    ) -> Dict[str, Any]:
        return {
            "metadata": {
                "name": name,
                "version": "1.0",
                "description": DESCRIPTION_TEMPLATES.get(style, DESCRIPTION_TEMPLATES["完全随机"]),
                "appearance": {
                    "height": height,
                    "build": build,
                    **appearance_summary,
                },
            },
            "big_five": big_five,
            "speech_style": {
                "greetings": greetings,
                "mutter_templates": mutter_templates,
                "verbal_ticks": verbal_tick,
            },
        }

    @staticmethod
    def _build_capabilities_yaml(
        supported_actions: List[str],
        max_wpm: int,
        max_servo_speed: float,
    ) -> Dict[str, Any]:
        return {
            "carrier_type": "smart_plush_toy",
            "actuators": {
                "speech": {
                    "enabled": True,
                    "max_words_per_minute": max_wpm,
                },
                "motion": {
                    "enabled": True,
                    "supported_actions": supported_actions,
                    "speed_limits": {
                        "max_servo_angle_speed": round(max_servo_speed, 2),
                    },
                },
                "physics_limits": {
                    "can_fly": False,
                    "can_swim": False,
                    "max_height_jump": 0.0,
                    "requires_power_plug": False,
                },
            },
        }

    @staticmethod
    def _build_system_limits_yaml(depletion_rate: float) -> Dict[str, Any]:
        return {
            "limits": {
                "energy": {
                    "max_value": 100.0,
                    "initial_value": 100.0,
                    "depletion_rate_per_sec": round(depletion_rate, 4),
                    "depletion_per_remote_chat": round(random.uniform(2.0, 3.5), 2),
                    "depletion_per_local_chat": round(random.uniform(0.3, 0.8), 2),
                    "recovery_rate_sleep_per_sec": round(random.uniform(0.03, 0.08), 4),
                },
                "fatigue": {
                    "initial_value": 0.0,
                    "max_value": 100.0,
                    "accumulation_rate_per_sec": round(random.uniform(0.002, 0.005), 4),
                    "decay_rate_sleep_per_sec": round(random.uniform(0.03, 0.06), 4),
                    "hibernation_threshold": 95.0,
                    "wakeup_threshold": round(random.uniform(10.0, 20.0), 1),
                },
                "runtime_usage": {
                    "observe_only": True,
                    "daily_token_budget": random.randint(8000, 12000),
                    "local_token_cost": 0,
                    "remote_token_cost": 1,
                },
            },
        }

    # ------------------------------------------------------------------
    # generate — 主入口
    # ------------------------------------------------------------------

    def generate(
        self,
        name: str,
        anatomy_type: str,
        personality_style: str,
        height: str,
        build: str,
        config_dir: str,
        elfie_id: str,
    ) -> Dict[str, str]:
        """旧身体形态入口；新代码应调用 :meth:`generate_for_species`。

        ``anatomy_type`` 不再决定视觉身份。保留此包装仅为了尚未迁移的身体
        模块和测试，旧个体统一映射到默认狐狸母版。
        """
        if anatomy_type not in VALID_LEGACY_ANATOMY_TYPES:
            raise ValueError(
                f"无效 anatomy_type: {anatomy_type!r}。"
                f"可选: {', '.join(VALID_LEGACY_ANATOMY_TYPES)}"
            )
        return self.generate_for_species(
            name=name,
            species_id="fox",
            personality_style=personality_style,
            height=height,
            build=build,
            config_dir=config_dir,
            elfie_id=elfie_id,
        )

    def generate_for_species(
        self,
        name: str,
        species_id: str,
        personality_style: str,
        height: str,
        build: str,
        config_dir: str,
        elfie_id: str,
        appearance_seed: int | None = None,
    ) -> Dict[str, str]:
        """生成稳定视觉档案及现有大脑兼容配置。

        Args:
            name: 精灵名字。
            species_id: 物种，当前为 ``"dog"`` 或 ``"fox"``。
            personality_style: 性格风格（6 种预设之一）。
            height: 身高，``"short"`` / ``"standard"`` / ``"tall"``。
            build: 体型，``"slim"`` / ``"standard"`` / ``"plump"``。
            config_dir: 配置目录路径。
            elfie_id: 精灵唯一标识。

        Returns:
            ``{"elfie_id": ..., "config_dir": ..., "species_id": ...}``。

        Raises:
            ValueError: 任意参数超出允许范围。
        """
        # ------------------------------------------------------------------
        # 参数校验（使用共享配置模块读取动态配置）
        # ------------------------------------------------------------------
        from app.features.adoption.config import (  # noqa: PLC0415
            get_allowed_personality_styles,
            get_allowed_species_ids,
        )

        allowed_styles = get_allowed_personality_styles()
        if personality_style not in allowed_styles:
            raise ValueError(
                f"未知 personality_style: {personality_style!r}。"
                f" 可选: {', '.join(allowed_styles)}"
            )
        if height not in VALID_HEIGHTS:
            raise ValueError(
                f"无效 height: {height!r}。可选: {', '.join(VALID_HEIGHTS)}"
            )
        if build not in VALID_BUILDS:
            raise ValueError(
                f"无效 build: {build!r}。可选: {', '.join(VALID_BUILDS)}"
            )
        allowed_species = get_allowed_species_ids()
        if species_id not in allowed_species:
            raise ValueError(
                f"无效 species_id: {species_id!r}。可选: {', '.join(allowed_species)}"
            )

        # ------------------------------------------------------------------
        # 创建配置目录
        # ------------------------------------------------------------------
        cfg_path = Path(config_dir)
        cfg_path.mkdir(parents=True, exist_ok=True)

        profile = create_visual_profile(
            elfie_id=elfie_id,
            display_name=name,
            species_id=species_id,
            seed=appearance_seed if appearance_seed is not None else secrets.randbits(63),
            height_direction=height,
            build_direction=build,
        )
        resolved = AppearanceResolver().resolve(profile)

        # ------------------------------------------------------------------
        # 生成随机值
        # ------------------------------------------------------------------
        big_five = self._pick_big_five(personality_style)
        verbal_tick = self._pick_verbal_tick()
        mutter_templates = self._pick_mutter_templates(name)
        greetings = self._pick_greetings(personality_style)
        supported_actions = self._pick_supported_actions()
        max_wpm = random.randint(80, 150)
        max_servo_speed = random.uniform(40, 80)
        base_depletion_rate = random.uniform(0.003, 0.008)
        depletion_rate = self._compute_depletion_rate(
            base_depletion_rate, height, build,
        )

        # ------------------------------------------------------------------
        # 构建 YAML 字典
        # ------------------------------------------------------------------
        personality = self._build_personality_yaml(
            name,
            personality_style,
            height,
            build,
            {
                "species": species_id,
                "height_scale": resolved.height_scale,
                "build_scale": resolved.build_scale,
            },
            big_five, verbal_tick, mutter_templates, greetings,
        )
        capabilities = self._build_capabilities_yaml(
            supported_actions, max_wpm, max_servo_speed,
        )
        system_limits = self._build_system_limits_yaml(depletion_rate)

        # profile.yaml 是稳定事实来源；旧三份 YAML 在迁移期继续双写给现有 API。
        profile = replace(
            profile,
            personality=personality,
            capabilities=capabilities,
            system_limits=system_limits,
        )
        ElfieProfileRepository(cfg_path).save(profile)

        # ------------------------------------------------------------------
        # 写入 YAML 文件
        # ------------------------------------------------------------------
        yaml_options: Dict[str, Any] = {
            "allow_unicode": True,
            "sort_keys": False,
            "default_flow_style": False,
            "encoding": "utf-8",
        }

        with open(cfg_path / "personality.yaml", "w", encoding="utf-8") as f:
            yaml.dump(personality, f, **yaml_options)

        with open(cfg_path / "capabilities.yaml", "w", encoding="utf-8") as f:
            yaml.dump(capabilities, f, **yaml_options)

        with open(cfg_path / "system_limits.yaml", "w", encoding="utf-8") as f:
            yaml.dump(system_limits, f, **yaml_options)

        logger.info(
            "Generated config for elfie %s (%s) at %s",
            elfie_id, name, config_dir,
        )

        return {
            "elfie_id": elfie_id,
            "config_dir": config_dir,
            "species_id": species_id,
        }
