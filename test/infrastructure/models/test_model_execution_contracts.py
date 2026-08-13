from infrastructure.models.model_execution_contracts import ModelExecutionRequest


def test_default_tools_exclude_deferred_mutating_tools():
    request = ModelExecutionRequest("hello")
    assert request.allowed_tools == ("web_search", "local_file")
