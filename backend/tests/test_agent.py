import pytest
from sqlalchemy import select
from app.models.appointment import Appointment
from app.models.appointment_slot import AppointmentSlot
from app.models.audit_event import AuditEvent
from app.agent.schemas import ToolCallIntent, ConversationStep, ConfirmationStatus
from app.agent.tool_router import RestrictedToolRouter
from app.agent.conversation_manager import ConversationManager


def test_restricted_tool_router_allowlist(db_session, seeded_hospital_data):
    """Restricted tool router blocks unauthorized tools and direct SQL execution."""
    router = RestrictedToolRouter()

    # Attempt unauthorized tool
    intent_unauthorized = ToolCallIntent(
        tool_name="drop_database",
        arguments={"table": "appointments"},
    )
    result = router.execute_tool(db_session, intent_unauthorized)
    assert not result.success
    assert "Access Denied" in result.error
    assert "drop_database" in result.error

    # Attempt arbitrary query execution
    intent_sql = ToolCallIntent(
        tool_name="execute_raw_sql",
        arguments={"sql": "SELECT * FROM doctors"},
    )
    result_sql = router.execute_tool(db_session, intent_sql)
    assert not result_sql.success
    assert "Access Denied" in result_sql.error


def test_restricted_tool_router_argument_validation(db_session, seeded_hospital_data):
    """Restricted tool router enforces strict parameter validation and rejects malformed inputs."""
    router = RestrictedToolRouter()

    # Disallowed argument in search_doctors
    res1 = router.execute_tool(
        db_session,
        ToolCallIntent(tool_name="search_doctors", arguments={"unexpected_flag": True}),
    )
    assert not res1.success
    assert "Invalid arguments" in res1.error

    # Missing doctor_id in get_available_slots
    res2 = router.execute_tool(
        db_session,
        ToolCallIntent(tool_name="get_available_slots", arguments={}),
    )
    assert not res2.success
    assert "Missing required argument 'doctor_id'" in res2.error

    # Missing required fields in book_appointment
    res3 = router.execute_tool(
        db_session,
        ToolCallIntent(
            tool_name="book_appointment",
            arguments={"patient_reference": "PAT-1"},
        ),
    )
    assert not res3.success
    assert "Missing required argument" in res3.error


def test_agent_doctor_search_by_specialty(client, seeded_hospital_data):
    """Agent handles clinical specialty query, invokes search_doctors tool, and presents doctors."""
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "I am experiencing chest pain and need to see a cardiologist"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Rajesh Sharma" in data["reply"]
    assert any(t["tool_name"] == "search_doctors" and t["success"] for t in data["tool_trace"])


def test_agent_slot_discovery(client, seeded_hospital_data):
    """Agent discovers open slots for selected doctor using get_available_slots tool."""
    # Send message selecting Dr. Sharma
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "I would like an appointment with Dr. Sharma"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["step"] == "COLLECTING_SLOT"
    assert "slot-sharma-avail-1" not in data["reply"]
    assert ("AM" in data["reply"] or "PM" in data["reply"] or ":" in data["reply"])
    assert any(t["tool_name"] == "get_available_slots" and t["success"] for t in data["tool_trace"])


def test_agent_missing_details_prompts_sequentially(client, seeded_hospital_data):
    """Agent identifies missing booking details and prompts patient turn-by-turn."""
    session_id = "test-session-multi-turn"

    # Turn 1: Specialty query -> prompts doctor
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I need cardiology consultation"},
    )
    assert r1.status_code == 200
    assert "doctor" in r1.json()["missing_details"]

    # Turn 2: Select doctor -> prompts slot
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I choose Dr. Rajesh Sharma"},
    )
    assert r2.status_code == 200
    assert "slot" in r2.json()["missing_details"]

    # Turn 3: Select slot -> prompts reason
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I want slot-sharma-avail-1"},
    )
    assert r3.status_code == 200
    assert "reason" in r3.json()["missing_details"]

    # Turn 4: Provide reason -> prompts patient reference
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "reason: Evaluation for intermittent palpitations"},
    )
    assert r4.status_code == 200
    assert "patient_reference" in r4.json()["missing_details"]

    # Turn 5: Provide patient reference -> all details present, enters AWAITING_CONFIRMATION
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "My patient reference is PAT-2026-9011"},
    )
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["step"] == "AWAITING_CONFIRMATION"
    assert d5["confirmation_status"] == "PENDING"
    assert len(d5["missing_details"]) == 0
    assert "Please verify and confirm" in d5["reply"]


def test_explicit_confirmation_gate_prevents_premature_booking(client, db_session, seeded_hospital_data):
    """Booking tool is never executed until explicit affirmative confirmation is received."""
    session_id = "test-gate-session"

    # Set up completed draft awaiting confirmation
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I choose Dr. Sharma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I pick slot-sharma-avail-1"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "reason: Cardiac checkup"})
    r = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-1122"})
    assert r.json()["step"] == "AWAITING_CONFIRMATION"

    # Confirm no appointment was created in DB yet
    appts_before = db_session.scalars(select(Appointment)).all()
    assert len(appts_before) == 1  # only pre-existing seeded appointment

    # Patient cancels
    r_cancel = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "No, cancel the booking"},
    )
    assert r_cancel.json()["step"] == "CANCELLED"
    assert r_cancel.json()["confirmation_status"] == "REJECTED"

    # Confirm no appointment was created
    appts_after = db_session.scalars(select(Appointment)).all()
    assert len(appts_after) == 1


def test_changed_details_invalidates_prior_confirmation(client, db_session, seeded_hospital_data):
    """Changing slot or doctor invalidates prior confirmation draft and updates summary."""
    session_id = "test-change-draft-session"

    # Fill draft with slot 1
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Dr. Sharma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "reason: Palpitations"})
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-3344"})
    assert r1.json()["step"] == "AWAITING_CONFIRMATION"
    assert r1.json()["draft"]["slot_id"] == "slot-sharma-avail-1"

    # User changes slot to slot-sharma-avail-2
    r_change = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "actually change slot to slot-sharma-avail-2"},
    )
    assert r_change.json()["draft"]["slot_id"] == "slot-sharma-avail-2"
    # Confirmation is re-prompted with new details, not booked yet
    assert r_change.json()["step"] == "AWAITING_CONFIRMATION"
    assert "slot-sharma-avail-2" not in r_change.json()["reply"]
    assert ("AM" in r_change.json()["reply"] or "PM" in r_change.json()["reply"] or ":" in r_change.json()["reply"])

    # Now explicitly confirm
    r_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "YES"},
    )
    assert r_confirm.json()["step"] == "BOOKED"
    assert r_confirm.json()["booked_appointment"]["slot_id"] == "slot-sharma-avail-2"


def test_duplicate_confirmation_attempt(client, db_session, seeded_hospital_data):
    """Agent prevents duplicate booking attempts when session is already booked."""
    session_id = "test-dup-session"

    # Complete and confirm booking
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Dr. Sharma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "reason: Checkup"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-5566"})
    r_booked = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "YES"})
    assert r_booked.json()["step"] == "BOOKED"
    appt_id = r_booked.json()["booked_appointment"]["appointment_id"]

    # Confirm again
    r_dup = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "CONFIRM"},
    )
    assert "already confirmed and booked" in r_dup.json()["reply"]
    assert appt_id in r_dup.json()["reply"]

    # Verify in DB: only 1 appointment booked for slot-sharma-avail-1
    appts = db_session.scalars(
        select(Appointment).where(Appointment.slot_id == "slot-sharma-avail-1")
    ).all()
    assert len(appts) == 1


def test_session_isolation(client, seeded_hospital_data):
    """Sessions are strictly isolated; patient details from one session do not leak to another."""
    session_a = "session-isolated-aaa"
    session_b = "session-isolated-bbb"

    # Populate session A
    client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_a, "message": "PAT-CONFIDENTIAL-999"},
    )
    state_a = client.get(f"/api/v1/agent/sessions/{session_a}").json()
    assert state_a["draft"]["patient_reference"] == "PAT-CONFIDENTIAL-999"

    # Check session B
    client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_b, "message": "Hello I want a doctor"},
    )
    state_b = client.get(f"/api/v1/agent/sessions/{session_b}").json()
    assert state_b["draft"]["patient_reference"] is None
    assert "PAT-CONFIDENTIAL-999" not in str(state_b)


def test_unavailable_slot_conflict_handling(client, db_session, seeded_hospital_data):
    """Unavailable slot (e.g. already booked) causes 409 Conflict, cleared slot, and no duplicate appointment."""
    session_id = "test-conflict-session"

    # Try booking slot-sharma-booked-3 (which is already BOOKED in seeded data)
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Dr. Sharma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-booked-3"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "reason: Routine review"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-7788"})

    # Send explicit confirmation
    r_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "YES"},
    )
    d = r_confirm.json()

    # Must NOT report success or mark as BOOKED
    assert d["step"] == "COLLECTING_SLOT"
    assert d["booked_appointment"] is None
    assert d["draft"]["slot_id"] is None
    assert "Booking could not be completed" in d["reply"]
    assert "409" in d["reply"] or "unavailable" in d["reply"]


def test_successful_booking_end_to_end_with_db_commit(client, db_session, seeded_hospital_data):
    """End-to-end conversation leads to explicit confirmation, atomic booking commit, and audit event."""
    session_id = "test-e2e-success"

    # Multi-turn interaction
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Dr. Rajesh Sharma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "reason: Angina consultation"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-8899"})

    # Explicit confirmation
    r_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "YES, please book the appointment"},
    )
    assert r_confirm.status_code == 200
    res = r_confirm.json()

    assert res["step"] == "BOOKED"
    assert res["confirmation_status"] == "CONFIRMED"
    appt_data = res["booked_appointment"]
    assert appt_data is not None
    assert appt_data["patient_reference"] == "PAT-2026-8899"
    assert appt_data["appointment_status"] == "CONFIRMED"
    assert appt_data["slot_id"] == "slot-sharma-avail-1"

    # Verify directly in Database
    appt_in_db = db_session.scalars(
        select(Appointment).where(Appointment.id == appt_data["appointment_id"])
    ).first()
    assert appt_in_db is not None
    assert appt_in_db.patient_reference == "PAT-2026-8899"
    assert appt_in_db.appointment_status == "CONFIRMED"

    # Verify slot was transitioned to BOOKED
    slot_in_db = db_session.scalars(
        select(AppointmentSlot).where(AppointmentSlot.id == "slot-sharma-avail-1")
    ).first()
    assert slot_in_db.status == "BOOKED"

    # Verify audit event in DB
    audit_in_db = db_session.scalars(
        select(AuditEvent).where(AuditEvent.entity_id == appt_in_db.id)
    ).first()
    assert audit_in_db is not None
    assert audit_in_db.action == "APPOINTMENT_BOOKED"
    assert audit_in_db.actor_reference == "AI_VOICE_AGENT"


# ==============================================================================
# Phase 2+: Gemini Adapter & Multilingual (TE, TA, KN, HI, EN) Test Suite
# ==============================================================================


def test_gemini_adapter_missing_credentials_handling():
    """GeminiReasoningAdapter handles missing API credentials safely without leaking secrets."""
    from app.agent.adapters import GeminiReasoningAdapter, ReasoningAdapterError
    from app.agent.schemas import AgentSessionState

    session = AgentSessionState(session_id="test-missing-key")

    # 1. Strict mode raises structured ReasoningAdapterError
    strict_adapter = GeminiReasoningAdapter(api_key="", strict_mode=True)
    with pytest.raises(ReasoningAdapterError) as exc_info:
        strict_adapter.plan_and_respond(session, "I need a cardiologist", ["search_doctors"])
    assert exc_info.value.code == "MISSING_CREDENTIALS"
    assert "GEMINI_API_KEY" in exc_info.value.safe_message

    # 2. Default safe mode returns user-safe fallback reply and records last_error
    safe_adapter = GeminiReasoningAdapter(api_key="", strict_mode=False)
    action = safe_adapter.plan_and_respond(session, "నాకు కార్డియాలజిస్ట్ కావాలి", ["search_doctors"])
    assert action.tool_call is None
    assert safe_adapter.last_error is not None
    assert "GEMINI_API_KEY" in safe_adapter.last_error
    assert session.language == "te"


def test_gemini_adapter_provider_failures_timeout_and_http_error():
    """GeminiReasoningAdapter handles provider timeouts, HTTP 500s, and malformed responses safely."""
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter, ReasoningAdapterError
    from app.agent.schemas import AgentSessionState

    session = AgentSessionState(session_id="test-provider-failures")

    # 1. Timeout simulation
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated provider timeout")

    timeout_client = httpx.Client(transport=httpx.MockTransport(timeout_handler))
    adapter_timeout = GeminiReasoningAdapter(
        api_key="test-fake-key-never-leaked",
        model="gemini-3.8-flash",
        timeout_seconds=2.5,
        http_client=timeout_client,
        strict_mode=False,
    )
    act_timeout = adapter_timeout.plan_and_respond(session, "Hello", ["search_doctors"])
    assert act_timeout.tool_call is None
    assert adapter_timeout.last_error is not None
    assert "timed out" in adapter_timeout.last_error.lower()
    assert "test-fake-key-never-leaked" not in act_timeout.reply
    assert "test-fake-key-never-leaked" not in adapter_timeout.last_error

    # 2. HTTP 500 simulation
    def error_500_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "Internal provider failure"}})

    err_client = httpx.Client(transport=httpx.MockTransport(error_500_handler))
    adapter_500 = GeminiReasoningAdapter(
        api_key="test-fake-key-never-leaked",
        model="gemini-3.8-flash",
        http_client=err_client,
        strict_mode=True,
    )
    with pytest.raises(ReasoningAdapterError) as exc_info:
        adapter_500.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_info.value.code == "PROVIDER_HTTP_ERROR"
    assert exc_info.value.status_code == 500
    assert "test-fake-key-never-leaked" not in exc_info.value.safe_message

    # 3. Empty candidates simulation
    def empty_candidates_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    empty_client = httpx.Client(transport=httpx.MockTransport(empty_candidates_handler))
    adapter_empty = GeminiReasoningAdapter(
        api_key="test-fake-key-never-leaked",
        http_client=empty_client,
        strict_mode=True,
    )
    with pytest.raises(ReasoningAdapterError) as exc_empty:
        adapter_empty.plan_and_respond(session, "Hello", ["search_doctors"])
    assert exc_empty.value.code == "INVALID_PROVIDER_RESPONSE"


