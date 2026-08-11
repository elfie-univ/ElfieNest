import os
import tempfile

import pytest

from infrastructure.models.inference.multimodal import assemble_multimodal_payload


def test_assemble_multimodal_payload_for_ollama():
    messages = [{"role": "user", "content": "Describe"}]

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image_file:
        image_file.write(b"fake image data")
        image_path = image_file.name

    try:
        result = assemble_multimodal_payload(messages, [image_path], None, "ollama")
    finally:
        os.unlink(image_path)

    assert result is messages
    assert result[0]["images"]


def test_assemble_multimodal_payload_for_cloud_audio():
    messages = [{"role": "user", "content": "Transcribe"}]

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
        audio_file.write(b"fake audio data")
        audio_path = audio_file.name

    try:
        result = assemble_multimodal_payload(messages, None, audio_path, "openai")
    finally:
        os.unlink(audio_path)

    assert result is messages
    assert result[0]["content"][1]["type"] == "input_audio"


def test_assemble_multimodal_payload_raises_for_missing_image():
    messages = [{"role": "user", "content": "Describe"}]

    with pytest.raises(FileNotFoundError):
        assemble_multimodal_payload(messages, ["missing.jpg"], None, "ollama")
