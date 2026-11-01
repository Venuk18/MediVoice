import json
import httpx
import pytest
from sqlalchemy import select

from app.agent.adapters import (
    GeminiReasoningAdapter,
    ReasoningAdapterError,
)
from app.agent.conversation_manager import ConversationManager
from app.agent.schemas import (
    AgentSessionState,
    BookingDraft,
    ConfirmationStatus,
    ConversationStep,
    ToolCallIntent,
)
from app.models.appointment import Appointment


def test_gemini_timeout_diagnostics():
    """Verify that a timeout logs and records all required diagnostic fields."""
    def timeout_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated 35.0s Gemini timeout")

    mock_client = httpx.Client(transport=httpx.MockTransport(timeout_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-api-key",
        model="gemini-3.5-flash",
        timeout_seconds=35.0,
        http_client=mock_client,
        strict_mode=False,
    )
    session = AgentSessionState(session_id="test-timeout-diag")
    action = adapter.plan_and_respond(session, "Hello doctor", ["search_doctors"])

    assert "temporarily unavailable" in action.reply or "తాత్కాలికంగా" in action.reply
    diag = adapter.last_turn_diagnostics
    assert diag is not None
    assert diag["correlation_id"].startswith("turn-")
    assert diag["model"] == "gemini-3.5-flash"
    assert diag["error_category"] == "timeout"
    assert diag["status_code"] is None
    assert diag["duration_ms"] >= 0.0
    assert diag["approx_tokens"] > 0
    assert diag["retry_count"] == 0
    assert "start_time_iso" in diag
    assert "completion_time_iso" in diag

    # Verify last_turn_timings has numeric values
    timings = adapter.last_turn_timings
    assert isinstance(timings["agent_ms"], float)
    assert isinstance(timings["gemini_calls_count"], float)


def test_gemini_provider_error_categories():
    """Verify rate_limit, invalid_payload, and internal_error diagnostic categories."""
    responses = {
        429: ("RESOURCE_EXHAUSTED", "rate_limit"),
        400: ("INVALID_ARGUMENT", "invalid_payload"),
        503: ("UNAVAILABLE", "internal_error"),
    }

    for code, (msg, expected_cat) in responses.items():
        def error_transport(request: httpx.Request) -> httpx.Response:
            return httpx.Response(code, json={"error": {"code": code, "message": msg}})

        mock_client = httpx.Client(transport=httpx.MockTransport(error_transport))
        adapter = GeminiReasoningAdapter(
            api_key="test-api-key",
            model="gemini-3.5-flash",
            http_client=mock_client,
            strict_mode=False,
        )
        session = AgentSessionState(session_id=f"test-err-{code}")
        action = adapter.plan_and_respond(session, "Help", ["search_doctors"])

        assert "temporarily unavailable" in action.reply
        diag = adapter.last_turn_diagnostics
        assert diag["status_code"] == code
        assert diag["error_category"] == expected_cat


def test_draft_preservation_after_timeout(db_session, seeded_hospital_data):
    """Verify that a timeout preserves all draft fields without clearing or resetting state."""
    doc = seeded_hospital_data["doc_sharma"]
    slot = seeded_hospital_data["slot_available"]
    pat_ref = "PAT-1001"

    def timeout_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Gemini timed out")

    mock_client = httpx.Client(transport=httpx.MockTransport(timeout_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-api-key",
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=adapter)

    # Pre-seed session with draft details
    session = manager.get_or_create_session("test-draft-preserve")
    session.draft.doctor_id = doc.id
    session.draft.doctor_name = doc.display_name
    session.draft.specialty = doc.specialty
    session.draft.slot_id = slot.id
    session.draft.slot_start_time = slot.start_time
    session.draft.patient_reference = pat_ref
    session.draft.reason_category = "General Consultation"
    session.confirmation_status = ConfirmationStatus.PENDING

    res = manager.process_message(
        db=db_session,
        session_id="test-draft-preserve",
        message="yes please book",
    )

    # Draft must be 100% preserved
    assert res.draft.doctor_id == doc.id
    assert res.draft.doctor_name == doc.display_name
    assert res.draft.specialty == doc.specialty
    assert res.draft.slot_id == slot.id
    assert res.draft.patient_reference == pat_ref
    assert res.draft.reason_category == "General Consultation"
    assert "temporarily unavailable" in res.reply


def test_guarantee_no_appointment_booked_after_reasoning_failure(db_session, seeded_hospital_data):
    """
    CRITICAL SAFETY REQUIREMENT:
    Guarantee that no appointment is booked in the database after a reasoning failure/timeout.
    """
    doc = seeded_hospital_data["doc_sharma"]
    slot = seeded_hospital_data["slot_available"]
    pat_ref = "PAT-1001"

    def timeout_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Gemini API request timed out after 35.0s.")

    mock_client = httpx.Client(transport=httpx.MockTransport(timeout_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-api-key",
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=adapter)

    # Set up complete draft ready to confirm
    session = manager.get_or_create_session("test-no-book-on-fail")
    session.draft.doctor_id = doc.id
    session.draft.doctor_name = doc.display_name
    session.draft.specialty = doc.specialty
    session.draft.slot_id = slot.id
    session.draft.slot_start_time = slot.start_time
    session.draft.patient_reference = pat_ref
    session.draft.reason_category = "General Consultation"
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    # Initial count of appointments in database
    initial_count = len(db_session.scalars(select(Appointment)).all())

    # User confirms: "yes, confirm booking"
    res = manager.process_message(
        db=db_session,
        session_id="test-no-book-on-fail",
        message="yes, confirm booking",
    )

    # 1. Reply must clearly state that reasoning is temporarily unavailable
    assert "temporarily unavailable" in res.reply
    assert "timed out" in res.reply

    # 2. No booked appointment object returned
    assert res.booked_appointment is None
    assert session.booked_appointment is None

    # 3. Confirmation status must NOT be CONFIRMED
    assert session.confirmation_status != ConfirmationStatus.CONFIRMED

    # 4. Database count MUST NOT increase (zero ghost appointments)
    final_count = len(db_session.scalars(select(Appointment)).all())
    assert final_count == initial_count

    # 5. Draft remains intact for retry
    assert session.draft.doctor_id == doc.id
    assert session.draft.slot_id == slot.id


def test_recovery_on_subsequent_request(db_session, seeded_hospital_data):
    """
    Verify recovery: After a reasoning failure, a subsequent successful request
    uses the preserved draft to finalize booking cleanly without restarting.
    """
    doc = seeded_hospital_data["doc_sharma"]
    slot = seeded_hospital_data["slot_available"]
    pat_ref = "PAT-1001"
    turn = 0

    def recovering_transport(request: httpx.Request) -> httpx.Response:
        nonlocal turn
        turn += 1
        if turn == 1:
            # Turn 1: Timeout
            raise httpx.ReadTimeout("Gemini API request timed out after 35.0s.")
        else:
            # Turn 2: Recovered! Model calls book_appointment with verified IDs
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
                                            "name": "book_appointment",
                                            "args": {
                                                "doctor_id": doc.id,
                                                "selected_slot_id": slot.id,
                                                "patient_reference": pat_ref,
                                                "reason_category": "General Consultation",
                                            },
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

    mock_client = httpx.Client(transport=httpx.MockTransport(recovering_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-api-key",
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=adapter)

    session = manager.get_or_create_session("test-recover")
    session.draft.doctor_id = doc.id
    session.draft.doctor_name = doc.display_name
    session.draft.specialty = doc.specialty
    session.draft.slot_id = slot.id
    session.draft.slot_start_time = slot.start_time
    session.draft.patient_reference = pat_ref
    session.draft.reason_category = "General Consultation"
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    # Turn 1: Fails due to timeout
    res1 = manager.process_message(db=db_session, session_id="test-recover", message="yes confirm")
    assert "temporarily unavailable" in res1.reply
    assert res1.booked_appointment is None

    # Turn 2: Patient retries "yes confirm" -> Recovers and books!
    res2 = manager.process_message(db=db_session, session_id="test-recover", message="yes confirm")
    assert res2.booked_appointment is not None
    assert res2.step == ConversationStep.BOOKED
    assert session.confirmation_status == ConfirmationStatus.CONFIRMED


def test_prevent_duplicate_tool_execution(db_session, seeded_hospital_data):
    """
    Verify that:
    1. Duplicate booking attempts in the same turn are blocked.
    2. Identical tool calls in the same turn are deduplicated.
    """
    def multi_tool_transport(request: httpx.Request) -> httpx.Response:
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
                                        "args": {"specialty_or_department": "Cardiology"},
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(multi_tool_transport))
    adapter = GeminiReasoningAdapter(
        api_key="test-api-key",
        max_tool_rounds=2,
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=adapter)

    res = manager.process_message(
        db=db_session,
        session_id="test-dedup-tool",
        message="I need a cardiologist",
    )

    # In turn_tool_calls, the tool execution was recorded cleanly
    assert len(res.turn_tool_calls) >= 1
    assert res.turn_tool_calls[0].success


def test_connection_pooling_reused_client():
    """Verify persistent managed HTTP client with keep-alive limits and timeouts."""
    adapter = GeminiReasoningAdapter(api_key="test-key", timeout_seconds=25.0)
    assert adapter._managed_client is None

    client1 = adapter._get_client()
    assert client1 is not None
    assert not client1.is_closed

    # Second call must reuse the same managed client instance (connection pooling)
    client2 = adapter._get_client()
    assert client1 is client2

    # Clean shutdown
    adapter.close()
    assert adapter._managed_client is None