def test_gemini_adapter_response_parsing_and_multi_round_tool_calling(db_session, seeded_hospital_data):
    """
    GeminiReasoningAdapter parses functionCall parts, strips internal thought parts,
    chains search_doctors -> get_available_slots via tool_executor, and strips <draft> metadata.
    """
    import json
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    call_count = 0
    captured_requests = []

    def mock_gemini_transport(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content.decode("utf-8"))
        captured_requests.append(body)

        if call_count == 1:
            # Round 1: Model emits internal thought + functionCall for search_doctors
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {"text": "Internal reasoning: user wants Cardiology in Telugu.", "thought": True},
                                    {
                                        "functionCall": {
                                            "name": "search_doctors",
                                            "args": {"specialty_or_department": "Cardiology"},
                                        },
                                        "thoughtSignature": "sig-round-1",
                                    },
                                ],
                            }
                        }
                    ]
                },
            )
        elif call_count == 2:
            # Round 2: Model receives doctor list and calls get_available_slots
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
                                            "name": "get_available_slots",
                                            "args": {"doctor_id": "doc-sharma-1"},
                                        },
                                        "thoughtSignature": "sig-round-2",
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        else:
            # Round 3: Model presents real slots in Telugu + <draft> update block
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {"text": "Secret chain of thought", "thought": True},
                                    {
                                        "text": (
                                            "డాక్టర్ రాజేష్ శర్మ (Cardiology) అందుబాటులో ఉన్నారు. "
                                            "అందుబాటులో ఉన్న స్లాట్లు: slot-sharma-avail-1, slot-sharma-avail-2. "
                                            "మీకు ఏ స్లాట్ కావాలో తెలపండి.\n"
                                            '<draft>{"doctor_id": "doc-sharma-1", "doctor_name": "Dr. Rajesh Sharma", "specialty": "Cardiology"}</draft>'
                                        )
                                    },
                                ],
                            }
                        }
                    ]
                },
            )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_gemini_transport))
    gemini_adapter = GeminiReasoningAdapter(
        api_key="mock-gemini-key",
        model="gemini-3.8-flash",
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=gemini_adapter)

    res = manager.process_message(
        db=db_session,
        session_id="gemini-multi-round-te",
        message="నాకు గుండె నొప్పిగా ఉంది, కార్డియాలజిస్ట్ కావాలి",
    )

    assert call_count == 3
    assert res.language == "te"
    assert res.step == ConversationStep.COLLECTING_SLOT
    assert res.draft.doctor_id == "doc-sharma-1"
    assert res.draft.doctor_name == "Dr. Rajesh Sharma"
    assert "డాక్టర్ రాజేష్ శర్మ" in res.reply
    assert "slot-sharma-avail-1" not in res.reply
    # Internal thoughts and <draft> tags must never leak to patient reply
    assert "Internal reasoning" not in res.reply
    assert "Secret chain of thought" not in res.reply
    assert "<draft>" not in res.reply

    # Both tools executed and logged in trace
    tool_names = [t.tool_name for t in res.tool_trace]
    assert tool_names == ["search_doctors", "get_available_slots"]
    # Verify thoughtSignature was preserved in Round 2 request payload
    assert "sig-round-1" in json.dumps(captured_requests[1])


def test_telugu_ambiguous_ack_requires_explicit_confirmation_exactly_once(
    db_session, seeded_hospital_data
):
    from app.agent.adapters import MockReasoningAdapter
    from app.agent.conversation_manager import ConversationManager
    from app.agent.schemas import BookingDraft, ConfirmationStatus, ConversationStep

    slot = seeded_hospital_data["slot_available"]
    doctor = seeded_hospital_data["doc_sharma"]
    manager = ConversationManager(adapter=MockReasoningAdapter())
    session = manager.get_or_create_session("telugu-confirm-clarification")
    session.language = "te"
    session.draft = BookingDraft(
        doctor_id=doctor.id,
        doctor_name=doctor.display_name,
        specialty=doctor.specialty,
        slot_id=slot.id,
        slot_start_time=slot.start_time.isoformat(),
        reason_category="సాధారణ తనిఖీ",
        patient_reference="PAT-2026-ACK01",
    )
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()
    session.step = ConversationStep.AWAITING_CONFIRMATION

    acknowledgement = manager.process_message(db_session, "సరే", session_id=session.session_id)
    assert acknowledgement.confirmation_status == ConfirmationStatus.PENDING
    assert acknowledgement.step == ConversationStep.AWAITING_CONFIRMATION
    assert "అవును" in acknowledgement.reply
    assert db_session.query(Appointment).filter(Appointment.slot_id == slot.id).count() == 0

    confirmed = manager.process_message(db_session, "అవును", session_id=session.session_id)
    assert confirmed.step == ConversationStep.BOOKED
    assert confirmed.confirmation_status == ConfirmationStatus.CONFIRMED
    assert slot.id not in confirmed.reply
    assert db_session.query(Appointment).filter(Appointment.slot_id == slot.id).count() == 1

    manager.process_message(db_session, "అవును", session_id=session.session_id)
    assert db_session.query(Appointment).filter(Appointment.slot_id == slot.id).count() == 1


def test_unclear_telugu_cab_statement_asks_clarification_and_preserves_booking_state(
    db_session, seeded_hospital_data
):
    from app.agent.adapters import MockReasoningAdapter
    from app.agent.conversation_manager import ConversationManager
    from app.agent.schemas import BookingDraft

    slot = seeded_hospital_data["slot_available"]
    doctor = seeded_hospital_data["doc_sharma"]
    manager = ConversationManager(adapter=MockReasoningAdapter())
    session = manager.get_or_create_session("telugu-cab-clarification")
    session.language = "te"
    session.draft = BookingDraft(
        doctor_id=doctor.id,
        doctor_name=doctor.display_name,
        specialty=doctor.specialty,
        slot_id=slot.id,
        slot_start_time=slot.start_time.isoformat(),
        reason_category="జ్వరం",
        patient_reference="PAT-2026-CAB01",
    )

    result = manager.process_message(db_session, "ఏదో మన cab లోనే తీసుకోవాలి", session_id=session.session_id)
    assert "క్యాబ్ గురించి" in result.reply
    assert result.draft.slot_id == slot.id
    assert result.draft.patient_reference == "PAT-2026-CAB01"


def test_gemini_adapter_max_tool_rounds_bound(db_session, seeded_hospital_data):
    """GeminiReasoningAdapter enforces max_tool_rounds to prevent runaway tool loops."""
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    calls = 0

    def runaway_tool_transport(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
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

    mock_client = httpx.Client(transport=httpx.MockTransport(runaway_tool_transport))
    gemini_adapter = GeminiReasoningAdapter(
        api_key="mock-key",
        max_tool_rounds=2,
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=gemini_adapter)

    res = manager.process_message(
        db=db_session,
        session_id="test-bounded-rounds",
        message="I need a cardiologist",
    )
    # Must stop after max_tool_rounds (2)
    assert calls == 2
    assert len(res.tool_trace) == 2
    assert res.reply


def test_gemini_adapter_confirmation_gate_blocks_premature_book_appointment(db_session, seeded_hospital_data):
    """
    Even if the LLM prematurely emits book_appointment before confirmation is pending,
    ConversationManager strictly blocks execution and requires explicit confirmation first.
    """
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    def premature_book_transport(request: httpx.Request) -> httpx.Response:
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
                                            "patient_reference": "PAT-2026-PREMATURE",
                                            "doctor_id": "doc-sharma-1",
                                            "selected_slot_id": "slot-sharma-avail-1",
                                            "reason_category": "Chest pain",
                                        },
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(premature_book_transport))
    gemini_adapter = GeminiReasoningAdapter(
        api_key="mock-key",
        max_tool_rounds=1,
        http_client=mock_client,
    )
    manager = ConversationManager(adapter=gemini_adapter)

    res = manager.process_message(
        db=db_session,
        session_id="test-premature-llm-book",
        message="Book Dr. Sharma slot-sharma-avail-1 for chest pain PAT-2026-PREMATURE",
    )

    # Must NOT be booked in DB! Instead enters AWAITING_CONFIRMATION with PENDING status
    assert res.step == ConversationStep.AWAITING_CONFIRMATION
    assert res.confirmation_status == ConfirmationStatus.PENDING
    assert res.booked_appointment is None
    appts = db_session.scalars(
        select(Appointment).where(Appointment.patient_reference == "PAT-2026-PREMATURE")
    ).all()
    assert len(appts) == 0


def test_multilingual_telugu_end_to_end_booking(client, db_session, seeded_hospital_data):
    """Full Telugu (te) appointment booking conversation maintains Telugu language through confirmation."""
    session_id = "test-lang-telugu"

    # Turn 1: Telugu specialty query
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు గుండె నొప్పిగా ఉంది, కార్డియాలజిస్ట్ కావాలి"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["language"] == "te"
    assert d1["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Rajesh Sharma" in d1["reply"]
    assert any("\u0C00" <= ch <= "\u0C7F" for ch in d1["reply"])

    # Turn 2: Select doctor in Telugu
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "డాక్టర్ రాజేష్ శర్మ గారితో అపాయింట్‌మెంట్ కావాలి"},
    )
    d2 = r2.json()
    assert d2["language"] == "te"
    assert d2["step"] == "COLLECTING_SLOT"
    assert "slot-sharma-avail-1" not in d2["reply"]
    assert ("AM" in d2["reply"] or "PM" in d2["reply"] or ":" in d2["reply"])
    assert any("\u0C00" <= ch <= "\u0C7F" for ch in d2["reply"])

    # Turn 3: Select slot (ASCII identifier, must preserve Telugu language!)
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-sharma-avail-1"},
    )
    d3 = r3.json()
    assert d3["language"] == "te"
    assert d3["step"] == "COLLECTING_DETAILS"
    assert "reason" in d3["missing_details"]
    assert any("\u0C00" <= ch <= "\u0C7F" for ch in d3["reply"])

    # Turn 4: Provide reason in Telugu
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "కారణం: ఛాతీ నొప్పి మరియు గుండె దడ"},
    )
    d4 = r4.json()
    assert d4["language"] == "te"
    assert "patient_reference" in d4["missing_details"]
    assert any("\u0C00" <= ch <= "\u0C7F" for ch in d4["reply"])

    # Turn 5: Provide synthetic patient reference
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "PAT-2026-TE01"},
    )
    d5 = r5.json()
    assert d5["language"] == "te"
    assert d5["step"] == "AWAITING_CONFIRMATION"
    assert d5["confirmation_status"] == "PENDING"
    assert "PAT-2026-TE01" in d5["reply"]
    assert any("\u0C00" <= ch <= "\u0C7F" for ch in d5["reply"])

    # Turn 6: Confirm in Telugu ('అవును')
    r6 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "అవును"},
    )
    d6 = r6.json()
    assert d6["language"] == "te"
    assert d6["step"] == "BOOKED"
    assert d6["confirmation_status"] == "CONFIRMED"
    assert d6["booked_appointment"]["patient_reference"] == "PAT-2026-TE01"
    assert any("\u0C00" <= ch <= "\u0C7F" for ch in d6["reply"])


def test_multilingual_tamil_end_to_end_booking(client, db_session, seeded_hospital_data):
    """Full Tamil (ta) appointment booking conversation maintains Tamil language through confirmation."""
    session_id = "test-lang-tamil"

    # Turn 1: Tamil Neurology query
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "எனக்கு தலைவலி உள்ளது, நரம்பியல் மருத்துவர் வேண்டும்"},
    )
    d1 = r1.json()
    assert d1["language"] == "ta"
    assert d1["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Priya Nair" in d1["reply"]
    assert any("\u0B80" <= ch <= "\u0BFF" for ch in d1["reply"])

    # Turn 2: Choose Dr. Priya Nair in Tamil
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "டாக்டர் பிரியா நாயர்"},
    )
    d2 = r2.json()
    assert d2["language"] == "ta"
    assert d2["step"] == "COLLECTING_SLOT"
    assert "slot-nair-avail-1" not in d2["reply"]
    assert any("\u0B80" <= ch <= "\u0BFF" for ch in d2["reply"])

    # Turn 3: Select slot
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-nair-avail-1"},
    )
    d3 = r3.json()
    assert d3["language"] == "ta"
    assert any("\u0B80" <= ch <= "\u0BFF" for ch in d3["reply"])

    # Turn 4: Provide reason in Tamil
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "காரணம்: ஒற்றைத் தலைவலி பரிசோதனை"},
    )
    d4 = r4.json()
    assert d4["language"] == "ta"
    assert any("\u0B80" <= ch <= "\u0BFF" for ch in d4["reply"])

    # Turn 5: Provide patient reference
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "PAT-2026-TA02"},
    )
    d5 = r5.json()
    assert d5["language"] == "ta"
    assert d5["step"] == "AWAITING_CONFIRMATION"
    assert any("\u0B80" <= ch <= "\u0BFF" for ch in d5["reply"])

    # Turn 6: Confirm in Tamil ('ஆம்')
    r6 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "ஆம்"},
    )
    d6 = r6.json()
    assert d6["language"] == "ta"
    assert d6["step"] == "BOOKED"
    assert d6["booked_appointment"]["patient_reference"] == "PAT-2026-TA02"
    assert any("\u0B80" <= ch <= "\u0BFF" for ch in d6["reply"])


