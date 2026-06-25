from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("elfienest.simulation.tts")


async def async_generate_tts(
    text: str,
    output_path: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def synthesize_voice(
    *,
    elfie_id: str,
    text: str,
    temp_audio_dir: str,
    http_port: int,
    tts_enabled: bool,
) -> Optional[str]:
    if not text:
        return None

    if not tts_enabled:
        logger.debug("TTS disabled, skipping voice synthesis for %s", elfie_id)
        return None

    filename = f"voice_{elfie_id}_{int(time.time() * 1000)}.mp3"
    output_path = os.path.join(temp_audio_dir, filename)

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(async_generate_tts(text, output_path))
        loop.close()
    except Exception as exc:
        logger.warning(
            "⚠️ [语音服务] edge-tts 合成失败 (可能是网络超时或包未完全安装)，优雅降级为空音频: %s",
            exc,
        )
        return None

    audio_url = f"http://127.0.0.1:{http_port}/{filename}"
    logger.info("🎤 [语音服务] 精灵 '%s' 发言音频合成成功 -> %s", elfie_id, audio_url)
    return audio_url
