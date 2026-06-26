from runtime.agent import _API_DISPATCH, _STREAM_DISPATCH
from runtime.agent import _call_ollama_api, _stream_ollama_api
from runtime.providers.dispatch import API_DISPATCH, call_ollama_api
from runtime.providers.streaming import STREAM_DISPATCH, stream_ollama_api


def test_legacy_dispatch_exports_match_provider_module():
    assert _API_DISPATCH is API_DISPATCH
    assert _call_ollama_api is call_ollama_api


def test_legacy_streaming_exports_match_provider_module():
    assert _STREAM_DISPATCH is STREAM_DISPATCH
    assert _stream_ollama_api is stream_ollama_api
