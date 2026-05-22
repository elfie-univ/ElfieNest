import logging
from typing import Dict, Any

logger = logging.getLogger("elfie.interface.sensors.vision")

class VisionSensor:
    """底层：感官输入 - 眼睛 (视觉传感器)"""

    def __init__(self):
        self.last_seen_image_path = ""
        self.last_analysis_results = {}

    def see_image(self, image_path: str) -> Dict[str, Any]:
        """
        捕获或接收到一张外界图片 (如主人在微信中发来的图)
        :param image_path: 图片的磁盘绝对路径或 URL
        :return: 经过初步解析得到的图片特征字典
        """
        logger.info(f"👁️ [视觉感官捕获图片] 正在读取: {image_path}")
        self.last_seen_image_path = image_path
        
        # 简单模拟视觉皮层分析 (多模态 LLM 调用前置解析)
        # 如果是含有账单字眼的图片，打上特定标签，以便丘脑做高精度上下文拼装
        analysis = {
            "has_image": True,
            "path": image_path,
            "contains_text": True,
            "inferred_type": "invoice_or_bill" if "bill" in image_path.lower() or "账单" in image_path else "general_photo",
            "detected_objects": ["numbers", "table", "document"]
        }
        
        self.last_analysis_results = analysis
        return analysis

    def get_last_seen(self) -> Dict[str, Any]:
        return self.last_analysis_results
