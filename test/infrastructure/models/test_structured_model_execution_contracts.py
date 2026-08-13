from infrastructure.models.model_execution_contracts import (
    StructuredGenerationMode,
    StructuredModelExecutionRequest,
)


def test_structured_request_carries_tools_into_shared_executor():
    request = StructuredModelExecutionRequest(
        prompt="return json",
        messages=(),
        response_schema_name="answer",
        response_schema={"type": "object"},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=("web_search",),
    )
    assert request.allowed_tools == ("web_search",)
