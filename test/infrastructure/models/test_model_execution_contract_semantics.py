from infrastructure.models.model_execution_contracts import ModelExecutionRequest


def test_model_execution_request_uses_semantic_role():
    request = ModelExecutionRequest("hello", semantic_role="vision")
    assert request.semantic_role == "vision"