def test_multilingual_kannada_conversation_and_cancellation(client, db_session, seeded_hospital_data):
    """Kannada (kn) conversation maintains Kannada responses and honors Kannada cancellation ('ಬೇಡ')."""
    session_id = "test-lang-kannada"

    # Turn 1: Select Dr. Sharma in Kannada
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "ನನಗೆ ಡಾ. ರಾಜೇಶ್ ಶರ್ಮಾ ಅವರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು"},
    )
    d1 = r1.json()
    assert d1["language"] == "kn"
    assert d1["step"] == "COLLECTING_SLOT"
    assert "slot-sharma-avail-1" not in d1["reply"]
    assert any("\u0C80" <= ch <= "\u0CFF" for ch in d1["reply"])

    # Turn 2: Select slot, reason, and patient ref
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "ಕಾರಣ: ಎದೆ ನೋವು ತಪಾಸಣೆ"})
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-KN03"})
    d4 = r4.json()
    assert d4["language"] == "kn"
    assert d4["step"] == "AWAITING_CONFIRMATION"
    assert any("\u0C80" <= ch <= "\u0CFF" for ch in d4["reply"])

    # Turn 5: Cancel in Kannada ('ಬೇಡ')
    r_cancel = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "ಬೇಡ"},
    )
    d_cancel = r_cancel.json()
    assert d_cancel["language"] == "kn"
    assert d_cancel["step"] == "CANCELLED"
    assert d_cancel["confirmation_status"] == "REJECTED"
    assert any("\u0C80" <= ch <= "\u0CFF" for ch in d_cancel["reply"])

    # Verify no appointment created for PAT-2026-KN03
    appts = db_session.scalars(
        select(Appointment).where(Appointment.patient_reference == "PAT-2026-KN03")
    ).all()
    assert len(appts) == 0


def test_multilingual_hindi_end_to_end_with_changed_details_reconfirmation(client, db_session, seeded_hospital_data):
    """Hindi (hi) conversation handles slot change invalidation and Hindi confirmation ('हाँ')."""
    session_id = "test-lang-hindi"

    # Turn 1: Hindi Cardiology query
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "मुझे सीने में दर्द है, कार्डियोलॉजिस्ट दिखाना है"},
    )
    d1 = r1.json()
    assert d1["language"] == "hi"
    assert d1["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Rajesh Sharma" in d1["reply"]
    assert any("\u0900" <= ch <= "\u097F" for ch in d1["reply"])

    # Turn 2: Select Dr. Sharma in Hindi
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "डॉ. राजेश शर्मा"},
    )
    d2 = r2.json()
    assert d2["language"] == "hi"
    assert d2["step"] == "COLLECTING_SLOT"

    # Turn 3-5: Complete draft with slot-sharma-avail-1
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "कारण: सीने में दर्द की जांच"})
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "PAT-2026-HI04"})
    assert r5.json()["step"] == "AWAITING_CONFIRMATION"
    assert r5.json()["language"] == "hi"

    # Turn 6: Change slot in Hindi -> invalidates prior confirmation and re-prompts in Hindi
    r_change = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "कृपया स्लॉट बदलकर slot-sharma-avail-2 करें"},
    )
    d_change = r_change.json()
    assert d_change["language"] == "hi"
    assert d_change["step"] == "AWAITING_CONFIRMATION"
    assert d_change["draft"]["slot_id"] == "slot-sharma-avail-2"
    assert "slot-sharma-avail-2" not in d_change["reply"]
    assert ("AM" in d_change["reply"] or "PM" in d_change["reply"] or ":" in d_change["reply"])

    # Turn 7: Confirm in Hindi ('हाँ')
    r_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "हाँ"},
    )
    d_confirm = r_confirm.json()
    assert d_confirm["language"] == "hi"
    assert d_confirm["step"] == "BOOKED"
    assert d_confirm["booked_appointment"]["slot_id"] == "slot-sharma-avail-2"
    assert d_confirm["booked_appointment"]["patient_reference"] == "PAT-2026-HI04"
    assert any("\u0900" <= ch <= "\u097F" for ch in d_confirm["reply"])


def test_gemini_adapter_multilingual_prompt_and_response_consistency_all_5_languages(db_session, seeded_hospital_data):
    """GeminiReasoningAdapter detects and preserves language consistency across Telugu, Tamil, Kannada, Hindi, and English."""
    import json
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    lang_samples = [
        ("te", "నాకు కార్డియాలజిస్ట్ కావాలి", "డాక్టర్ రాజేష్ శర్మ అందుబాటులో ఉన్నారు."),
        ("ta", "எனக்கு இருதய மருத்துவர் வேண்டும்", "டாக்டர் ராஜேஷ் சர்மா உள்ளார்."),
        ("kn", "ನನಗೆ ಹೃದ್ರೋಗ ತಜ್ಞರು ಬೇಕು", "ಡಾ. ರಾಜೇಶ್ ಶರ್ಮಾ ಲಭ್ಯವಿದ್ದಾರೆ."),
        ("hi", "मुझे हृदय रोग विशेषज्ञ चाहिए", "डॉ. राजेश शर्मा उपलब्ध हैं।"),
        ("en", "I need a cardiologist", "Dr. Rajesh Sharma is available."),
    ]

    for expected_lang, user_prompt, model_reply in lang_samples:
        captured_sys_prompt = ""

        def make_transport(reply_text: str):
            def _transport(request: httpx.Request) -> httpx.Response:
                nonlocal captured_sys_prompt
                body = json.loads(request.content.decode("utf-8"))
                captured_sys_prompt = body["systemInstruction"]["parts"][0]["text"]
                return httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "content": {
                                    "role": "model",
                                    "parts": [
                                        {
                                            "text": (
                                                f"{reply_text}\n"
                                                '<draft>{"specialty": "Cardiology"}</draft>'
                                            )
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )

            return _transport

        client_http = httpx.Client(transport=httpx.MockTransport(make_transport(model_reply)))
        adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=client_http)
        manager = ConversationManager(adapter=adapter)

        res = manager.process_message(
            db=db_session,
            session_id=f"lang-consistency-{expected_lang}",
            message=user_prompt,
        )
        assert res.language == expected_lang
        assert model_reply in res.reply
        assert f"code: '{expected_lang}'" in captured_sys_prompt


def test_gemini_adapter_end_to_end_booking_with_explicit_confirmation(db_session, seeded_hospital_data):
    """GeminiReasoningAdapter executes full appointment workflow through explicit confirmation gate and DB commit."""
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    turn = 0

    def e2e_gemini_transport(request: httpx.Request) -> httpx.Response:
        nonlocal turn
        turn += 1
        if turn == 1:
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
        elif turn == 2:
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
                                            "name": "get_available_slots",
                                            "args": {"doctor_id": "doc-sharma-1"},
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        else:
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "text": (
                                            "Please confirm your appointment with Dr. Rajesh Sharma in slot-sharma-avail-1.\n"
                                            '<draft>{"doctor_id": "doc-sharma-1", "doctor_name": "Dr. Rajesh Sharma", '
                                            '"specialty": "Cardiology", "slot_id": "slot-sharma-avail-1", '
                                            '"reason_category": "Chest pain checkup", "patient_reference": "PAT-2026-GEM99"}</draft>'
                                        )
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

    mock_client = httpx.Client(transport=httpx.MockTransport(e2e_gemini_transport))
    adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=mock_client)
    manager = ConversationManager(adapter=adapter)

    # Turn 1: User provides full request -> adapter searches doctors & slots, fills draft, and enters AWAITING_CONFIRMATION
    r1 = manager.process_message(
        db=db_session,
        session_id="gemini-e2e-book",
        message="Book Dr. Sharma slot-sharma-avail-1 for Chest pain checkup, patient PAT-2026-GEM99",
    )
    assert r1.step == ConversationStep.AWAITING_CONFIRMATION
    assert r1.confirmation_status == ConfirmationStatus.PENDING
    assert r1.booked_appointment is None

    # Turn 2: User explicitly confirms -> ConversationManager commits booking via book_appointment tool
    r2 = manager.process_message(
        db=db_session,
        session_id="gemini-e2e-book",
        message="YES",
    )
    assert r2.step == ConversationStep.BOOKED
    assert r2.confirmation_status == ConfirmationStatus.CONFIRMED
    assert r2.booked_appointment is not None
    assert r2.booked_appointment["patient_reference"] == "PAT-2026-GEM99"


def test_gemini_adapter_changed_details_invalidates_prior_confirmation(db_session, seeded_hospital_data):
    """When patient modifies slot during AWAITING_CONFIRMATION with GeminiReasoningAdapter, confirmation resets to PENDING."""
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    call_idx = 0

    def change_transport(request: httpx.Request) -> httpx.Response:
        nonlocal call_idx
        call_idx += 1
        slot_id = "slot-sharma-avail-1" if call_idx == 1 else "slot-sharma-avail-2"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": (
                                        f"Updated slot to {slot_id}. Please confirm.\n"
                                        f'<draft>{{"doctor_id": "doc-sharma-1", "doctor_name": "Dr. Rajesh Sharma", '
                                        f'"specialty": "Cardiology", "slot_id": "{slot_id}", '
                                        f'"reason_category": "Palpitations", "patient_reference": "PAT-2026-CHG1"}}</draft>'
                                    )
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(change_transport))
    adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=mock_client)
    manager = ConversationManager(adapter=adapter)

    r1 = manager.process_message(
        db=db_session,
        session_id="gemini-change-slot",
        message="Dr. Sharma slot-sharma-avail-1 reason: Palpitations PAT-2026-CHG1",
    )
    assert r1.step == ConversationStep.AWAITING_CONFIRMATION
    assert r1.draft.slot_id == "slot-sharma-avail-1"

    # Change slot instead of confirming
    r2 = manager.process_message(
        db=db_session,
        session_id="gemini-change-slot",
        message="change to slot-sharma-avail-2",
    )
    assert r2.step == ConversationStep.AWAITING_CONFIRMATION
    assert r2.confirmation_status == ConfirmationStatus.PENDING
    assert r2.draft.slot_id == "slot-sharma-avail-2"
    assert r2.booked_appointment is None


def test_gemini_adapter_unavailable_slot_and_duplicate_booking_conflict(db_session, seeded_hospital_data):
    """GeminiReasoningAdapter session surfaces 409 Conflict when confirming an already booked slot."""
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    def conflict_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": (
                                        "Please confirm slot-sharma-booked-3.\n"
                                        '<draft>{"doctor_id": "doc-sharma-1", "doctor_name": "Dr. Rajesh Sharma", '
                                        '"specialty": "Cardiology", "slot_id": "slot-sharma-booked-3", '
                                        '"reason_category": "Checkup", "patient_reference": "PAT-2026-CONF"}</draft>'
                                    )
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(conflict_transport))
    adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=mock_client)
    manager = ConversationManager(adapter=adapter)

    r1 = manager.process_message(
        db=db_session,
        session_id="gemini-conflict-test",
        message="Book slot-sharma-booked-3",
    )
    assert r1.step == ConversationStep.AWAITING_CONFIRMATION

    r2 = manager.process_message(
        db=db_session,
        session_id="gemini-conflict-test",
        message="YES",
    )
    assert r2.step == ConversationStep.COLLECTING_SLOT
    assert r2.booked_appointment is None
    assert r2.draft.slot_id is None
    assert any(t.tool_name == "book_appointment" and not t.success for t in r2.tool_trace)


def test_gemini_adapter_unapproved_tool_rejected_by_router(db_session, seeded_hospital_data):
    """If Gemini emits an unapproved tool call, RestrictedToolRouter blocks it and returns safe error."""
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    call_num = 0

    def unapproved_tool_transport(request: httpx.Request) -> httpx.Response:
        nonlocal call_num
        call_num += 1
        if call_num == 1:
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
                                            "name": "execute_raw_sql",
                                            "args": {"query": "DELETE FROM appointments"},
                                        }
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "I can only search doctors, check slots, or book appointments."}],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(unapproved_tool_transport))
    adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=mock_client)
    manager = ConversationManager(adapter=adapter)

    res = manager.process_message(
        db=db_session,
        session_id="gemini-unapproved-tool",
        message="Run SQL query",
    )
    assert len(res.tool_trace) == 1
    assert res.tool_trace[0].tool_name == "execute_raw_sql"
    assert not res.tool_trace[0].success
    assert "Access Denied" in (res.tool_trace[0].error or "")


def test_multilingual_search_doctors_aliases_in_all_5_languages(db_session, seeded_hospital_data):
    """search_doctors_tool resolves native-script Telugu, Tamil, Kannada, Hindi, and English queries."""
    from app.services.doctor_service import search_doctors_tool

    queries = [
        ("కార్డియాలజీ", "Cardiology"),
        ("நரம்பியல்", "Neurology"),
        ("ಹೃದ್ರೋಗ", "Cardiology"),
        ("कार्डियोलॉजी", "Cardiology"),
        ("Cardiology", "Cardiology"),
    ]
    for q, expected_spec in queries:
        results = search_doctors_tool(db_session, specialty_or_department=q)
        assert len(results) >= 1
        assert results[0]["specialty"] == expected_spec


