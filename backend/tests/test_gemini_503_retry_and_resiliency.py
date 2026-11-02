import json
import pytest
import httpx
from unittest.mock import MagicMock
from app.agent.adapters import GeminiReasoningAdapter, ReasoningAdapterError
from app.agent.schemas import AgentSessionState, BookingDraft, ConfirmationStatus, ConversationStep, ToolExecutionResult
from app.agent.conversation_manager import ConversationManager
from app.agent.tool_router import RestrictedToolRouter


def _make_mock_client(responses):
    """Creates an httpx.Client with a sequential MockTransport returning the given responses."""
    resp_iter = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            item = next(resp_iter)
        except StopIteration:
            raise RuntimeError("Ran out of mock responses")

        if isinstance(item, Exception):
            raise item
        status_code, json_body, headers = item
        return httpx.Response(
            status_code=status_code,
            headers=headers or {"content-type": "application/json"},
            content=json.dumps(json_body).encode("utf-8"),
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


# 1. Temporary 503 recovery (503 -> 200)
def test_gemini_503_transient_recovery():
    success_payload = {
        "candidates": [{
            "content": {"parts": [{"text": "Hello, I can help you with your booking."}], "role": "model"},
            "finishReason": "STOP"
        }]
    }
    client = _make_mock_client([
        (503, {"error": {"code": 503, "message": "High demand, please try again."}}, {}),
        (200, success_payload, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    sleep_calls = []
    adapter._sleeper = lambda s: sleep_calls.append(s)

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(session, "Hi", available_tools=[])

    assert action.reply == "Hello, I can help you with your booking."
    assert adapter.retry_count == 1
    assert len(sleep_calls) == 1
    assert adapter._last_status_code == 200


# 2. Persistent 503 exceeding retry limits (503 -> 503 -> 503 -> fails safely)
def test_gemini_503_persistent_exhaustion():
    client = _make_mock_client([
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    sleep_calls = []
    adapter._sleeper = lambda s: sleep_calls.append(s)

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(session, "Hi", available_tools=[])

    # Fails safely with localized provider error message, without crashing
    assert "temporarily unavailable" in action.reply
    assert "HTTP 503" in action.reply
    assert adapter.retry_count == 2
    assert len(sleep_calls) == 2
    assert adapter.last_error == "Gemini API returned HTTP 503."


# 3. HTTP 429 transient with Retry-After header (429 -> 200)
def test_gemini_429_transient_with_retry_after():
    success_payload = {
        "candidates": [{
            "content": {"parts": [{"text": "Quota recovered successfully."}], "role": "model"},
            "finishReason": "STOP"
        }]
    }
    client = _make_mock_client([
        (429, {"error": {"code": 429, "message": "Rate limit exceeded"}}, {"Retry-After": "1.5"}),
        (200, success_payload, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    sleep_calls = []
    adapter._sleeper = lambda s: sleep_calls.append(s)

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(session, "Hi", available_tools=[])

    assert action.reply == "Quota recovered successfully."
    assert adapter.retry_count == 1
    assert sleep_calls == [1.5]


# 4. HTTP 429 daily free tier quota exhausted -> fail-fast without retry
def test_gemini_429_daily_quota_fails_fast():
    daily_quota_body = {
        "error": {
            "code": 429,
            "message": "Generate content requests per day limit exceeded on Free Tier.",
        }
    }
    client = _make_mock_client([
        (429, daily_quota_body, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.5-flash",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    sleep_calls = []
    adapter._sleeper = lambda s: sleep_calls.append(s)

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(session, "Hi", available_tools=[])

    assert "temporarily unavailable" in action.reply
    assert "HTTP 429" in action.reply
    # Zero retries because daily quota is permanent
    assert adapter.retry_count == 0
    assert len(sleep_calls) == 0


# 5. Network error retry (ConnectError -> 200)
def test_gemini_network_error_retry():
    success_payload = {
        "candidates": [{
            "content": {"parts": [{"text": "Recovered from network drop."}], "role": "model"},
            "finishReason": "STOP"
        }]
    }
    client = _make_mock_client([
        httpx.ConnectError("Connection reset by peer"),
        (200, success_payload, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    sleep_calls = []
    adapter._sleeper = lambda s: sleep_calls.append(s)

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(session, "Hi", available_tools=[])

    assert action.reply == "Recovered from network drop."
    assert adapter.retry_count == 1
    assert len(sleep_calls) == 1


# 6. Retry limits strictly bounded (max_retries=1 means at most 1 retry)
def test_gemini_retry_limits_strictly_bounded():
    client = _make_mock_client([
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=1,
        retry_backoff_base=0.01,
    )
    sleep_calls = []
    adapter._sleeper = lambda s: sleep_calls.append(s)

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(session, "Hi", available_tools=[])

    assert adapter.retry_count == 1
    assert len(sleep_calls) == 1


# 7. Tool orchestration continuity during retry
def test_tool_orchestration_continuity_with_retry():
    tool_call_payload = {
        "candidates": [{
            "content": {
                "parts": [{
                    "functionCall": {
                        "name": "search_doctors",
                        "args": {"specialty": "Cardiology"}
                    }
                }],
                "role": "model"
            },
            "finishReason": "STOP"
        }]
    }
    final_reply_payload = {
        "candidates": [{
            "content": {"parts": [{"text": "Found Dr. Sharma in Cardiology."}], "role": "model"},
            "finishReason": "STOP"
        }]
    }

    # Turn round 1: 503 then tool_call_payload. Round 2: final_reply_payload
    client = _make_mock_client([
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
        (200, tool_call_payload, {}),
        (200, final_reply_payload, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    adapter._sleeper = lambda s: None

    mock_executor = MagicMock(side_effect=lambda intent: ToolExecutionResult(
        tool_name=intent.tool_name,
        success=True,
        data=[{"doctor_id": "doc-1", "display_name": "Dr. Sharma", "specialty": "Cardiology"}],
        error=None,
    ))

    session = AgentSessionState(session_id="test-session")
    action = adapter.plan_and_respond(
        session, "I need a cardiologist",
        available_tools=["search_doctors"],
        tool_executor=mock_executor,
    )

    assert action.reply == "Found Dr. Sharma in Cardiology."
    assert mock_executor.call_count == 1
    assert adapter.retry_count == 1


# 8. Appointment workflow continuity during 503 failure
def test_appointment_workflow_continuity_during_gemini_503():
    """A temporary 503 must never confirm, duplicate, or erase an existing appointment draft."""
    client = _make_mock_client([
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
        (503, {"error": {"code": 503, "message": "High demand"}}, {}),
    ])

    adapter = GeminiReasoningAdapter(
        api_key="mock_key",
        model="gemini-3.1-flash-lite",
        http_client=client,
        max_retries=2,
        retry_backoff_base=0.01,
    )
    adapter._sleeper = lambda s: None

    manager = ConversationManager(adapter=adapter)
    session = manager.get_or_create_session("sess-continuity")
    session.draft.doctor_id = "doc-123"
    session.draft.doctor_name = "Dr. Vikram Mehta"
    session.draft.slot_id = "slot-456"
    session.draft.patient_reference = "PAT-999"
    session.confirmation_status = ConfirmationStatus.PENDING
    session.step = ConversationStep.AWAITING_CONFIRMATION

    initial_draft_doctor = session.draft.doctor_name
    initial_draft_slot = session.draft.slot_id

    mock_db = MagicMock()
    resp = manager.process_message(mock_db, "Yes, please confirm", session_id="sess-continuity")

    # 1. Did not falsely confirm appointment
    assert session.confirmation_status != ConfirmationStatus.CONFIRMED
    # 2. Did not lose the draft parameters
    assert session.draft.doctor_name == initial_draft_doctor
    assert session.draft.slot_id == initial_draft_slot
    # 3. Patient receives safe provider error guidance
    assert "temporarily unavailable" in resp.reply
    assert "HTTP 503" in resp.reply
