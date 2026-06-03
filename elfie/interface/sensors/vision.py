import logging
import os
from typing import Any, Dict

logger = logging.getLogger("elfie.interface.sensors.vision")


class VisionSensor:
    """神经交互总线：眼睛 (虚拟视觉传感器)"""

    def __init__(self):
        self.last_viewport_image_path = ""
        self.last_analysis_results = {}

    def receive_viewport_snapshot(self, image_path: str) -> Dict[str, Any]:
        """
        接收来自 Godot 精灵主观视角 Camera3D 渲染的视口截图
        :param image_path: 视口图片在本地磁盘的路径 (如 /tmp/elfie_viewport.png)
        :return: 经过初步解析得到的图像语义描述字典，传递给丘脑
        """
        logger.info(
            f"👁️ [神经视觉总线] 捕获到 Godot Camera3D 主观视口快照: {image_path}"
        )
        self.last_viewport_image_path = image_path

        # 精确模拟在宿舍中的视觉感知分析结果 (前置特征检测)
        basename = os.path.basename(image_path).lower()

        # 宿舍中有门，有同伴小精灵，有桌椅
        detected_objects = ["floor", "walls"]
        description = "我站在虚拟小宿舍中，环顾四周..."

        if "door" in basename or "gate" in basename:
            detected_objects.extend(["door", "portal"])
            description = "我看到宿舍的门关着，不知道外面有什么好玩的哒！"
        elif "elfie" in basename or "buddy" in basename:
            detected_objects.extend(["elfie_buddy", "joint_entity"])
            description = "我看到另一只小精灵正在宿舍地板上打滚，它好快乐呀！"
        elif "desk" in basename or "chair" in basename:
            detected_objects.extend(["desk", "chair", "obstacle"])
            description = "我面前有一套干净的宿舍桌椅，我可以走过去探索一下。"
        else:
            # 默认视角：看见一扇虚掩着的红木门，或者一片温馨的宿舍房间
            detected_objects.extend(["dormitory_room", "wooden_door"])
            description = "我看到宿舍房间里暖洋洋的，正中央有一扇紧闭的红木大门。"

        analysis = {
            "has_image": True,
            "path": image_path,
            "detected_objects": detected_objects,
            "description": description,
            "source": "Godot_Camera3D_Viewport",
        }

        self.last_analysis_results = analysis
        return analysis

    def get_last_seen(self) -> Dict[str, Any]:
        return self.last_analysis_results