def test_agent_config_endpoint_hides_api_key(client):
    """GET /api/v1/agent/config exposes provider, model, and supported languages without leaking GEMINI_API_KEY."""
    resp = client.get("/api/v1/agent/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "adapter_class" in data
    assert "provider" in data
    assert "supported_languages" in data
    assert set(data["supported_languages"]) == {"en", "te", "ta", "kn", "hi"}
    assert "api_key" not in str(data).lower()


def test_create_reasoning_adapter_factory_selection():
    """create_reasoning_adapter selects MockReasoningAdapter or GeminiReasoningAdapter appropriately."""
    from app.agent.adapters import create_reasoning_adapter, MockReasoningAdapter, GeminiReasoningAdapter

    mock_ad = create_reasoning_adapter(provider="mock")
    assert isinstance(mock_ad, MockReasoningAdapter)

    # Without API key, gemini provider falls back safely to MockReasoningAdapter
    fallback_ad = create_reasoning_adapter(provider="gemini", api_key="")
    assert isinstance(fallback_ad, MockReasoningAdapter)

    # With API key, gemini provider instantiates GeminiReasoningAdapter
    gem_ad = create_reasoning_adapter(provider="gemini", api_key="test-key", model="gemini-3.8-flash")
    assert isinstance(gem_ad, GeminiReasoningAdapter)
    assert gem_ad.model == "gemini-3.8-flash"


def test_regression_numeric_slot_selection_101_and_invalid_slot_id_101(
    client, db_session, seeded_hospital_data
):
    """
    Reproduces and verifies the exact reported conversation flow:
    - Assistant lists slot-101 and slot-102 for Dr. Rajesh Sharma.
    - Patient enters 'slot-id-101' (not offered) -> rejected with actual available IDs (slot-101, slot-102).
    - Patient enters '101' -> normalized to 'slot-101' because slot-101 is in the offered list.
    - Patient says 'chest pain' (without 'reason:' prefix) -> persisted, urgent guidance shown, advances to confirmation.
    - Explicit confirmation required before book_appointment is called.
    """
    from datetime import datetime, timedelta, timezone

    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    sharma = seeded_hospital_data["doc_sharma"]

    # Replace Dr. Sharma's available test slots with slot-101 and slot-102 to match the exact scenario
    for old_slot_id in ("slot-sharma-avail-1", "slot-sharma-avail-2"):
        old_s = db_session.get(AppointmentSlot, old_slot_id)
        if old_s:
            old_s.status = "BOOKED"

    slot_101 = AppointmentSlot(
        id="slot-101",
        doctor_id=sharma.id,
        start_time=now_utc + timedelta(days=1, hours=10),
        end_time=now_utc + timedelta(days=1, hours=10, minutes=30),
        status="AVAILABLE",
    )
    slot_102 = AppointmentSlot(
        id="slot-102",
        doctor_id=sharma.id,
        start_time=now_utc + timedelta(days=1, hours=14),
        end_time=now_utc + timedelta(days=1, hours=14, minutes=30),
        status="AVAILABLE",
    )
    db_session.add_all([slot_101, slot_102])
    db_session.commit()

    session_id = "regression-flow-101"
    pat_ref = "PAT-2026-4409"

    # Turn 1: Select Dr. Rajesh Sharma -> assistant lists slot-101 and slot-102
    r1 = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "I want to book an appointment with Dr. Rajesh Sharma",
            "patient_reference": pat_ref,
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["step"] == "COLLECTING_SLOT"
    assert "slot-101" not in d1["reply"]
    assert ("AM" in d1["reply"] or "PM" in d1["reply"] or ":" in d1["reply"])
    assert d1["draft"]["doctor_id"] == sharma.id
    assert d1["draft"]["patient_reference"] == pat_ref

    # Turn 2: Patient enters invalid ID 'slot-id-101' -> rejected with actual available IDs
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-id-101"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["slot_id"] is None
    assert "slot-id-101" not in d2["reply"]
    assert ("not available" in d2["reply"].lower() or "choose" in d2["reply"].lower())
    assert "<!--" not in d2["reply"]

    # Turn 3: Patient enters '101' -> normalized to 'slot-101' and advances to COLLECTING_DETAILS (reason)
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "101"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["draft"]["slot_id"] == "slot-101"
    assert d3["draft"]["slot_start_time"] is not None
    assert d3["step"] == "COLLECTING_DETAILS"
    assert "reason" in d3["missing_details"]
    assert "slot-101" not in d3["reply"]
    assert ("AM" in d3["reply"] or "PM" in d3["reply"] or ":" in d3["reply"])

    # Turn 4: Patient says 'chest pain' (natural language without 'reason:' prefix)
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "chest pain"},
    )
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["draft"]["reason_category"] == "chest pain"
    assert d4["step"] == "AWAITING_CONFIRMATION"
    assert d4["confirmation_status"] == "PENDING"
    assert d4["missing_details"] == []
    # Complete confirmation summary with doctor, slot ID + date/time, patient reference, and reason
    assert "Dr. Rajesh Sharma" in d4["reply"]
    assert "slot-101" not in d4["reply"]
    assert ("AM" in d4["reply"] or "PM" in d4["reply"] or ":" in d4["reply"])
    assert pat_ref in d4["reply"]
    assert "chest pain" in d4["reply"]
    # Concise urgent chest-pain emergency guidance included without blocking booking
    assert "108" in d4["reply"] or "emergency" in d4["reply"].lower()
    # Never call book_appointment before explicit confirmation
    assert not any(t["tool_name"] == "book_appointment" for t in d4["tool_trace"])

    # Turn 5: Explicit confirmation -> books appointment
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "YES"},
    )
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["step"] == "BOOKED"
    assert d5["confirmation_status"] == "CONFIRMED"
    assert d5["booked_appointment"]["slot_id"] == "slot-101"
    assert d5["booked_appointment"]["patient_reference"] == pat_ref


def test_regression_numeric_slot_rejected_when_not_in_offered_slots(client, seeded_hospital_data):
    """
    When the patient enters '101', it must NOT be normalized to 'slot-101' if 'slot-101'
    was not included in the current offered-slot list (e.g. when offered slots are
    slot-sharma-avail-1 and slot-sharma-avail-2).
    """
    session_id = "regression-unoffered-101"

    # Turn 1: Select Dr. Sharma -> offered slots are slot-sharma-avail-1 and slot-sharma-avail-2
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Dr. Rajesh Sharma"},
    )
    assert r1.status_code == 200
    assert "slot-sharma-avail-1" not in r1.json()["reply"]
    assert ("AM" in r1.json()["reply"] or "PM" in r1.json()["reply"] or ":" in r1.json()["reply"])

    # Turn 2: Patient enters '101' -> rejected because 'slot-101' is not in offered slots
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "101"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["draft"]["slot_id"] is None
    assert d2["step"] == "COLLECTING_SLOT"
    assert "slot-sharma-avail-1" not in d2["reply"]
    assert ("AM" in d2["reply"] or "PM" in d2["reply"] or ":" in d2["reply"])
    assert "slot-sharma-avail-2" not in d2["reply"]


def test_regression_natural_language_reason_without_prefix_advances_step(
    client, seeded_hospital_data
):
    """
    Natural-language reason replies such as 'chest pain' without a 'reason:' prefix
    are persisted, do not repeat the reason question, provide concise emergency guidance,
    and advance the conversation to the next step / confirmation.
    """
    session_id = "regression-natural-reason-no-prefix"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Dr. Sharma"})
    r_slot = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-sharma-avail-1"},
    )
    assert r_slot.json()["step"] == "COLLECTING_DETAILS"
    assert "reason" in r_slot.json()["missing_details"]

    # Reply with bare 'chest pain' (no 'reason:' prefix, no pre-set patient_reference)
    r_reason = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "chest pain"},
    )
    d_reason = r_reason.json()
    assert d_reason["draft"]["reason_category"] == "chest pain"
    assert "reason" not in d_reason["missing_details"]
    assert d_reason["missing_details"] == ["patient_reference"]
    assert "108" in d_reason["reply"] or "emergency" in d_reason["reply"].lower()

    # Now provide patient reference -> advances to AWAITING_CONFIRMATION with complete summary
    r_pat = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "PAT-2026-7788"},
    )
    d_pat = r_pat.json()
    assert d_pat["step"] == "AWAITING_CONFIRMATION"
    assert d_pat["confirmation_status"] == "PENDING"
    assert "Dr. Rajesh Sharma" in d_pat["reply"]
    assert "slot-sharma-avail-1" not in d_pat["reply"]
    assert ("AM" in d_pat["reply"] or "PM" in d_pat["reply"] or ":" in d_pat["reply"])
    assert "PAT-2026-7788" in d_pat["reply"]
    assert "chest pain" in d_pat["reply"]


def test_regression_mid_conversation_language_switching_preserves_state(
    client, db_session, seeded_hospital_data
):
    """
    Switching languages mid-conversation to Telugu, Tamil, Kannada, Hindi, or English
    preserves doctor, slot, reason, and patient reference without resetting or stalling.
    """
    session_id = "regression-lang-switch-mid-flow"
    pat_ref = "PAT-2026-6655"

    # Turn 1 (English): Select Dr. Rajesh Sharma
    r1 = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "I want an appointment with Dr. Rajesh Sharma",
            "patient_reference": pat_ref,
        },
    )
    assert r1.json()["language"] == "en"
    assert r1.json()["step"] == "COLLECTING_SLOT"

    # Turn 2: Switch to Telugu while at COLLECTING_SLOT
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Switch to Telugu"},
    )
    d2 = r2.json()
    assert d2["language"] == "te"
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_name"] == "Dr. Rajesh Sharma"
    assert d2["draft"]["patient_reference"] == pat_ref
    assert "slot-sharma-avail-1" not in d2["reply"]
    assert ("AM" in d2["reply"] or "PM" in d2["reply"] or ":" in d2["reply"])

    # Turn 3: Select valid offered slot while in Telugu
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-sharma-avail-1"},
    )
    d3 = r3.json()
    assert d3["language"] == "te"
    assert d3["draft"]["slot_id"] == "slot-sharma-avail-1"
    assert d3["step"] == "COLLECTING_DETAILS"
    assert d3["draft"]["reason_category"] is None

    # Turn 4: Provide natural-language reason 'chest pain' -> advances to confirmation in Telugu
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "chest pain"},
    )
    d4 = r4.json()
    assert d4["language"] == "te"
    assert d4["draft"]["reason_category"] == "chest pain"
    assert d4["step"] == "AWAITING_CONFIRMATION"
    assert d4["confirmation_status"] == "PENDING"
    assert "Dr. Rajesh Sharma" in d4["reply"]
    assert "slot-sharma-avail-1" not in d4["reply"]
    assert ("AM" in d4["reply"] or "PM" in d4["reply"] or ":" in d4["reply"])
    assert pat_ref in d4["reply"]
    assert "chest pain" in d4["reply"]

    # Turn 5: Switch to Tamil, Kannada, Hindi, and English during AWAITING_CONFIRMATION
    for switch_msg, expected_lang in [
        ("தமிழ்", "ta"),
        ("ಕನ್ನಡ", "kn"),
        ("हिन्दी", "hi"),
        ("Switch to English", "en"),
        ("తెలుగులో మాట్లాడండి", "te"),
    ]:
        r_sw = client.post(
            "/api/v1/agent/chat",
            json={"session_id": session_id, "message": switch_msg},
        )
        d_sw = r_sw.json()
        assert d_sw["language"] == expected_lang
        assert d_sw["step"] == "AWAITING_CONFIRMATION"
        assert d_sw["confirmation_status"] == "PENDING"
        assert d_sw["draft"]["doctor_name"] == "Dr. Rajesh Sharma"
        assert d_sw["draft"]["slot_id"] == "slot-sharma-avail-1"
        assert d_sw["draft"]["reason_category"] == "chest pain"
        assert d_sw["draft"]["patient_reference"] == pat_ref

    # Turn 6: Confirm in Telugu
    r_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "అవును"},
    )
    d_confirm = r_confirm.json()
    assert d_confirm["step"] == "BOOKED"
    assert d_confirm["confirmation_status"] == "CONFIRMED"
    assert d_confirm["booked_appointment"]["slot_id"] == "slot-sharma-avail-1"


