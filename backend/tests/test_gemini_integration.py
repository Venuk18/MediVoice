import json
import httpx
import pytest

from app.agent.adapters import (
    GeminiReasoningAdapter,
    MockReasoningAdapter,
    ReasoningAdapterError,
    create_reasoning_adapter,
)
from app.agent.schemas import AgentSessionState, ToolCallIntent
from app.agent.tool_router import RestrictedToolRouter


def test_gemini_missing_api_key():
    adapter = GeminiReasoningAdapter(api_key="", strict_mode=True)
    session = AgentSessionState(session_id="test-missing-key")
    with pytest.raises(ReasoningAdapterError) as exc_info:
        adapter.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_info.value.code == "MISSING_CREDENTIALS"
    assert "GEMINI_API_KEY" in exc_info.value.safe_message


def test_gemini_valid_config():
    adapter = GeminiReasoningAdapter(
        api_key="valid-test-key",
        model="gemini-3.8-flash",
        timeout_seconds=20.0,
        max_tool_rounds=3,
    )
    assert adapter.api_key == "valid-test-key"
    assert adapter.model == "gemini-3.8-flash"
    assert adapter.timeout_seconds == 20.0
    assert adapter.max_tool_rounds == 3


def test_gemini_provider_timeout():
    def timeout_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout waiting for Gemini")

    mock_client = httpx.Client(transport=httpx.MockTransport(timeout_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-key",
        timeout_seconds=2.0,
        http_client=mock_client,
        strict_mode=True,
    )
    session = AgentSessionState(session_id="test-timeout")
    with pytest.raises(ReasoningAdapterError) as exc_info:
        adapter.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_info.value.code == "PROVIDER_TIMEOUT"


def test_gemini_auth_failure():
    def auth_fail_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": 401, "message": "API_KEY_INVALID"}})

    mock_client = httpx.Client(transport=httpx.MockTransport(auth_fail_transport))
    adapter = GeminiReasoningAdapter(
        api_key="invalid-key",
        http_client=mock_client,
        strict_mode=True,
    )
    session = AgentSessionState(session_id="test-auth-fail")
    with pytest.raises(ReasoningAdapterError) as exc_info:
        adapter.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_info.value.code == "PROVIDER_HTTP_ERROR"
    assert exc_info.value.status_code == 401


def test_gemini_rate_limit():
    def rate_limit_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": 429, "message": "RESOURCE_EXHAUSTED"}})

    mock_client = httpx.Client(transport=httpx.MockTransport(rate_limit_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-key",
        http_client=mock_client,
        strict_mode=True,
    )
    session = AgentSessionState(session_id="test-rate-limit")
    with pytest.raises(ReasoningAdapterError) as exc_info:
        adapter.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_info.value.code == "PROVIDER_HTTP_ERROR"
    assert exc_info.value.status_code == 429


def test_gemini_malformed_response():
    def non_json_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Bad Gateway HTML")

    mock_client = httpx.Client(transport=httpx.MockTransport(non_json_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-key",
        http_client=mock_client,
        strict_mode=True,
    )
    session = AgentSessionState(session_id="test-malformed")
    with pytest.raises(ReasoningAdapterError) as exc_info:
        adapter.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_info.value.code == "INVALID_PROVIDER_RESPONSE"


def test_gemini_tool_call_parsing():
    def tool_call_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "search_doctors",
                                        "args": {"specialty_or_department": "Neurology"},
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(tool_call_transport))
    adapter = GeminiReasoningAdapter(api_key="test-key", http_client=mock_client)
    session = AgentSessionState(session_id="test-tool-parse")
    action = adapter.plan_and_respond(session, "I have severe migraines", ["search_doctors"])
    assert action.tool_call is not None
    assert action.tool_call.tool_name == "search_doctors"
    assert action.tool_call.arguments == {"specialty_or_department": "Neurology"}


def test_restricted_tool_router_blocks_unauthorized_tools(db_session, seeded_hospital_data):
    router = RestrictedToolRouter()
    # Proposed tool not in allowed set
    forbidden_intent = ToolCallIntent(tool_name="drop_database_table", arguments={})
    res = router.execute_tool(db=db_session, intent=forbidden_intent)
    assert res.success is False
    assert "not permitted" in res.error.lower()


def test_mock_provider_fallback_remains_functional(db_session, seeded_hospital_data):
    adapter = create_reasoning_adapter(provider="mock")
    assert isinstance(adapter, MockReasoningAdapter)
    session = AgentSessionState(session_id="test-mock-works")
    action = adapter.plan_and_respond(session, "Hello", ["search_doctors"])
    assert action.reply
    assert len(action.reply) > 0
