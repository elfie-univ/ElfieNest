from ai_runtime.gateway.request import (
    StructuredGenerationMode,
    StructuredRuntimeRequest,
)


def test_structured_request_carries_tools_into_shared_executor():
    request = StructuredRuntimeRequest(
        prompt="return json",
        messages=(),
        response_schema_name="answer",
        response_schema={"type": "object"},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=("web_search",),
    )
    assert request.allowed_tools == ("web_search",)