def test_regression_gemini_adapter_numeric_slot_invalid_slot_and_natural_reason(
    db_session, seeded_hospital_data
):
    """
    Verifies that GeminiReasoningAdapter also enforces slot validation against offered slots,
    normalizes valid bare numeric slots (101 -> slot-101 when offered), rejects invalid slot IDs
    without calling Gemini to invent slots, and extracts natural-language reasons like 'chest pain'.
    """
    from datetime import datetime, timedelta, timezone
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter

    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    sharma = seeded_hospital_data["doc_sharma"]

    # Seed slot-101 and slot-102 for Dr. Sharma
    for old_slot_id in ("slot-sharma-avail-1", "slot-sharma-avail-2"):
        old_s = db_session.get(AppointmentSlot, old_slot_id)
        if old_s:
            old_s.status = "BOOKED"

    db_session.add_all(
        [
            AppointmentSlot(
                id="slot-101",
                doctor_id=sharma.id,
                start_time=now_utc + timedelta(days=1, hours=10),
                end_time=now_utc + timedelta(days=1, hours=10, minutes=30),
                status="AVAILABLE",
            ),
            AppointmentSlot(
                id="slot-102",
                doctor_id=sharma.id,
                start_time=now_utc + timedelta(days=1, hours=14),
                end_time=now_utc + timedelta(days=1, hours=14, minutes=30),
                status="AVAILABLE",
            ),
        ]
    )
    db_session.commit()

    def mock_gemini_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": (
                                        "Please share the missing details or confirm your booking.\n"
                                        f"[[DRAFT: doctor_id={sharma.id} | doctor_name={sharma.display_name} | "
                                        f"specialty={sharma.specialty} | slot_id=slot-101 | "
                                        "reason_category=chest pain | patient_reference=PAT-2026-5050]]"
                                    )
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_gemini_handler))
    adapter = GeminiReasoningAdapter(api_key="test-gemini-key", http_client=mock_client)
    manager = ConversationManager(adapter=adapter)
    session_id = "gemini-regression-slot-and-reason"

    # Seed session with Dr. Sharma and offered slots from get_available_slots
    session = manager.get_or_create_session(session_id, initial_patient_ref="PAT-2026-5050")
    session.draft.doctor_id = sharma.id
    session.draft.doctor_name = sharma.display_name
    session.draft.specialty = sharma.specialty
    slot_res = manager.tool_router.execute_tool(
        db_session,
        ToolCallIntent(tool_name="get_available_slots", arguments={"doctor_id": sharma.id}),
    )
    session.tool_trace.append(slot_res)

    # 1. Invalid slot 'slot-id-101' is rejected before accepting any hallucinated slot
    res_invalid = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="slot-id-101",
    )
    assert res_invalid.draft.slot_id is None
    assert res_invalid.step == ConversationStep.COLLECTING_SLOT
    assert "slot-id-101" not in res_invalid.reply
    assert ("not available" in res_invalid.reply.lower() or "choose" in res_invalid.reply.lower())
    assert "<!--" not in res_invalid.reply

    # 2. Bare numeric '101' normalizes to 'slot-101'
    res_num = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="101",
    )
    assert res_num.draft.slot_id == "slot-101"

    # 3. Natural-language 'chest pain' advances to AWAITING_CONFIRMATION with urgent guidance
    res_reason = manager.process_message(
        db=db_session,
        session_id=session_id,
        message="chest pain",
    )
    assert res_reason.draft.reason_category == "chest pain"
    assert res_reason.step == ConversationStep.AWAITING_CONFIRMATION
    assert res_reason.confirmation_status == ConfirmationStatus.PENDING
    assert "108" in res_reason.reply or "emergency" in res_reason.reply.lower()


# ==============================================================================
# Step 1: Natural Multilingual Conversation Test Suite
# ==============================================================================


def test_greetings_and_general_appointment_questions_in_all_5_languages(client, seeded_hospital_data):
    """
    Verifies natural responses to standalone greetings, general 'how to book' intent,
    department inquiries, and hospital timing questions across English, Telugu, Tamil,
    Kannada, and Hindi without corrupting session state.
    """
    greetings_by_lang = [
        ("en", "Hello", "Aarogya One Hospital"),
        ("te", "నమస్కారం", "ఆరోగ్య వన్"),
        ("ta", "வணக்கம்", "ஆரோக்கியா ஒன்"),
        ("kn", "ನಮಸ್ಕಾರ", "ಆರೋಗ್ಯ ಒನ್"),
        ("hi", "नमस्ते", "आरोग्य वन"),
    ]
    for expected_lang, msg, expected_phrase in greetings_by_lang:
        resp = client.post(
            "/api/v1/agent/chat",
            json={"session_id": f"greet-{expected_lang}", "message": msg},
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["language"] == expected_lang
        assert expected_phrase in d["reply"]
        assert d["draft"]["doctor_id"] is None

    # General department and timing inquiries
    r_dept = client.post(
        "/api/v1/agent/chat",
        json={"session_id": "general-q-en", "message": "What departments are available at the hospital?"},
    )
    assert r_dept.status_code == 200
    assert "Cardiology" in r_dept.json()["reply"]
    assert "Neurology" in r_dept.json()["reply"]

    r_hours_te = client.post(
        "/api/v1/agent/chat",
        json={"session_id": "general-q-te", "message": "హాస్పిటల్ సమయాలు ఏమిటి?"},
    )
    assert r_hours_te.status_code == 200
    assert r_hours_te.json()["language"] == "te"
    assert "08:00" in r_hours_te.json()["reply"]

    r_how_hi = client.post(
        "/api/v1/agent/chat",
        json={"session_id": "general-q-hi", "message": "मुझे अपॉइंटमेंट बुक करना है, कैसे करूँ?"},
    )
    assert r_how_hi.status_code == 200
    assert r_how_hi.json()["language"] == "hi"
    assert "आरोग्य वन" in r_how_hi.json()["reply"]


def test_general_question_mid_conversation_does_not_overwrite_visit_reason(client, seeded_hospital_data):
    """
    When the assistant asks for the clinical visit reason (after doctor and slot selection)
    and the patient asks a general question like 'What are the hospital timings?' or says 'Hello',
    the assistant answers the question and re-prompts for the reason instead of saving the question as the reason.
    """
    session_id = "mid-flow-question-safety"
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Dr. Rajesh Sharma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})

    # Ask hospital timings when reason is expected
    r_q = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "What are the hospital timings?"},
    )
    d_q = r_q.json()
    assert d_q["draft"]["reason_category"] is None
    assert "reason" in d_q["missing_details"]
    assert "08:00" in d_q["reply"]

    # Now provide actual reason
    r_reason = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Routine cardiac checkup"},
    )
    assert r_reason.json()["draft"]["reason_category"] == "Routine cardiac checkup"


def test_transliterated_and_mixed_language_conversations_across_indic_languages(
    client, db_session, seeded_hospital_data
):
    """
    Verifies that Romanized/transliterated phrases (Tenglish, Tanglish, Kanglish, Hinglish)
    and mixed-language inputs accurately detect language, resolve specialties via search_doctors,
    and maintain context.
    """
    from app.models.department import Department
    from app.models.doctor import Doctor

    hosp = seeded_hospital_data["hospital"]
    ortho_dept = Department(
        id="dept-ortho-translit", hospital_id=hosp.id, name="Orthopedics", description="Bone & Joint", is_active=True
    )
    gen_dept = Department(
        id="dept-gen-translit", hospital_id=hosp.id, name="General Medicine", description="Internal Med", is_active=True
    )
    db_session.add_all([ortho_dept, gen_dept])
    db_session.flush()
    db_session.add_all(
        [
            Doctor(
                id="doc-mehta-translit",
                hospital_id=hosp.id,
                department_id=ortho_dept.id,
                display_name="Dr. Vikram Mehta",
                specialty="Orthopedics",
                is_active=True,
            ),
            Doctor(
                id="doc-rao-translit",
                hospital_id=hosp.id,
                department_id=gen_dept.id,
                display_name="Dr. Sunita Rao",
                specialty="General Medicine",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    cases = [
        ("te", "Namaskaram, naaku gunde noppi undi, cardiologist kavali", "Cardiology", "Dr. Rajesh Sharma"),
        ("ta", "Vanakkam, enakku thalaivali, neurologist vendum", "Neurology", "Dr. Priya Nair"),
        ("kn", "Namaskara, nanage mandi novu ide, orthopedics vaidyaru beku", "Orthopedics", "Dr. Vikram Mehta"),
        ("hi", "Namaste, mujhe bukhar hai, general medicine doctor chahiye", "General Medicine", "Dr. Sunita Rao"),
    ]
    for expected_lang, message, expected_specialty, expected_doc in cases:
        resp = client.post(
            "/api/v1/agent/chat",
            json={"session_id": f"translit-{expected_lang}", "message": message},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == expected_lang
        assert data["draft"]["specialty"] == expected_specialty
        assert expected_doc in data["reply"]
        assert any(t["tool_name"] == "search_doctors" and t["success"] for t in data["tool_trace"])


def test_contextual_follow_up_ordinal_doctor_and_slot_selection(client, db_session, seeded_hospital_data):
    """
    Verifies follow-up selections that depend on earlier context:
    - 'first doctor' / 'మొదటి డాక్టర్' selects the first listed doctor from search_doctors trace.
    - 'second slot' / 'రెండవ స్లాట్' selects the second offered slot from get_available_slots trace.
    """
    session_id = "contextual-ordinal-flow"

    # Turn 1: Search Cardiology in Telugu -> returns Dr. Rajesh Sharma
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "కార్డియాలజీ డాక్టర్లు ఎవరు ఉన్నారు?"},
    )
    assert r1.status_code == 200
    assert r1.json()["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Rajesh Sharma" in r1.json()["reply"]

    # Turn 2: Select 'మొదటి డాక్టర్' (first doctor) -> selects Dr. Rajesh Sharma and fetches his slots
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "మొదటి డాక్టర్"},
    )
    d2 = r2.json()
    assert d2["draft"]["doctor_name"] == "Dr. Rajesh Sharma"
    assert d2["step"] == "COLLECTING_SLOT"
    assert "slot-sharma-avail-1" not in d2["reply"]
    assert ("AM" in d2["reply"] or "PM" in d2["reply"] or ":" in d2["reply"])
    assert "slot-sharma-avail-2" not in d2["reply"]

    # Turn 3: Select 'రెండవ స్లాట్' (second slot) -> selects slot-sharma-avail-2
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "రెండవ స్లాట్"},
    )
    d3 = r3.json()
    assert d3["draft"]["slot_id"] == "slot-sharma-avail-2"
    assert d3["step"] == "COLLECTING_DETAILS"


def test_corrections_switching_doctor_reason_and_slot_mid_conversation(
    client, db_session, seeded_hospital_data
):
    """
    Verifies that patients can change their mind mid-conversation:
    - Saying 'No, I want Dr. Priya Nair instead' switches doctor (clearing old slot) rather than cancelling.
    - Saying 'change reason to migraine' updates reason_category and invalidates prior confirmation.
    """
    session_id = "test-mid-flow-corrections"

    # Start with Dr. Sharma and slot-sharma-avail-1
    client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Dr. Rajesh Sharma", "patient_reference": "PAT-2026-3030"},
    )
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "slot-sharma-avail-1"})
    r_conf1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Routine checkup"})
    assert r_conf1.json()["step"] == "AWAITING_CONFIRMATION"
    assert r_conf1.json()["draft"]["doctor_name"] == "Dr. Rajesh Sharma"

    # Patient corrects doctor: "No, I want Dr. Priya Nair instead"
    r_switch_doc = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "No, I want Dr. Priya Nair instead"},
    )
    d_switch = r_switch_doc.json()
    assert d_switch["step"] == "COLLECTING_SLOT"
    assert d_switch["draft"]["doctor_name"] == "Dr. Priya Nair"
    assert d_switch["draft"]["slot_id"] is None
    assert "slot-nair-avail-1" not in d_switch["reply"]
    assert ("AM" in d_switch["reply"] or "PM" in d_switch["reply"] or ":" in d_switch["reply"])

    # Select first slot for Dr. Priya Nair
    r_slot = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "first slot"},
    )
    d_slot = r_slot.json()
    assert d_slot["draft"]["slot_id"] == "slot-nair-avail-1"
    assert d_slot["step"] == "AWAITING_CONFIRMATION"

    # Correct the visit reason during AWAITING_CONFIRMATION
    r_reason_chg = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "change reason to Heart palpitations follow-up"},
    )
    d_rchg = r_reason_chg.json()
    assert d_rchg["draft"]["reason_category"] == "Heart palpitations follow-up"
    assert d_rchg["step"] == "AWAITING_CONFIRMATION"
    assert d_rchg["confirmation_status"] == "PENDING"
    assert d_rchg["booked_appointment"] is None


def test_ambiguous_replies_and_cancellation_recovery(client, db_session, seeded_hospital_data):
    """
    Verifies:
    - Ambiguous replies ('maybe', 'not sure', 'ఏమో', 'पता नहीं') at confirmation do NOT commit a booking.
    - After cancelling a booking, sending a new doctor/specialty request cleanly starts a new draft in the same session.
    """
    session_id = "test-ambiguous-and-cancel-recovery"

    client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "Book Dr. Sharma for routine checkup",
            "patient_reference": "PAT-2026-4141",
        },
    )
    r_ready = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-sharma-avail-1"},
    )
    assert r_ready.json()["step"] == "AWAITING_CONFIRMATION"

    # Send ambiguous reply
    r_ambig = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I am not sure, let me think"},
    )
    d_ambig = r_ambig.json()
    assert d_ambig["step"] == "AWAITING_CONFIRMATION"
    assert d_ambig["booked_appointment"] is None
    assert "not booked yet" in d_ambig["reply"].lower()

    # Cancel booking
    r_cancel = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Cancel the booking"},
    )
    assert r_cancel.json()["step"] == "CANCELLED"

    # Resume in same session with a new doctor request
    r_resume = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Actually, I want to book with Dr. Priya Nair"},
    )
    d_resume = r_resume.json()
    assert d_resume["step"] == "COLLECTING_SLOT"
    assert d_resume["draft"]["doctor_name"] == "Dr. Priya Nair"
    assert "slot-nair-avail-1" not in d_resume["reply"]
    assert ("AM" in d_resume["reply"] or "PM" in d_resume["reply"] or ":" in d_resume["reply"])


