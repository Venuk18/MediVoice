"""
Regression and End-to-End Tests for Conversation Intelligence, Context Management & Latency Optimization.

Verifies:
- Test A: New patient booking flow:
  "Cardiology" -> "Anyone is okay" -> "Okay, proceed" -> "No, I'm new" -> name -> phone -> explicit confirm -> booked.
- Test B: Returning patient booking flow:
  "Yes" -> reference lookup/phone -> confirmed.
- Test C: Cancellation:
  "Cancel this appointment request" -> cancelled.
  "No" when asked about previous visits -> does NOT cancel.
- Test D: Lab report failure and gratitude:
  Invalid code -> failure message -> "Okay, thanks for your support" -> warm closing without code prompt.
- Test E: Tool deduplication:
  Verify doctor search is NOT re-executed when selecting slot.
  Verify slot listing is NOT re-executed when patient provides name.
  Verify response contains only current-turn tool calls.
- Test F: Conversation continuity across short responses:
  Verify full flow works with short responses: "anyone", "okay", "no", "yes".
"""

import pytest
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.agent.schemas import ConversationStep, ConfirmationStatus


def test_a_new_patient_booking_flow(client, db_session, seeded_hospital_data):
    """
    Test A: New patient booking flow:
    "Cardiology" -> "Anyone is okay" -> "Okay, proceed" -> "No, I'm new" -> name -> phone -> explicit confirm -> booked.
    """
    session_id = "test-conv-intel-a"

    # Turn 1: Specify specialty -> searches doctors for Cardiology
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert "Cardiology" in d1["reply"] or "Dr." in d1["reply"]
    assert any(tc["tool_name"] == "search_doctors" for tc in d1.get("tool_calls", []))

    # Turn 2: Flexible doctor selection ("Anyone is okay") -> executes get_available_slots and suggests earliest slot
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anyone is okay"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert "earliest" in d2["reply"].lower() or "slot" in d2["reply"].lower()
    assert any(tc["tool_name"] == "get_available_slots" for tc in d2.get("tool_calls", []))

    # Turn 3: Accept / proceed with suggested slot
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay, proceed"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert "visited" in d3["reply"].lower()

    # Turn 4: New patient ("No, I'm new") -> MUST NOT CANCEL
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, I'm new"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["step"] != ConversationStep.CANCELLED
    assert "cancel" not in d4["reply"].lower()
    assert "name" in d4["reply"].lower()

    # Turn 5: Provide full name
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Aarav Sharma"})
    assert r5.status_code == 200
    d5 = r5.json()
    assert "mobile" in d5["reply"].lower() or "phone" in d5["reply"].lower()

    # Turn 6: Provide phone number -> auto-registers patient and presents booking summary
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9876543210"})
    assert r6.status_code == 200
    d6 = r6.json()
    assert "confirm" in d6["reply"].lower() or "summary" in d6["reply"].lower()
    assert d6["step"] == ConversationStep.AWAITING_CONFIRMATION

    # Turn 7: Explicit confirmation -> booked
    r7 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, confirm it"})
    assert r7.status_code == 200
    d7 = r7.json()
    assert d7["step"] == ConversationStep.BOOKED
    assert "confirmed" in d7["reply"].lower() or "appointment id" in d7["reply"].lower()

    # Verify db persistence
    created_patient = db_session.query(Patient).filter(Patient.phone_number == "9876543210").first()
    assert created_patient is not None
    assert created_patient.full_name == "Aarav Sharma"

    created_appt = db_session.query(Appointment).filter(Appointment.patient_reference == created_patient.patient_reference).first()
    assert created_appt is not None
    assert created_appt.appointment_status == "CONFIRMED"


def test_b_returning_patient_booking_flow(client, db_session, seeded_hospital_data):
    """
    Test B: Returning patient booking flow:
    "Yes" -> reference lookup/phone -> confirmed.
    """
    session_id = "test-conv-intel-b"

    # Seed returning patient
    existing_p = Patient(
        patient_reference="PAT-2024-8899",
        full_name="Meera Krishnan",
        phone_number="9840112233",
    )
    db_session.add(existing_p)
    db_session.commit()

    # Reach patient identification stage
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anyone is okay"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay, proceed"})

    # Turn 4: Patient indicates they are returning with "Yes"
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert "mobile" in d4["reply"].lower() or "reference" in d4["reply"].lower() or "number" in d4["reply"].lower()

    # Turn 5: Patient provides phone number
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9840112233"})
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["step"] == ConversationStep.AWAITING_CONFIRMATION
    assert "PAT-2024-8899" in d5["reply"] or "Meera" in d5["reply"]

    # Turn 6: Confirm booking
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, please confirm"})
    assert r6.status_code == 200
    d6 = r6.json()
    assert d6["step"] == ConversationStep.BOOKED
    assert "confirmed" in d6["reply"].lower()


