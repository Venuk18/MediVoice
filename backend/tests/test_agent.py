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
    assert "slot-sharma-avail-1" in data["reply"]
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
    assert "slot-sharma-avail-2" in r_change.json()["reply"]

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
    assert "slot-sharma-avail-1" in res.reply
    # Internal thoughts and <draft> tags must never leak to patient reply
    assert "Internal reasoning" not in res.reply
    assert "Secret chain of thought" not in res.reply
    assert "<draft>" not in res.reply

    # Both tools executed and logged in trace
    tool_names = [t.tool_name for t in res.tool_trace]
    assert tool_names == ["search_doctors", "get_available_slots"]
    # Verify thoughtSignature was preserved in Round 2 request payload
    assert "sig-round-1" in json.dumps(captured_requests[1])


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
    assert "slot-sharma-avail-1" in d2["reply"]
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
    assert "slot-nair-avail-1" in d2["reply"]
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
    assert "slot-sharma-avail-1" in d1["reply"]
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
    assert "slot-sharma-avail-2" in d_change["reply"]

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
    assert "slot-101" in d1["reply"]
    assert "slot-102" in d1["reply"]
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
    assert "slot-id-101" in d2["reply"]
    assert "not a valid offered slot ID" in d2["reply"]
    assert "slot-101" in d2["reply"]
    assert "slot-102" in d2["reply"]

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
    assert "slot-101" in d3["reply"]

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
    assert "slot-101" in d4["reply"]
    assert d4["draft"]["slot_start_time"] in d4["reply"]
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
    assert "slot-sharma-avail-1" in r1.json()["reply"]

    # Turn 2: Patient enters '101' -> rejected because 'slot-101' is not in offered slots
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "101"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["draft"]["slot_id"] is None
    assert d2["step"] == "COLLECTING_SLOT"
    assert "slot-sharma-avail-1" in d2["reply"]
    assert "slot-sharma-avail-2" in d2["reply"]


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
    assert "slot-sharma-avail-1" in d_pat["reply"]
    assert d_pat["draft"]["slot_start_time"] in d_pat["reply"]
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
    assert "slot-sharma-avail-1" in d2["reply"]

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
    assert "slot-sharma-avail-1" in d4["reply"]
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
    assert "slot-id-101" in res_invalid.reply
    assert "slot-101" in res_invalid.reply
    assert "slot-102" in res_invalid.reply

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


