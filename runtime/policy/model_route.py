"""每精灵模型路由配置。

支持每个精灵独立配置模型路由策略：
- 场景槽定义（idle/deep/vision/tool_use/sleep）
- 主模型 + 降级链
- 能量阈值触发降级

配置文件路径: ~/.elfienest/elfies/{elfie_id}/model_route.yaml
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from runtime.config import LLMRuntimeConfig
from runtime.storage.data_home import get_elfie_config_dir

logger = logging.getLogger("runtime.policy.model_route")


# ---------------------------------------------------------------------------
# 场景槽定义
# ---------------------------------------------------------------------------

SCENE_SLOTS = ["idle", "deep", "vision", "tool_use", "sleep"]


@dataclass
class SceneRoute:
    """单个场景的路由配置。

    Attributes:
        primary: 主模型，格式 "{provider}/{model}"，如 "openai/gpt-4o"
        fallbacks: 降级链，当主模型不可用或能量不足时依次尝试
        energy_threshold: 触发降级的能量阈值 (0-100)
    """
    primary: str
    fallbacks: List[str] = field(default_factory=list)
    energy_threshold: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneRoute":
        return cls(
            primary=data.get("primary", "ollama/qwen3.5:0.8b"),
            fallbacks=data.get("fallbacks", []),
            energy_threshold=data.get("energy_threshold", 0.0),
        )


@dataclass
class ModelRoute:
    """精灵的完整模型路由配置。

    Attributes:
        elfie_id: 精灵 ID
        scene_routes: 场景路由映射，key 为场景槽名称
        updated_at: 最后更新时间 (ISO 格式字符串)
    """
    elfie_id: str
    scene_routes: Dict[str, SceneRoute] = field(default_factory=dict)
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "elfie_id": self.elfie_id,
            "scene_routes": {
                scene: route.to_dict() for scene, route in self.scene_routes.items()
            },
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelRoute":
        scene_routes = {}
        for scene, route_data in data.get("scene_routes", {}).items():
            scene_routes[scene] = SceneRoute.from_dict(route_data)
        return cls(
            elfie_id=data.get("elfie_id", ""),
            scene_routes=scene_routes,
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# 系统默认路由
# ---------------------------------------------------------------------------

DEFAULT_SCENE_ROUTES: Dict[str, SceneRoute] = {
    "idle": SceneRoute(
        primary="ollama/qwen3.5:0.8b",
        fallbacks=[],
        energy_threshold=0,
    ),
    "deep": SceneRoute(
        primary="deepseek/deepseek-chat",
        fallbacks=["ollama/qwen3.5:0.8b"],
        energy_threshold=30,
    ),
    "vision": SceneRoute(
        primary="ollama/moondream",
        fallbacks=[],
        energy_threshold=0,
    ),
    "tool_use": SceneRoute(
        primary="deepseek/deepseek-chat",
        fallbacks=["ollama/qwen3.5:0.8b"],
        energy_threshold=20,
    ),
    "sleep": SceneRoute(
        primary="ollama/qwen3.5:0.8b",
        fallbacks=[],
        energy_threshold=0,
    ),
}


# ---------------------------------------------------------------------------
# 路由配置加载/保存
# ---------------------------------------------------------------------------

def _get_model_route_path(elfie_id: str, config_dir: str | Path | None = None) -> Path:
    """获取精灵路由配置文件路径"""
    if config_dir is not None:
        return Path(config_dir) / "model_route.yaml"
    return get_elfie_config_dir(elfie_id) / "model_route.yaml"


def load_model_route(elfie_id: str, config_dir: str | Path | None = None) -> ModelRoute:
    """加载精灵的路由配置，如果不存在则返回系统默认配置。

    Args:
        elfie_id: 精灵 ID

    Returns:
        ModelRoute 实例，包含该精灵的所有场景路由
    """
    route_path = _get_model_route_path(elfie_id, config_dir)

    if not route_path.exists():
        logger.info(f"精灵 '{elfie_id}' 无自定义路由配置，使用系统默认路由")
        return create_default_route(elfie_id)

    try:
        with open(route_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        route = ModelRoute.from_dict(data)
        route.elfie_id = elfie_id  # 确保 elfie_id 正确
        logger.info(f"已加载精灵 '{elfie_id}' 的路由配置")
        return route
    except Exception as e:
        logger.warning(f"加载精灵 '{elfie_id}' 路由配置失败: {e}，使用系统默认")
        return create_default_route(elfie_id)


def save_model_route(route: ModelRoute, config_dir: str | Path | None = None) -> None:
    """保存精灵的路由配置到 YAML 文件。

    Args:
        route: 要保存的路由配置
    """
    # 更新时间戳
    route.updated_at = datetime.now().isoformat()

    # 确保目录存在
    route_config_dir = (
        Path(config_dir)
        if config_dir is not None
        else get_elfie_config_dir(route.elfie_id)
    )
    route_config_dir.mkdir(parents=True, exist_ok=True)

    # 写入文件
    route_path = _get_model_route_path(route.elfie_id, route_config_dir)
    with open(route_path, "w", encoding="utf-8") as f:
        yaml.dump(route.to_dict(), f, allow_unicode=True, default_flow_style=False)

    logger.info(f"已保存精灵 '{route.elfie_id}' 的路由配置到 {route_path}")


def create_default_route(elfie_id: str) -> ModelRoute:
    """创建使用系统默认值的路由配置。

    Args:
        elfie_id: 精灵 ID

    Returns:
        包含所有 5 个场景槽默认配置的 ModelRoute
    """
    scene_routes = {
        scene: SceneRoute(
            primary=route.primary,
            fallbacks=list(route.fallbacks),  # 复制列表避免共享引用
            energy_threshold=route.energy_threshold,
        )
        for scene, route in DEFAULT_SCENE_ROUTES.items()
    }

    return ModelRoute(
        elfie_id=elfie_id,
        scene_routes=scene_routes,
        updated_at=None,
    )


# ---------------------------------------------------------------------------
# 模型解析
# ---------------------------------------------------------------------------

def _parse_model_spec(spec: str) -> Tuple[str, str]:
    """解析模型规格字符串为 (provider, model_name)。

    Args:
        spec: 模型规格，格式 "{provider}/{model}"，如 "openai/gpt-4o"

    Returns:
        (provider, model_name) 元组
    """
    if "/" not in spec:
        # 默认为 ollama
        return "ollama", spec

    parts = spec.split("/", 1)
    return parts[0], parts[1]


def _check_provider_available(provider: str, config: LLMRuntimeConfig) -> bool:
    """检查服务商是否可用（有 API Key 或为本地 ollama）"""
    if provider == "ollama":
        return True

    provider_config = config.providers.get(provider, {})
    api_key = provider_config.get("api_key", "")
    status = provider_config.get("status", "inactive")

    return bool(api_key) and status == "active"


def resolve_model(
    elfie_id: str,
    scene: str,
    energy: float,
    config: LLMRuntimeConfig,
) -> Tuple[str, str]:
    """解析场景对应的模型，考虑能量阈值和降级链。

    Args:
        elfie_id: 精灵 ID
        scene: 场景槽名称 (idle/deep/vision/tool_use/sleep)
        energy: 当前精力值 (0-100)
        config: LLM 运行时配置

    Returns:
        (provider, model_name) 元组
    """
    # 加载路由配置
    route = load_model_route(elfie_id)

    # 获取场景路由
    scene_route = route.scene_routes.get(scene)
    if not scene_route:
        logger.warning(f"未知场景 '{scene}'，使用 idle 默认路由")
        scene_route = route.scene_routes.get("idle", DEFAULT_SCENE_ROUTES["idle"])

    # 构建候选模型列表：主模型 + 降级链
    candidates = [scene_route.primary] + scene_route.fallbacks

    # 能量不足时跳过主模型，直接尝试降级链
    start_idx = 0 if energy >= scene_route.energy_threshold else 1

    if start_idx >= len(candidates):
        start_idx = len(candidates) - 1  # 至少尝试最后一个

    # 遍历候选模型
    for i in range(start_idx, len(candidates)):
        spec = candidates[i]
        provider, model_name = _parse_model_spec(spec)

        # 检查服务商可用性
        if _check_provider_available(provider, config):
            if i > 0:
                logger.info(
                    f"精灵 '{elfie_id}' 场景 '{scene}' 因能量 {energy}% < {scene_route.energy_threshold}% "
                    f"降级使用 {provider}/{model_name}"
                )
            return provider, model_name
        else:
            logger.warning(f"服务商 '{provider}' 不可用，尝试下一个候选")

    # 最终兜底：使用 ollama 本地模型
    logger.warning(
        f"精灵 '{elfie_id}' 场景 '{scene}' 所有候选模型均不可用，"
        f"降级到 ollama/qwen3.5:0.8b 作为最终兜底"
    )
    return "ollama", "qwen3.5:0.8b"