def test_c_cancellation_vs_isolated_no(client, db_session, seeded_hospital_data):
    """
    Test C: Cancellation:
    - "Cancel this appointment request" -> cancelled.
    - "No" when asked about previous visits -> does NOT cancel.
    """
    # Part 1: Explicit cancellation
    s1 = "test-cancel-explicit"
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Cardiology"})
    r_cancel = client.post(
        "/api/v1/agent/chat",
        json={"session_id": s1, "message": "Cancel this appointment request"},
    )
    assert r_cancel.status_code == 200
    d_cancel = r_cancel.json()
    assert d_cancel["step"] == ConversationStep.CANCELLED
    assert "cancelled" in d_cancel["reply"].lower() or "canceled" in d_cancel["reply"].lower()

    # Part 2: Isolated 'No' when asked about previous visits does NOT cancel
    s2 = "test-no-not-cancel"
    client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Cardiology"})
    client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Anyone is okay"})
    r_ask_vis = client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Okay, proceed"})
    assert "visited" in r_ask_vis.json()["reply"].lower()

    # Patient replies with isolated "No"
    r_no = client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "No"})
    assert r_no.status_code == 200
    d_no = r_no.json()
    assert d_no["step"] != ConversationStep.CANCELLED
    assert "cancelled" not in d_no["reply"].lower()
    assert "name" in d_no["reply"].lower()


def test_d_lab_report_failure_and_gratitude(client, db_session, seeded_hospital_data):
    """
    Test D: Lab report failure and gratitude:
    Invalid code -> failure message -> "Okay, thanks for your support" -> warm closing without code prompt.
    """
    session_id = "test-lab-gratitude"

    # Turn 1: Ask for lab report
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Check lab report"})
    assert r1.status_code == 200
    assert "code" in r1.json()["reply"].lower()

    # Turn 2: Invalid code
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "999999"})
    assert r2.status_code == 200
    assert "invalid" in r2.json()["reply"].lower() or "expired" in r2.json()["reply"].lower() or "not found" in r2.json()["reply"].lower()

    # Turn 3: Patient expresses gratitude / closure
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay, thanks for your support"})
    assert r3.status_code == 200
    d3 = r3.json()
    # Must NOT prompt for the 6-digit code again!
    assert "code" not in d3["reply"].lower()
    assert "welcome" in d3["reply"].lower() or "day" in d3["reply"].lower() or "help" in d3["reply"].lower()


def test_e_tool_deduplication_and_turn_tool_calls(client, db_session, seeded_hospital_data):
    """
    Test E: Tool deduplication & current-turn tool calls:
    Verify doctor search is NOT re-executed when selecting slot.
    Verify slot listing is NOT re-executed when patient provides name.
    Verify response contains only current-turn tool calls.
    """
    session_id = "test-tool-dedup"

    # Turn 1: Specify specialty -> executes search_doctors for Cardiology
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
    d1 = r1.json()
    assert len(d1.get("tool_calls", [])) == 1
    assert d1["tool_calls"][0]["tool_name"] == "search_doctors"

    # Turn 2: Flexible doctor selection -> executes get_available_slots (does NOT re-execute search_doctors)
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anyone is okay"})
    d2 = r2.json()
    assert len(d2.get("tool_calls", [])) == 1
    assert d2["tool_calls"][0]["tool_name"] == "get_available_slots"

    # Turn 3: Confirm suggested slot (0 turn tool calls)
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay, proceed"})
    d3 = r3.json()
    assert len(d3.get("tool_calls", [])) == 0

    # Turn 4: Patient status (0 turn tool calls)
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, I am new"})
    d4 = r4.json()
    assert len(d4.get("tool_calls", [])) == 0

    # Turn 5: Patient name (0 turn tool calls)
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Rohit Verma"})
    d5 = r5.json()
    assert len(d5.get("tool_calls", [])) == 0

    # Turn 6: Phone number -> executes only register_patient
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9876543210"})
    d6 = r6.json()
    assert len(d6.get("tool_calls", [])) == 1
    assert d6["tool_calls"][0]["tool_name"] == "register_patient"


def test_f_conversation_continuity_short_responses(client, db_session, seeded_hospital_data):
    """
    Test F: Conversation continuity across short responses:
    Verify full flow works with short responses: "anyone", "okay", "no", "yes".
    """
    session_id = "test-short-responses"

    # 1. Cardiology
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
    assert r1.status_code == 200

    # 2. Short response: "anyone"
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "anyone"})
    assert r2.status_code == 200

    # 3. Short response: "okay"
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "okay"})
    assert r3.status_code == 200
    assert "visited" in r3.json()["reply"].lower()

    # 4. Short response: "no" -> marks new patient, asks name
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "no"})
    assert r4.status_code == 200
    assert "name" in r4.json()["reply"].lower()

    # 5. Name
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kavita Rao"})
    assert r5.status_code == 200

    # 6. Phone
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9811223344"})
    assert r6.status_code == 200
    assert r6.json()["step"] == ConversationStep.AWAITING_CONFIRMATION

    # 7. Short response: "yes" -> confirms and books
    r7 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "yes"})
    assert r7.status_code == 200
    assert r7.json()["step"] == ConversationStep.BOOKED
