import json
from unittest.mock import MagicMock, patch

from infrastructure.models.providers.dispatch import call_ollama_api


def test_food_provider_options_are_sent_without_overriding_core_fields():
    response = MagicMock()
    response.read.return_value = json.dumps({"message": {"content": "ok"}}).encode()
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False

    with patch(
        "infrastructure.models.providers.dispatch.open_provider_request",
        return_value=context,
    ) as urlopen:
        call_ollama_api(
            "http://localhost:11434",
            "qwen",
            [{"role": "user", "content": "hi"}],
            0.2,
            100,
            request_options={
                "model": "malicious-override",
                "temperature": 99,
                "think": True,
                "options": {"think": True},
            },
            timeout_seconds=4.5,
        )

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode())
    assert payload["model"] == "qwen"
    assert payload["think"] is False
    assert payload["options"]["temperature"] == 0.2
    assert "think" not in payload["options"]
    assert urlopen.call_args.kwargs["timeout"] == 4.5


def test_runtime_can_explicitly_enable_top_level_ollama_thinking():
    response = MagicMock()
    response.read.return_value = json.dumps({"message": {"content": "ok"}}).encode()
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False

    with patch(
        "infrastructure.models.providers.dispatch.open_provider_request",
        return_value=context,
    ) as urlopen:
        call_ollama_api(
            "http://localhost:11434",
            "qwen",
            [{"role": "user", "content": "hi"}],
            0.2,
            100,
            thinking=True,
        )

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode())
    assert payload["think"] is True
    assert "think" not in payload["options"]
