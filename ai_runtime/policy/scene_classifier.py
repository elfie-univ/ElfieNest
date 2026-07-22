"""场景分类器。

基于注意力网络状态 + 关键词映射，将当前请求分类到 5 个场景槽之一：
- idle: 闲散/默认模式
- deep: 深度认知（复杂计算、搜索、代码）
- vision: 视觉处理（图片、视频）
- tool_use: 工具调用（搜索、执行）
- sleep: 睡眠/低能耗状态

分类优先级：
1. tool_call_pending → tool_use (最高)
2. has_image/has_audio → vision
3. 注意力网络状态 (SN/CEN/DMN)
4. 关键词映射
5. 默认 → idle
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger("ai_runtime.policy.scene_classifier")


# ---------------------------------------------------------------------------
# 场景槽定义（与 model_route.py 保持一致）
# ---------------------------------------------------------------------------

SCENE_SLOTS = ["idle", "deep", "vision", "tool_use", "sleep"]


# ---------------------------------------------------------------------------
# 关键词映射
# ---------------------------------------------------------------------------

DEEP_KEYWORDS = [
    "计算", "算出", "帮我算", "搜索", "查一下", "最新",
    "代码", "分析", "推理", "规划", "设计",
]

VISION_KEYWORDS = [
    "看看", "图片", "照片", "图像", "视频",
    "识别", "描述一下", "看一下",
]

TOOL_USE_KEYWORDS = [
    "帮我", "执行", "调用", "使用工具",
    "搜索一下", "查一下", "联网",
]


# ---------------------------------------------------------------------------
# 场景分类
# ---------------------------------------------------------------------------

def classify_scene(
    prompt: str,
    attention_state: Optional[Dict[str, float]] = None,
    has_image: bool = False,
    has_audio: bool = False,
    tool_call_pending: bool = False,
) -> str:
    """分类当前场景到 5 个场景槽之一。

    分类逻辑：
    1. tool_call_pending → "tool_use" (最高优先级)
    2. has_image or has_audio → "vision"
    3. attention_state:
       - SN (Salience Network) 高 → "tool_use" (警觉/紧急)
       - CEN (Central Executive Network) 高 → "deep" (深度认知)
       - DMN (Default Mode Network) 高 → "idle" (闲散/默认)
    4. 关键词映射：
       - 计算/搜索/代码/分析 → "deep"
       - 看看/图片/照片 → "vision"
       - 帮我/执行/调用 → "tool_use"
    5. 默认 → "idle"

    Args:
        prompt: 用户输入文本
        attention_state: 注意力网络状态，格式 {"SN": float, "CEN": float, "DMN": float}
                        值为 0-100 的浮点数，也可传入 {"current_network": "SN/CEN/DMN"} 字符串格式
        has_image: 是否有图片输入
        has_audio: 是否有音频输入
        tool_call_pending: 是否有待处理的工具调用

    Returns:
        Scene slot name: "idle" | "deep" | "vision" | "tool_use" | "sleep"
    """
    # 1. 最高优先级：待处理的工具调用
    if tool_call_pending:
        logger.info("场景分类: tool_call_pending → tool_use")
        return "tool_use"

    # 2. 多模态输入 → vision
    if has_image or has_audio:
        logger.info(f"场景分类: has_image={has_image}, has_audio={has_audio} → vision")
        return "vision"

    # 3. 注意力网络状态
    if attention_state:
        # 支持字符串格式的 current_network
        if "current_network" in attention_state:
            network = attention_state["current_network"]
            if network == "SN":
                logger.info("场景分类: SN 网络 → tool_use")
                return "tool_use"
            elif network == "CEN":
                logger.info("场景分类: CEN 网络 → deep")
                return "deep"
            elif network == "DMN":
                logger.info("场景分类: DMN 网络 → idle")
                return "idle"

        # 支持数值格式的网络状态
        sn_score = attention_state.get("SN", 0.0)
        cen_score = attention_state.get("CEN", 0.0)
        dmn_score = attention_state.get("DMN", 0.0)

        # SN 高 → tool_use (警觉/紧急)
        if sn_score >= 70.0:
            logger.info(f"场景分类: SN 高 ({sn_score}) → tool_use")
            return "tool_use"

        # CEN 高 → deep (深度认知)
        if cen_score >= 50.0:
            logger.info(f"场景分类: CEN 高 ({cen_score}) → deep")
            return "deep"

        # DMN 高 → idle
        if dmn_score >= 50.0:
            logger.info(f"场景分类: DMN 高 ({dmn_score}) → idle")
            return "idle"

    # 4. 关键词映射
    # 检查 tool_use 关键词
    for kw in TOOL_USE_KEYWORDS:
        if kw in prompt:
            logger.info(f"场景分类: 关键词 '{kw}' → tool_use")
            return "tool_use"

    # 检查 deep 关键词
    for kw in DEEP_KEYWORDS:
        if kw in prompt:
            logger.info(f"场景分类: 关键词 '{kw}' → deep")
            return "deep"

    # 检查 vision 关键词
    for kw in VISION_KEYWORDS:
        if kw in prompt:
            logger.info(f"场景分类: 关键词 '{kw}' → vision")
            return "vision"

    # 5. 默认 → idle
    logger.info("场景分类: 无明确信号 → idle (默认)")
    return "idle"
