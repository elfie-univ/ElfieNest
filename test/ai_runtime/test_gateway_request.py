from ai_runtime.gateway.request import RuntimeRequest


def test_default_tools_exclude_deferred_mutating_tools():
    request = RuntimeRequest("hello")
    assert request.allowed_tools == ("web_search", "local_file")