def test_concise_slot_reminder_avoids_redundant_slot_list_repetition(client, seeded_hospital_data):
    """
    When slots have already been fetched and displayed for a selected doctor, and the patient
    provides their Patient Reference ID or visit reason before choosing a slot, the assistant
    acknowledges the detail and concisely asks for a slot ID without re-invoking get_available_slots.
    """
    session_id = "test-no-redundant-slot-dump"

    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I want to see Dr. Rajesh Sharma"},
    )
    assert r1.json()["step"] == "COLLECTING_SLOT"
    slot_calls_after_t1 = sum(1 for t in r1.json()["tool_trace"] if t["tool_name"] == "get_available_slots")
    assert slot_calls_after_t1 == 1

    # Patient provides patient reference before picking a slot
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "My patient ID is PAT-2026-9900"},
    )
    d2 = r2.json()
    assert d2["draft"]["patient_reference"] == "PAT-2026-9900"
    assert d2["step"] == "COLLECTING_SLOT"
    slot_calls_after_t2 = sum(1 for t in d2["tool_trace"] if t["tool_name"] == "get_available_slots")
    # Did not re-run get_available_slots unnecessarily
    assert slot_calls_after_t2 == 1
    assert "slot-sharma-avail-1" not in d2["reply"]
    assert ("AM" in d2["reply"] or "PM" in d2["reply"] or ":" in d2["reply"])


def test_urgent_symptoms_across_languages_provide_emergency_guidance(client, seeded_hospital_data):
    """
    Urgent symptoms (chest pain, severe shortness of breath, stroke/paralysis) in any supported
    language immediately include emergency guidance (108 / 112) without diagnosing the patient.
    """
    urgent_inputs = [
        ("en", "I have severe shortness of breath and chest tightness"),
        ("te", "నాకు ఊపిరి ఆడటం లేదు మరియు ఛాతీ నొప్పిగా ఉంది"),
        ("ta", "எனக்கு கடுமையான நெஞ்சு வலி மற்றும் மூச்சுத்திணறல் உள்ளது"),
        ("kn", "ನನಗೆ ತೀವ್ರ ಎದೆ ನೋವು ಮತ್ತು ಉಸಿರಾಟದ ತೊಂದರೆ ಇದೆ"),
        ("hi", "मुझे सीने में दर्द और सांस लेने में तकलीफ हो रही है"),
    ]
    for lang_code, text in urgent_inputs:
        resp = client.post(
            "/api/v1/agent/chat",
            json={"session_id": f"urgent-{lang_code}", "message": text},
        )
        assert resp.status_code == 200
        d = resp.json()
        assert d["language"] == lang_code
        assert "108" in d["reply"]


def test_end_user_test_1_exact_telugu_conversation_regression(client, seeded_hospital_data):
    """
    Reproduces and verifies the exact End-User Test 1 conversation in Telugu:
    1. User starts in Telugu -> Assistant replies naturally in Telugu (never generic English intro).
    2. User says 'నాకు తెలియదు ఎవరు' (I don't know who) -> Assistant responds empathetically in Telugu
       with a helpful follow-up question, without repeating the generic introduction or resetting.
    3. User reports severe chest pain ('నాకు తీవ్రమైన ఛాతీ నొప్పిగా ఉంది') -> Assistant prioritizes
       immediate emergency care (108 / 112) in Telugu and does NOT continue routine cardiologist selection.
    4. User continues describing urgent symptoms -> Assistant repeats concise emergency guidance in Telugu.
    """
    from app.agent.adapters import LOCALIZED_MESSAGES, has_expected_language_script

    session_id = "end-user-test-1-telugu"

    # Turn 1: Telugu appointment greeting/request
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నమస్కారం, నాకు డాక్టర్ అపాయింట్‌మెంట్ కావాలి"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["language"] == "te"
    assert has_expected_language_script(d1["reply"], "te")
    assert "Hello! I am the MediVoice" not in d1["reply"]

    # Turn 2: User says "నాకు తెలియదు ఎవరు" (I don't know who)
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు తెలియదు ఎవరు"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["language"] == "te"
    assert d2["step"] != "CANCELLED"
    assert has_expected_language_script(d2["reply"], "te")
    # Must NOT repeat the generic greeting/introduction
    assert d2["reply"] != LOCALIZED_MESSAGES["te"]["greeting"]
    assert d2["reply"] != LOCALIZED_MESSAGES["en"]["greeting"]
    # Must empathetically help the user choose by asking about symptom/department
    assert "పర్వాలేదు" in d2["reply"]
    assert "?" in d2["reply"]

    # Turn 3: User reports severe chest pain in Telugu
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు తీవ్రమైన ఛాతీ నొప్పిగా ఉంది"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["language"] == "te"
    assert has_expected_language_script(d3["reply"], "te")
    assert "108" in d3["reply"]
    assert "112" in d3["reply"]
    # Must NOT continue into routine cardiologist selection or list Dr. Sharma / Dr. Nair
    assert "Dr. Rajesh Sharma" not in d3["reply"]
    assert "Dr. Priya Nair" not in d3["reply"]
    assert d3["draft"]["doctor_id"] is None
    assert not any(t["tool_name"] == "search_doctors" for t in d3["tool_trace"])

    # Turn 4: User continues describing urgent symptoms
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "ఇంకా నొప్పి ఎక్కువైంది మరియు చెమటలు పడుతున్నాయి"},
    )
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["language"] == "te"
    assert has_expected_language_script(d4["reply"], "te")
    assert "108" in d4["reply"]
    assert "Dr. Rajesh Sharma" not in d4["reply"]
    assert d4["draft"]["doctor_id"] is None


def test_uncertainty_handling_all_five_languages_before_and_after_doctor_search(
    client, seeded_hospital_data
):
    """
    Verifies Requirement B (Handling uncertainty) across all 5 languages (en, te, ta, kn, hi):
    - Recognizes 'I don't know which doctor' / 'I'm not sure' and native equivalents.
    - Responds empathetically with a clear follow-up question or next step.
    - Does not reset/cancel the conversation or repeat the generic introduction.
    - Does not infer a medical diagnosis from uncertainty.
    """
    from app.agent.adapters import LOCALIZED_MESSAGES, has_expected_language_script

    cases = [
        ("en", "Hello, I need an appointment", "I don't know which doctor to see", "Cardiology", "I'm not sure"),
        ("te", "నమస్కారం, అపాయింట్‌మెంట్ కావాలి", "నాకు తెలియదు ఎవరు", "కార్డియాలజీ", "నాకు తెలీదు"),
        ("ta", "வணக்கம், அப்பாயின்ட்மென்ட் வேண்டும்", "எனக்கு தெரியவில்லை எந்த மருத்துவர்", "இதய மருத்துவம்", "எனக்கு தெரியவில்லை"),
        ("kn", "ನಮಸ್ಕಾರ, ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು", "ನನಗೆ ಗೊತ್ತಿಲ್ಲ ಯಾವ ವೈದ್ಯರು", "ಹೃದ್ರೋಗ ವಿಭಾಗ", "ನನಗೆ ಗೊತ್ತಿಲ್ಲ"),
        ("hi", "नमस्ते, मुझे अपॉइंटमेंट चाहिए", "मुझे नहीं पता कौन सा डॉक्टर", "कार्डियोलॉजी", "मुझे नहीं पता"),
    ]

    for lang_code, greet_msg, uncertain_initial, spec_msg, uncertain_after_list in cases:
        sid = f"uncertain-flow-{lang_code}"

        # 1. Initial greeting
        r1 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": greet_msg})
        assert r1.status_code == 200
        assert r1.json()["language"] == lang_code

        # 2. Uncertainty before any specialty/doctor is chosen
        r2 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": uncertain_initial})
        d2 = r2.json()
        assert d2["language"] == lang_code
        assert d2["step"] != "CANCELLED"
        assert has_expected_language_script(d2["reply"], lang_code)
        assert d2["reply"] != LOCALIZED_MESSAGES[lang_code]["greeting"]
        assert d2["reply"] != LOCALIZED_MESSAGES["en"]["greeting"]
        assert d2["draft"]["doctor_id"] is None

        # 3. User asks for Cardiology -> doctors are listed
        r3 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": spec_msg})
        d3 = r3.json()
        assert d3["language"] == lang_code
        assert "Dr. Rajesh Sharma" in d3["reply"]

        # 4. User expresses uncertainty about which listed doctor to pick
        r4 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": uncertain_after_list})
        d4 = r4.json()
        assert d4["language"] == lang_code
        assert d4["step"] != "CANCELLED"
        assert has_expected_language_script(d4["reply"], lang_code)
        assert "Dr. Rajesh Sharma" in d4["reply"]
        assert d4["reply"] != LOCALIZED_MESSAGES[lang_code]["greeting"]


def test_severe_emergency_priority_halts_routine_booking_all_five_languages(
    client, seeded_hospital_data
):
    """
    Verifies Requirement C (Emergency priority) across all 5 languages (en, te, ta, kn, hi):
    - Severe chest pain or life-threatening symptoms advise immediate emergency evaluation (108 / 112).
    - Routine doctor selection or slot booking is NOT continued in the same response.
    - Follow-up urgent symptom messages repeat concise safety guidance rather than routine booking.
    """
    from app.agent.adapters import has_expected_language_script

    emergency_cases = [
        (
            "en",
            "I am having severe chest pain and sweating",
            "The pain is spreading to my left arm and I feel dizzy",
        ),
        (
            "te",
            "నాకు తీవ్రమైన ఛాతీ నొప్పిగా ఉంది, ఊపిరి ఆడటం లేదు",
            "నొప్పి ఇంకా ఎక్కువగా ఉంది, తల తిరుగుతోంది",
        ),
        (
            "ta",
            "எனக்கு கடுமையான நெஞ்சு வலி மற்றும் மூச்சுத்திணறல் உள்ளது",
            "வலி அதிகமாகிறது மற்றும் வியர்க்கிறது",
        ),
        (
            "kn",
            "ನನಗೆ ತೀವ್ರ ಎದೆ ನೋವು ಮತ್ತು ಉಸಿರಾಟದ ತೊಂದರೆ ಇದೆ",
            "ನೋವು ಇನ್ನೂ ಹೆಚ್ಚಾಗುತ್ತಿದೆ ಮತ್ತು ಬೆವರುತ್ತಿದೆ",
        ),
        (
            "hi",
            "मुझे तेज सीने में दर्द हो रहा है और सांस लेने में तकलीफ है",
            "दर्द और बढ़ रहा है और पसीना आ रहा है",
        ),
    ]

    for lang_code, msg1, msg2 in emergency_cases:
        sid = f"severe-emergency-{lang_code}"

        # Turn 1: Severe symptom
        r1 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": msg1})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["language"] == lang_code
        assert has_expected_language_script(d1["reply"], lang_code)
        assert "108" in d1["reply"]
        assert "112" in d1["reply"]
        # Routine doctor list must NOT appear
        assert "Dr. Rajesh Sharma" not in d1["reply"]
        assert "Dr. Priya Nair" not in d1["reply"]
        assert d1["draft"]["doctor_id"] is None
        assert len(d1["tool_trace"]) == 0

        # Turn 2: Continued urgent symptoms
        r2 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": msg2})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["language"] == lang_code
        assert has_expected_language_script(d2["reply"], lang_code)
        assert "108" in d2["reply"]
        assert "Dr. Rajesh Sharma" not in d2["reply"]
        assert d2["draft"]["doctor_id"] is None
        assert len(d2["tool_trace"]) == 0


def test_language_consistency_preserved_across_english_inputs_and_gemini_fallback(
    db_session, seeded_hospital_data
):
    """
    Verifies Requirement A (Language consistency):
    - Once a Telugu (or other Indic) conversation is underway, short English/Latin replies or
      general questions do not reset session.language to English unless the user explicitly switches.
    - If GeminiReasoningAdapter returns an unlocalized English fallback during an active Telugu session,
      ensure_response_in_session_language replaces it with the localized Telugu response.
    """
    import httpx
    from app.agent.adapters import GeminiReasoningAdapter, has_expected_language_script

    def english_leaking_gemini_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": (
                                        "Hello! I am the MediVoice Hospital Assistant for Aarogya One Hospital. "
                                        "Which specialty or symptoms do you need consultation for?\n"
                                        "<draft>{}</draft>"
                                    )
                                }
                            ],
                        }
                    }
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(english_leaking_gemini_transport))
    adapter = GeminiReasoningAdapter(api_key="mock-key", http_client=mock_client)
    manager = ConversationManager(adapter=adapter)

    # Turn 1: User speaks Telugu, model tries to reply in generic English -> post-processor enforces Telugu
    r1 = manager.process_message(
        db=db_session,
        session_id="te-sticky-session",
        message="నమస్కారం, నాకు అపాయింట్‌మెంట్ కావాలి",
    )
    assert r1.language == "te"
    assert has_expected_language_script(r1.reply, "te")
    assert "Hello! I am the MediVoice" not in r1.reply

    # Turn 2: User sends an English phrase without an explicit language switch -> Telugu is preserved
    r2 = manager.process_message(
        db=db_session,
        session_id="te-sticky-session",
        message="I don't know which doctor",
    )
    assert r2.language == "te"
    assert has_expected_language_script(r2.reply, "te")
    assert "పర్వాలేదు" in r2.reply

    # Turn 3: User explicitly switches to English -> language switches to 'en'
    r3 = manager.process_message(
        db=db_session,
        session_id="te-sticky-session",
        message="switch to English",
    )
    assert r3.language == "en"


# ==============================================================================
# End-User Regression Fix: Context and Follow-Through (Bug 1 & Bug 2)
# ==============================================================================


