from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any


def assemble_multimodal_payload(
    messages: list[dict[str, Any]],
    images: list[str] | None = None,
    audio: str | None = None,
    provider: str = "ollama",
) -> list[dict[str, Any]]:
    user_msg_idx = -1
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx]["role"] == "user":
            user_msg_idx = idx
            break

    if user_msg_idx == -1:
        messages.append({"role": "user", "content": ""})
        user_msg_idx = len(messages) - 1

    original_text = messages[user_msg_idx]["content"]

    if provider == "ollama":
        images_base64 = []
        if images:
            for img_path in images:
                if not os.path.exists(img_path):
                    raise FileNotFoundError(f"❌ 找不到图片文件: '{img_path}'")
                with open(img_path, "rb") as image_file:
                    images_base64.append(
                        base64.b64encode(image_file.read()).decode("utf-8")
                    )
            messages[user_msg_idx]["images"] = images_base64
        return messages

    content_list: list[dict[str, Any]] = [{"type": "text", "text": original_text}]

    if images:
        for img_path in images:
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"❌ 找不到图片文件: '{img_path}'")
            mime_type, _ = mimetypes.guess_type(img_path)
            mime_type = mime_type or "image/jpeg"
            with open(img_path, "rb") as image_file:
                b64_data = base64.b64encode(image_file.read()).decode("utf-8")
            content_list.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                }
            )

    if audio:
        if not os.path.exists(audio):
            raise FileNotFoundError(f"❌ 找不到音频文件: '{audio}'")
        mime_type, _ = mimetypes.guess_type(audio)
        mime_type = mime_type or "audio/mp3"
        if mime_type == "audio/mpeg" and audio.endswith(".mp3"):
            mime_type = "audio/mp3"

        with open(audio, "rb") as audio_file:
            b64_data = base64.b64encode(audio_file.read()).decode("utf-8")

        content_list.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": b64_data,
                    "format": mime_type.split("/")[-1],
                },
            }
        )

    messages[user_msg_idx]["content"] = content_list
    return messages
