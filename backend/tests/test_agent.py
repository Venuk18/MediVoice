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
