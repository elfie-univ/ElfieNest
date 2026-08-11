from infrastructure.models.runtime_contracts import RuntimeRequest


def test_runtime_request_uses_semantic_role():
    request = RuntimeRequest("hello", semantic_role="vision")
    assert request.semantic_role == "vision"