def _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data):
    """Seeds General Medicine department, Dr. Vikram Mehta, and open slots matching production seed_data.py."""
    from datetime import datetime, timedelta, timezone
    from app.models.department import Department
    from app.models.doctor import Doctor

    hosp = seeded_hospital_data["hospital"]
    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    gen_dept = Department(
        id="test-dept-genmed",
        hospital_id=hosp.id,
        name="General Medicine",
        description="Internal Medicine and Primary Care",
        is_active=True,
    )
    db_session.add(gen_dept)
    db_session.flush()

    doc_mehta = Doctor(
        id="doc-mehta-5",
        hospital_id=hosp.id,
        department_id=gen_dept.id,
        display_name="Dr. Vikram Mehta",
        specialty="General Medicine",
        is_active=True,
    )
    db_session.add(doc_mehta)
    db_session.flush()

    slot_mehta_1 = AppointmentSlot(
        id="slot-mehta-avail-1",
        doctor_id=doc_mehta.id,
        start_time=now_utc + timedelta(days=1, hours=9),
        end_time=now_utc + timedelta(days=1, hours=9, minutes=30),
        status="AVAILABLE",
    )
    slot_mehta_2 = AppointmentSlot(
        id="slot-mehta-avail-2",
        doctor_id=doc_mehta.id,
        start_time=now_utc + timedelta(days=1, hours=11),
        end_time=now_utc + timedelta(days=1, hours=11, minutes=30),
        status="AVAILABLE",
    )
    db_session.add_all([slot_mehta_1, slot_mehta_2])
    db_session.commit()
    return doc_mehta


def test_bug1_telugu_sare_executes_pending_slot_offer_without_restarting(
    client, db_session, seeded_hospital_data
):
    """
    Reproduces and verifies Bug 1 (Telugu 'సరే' following an offer to show slots):
    1. Patient reports fever ('జ్వరం') -> Agent identifies General Medicine & Dr. Vikram Mehta.
    2. Patient says 'నాకు తెలియదు ఎవరు' (I do not know which doctor to choose).
    3. Agent offers to show Dr. Vikram Mehta's earliest available slots.
    4. Patient replies 'సరే' (Okay).
    5. Agent executes get_available_slots for Dr. Vikram Mehta and displays real slots,
       preserving Telugu language, visit reason ('జ్వరం'), and selected doctor without
       restarting symptom collection.
    """
    from app.agent.adapters import LOCALIZED_MESSAGES, has_expected_language_script

    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "bug1-telugu-sare-follow-through"

    # Turn 1: Patient reports fever in Telugu
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు జ్వరం ఉంది"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["language"] == "te"
    assert d1["step"] == "COLLECTING_DOCTOR"
    assert d1["draft"]["specialty"] == "General Medicine"
    assert d1["draft"]["reason_category"] == "జ్వరం"
    assert "Dr. Vikram Mehta" in d1["reply"]
    assert has_expected_language_script(d1["reply"], "te")

    # Turn 2: Patient says they do not know which doctor to choose
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు తెలియదు ఎవరు"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["language"] == "te"
    assert "Dr. Vikram Mehta" in d2["reply"]
    assert has_expected_language_script(d2["reply"], "te")

    # Turn 3: Patient replies 'సరే' (Okay) -> must execute get_available_slots for Dr. Vikram Mehta!
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "సరే"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["language"] == "te"
    assert d3["step"] == "COLLECTING_SLOT"
    assert d3["draft"]["doctor_id"] == "doc-mehta-5"
    assert d3["draft"]["doctor_name"] == "Dr. Vikram Mehta"
    assert d3["draft"]["specialty"] == "General Medicine"
    assert d3["draft"]["reason_category"] == "జ్వరం"
    # Must NOT restart symptom collection (clarify_need or greeting)
    assert d3["reply"] != LOCALIZED_MESSAGES["te"]["clarify_need"]
    assert d3["reply"] != LOCALIZED_MESSAGES["te"]["greeting"]
    # Real slots from backend tool must be present
    assert "slot-mehta-avail-1" not in d3["reply"]
    assert ("PM" in d3["reply"] or ":" in d3["reply"])
    assert any(
        t["tool_name"] == "get_available_slots"
        and t["success"]
        and any(s["slot_id"] == "slot-mehta-avail-1" for s in t["data"])
        for t in d3["tool_trace"]
    )


def test_bug1_contextual_affirmative_replies_in_all_five_languages(
    client, db_session, seeded_hospital_data
):
    """
    Verifies equivalent contextual affirmative replies in all 5 supported languages
    (English 'okay', Telugu 'సరే', Tamil 'சரி', Kannada 'ಸರಿ', Hindi 'ठीक है')
    execute the pending offered slot lookup via get_available_slots without resetting context.
    """
    from app.agent.adapters import LOCALIZED_MESSAGES, has_expected_language_script

    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)

    cases = [
        ("en", "I have fever", "I don't know which doctor", "okay"),
        ("te", "నాకు జ్వరం ఉంది", "నాకు తెలియదు ఎవరు", "సరే"),
        ("ta", "எனக்கு காய்ச்சல் உள்ளது", "எனக்கு தெரியவில்லை எந்த மருத்துவர்", "சரி"),
        ("kn", "ನನಗೆ ಜ್ವರ ಇದೆ", "ನನಗೆ ಗೊತ್ತಿಲ್ಲ ಯಾವ ವೈದ್ಯರು", "ಸರಿ"),
        ("hi", "मुझे बुखार है", "मुझे नहीं पता कौन सा डॉक्टर", "ठीक है"),
    ]

    for lang_code, symptom_msg, uncertain_msg, affirm_msg in cases:
        sid = f"bug1-all-langs-{lang_code}"

        # 1. Report fever -> identifies General Medicine & Dr. Vikram Mehta
        r1 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": symptom_msg})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["language"] == lang_code
        assert d1["draft"]["specialty"] == "General Medicine"
        assert "Dr. Vikram Mehta" in d1["reply"]

        # 2. Express uncertainty -> assistant offers to show Dr. Vikram Mehta's earliest available slots
        r2 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": uncertain_msg})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["language"] == lang_code
        assert "Dr. Vikram Mehta" in d2["reply"]

        # 3. Reply with contextual affirmative ('okay', 'సరే', 'சரி', 'ಸರಿ', 'ठीक है') -> retrieves slots
        r3 = client.post("/api/v1/agent/chat", json={"session_id": sid, "message": affirm_msg})
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["language"] == lang_code
        assert has_expected_language_script(d3["reply"], lang_code)
        assert d3["step"] == "COLLECTING_SLOT"
        assert d3["draft"]["doctor_id"] == "doc-mehta-5"
        assert d3["draft"]["doctor_name"] == "Dr. Vikram Mehta"
        assert d3["draft"]["specialty"] == "General Medicine"
        assert d3["draft"]["reason_category"] is not None
        assert "slot-mehta-avail-1" not in d3["reply"]
        assert ("PM" in d3["reply"] or ":" in d3["reply"])
        assert d3["reply"] != LOCALIZED_MESSAGES[lang_code]["clarify_need"]
        assert any(t["tool_name"] == "get_available_slots" and t["success"] for t in d3["tool_trace"])


def test_bug1_generic_affirmative_does_not_trigger_booking_without_explicit_confirmation(
    client, db_session, seeded_hospital_data
):
    """
    Verifies safety requirement:
    Generic contextual affirmative replies ('okay', 'ok', 'sure', 'సరే', 'சரி', 'ಸರಿ', 'ठीक है')
    must NOT trigger `book_appointment` when the session is at `AWAITING_CONFIRMATION`.
    Booking confirmation remains a separate, explicit step ('YES', 'CONFIRM', 'అవును', 'ஆம்', 'ಹೌದು', 'हाँ').
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)

    lang_cases = [
        ("te", "సరే", "అవును", "PAT-2026-SAFE-TE"),
        ("en", "okay", "YES", "PAT-2026-SAFE-EN"),
        ("ta", "சரி", "ஆம்", "PAT-2026-SAFE-TA"),
        ("kn", "ಸರಿ", "ಹೌದು", "PAT-2026-SAFE-KN"),
        ("hi", "ठीक है", "हाँ", "PAT-2026-SAFE-HI"),
    ]

    for idx, (lang_code, generic_ok, explicit_yes, pat_ref) in enumerate(lang_cases):
        # Add an open slot for each test iteration so each language can complete booking
        from datetime import datetime, timedelta, timezone

        now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        slot_id = f"slot-mehta-safe-{idx}"
        db_session.add(
            AppointmentSlot(
                id=slot_id,
                doctor_id="doc-mehta-5",
                start_time=now_utc + timedelta(days=2, hours=idx + 1),
                end_time=now_utc + timedelta(days=2, hours=idx + 1, minutes=30),
                status="AVAILABLE",
            )
        )
        db_session.commit()

        sid = f"no-premature-book-{lang_code}"
        client.post(
            "/api/v1/agent/chat",
            json={"session_id": sid, "message": "Dr. Vikram Mehta", "patient_reference": pat_ref},
        )
        client.post("/api/v1/agent/chat", json={"session_id": sid, "message": slot_id})
        r_ready = client.post(
            "/api/v1/agent/chat",
            json={"session_id": sid, "message": "reason: fever"},
        )
        assert r_ready.json()["step"] == "AWAITING_CONFIRMATION"
        assert r_ready.json()["confirmation_status"] == "PENDING"

        # Send generic 'okay' / 'సరే' / 'சரி' / 'ಸರಿ' / 'ठीक है' -> MUST NOT BOOK!
        r_generic = client.post(
            "/api/v1/agent/chat",
            json={"session_id": sid, "message": generic_ok},
        )
        d_generic = r_generic.json()
        assert d_generic["step"] == "AWAITING_CONFIRMATION"
        assert d_generic["confirmation_status"] == "PENDING"
        assert d_generic["booked_appointment"] is None
        assert not any(t["tool_name"] == "book_appointment" for t in d_generic["tool_trace"])

        # Verify no appointment exists in DB for pat_ref yet
        appts_before = db_session.scalars(
            select(Appointment).where(Appointment.patient_reference == pat_ref)
        ).all()
        assert len(appts_before) == 0

        # Now send EXPLICIT confirmation ('అవును', 'YES', 'ஆம்', 'ಹೌದು', 'हाँ') -> commits booking!
        r_explicit = client.post(
            "/api/v1/agent/chat",
            json={"session_id": sid, "message": explicit_yes},
        )
        d_explicit = r_explicit.json()
        assert d_explicit["step"] == "BOOKED"
        assert d_explicit["confirmation_status"] == "CONFIRMED"
        assert d_explicit["booked_appointment"] is not None
        assert d_explicit["booked_appointment"]["patient_reference"] == pat_ref


def test_bug2_fever_followed_by_fever_and_headache_preserves_general_medicine(
    client, db_session, seeded_hospital_data
):
    """
    Reproduces and verifies Bug 2 (Multiple symptoms trigger an unjustified specialty switch):
    1. Patient reports fever ('జ్వరం') -> Agent identifies General Medicine and offers Dr. Vikram Mehta.
    2. Patient adds 'జ్వరం, తలనొప్పి' (fever, headache).
    3. Agent preserves General Medicine and Dr. Vikram Mehta, updates reason_category to 'జ్వరం, తలనొప్పి',
       and does NOT switch to Neurology or Dr. Priya Nair.
    4. Patient replies 'సరే' (Okay) -> Agent retrieves Dr. Vikram Mehta's slots, and completes booking
       while preserving language ('te'), visit reason ('జ్వరం, తలనొప్పి'), selected doctor, and booking state.
    """
    from app.agent.adapters import has_expected_language_script

    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "bug2-telugu-fever-headache"

    # Turn 1: Patient reports fever in Telugu ('జ్వరం')
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "జ్వరం"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["language"] == "te"
    assert d1["draft"]["specialty"] == "General Medicine"
    assert d1["draft"]["reason_category"] == "జ్వరం"
    assert "Dr. Vikram Mehta" in d1["reply"]
    assert "Dr. Priya Nair" not in d1["reply"]

    # Turn 2: Patient adds 'జ్వరం, తలనొప్పి' (fever, headache)
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "జ్వరం, తలనొప్పి"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["language"] == "te"
    assert has_expected_language_script(d2["reply"], "te")
    # Must preserve General Medicine and Dr. Vikram Mehta (never switch to Neurology / Dr. Priya Nair)
    assert d2["draft"]["specialty"] == "General Medicine"
    assert d2["draft"]["reason_category"] == "జ్వరం, తలనొప్పి"
    assert "Dr. Vikram Mehta" in d2["reply"]
    assert "Dr. Priya Nair" not in d2["reply"]
    assert "Neurology" not in d2["reply"]

    # Turn 3: Patient accepts the offer to see Dr. Vikram Mehta's slots with 'సరే'
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "సరే"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["language"] == "te"
    assert d3["step"] == "COLLECTING_SLOT"
    assert d3["draft"]["doctor_id"] == "doc-mehta-5"
    assert d3["draft"]["doctor_name"] == "Dr. Vikram Mehta"
    assert d3["draft"]["specialty"] == "General Medicine"
    assert d3["draft"]["reason_category"] == "జ్వరం, తలనొప్పి"
    assert "slot-mehta-avail-1" not in d3["reply"]
    assert ("PM" in d3["reply"] or ":" in d3["reply"])

    # Turn 4: Select slot -> since reason_category ('జ్వరం, తలనొప్పి') is already preserved, asks only for patient_reference!
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-mehta-avail-1"},
    )
    d4 = r4.json()
    assert d4["language"] == "te"
    assert d4["step"] == "COLLECTING_DETAILS"
    assert d4["missing_details"] == ["patient_reference"]
    assert d4["draft"]["reason_category"] == "జ్వరం, తలనొప్పి"

    # Turn 5: Provide patient reference -> enters AWAITING_CONFIRMATION with preserved reason and doctor
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "PAT-2026-BUG12"},
    )
    d5 = r5.json()
    assert d5["language"] == "te"
    assert d5["step"] == "AWAITING_CONFIRMATION"
    assert d5["confirmation_status"] == "PENDING"
    assert "Dr. Vikram Mehta" in d5["reply"]
    assert "జ్వరం, తలనొప్పి" in d5["reply"]
    assert "PAT-2026-BUG12" in d5["reply"]

    # Turn 6: Explicit confirmation in Telugu ('అవును') -> books appointment
    r6 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "అవును"},
    )
    d6 = r6.json()
    assert d6["language"] == "te"
    assert d6["step"] == "BOOKED"
    assert d6["confirmation_status"] == "CONFIRMED"
    assert d6["booked_appointment"]["doctor_name"] == "Dr. Vikram Mehta"
    assert d6["booked_appointment"]["slot_id"] == "slot-mehta-avail-1"
    assert d6["booked_appointment"]["patient_reference"] == "PAT-2026-BUG12"


def test_bug2_explicit_user_requested_specialty_change_still_works(
    client, db_session, seeded_hospital_data
):
    """
    Verifies that while adding a common secondary symptom ('జ్వరం, తలనొప్పి') preserves General Medicine,
    an EXPLICIT user-requested specialty change (e.g. 'నాకు న్యూరాలజిస్ట్ కావాలి' or 'switch to Neurology instead')
    correctly switches to Neurology and Dr. Priya Nair.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "bug2-explicit-specialty-change"

    # Turn 1: Fever -> General Medicine (Dr. Vikram Mehta)
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "జ్వరం"},
    )
    assert r1.json()["draft"]["specialty"] == "General Medicine"
    assert "Dr. Vikram Mehta" in r1.json()["reply"]

    # Turn 2: Patient explicitly requests a Neurologist in Telugu ('నాకు న్యూరాలజిస్ట్ కావాలి')
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు న్యూరాలజిస్ట్ కావాలి"},
    )
    d2 = r2.json()
    assert d2["language"] == "te"
    assert d2["draft"]["specialty"] == "Neurology"
    assert "Dr. Priya Nair" in d2["reply"]

    # Also verify explicit specialty switch after a doctor was already selected
    session_id_2 = "bug2-explicit-switch-after-doc"
    client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id_2, "message": "Dr. Vikram Mehta"},
    )
    r_switch = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id_2, "message": "Actually switch to Neurology instead"},
    )
    d_switch = r_switch.json()
    assert d_switch["draft"]["specialty"] == "Neurology"
    assert d_switch["draft"]["doctor_id"] is None
    assert "Dr. Priya Nair" in d_switch["reply"]


