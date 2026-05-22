import logging
from typing import Dict, List
from elfie.elfie_individual import ElfieIndividual

logger = logging.getLogger("elfienest.coordinator")

class ElfieNestCoordinator:
    """精灵盒子协调器 (多精灵注册、社交事件与物理碰撞交互管理)"""

    def __init__(self):
        self.registered_elfies: Dict[str, ElfieIndividual] = {}

    def register_elfie(self, name: str, elfie: ElfieIndividual):
        """将一只小精灵接入盒子世界容器"""
        self.registered_elfies[name] = elfie
        logger.info(f"✨ [注册成功] 仿生生命体 '{name}' 已安全接入 ElfieNest 生态盒子。")

    def unregister_elfie(self, name: str):
        if name in self.registered_elfies:
            del self.registered_elfies[name]
            logger.info(f"🐾 精灵 '{name}' 离开了生态盒子。")

    def trigger_elfie_interaction(self, name_a: str, name_b: str, event_type: str = "collision"):
        """
        触发两只精灵之间的强物理/社交相互作用
        :param name_a: 精灵 A 的注册名
        :param name_b: 精灵 B 的注册名
        :param event_type: 交互类型 (如 collision 碰撞，chat 聊天)
        """
        if name_a not in self.registered_elfies or name_b not in self.registered_elfies:
            logger.error("交互触发失败：其中一只精灵未在盒子中注册！")
            return

        elfie_a = self.registered_elfies[name_a]
        elfie_b = self.registered_elfies[name_b]

        logger.info(f"🎭 [精灵大社交] '{name_a}' 与 '{name_b}' 发生了物理【{event_type}】交互！")

        if event_type == "collision":
            # 物理碰撞：刺激杏仁核化学值
            # A 精灵变得害羞而快乐 (吃醋度减少 5, 快乐度增加 10)
            elfie_a.amygdala.update_emotion("jealousy", -5.0)
            elfie_a.amygdala.update_emotion("happiness", 10.0)
            
            # B 精灵感到新奇和兴奋
            elfie_b.amygdala.update_emotion("boredom", -20.0)
            elfie_b.amygdala.update_emotion("happiness", 15.0)

            # 记录海马体日常事件
            elfie_a.hippocampus.record_episode(
                event_description=f"【社交事件】 我在精灵盒子广场上跟好伙伴 '{name_b}' 撞个满怀，非常高兴哒！",
                emotion_tag="happy"
            )
            elfie_b.hippocampus.record_episode(
                event_description=f"【社交事件】 伙伴 '{name_a}' 急匆匆地撞到了我，把我的无聊度都撞跑了哒！",
                emotion_tag="happy"
            )

    def dispatch_global_event(self, event_description: str, mood_impacts: Dict[str, float]):
        """向所有注册的精灵派发全局世界事件（如突然打雷、停电等环境恐慌）"""
        for name, elfie in self.registered_elfies.items():
            logger.info(f"🌍 [世界事件派发 -> {name}]: {event_description}")
            for emotion_name, impact in mood_impacts.items():
                elfie.amygdala.update_emotion(emotion_name, impact)
            
            elfie.hippocampus.record_episode(
                event_description=f"【环境大事件】 生态盒子世界发生了: {event_description}",
                emotion_tag=elfie.amygdala.get_dominant_mood()
            )
