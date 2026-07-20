import json
from unittest.mock import MagicMock, patch

from ai_runtime.providers.dispatch import call_ollama_api


def test_food_provider_options_are_sent_without_overriding_core_fields():
    response = MagicMock()
    response.read.return_value = json.dumps({"message": {"content": "ok"}}).encode()
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=context) as urlopen:
        call_ollama_api(
            "http://localhost:11434",
            "qwen",
            [{"role": "user", "content": "hi"}],
            0.2,
            100,
            request_options={
                "model": "malicious-override",
                "temperature": 99,
                "options": {"think": True},
            },
        )

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode())
    assert payload["model"] == "qwen"
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["think"] is True