def test_agent_lab_report_status_without_code_then_valid_and_invalid_followup(
    client, seeded_hospital_data
):
    """
    Conversational flow for lab report verification:
    1. User asks for lab report status without a code -> Agent asks for the 6-digit verification code.
    2. User enters a malformed code ('12345') -> Agent explains 6-digit requirement and stays ready.
    3. User enters an unknown 6-digit code ('999999') -> Agent explains code is invalid/expired.
    4. User enters a valid 6-digit code with leading zero ('048271') -> Agent calls check_lab_report_status
       and returns verified status without exposing patient_reference or internal IDs.
    """
    from app.services.lab_service import reset_verification_rate_limits

    reset_verification_rate_limits()
    session_id = "agent-lab-flow-en"

    # Turn 1: Ask for lab report status without code
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I want to check my lab report status"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert "6-digit" in d1["reply"] or "verification code" in d1["reply"].lower()
    assert not any(t["tool_name"] == "check_lab_report_status" for t in d1["tool_trace"])

    # Turn 2: Provide malformed 5-digit code ('12345')
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "12345"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert any(t["tool_name"] == "check_lab_report_status" for t in d2["tool_trace"])
    assert "6 digits" in d2["reply"] or "6-digit" in d2["reply"]

    # Turn 3: Provide unknown 6-digit code ('999999')
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "999999"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert "invalid or expired" in d3["reply"].lower()

    # Turn 4: Provide valid 6-digit code ('048271')
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "048271"},
    )
    assert r4.status_code == 200
    d4 = r4.json()
    assert "Cardiac Troponin I & Lipid Profile" in d4["reply"]
    assert "PROCESSING" in d4["reply"] or "Processing" in d4["reply"]
    # Privacy check: never expose synthetic patient_reference or internal order ID
    assert "PAT-1001" not in d4["reply"]
    assert "lab-overdue-1" not in d4["reply"]


def test_agent_lab_report_status_multilingual_all_5_languages(client, seeded_hospital_data):
    """
    Verifies conversational lab report status verification across all 5 languages
    (English, Telugu, Hindi, Tamil, Kannada) in both native script and Romanized forms.
    """
    from app.agent.adapters import has_expected_language_script
    from app.services.lab_service import reset_verification_rate_limits

    multilingual_cases = [
        ("en", "Check my lab report status", "048271", False),
        ("te", "నా ల్యాబ్ రిపోర్ట్ స్టేటస్ చెప్పండి", "048271", True),
        ("hi", "मेरी लैब रिपोर्ट का स्टेटस क्या है?", "839201", True),
        ("ta", "என் லேப் ரிப்போர்ட் நிலை என்ன?", "048271", True),
        ("kn", "ನನ್ನ ಲ್ಯಾಬ್ ವರದಿ ಸ್ಥಿತಿ ಏನು?", "839201", True),
        ("te", "naa lab report status cheppandi code 048271", None, True),
        ("hi", "meri lab report status bataiye code 839201", None, True),
        ("ta", "enaku lab report status venum code 048271", None, True),
        ("kn", "nanage lab report status beku code 839201", None, True),
    ]

    for idx, (expected_lang, first_msg, follow_up_code, expect_indic_script) in enumerate(multilingual_cases):
        reset_verification_rate_limits()
        sid = f"agent-lab-lang-{expected_lang}-{idx}"
        r1 = client.post(
            "/api/v1/agent/chat",
            json={"session_id": sid, "message": first_msg},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["language"] == expected_lang
        if expect_indic_script:
            assert has_expected_language_script(d1["reply"], expected_lang)

        if follow_up_code is not None:
            r2 = client.post(
                "/api/v1/agent/chat",
                json={"session_id": sid, "message": follow_up_code},
            )
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2["language"] == expected_lang
            if expect_indic_script:
                assert has_expected_language_script(d2["reply"], expected_lang)
            assert any(t["tool_name"] == "check_lab_report_status" and t["success"] for t in d2["tool_trace"])
            assert "PAT-1001" not in d2["reply"] and "PAT-1002" not in d2["reply"]
        else:
            assert any(t["tool_name"] == "check_lab_report_status" and t["success"] for t in d1["tool_trace"])


def test_agent_hospital_insurance_queries_and_multilingual_support(client, seeded_hospital_data):
    """
    Verifies hospital insurance queries through the conversational agent across all 5 languages:
    - Provider acceptance & plan coverage details
    - Cashless vs reimbursement filtering
    - Unsupported provider fallback with Insurance Desk contact
    - Mandatory non-guarantee disclaimer in every response
    """
    from app.agent.adapters import has_expected_language_script

    # 1. General accepted insurance providers query (English)
    r_en = client.post(
        "/api/v1/agent/chat",
        json={"session_id": "ins-en-1", "message": "Which insurance providers and cashless plans are accepted?"},
    )
    assert r_en.status_code == 200
    d_en = r_en.json()
    assert any(t["tool_name"] == "search_hospital_insurance" and t["success"] for t in d_en["tool_trace"])
    assert "Aarogya Shield Health Insurance" in d_en["reply"]
    assert "Legacy Metro" not in d_en["reply"]
    assert "does not guarantee coverage" in d_en["reply"]

    # 2. Unsupported insurance provider query
    r_unsup = client.post(
        "/api/v1/agent/chat",
        json={"session_id": "ins-en-unsup", "message": "Do you accept StarMax insurance?"},
    )
    assert r_unsup.status_code == 200
    d_unsup = r_unsup.json()
    assert "not currently listed" in d_unsup["reply"].lower()
    assert "1800-100-4200" in d_unsup["reply"]
    assert "does not guarantee coverage" in d_unsup["reply"]

    # 3. Multilingual insurance queries (Telugu, Hindi, Tamil, Kannada - native & Romanized)
    ins_cases = [
        ("te", "మీ హాస్పిటల్‌లో ఏ ఇన్సూరెన్స్ మరియు క్యాష్‌లెస్ ప్లాన్లు అంగీకరిస్తారు?"),
        ("hi", "आपके अस्पताल में कौन सा कैशलेस स्वास्थ्य बीमा और मेडिक्लेम स्वीकार किया जाता है?"),
        ("ta", "உங்கள் மருத்துவமனையில் எந்த மருத்துவ காப்பீடு மற்றும் கேஷ்லெஸ் திட்டங்கள் ஏற்றுக்கொள்ளப்படுகின்றன?"),
        ("kn", "ನಿಮ್ಮ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ ಯಾವ ಆರೋಗ್ಯ ವಿಮೆ ಮತ್ತು ಕ್ಯಾಶ್‌ಲೆಸ್ ಯೋಜನೆಗಳನ್ನು ಸ್ವೀಕರಿಸಲಾಗುತ್ತದೆ?"),
        ("te", "naaku insurance cashless details kavali"),
        ("hi", "mujhe cashless bima aur insurance plan chahiye"),
    ]
    for idx, (lang_code, msg) in enumerate(ins_cases):
        r_lang = client.post(
            "/api/v1/agent/chat",
            json={"session_id": f"ins-lang-{lang_code}-{idx}", "message": msg},
        )
        assert r_lang.status_code == 200
        d_lang = r_lang.json()
        assert d_lang["language"] == lang_code
        assert has_expected_language_script(d_lang["reply"], lang_code)
        assert "Aarogya Shield Health Insurance" in d_lang["reply"]
        assert "does not guarantee coverage" in d_lang["reply"]


def test_agent_preserves_booking_state_during_mid_flow_lab_and_insurance_questions(
    client, db_session, seeded_hospital_data
):
    """
    When a patient is in the middle of booking an appointment (e.g., in Telugu with doctor, slot,
    reason, and patient reference already collected at AWAITING_CONFIRMATION) and asks about
    hospital insurance or checks a lab report status, the agent answers the inquiry accurately
    WITHOUT losing the active language, doctor, slot, visit reason, or confirmation state.
    """
    from app.services.lab_service import reset_verification_rate_limits

    reset_verification_rate_limits()
    session_id = "mid-booking-lab-and-insurance-preserve"
    pat_ref = "PAT-2026-9900"

    # Turn 1: Select Dr. Rajesh Sharma in Telugu
    r1 = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "డాక్టర్ రాజేష్ శర్మ గారితో అపాయింట్‌మెంట్ కావాలి",
            "patient_reference": pat_ref,
        },
    )
    assert r1.json()["language"] == "te"
    assert r1.json()["step"] == "COLLECTING_SLOT"

    # Turn 2: Select slot-sharma-avail-1 and provide reason -> reaches AWAITING_CONFIRMATION
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-sharma-avail-1 గుండె దడ"},
    )
    d2 = r2.json()
    assert d2["language"] == "te"
    assert d2["step"] == "AWAITING_CONFIRMATION"
    assert d2["confirmation_status"] == "PENDING"
    assert d2["draft"]["doctor_id"] == "doc-sharma-1"
    assert d2["draft"]["slot_id"] == "slot-sharma-avail-1"
    assert d2["draft"]["reason_category"] == "గుండె దడ"

    # Turn 3: Mid-booking, patient asks about insurance in Telugu
    r_ins = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "మీ హాస్పిటల్‌లో ఆరోగ్య షీల్డ్ ఇన్సూరెన్స్ అంగీకరిస్తారా?"},
    )
    d_ins = r_ins.json()
    assert d_ins["language"] == "te"
    assert "Aarogya Shield Health Insurance" in d_ins["reply"]
    # Booking draft and confirmation state must remain completely intact!
    assert d_ins["step"] == "AWAITING_CONFIRMATION"
    assert d_ins["confirmation_status"] == "PENDING"
    assert d_ins["draft"]["doctor_id"] == "doc-sharma-1"
    assert d_ins["draft"]["slot_id"] == "slot-sharma-avail-1"
    assert d_ins["draft"]["reason_category"] == "గుండె దడ"
    assert d_ins["draft"]["patient_reference"] == pat_ref

    # Turn 4: Mid-booking, patient checks lab report status with code '048271'
    r_lab = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నా ల్యాబ్ రిపోర్ట్ కోడ్ 048271 స్టేటస్ చెప్పండి"},
    )
    d_lab = r_lab.json()
    assert d_lab["language"] == "te"
    assert "Cardiac Troponin I & Lipid Profile" in d_lab["reply"]
    # Booking draft and confirmation state still intact!
    assert d_lab["step"] == "AWAITING_CONFIRMATION"
    assert d_lab["confirmation_status"] == "PENDING"
    assert d_lab["draft"]["doctor_id"] == "doc-sharma-1"
    assert d_lab["draft"]["slot_id"] == "slot-sharma-avail-1"
    assert d_lab["draft"]["reason_category"] == "గుండె దడ"
    assert d_lab["draft"]["patient_reference"] == pat_ref

    # Turn 5: Patient explicitly confirms the pending appointment in Telugu ('అవును')
    r_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "అవును"},
    )
    d_confirm = r_confirm.json()
    assert d_confirm["language"] == "te"
    assert d_confirm["step"] == "BOOKED"
    assert d_confirm["confirmation_status"] == "CONFIRMED"
    assert d_confirm["booked_appointment"]["doctor_name"] == "Dr. Rajesh Sharma"
    assert d_confirm["booked_appointment"]["slot_id"] == "slot-sharma-avail-1"
    assert d_confirm["booked_appointment"]["patient_reference"] == pat_ref


