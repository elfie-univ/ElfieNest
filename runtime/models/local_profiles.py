from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalModelProfile:
    name: str
    min_memory_gb: int
    text_model: str
    vision_model: str = "moondream"


LOCAL_MODEL_PROFILES = (
    LocalModelProfile(name="tiny", min_memory_gb=0, text_model="qwen2.5:0.5b"),
    LocalModelProfile(name="small", min_memory_gb=8, text_model="qwen3.5:0.8b"),
    LocalModelProfile(name="medium", min_memory_gb=16, text_model="qwen2.5:3b"),
    LocalModelProfile(name="large", min_memory_gb=32, text_model="qwen2.5:7b"),
)


def select_local_profile(memory_gb: int) -> LocalModelProfile:
    selected = LOCAL_MODEL_PROFILES[0]
    for profile in LOCAL_MODEL_PROFILES:
        if memory_gb >= profile.min_memory_gb:
            selected = profile
    return selected
