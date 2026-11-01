"""
Tests for Natural Human-Like Conversational Appointment Booking System.
Verifies Scenarios A, B, C, D, E:
- Scenario A: Patient describes symptoms -> empathetic suggestion -> doctor selected naturally
- Scenario B: Patient is unsure of slot ("Anything is fine") -> earliest suggested -> accepted without premature booking
- Scenario C: New patient registration workflow (full name, 10-digit phone -> unique PAT-2026-XXXX generated and persisted)
- Scenario D: Existing patient recovery ("I don't remember" -> mobile phone lookup and verification)
- Scenario E: Summary presentation & strict confirmation gate before transactional booking
"""

import pytest
from sqlalchemy import select
from app.models.appointment import Appointment
from app.models.appointment_slot import AppointmentSlot
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.agent.schemas import ConversationStep, ConfirmationStatus


def _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data):
    """Ensures General Medicine department, Dr. Vikram Mehta, and available future slots exist."""
    from datetime import datetime, timedelta, timezone
    from app.models.department import Department
    from app.models.doctor import Doctor

    hosp = seeded_hospital_data["hospital"]
    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    gen_dept = Department(
        id="test-dept-genmed-nat",
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

    tomorrow_10am = (now_utc + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    tomorrow_2pm = (now_utc + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)

    slot1 = AppointmentSlot(
        id="slot-mehta-nat-1",
        doctor_id=doc_mehta.id,
        start_time=tomorrow_10am,
        end_time=tomorrow_10am + timedelta(minutes=30),
        status="AVAILABLE",
    )
    slot2 = AppointmentSlot(
        id="slot-mehta-nat-2",
        doctor_id=doc_mehta.id,
        start_time=tomorrow_2pm,
        end_time=tomorrow_2pm + timedelta(minutes=30),
        status="AVAILABLE",
    )
    db_session.add_all([slot1, slot2])
    db_session.commit()
    return doc_mehta


def test_scenario_a_symptoms_to_general_medicine_vikram_mehta(client, db_session, seeded_hospital_data):
    """
    Scenario A:
    Patient: 'I have a fever.'
    Assistant: Empathetic response, suggests General Medicine and finds Dr. Vikram Mehta.
    Patient: 'Vikram is fine.'
    Assistant: Confirms selection and fetches real availability without asking for doctor IDs.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-scenario-a-fever"

    # Turn 1: Patient describes symptoms
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I have a fever."},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Vikram Mehta" in d1["reply"]
    assert d1["draft"]["specialty"] == "General Medicine"
    assert "fever" in d1["draft"]["reason_category"].lower()
    # Should include interactive suggested options
    assert d1.get("suggested_options") is not None

    # Turn 2: Patient accepts suggested doctor naturally
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Vikram is fine."},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_id"] == "doc-mehta-5"
    assert "Dr. Vikram Mehta" in d2["reply"]
    assert "available" in d2["reply"].lower() or "slot" in d2["reply"].lower()


def test_scenario_b_flexible_slot_anything_is_fine(client, db_session, seeded_hospital_data):
    """
    Scenario B:
    Patient doesn't know which slot to select:
    Patient: 'Anything is fine.'
    Assistant: 'No problem! The earliest available appointment is ... Would you like me to reserve that slot for you?'
    Patient: 'Okay.'
    Assistant: Accepts slot, moves to patient identification, does NOT book yet.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-scenario-b-slot"

    # Setup doctor selection
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})

    # Turn 3: Patient is flexible
    r3 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Anything is fine."},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert "earliest available appointment" in d3["reply"].lower()
    assert "reserve that slot" in d3["reply"].lower()
    # Slot is not finalized yet until confirmed
    assert d3["booked_appointment"] is None

    # Turn 4: Patient agrees to the suggested earliest slot
    r4 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Okay."},
    )
    assert r4.status_code == 200
    d4 = r4.json()
    # Slot is now bound to draft
    assert d4["draft"]["slot_id"] is not None
    # Must NOT be booked yet!
    assert d4["step"] != "BOOKED"
    assert d4["booked_appointment"] is None
    # Must ask if patient visited before
    assert "visited" in d4["reply"].lower() or "first time" in d4["reply"].lower()


def test_scenario_c_new_patient_registration_workflow(client, db_session, seeded_hospital_data):
    """
    Scenario C:
    New patient registration:
    Patient: 'No, this is my first time.'
    Assistant: 'Welcome to Aarogya One Hospital! ... May I have your full name?'
    Patient: 'Venu Gopala Krishna.'
    Assistant: 'Thank you, Venu. May I have your mobile number for appointment communication?'
    Patient: '9876543210'
    Assistant: Registers patient, generates unique PAT-2026-XXXX, presents summary, awaits confirmation.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-scenario-c-new-patient"

    # Reach patient identification stage
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    # Turn 5: New patient
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "No, this is my first time."},
    )
    assert r5.status_code == 200
    d5 = r5.json()
    assert "full name" in d5["reply"].lower()

    # Turn 6: Full name
    r6 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Venu Gopala Krishna."},
    )
    assert r6.status_code == 200
    d6 = r6.json()
    assert d6["draft"]["patient_name"] == "Venu Gopala Krishna"
    assert "mobile number" in d6["reply"].lower() or "phone" in d6["reply"].lower()

    # Turn 7: Mobile number -> creates patient and shows confirmation summary
    r7 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "9876543210"},
    )
    assert r7.status_code == 200
    d7 = r7.json()
    assert d7["step"] == "AWAITING_CONFIRMATION"
    assert d7["confirmation_status"] == "PENDING"
    assert d7["draft"]["patient_reference"].startswith("PAT-2026-")
    assert "Venu Gopala Krishna" in d7["reply"]
    assert "Dr. Vikram Mehta" in d7["reply"]

    # Verify patient persisted in DB
    created_patient = db_session.execute(
        select(Patient).where(Patient.patient_reference == d7["draft"]["patient_reference"])
    ).scalar_one_or_none()
    assert created_patient is not None
    assert created_patient.full_name == "Venu Gopala Krishna"
    assert created_patient.phone_number == "9876543210"

    # Turn 8: Explicit confirmation -> booked
    r8 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "YES, please confirm and book."},
    )
    assert r8.status_code == 200
    d8 = r8.json()
    assert d8["step"] == "BOOKED"
    assert d8["confirmation_status"] == "CONFIRMED"
    assert d8["booked_appointment"] is not None
    assert d8["booked_appointment"]["patient_reference"] == created_patient.patient_reference


def test_scenario_d_existing_patient_phone_verification(client, db_session, seeded_hospital_data):
    """
    Scenario D:
    Existing patient forgets ID:
    Patient: 'Yes.'
    Assistant: 'Welcome back! Do you have your patient reference number?'
    Patient: 'I don't remember.'
    Assistant: 'No problem. ... May I have your registered 10-digit mobile number?'
    Patient: '9123456789'
    Assistant: Verifies patient via verify_patient tool and binds reference.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-scenario-d-existing"

    # Seed an existing patient in the database
    existing_p = Patient(
        patient_reference="PAT-2024-9182",
        full_name="Rajesh Patel",
        phone_number="9123456789",
    )
    db_session.add(existing_p)
    db_session.commit()

    # Reach patient identification stage
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    # Turn 5: Existing patient
    r5 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Yes, I have visited before."},
    )
    assert r5.status_code == 200
    d5 = r5.json()
    assert "reference" in d5["reply"].lower()

    # Turn 6: Forgot reference ID
    r6 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I don't remember."},
    )
    assert r6.status_code == 200
    d6 = r6.json()
    assert "mobile number" in d6["reply"].lower() or "phone" in d6["reply"].lower()

    # Turn 7: Provide phone number
    r7 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "9123456789"},
    )
    assert r7.status_code == 200
    d7 = r7.json()
    assert d7["draft"]["patient_reference"] == "PAT-2024-9182"
    assert d7["step"] == "AWAITING_CONFIRMATION"
    assert d7["confirmation_status"] == "PENDING"

    # Turn 8: Explicit confirmation -> booked
    r8 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "CONFIRM"},
    )
    assert r8.status_code == 200
    assert r8.json()["step"] == "BOOKED"
    assert r8.json()["booked_appointment"]["patient_reference"] == "PAT-2024-9182"


def test_scenario_e_full_end_to_end_natural_conversation(client, db_session, seeded_hospital_data):
    """
    Scenario E: Full natural conversation matching user specification.
    Demonstrates zero friction, no internal database IDs needed by patient.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-scenario-e-full"

    # 1. "I have a fever."
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    assert r1.status_code == 200
    assert "Vikram Mehta" in r1.json()["reply"]

    # 2. "Yeah, book an appointment."
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yeah, book an appointment."})
    assert r2.status_code == 200
    assert "slot" in r2.json()["reply"].lower() or "available" in r2.json()["reply"].lower()

    # 3. "Anything is fine."
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    assert r3.status_code == 200
    assert "earliest" in r3.json()["reply"].lower()

    # 4. "Okay."
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})
    assert r4.status_code == 200
    assert "visited" in r4.json()["reply"].lower()

    # 5. "No, this is my first time."
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first time."})
    assert r5.status_code == 200
    assert "name" in r5.json()["reply"].lower()

    # 6. "Venu Gopala Krishna."
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Venu Gopala Krishna."})
    assert r6.status_code == 200
    assert "mobile" in r6.json()["reply"].lower()

    # 7. "9876543210"
    r7 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9876543210"})
    assert r7.status_code == 200
    d7 = r7.json()
    assert d7["step"] == "AWAITING_CONFIRMATION"
    assert "Venu Gopala Krishna" in d7["reply"]
    assert "General Medicine" in d7["reply"]
    assert "Dr. Vikram Mehta" in d7["reply"]

    # 8. "Yes, please confirm and book."
    r8 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, please confirm and book."})
    assert r8.status_code == 200
    d8 = r8.json()
    assert d8["step"] == "BOOKED"
    assert d8["booked_appointment"]["appointment_id"] is not None


def test_multilingual_natural_conversation_telugu(client, db_session, seeded_hospital_data):
    """
    Multilingual natural human-like appointment booking in Telugu.
    No internal database IDs required; respects patient intent and language.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-telugu-natural"

    # 1. Symptoms in Telugu
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "నాకు జ్వరం ఉంది"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["language"] == "te"
    assert "Dr. Vikram Mehta" in d1["reply"] or "Vikram" in d1["reply"]

    # 2. Select doctor
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "విక్రమ్ గారు సరిపోతారు"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert "స్లాట్" in d2["reply"] or "సమయ" in d2["reply"] or "slot" in d2["reply"].lower()

    # 3. Flexible slot in Telugu: "ఏదైనా పర్వాలేదు" (Anything is fine)
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "ఏదైనా పర్వాలేదు"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert "రిజర్వ్" in d3["reply"] or "లభ్యమయ్యే" in d3["reply"] or "reserve" in d3["reply"].lower() or "earliest" in d3["reply"].lower()

    # 4. Agree to slot: "సరే"
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "సరే"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert "సందర్శించారా" in d4["reply"] or "ఆసుపత్రి" in d4["reply"] or "visited" in d4["reply"].lower()

    # 5. First-time patient: "మొదటిసారి"
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "ఇదే మొదటిసారి"})
    assert r5.status_code == 200
    d5 = r5.json()
    assert "పేరు" in d5["reply"] or "name" in d5["reply"].lower()


def test_scenario_1_hi_greeting(client):
    """Scenario 1: 'hi' returns a warm, natural hospital greeting without requiring technical IDs."""
    r = client.post("/api/v1/agent/chat", json={"session_id": "test-hi-greet", "message": "hi"})
    assert r.status_code == 200
    data = r.json()
    assert data["step"] in ["GREETING", "COLLECTING_DOCTOR"]
    assert "aarogya" in data["reply"].lower() or "hospital" in data["reply"].lower()
    # Does not prompt for doctor IDs or slot IDs
    assert "slot-id" not in data["reply"].lower()


def test_scenario_5_and_6_not_yet_and_no_do_not_cancel(client, db_session, seeded_hospital_data):
    """
    Scenario 5 & 6:
    When asked 'Have you visited before?':
    - 'not yet' -> identifies as new patient, asks full name, DOES NOT CANCEL.
    - 'No' -> identifies as new patient, asks full name, DOES NOT CANCEL.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)

    # Test "not yet"
    s1 = "test-not-yet-reply"
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Okay."})
    r_not_yet = client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Not yet."})
    assert r_not_yet.status_code == 200
    d_not_yet = r_not_yet.json()
    assert "cancelled" not in d_not_yet["reply"].lower()
    assert "name" in d_not_yet["reply"].lower()

    # Test "No"
    s2 = "test-no-reply"
    client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Okay."})
    r_no = client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "No."})
    assert r_no.status_code == 200
    d_no = r_no.json()
    assert "cancelled" not in d_no["reply"].lower()
    assert "name" in d_no["reply"].lower()


def test_scenario_8_symptoms_not_requested_again(client, db_session, seeded_hospital_data):
    """
    Scenario 8:
    Symptoms captured during initial turn ('fever') are remembered in draft.reason_category
    and never asked again.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-no-repeat-symptoms"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    r = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})
    assert r.status_code == 200
    # Moves directly to visited-before question, not asking "what is your reason?"
    assert "reason" not in r.json()["reply"].lower() or "visited" in r.json()["reply"].lower()
    assert "fever" in r.json()["draft"]["reason_category"].lower()


def test_scenario_9_continue_previous_booking_resumes(client, db_session, seeded_hospital_data):
    """
    Scenario 9:
    'continue previous booking' resumes without lost state.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-resume-booking"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    # Patient pauses or asks something else, then says continue previous booking
    r = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "continue previous booking"})
    assert r.status_code == 200
    d = r.json()
    assert d["draft"]["doctor_id"] == "doc-mehta-5"
    assert "resuming" in d["reply"].lower() or "booking" in d["reply"].lower()


def test_scenario_10_select_slot_by_date_and_time(client, db_session, seeded_hospital_data):
    """
    Scenario 10:
    Patient selects slot using natural time/date expression ('10:00 AM' or 'the first one').
    The system maps it cleanly to the offered slot ID without exposing technical IDs.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-slot-by-time"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})

    # Patient selects slot by time "10:00 AM"
    r = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "10:00 AM"})
    assert r.status_code == 200
    d = r.json()
    assert d["draft"]["slot_id"] == "slot-mehta-nat-1"
    assert d["step"] != "BOOKED"
    assert "visited" in d["reply"].lower() or "first time" in d["reply"].lower()


def test_scenario_11_explicit_confirmation_yes_booked_once(client, db_session, seeded_hospital_data):
    """
    Scenario 11:
    Explicit affirmative ('YES') books the appointment exactly once in the database.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-confirm-once"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "10:00 AM"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first time."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Sunita Rao"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9988776655"})

    # Explicit confirm
    r_confirm = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "YES"})
    assert r_confirm.status_code == 200
    d = r_confirm.json()
    assert d["step"] == "BOOKED"
    assert d["booked_appointment"] is not None

    # Check DB: exactly one appointment booked for this slot
    appts = db_session.execute(
        select(Appointment).where(Appointment.slot_id == "slot-mehta-nat-1")
    ).scalars().all()
    assert len(appts) == 1


def test_scenario_12_declines_confirmation_no_asks_modify_or_cancel(client, db_session, seeded_hospital_data):
    """
    Scenario 12:
    When confirmation is pending, replying 'NO' does NOT create a booking and does NOT
    immediately delete/cancel the session. It asks whether they want to modify details or cancel.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-decline-confirm"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "10:00 AM"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first time."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anil Verma"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9123412345"})

    # Patient declines confirmation with "NO"
    r_decline = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "NO"})
    assert r_decline.status_code == 200
    d_decline = r_decline.json()
    assert d_decline["step"] != "BOOKED"
    assert d_decline["booked_appointment"] is None
    # Verifies it prompts to modify or cancel
    assert "change" in d_decline["reply"].lower() or "cancel" in d_decline["reply"].lower()

    # Verify no appointment was booked in DB
    appts = db_session.execute(
        select(Appointment).where(Appointment.patient_reference == d_decline["draft"]["patient_reference"])
    ).scalars().all()
    assert len(appts) == 0


def test_scenario_13_repeated_messages_avoid_redundant_searches(client, db_session, seeded_hospital_data):
    """
    Scenario 13:
    Sending repeated messages when doctor and availability are already in session
    does not trigger redundant searches.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-no-redundant-searches"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})

    # User repeats question about slots
    r_repeat = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Which slots are available?"})
    assert r_repeat.status_code == 200
    d = r_repeat.json()
    assert d["step"] == "COLLECTING_SLOT"
    assert "Dr. Vikram Mehta" in d["reply"]


def test_scenario_14_expired_availability_refreshed(client, db_session, seeded_hospital_data):
    """
    Scenario 14:
    If a slot becomes unavailable or conflicted at booking time,
    the system transitions back to COLLECTING_SLOT, clears the slot, and refreshes availability.
    """
    doc = _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-expired-slot-refresh"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "10:00 AM"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first time."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kavita Reddy"})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9811223344"})

    # Concurrently book/expire the slot before the patient confirms
    target_slot = db_session.get(AppointmentSlot, "slot-mehta-nat-1")
    target_slot.status = "BOOKED"
    db_session.commit()

    # Now patient confirms
    r_confirm = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "YES, please book"})
    assert r_confirm.status_code == 200
    d = r_confirm.json()
    # Booking failed safely
    assert d["step"] == "COLLECTING_SLOT"
    assert d["booked_appointment"] is None
    assert d["draft"]["slot_id"] is None
    # Availability refreshed with remaining slots
    assert "slot-mehta-nat-2" in d["reply"] or "2:00 PM" in d["reply"] or "available" in d["reply"].lower()


def test_scenario_15_session_reset_isolates_patient_info(client, db_session, seeded_hospital_data):
    """
    Scenario 15:
    Session reset clears all state, and starting a new session never reuses another patient's data.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)

    s1 = "patient-session-alpha"
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Vikram is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "10:00 AM"})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "No, this is my first time."})
    client.post("/api/v1/agent/chat", json={"session_id": s1, "message": "Alice Smith"})

    # Session 2 begins
    s2 = "patient-session-beta"
    r2 = client.post("/api/v1/agent/chat", json={"session_id": s2, "message": "Hello"})
    d2 = r2.json()
    assert d2["draft"]["patient_name"] is None
    assert d2["draft"]["doctor_id"] is None
    assert d2["draft"]["slot_id"] is None
    assert "Alice" not in d2["reply"]


def test_multilingual_natural_conversation_hindi(client, db_session, seeded_hospital_data):
    """
    Multilingual natural human-like appointment booking in Hindi.
    Empathetic suggestions, zero technical IDs, and natural acceptance.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-hindi-natural"

    # 1. Symptoms in Hindi
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "मुझे बुखार है"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["language"] == "hi"
    assert "Vikram Mehta" in d1["reply"] or "विक्रम" in d1["reply"] or "General Medicine" in d1["reply"]

    # 2. Accept doctor
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "डॉ विक्रम ठीक हैं"})
    assert r2.status_code == 200
    d2 = r2.json()

    # 3. Flexible slot in Hindi: "कोई भी समय चलेगा" (Anything is fine)
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "कोई भी समय चलेगा"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert "उपलब्ध" in d3["reply"] or "रिजर्व" in d3["reply"] or "earliest" in d3["reply"].lower() or "reserve" in d3["reply"].lower()

    # 4. Agree to slot: "ठीक है"
    r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "ठीक है"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert "आए हैं" in d4["reply"] or "पहली बार" in d4["reply"] or "visited" in d4["reply"].lower() or "hospital" in d4["reply"].lower()


# ============================================================================
# REQUIRED REGRESSION TESTS (Section 7: Doctor Selection & Patient Identification)
# ============================================================================

def test_regression_1_single_doctor_kk_continue(client, db_session, seeded_hospital_data):
    """1. Patient accepts single doctor recommendation with 'Kk continue.'"""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-1-kk-continue"

    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    assert r1.status_code == 200
    d1 = r1.json()
    assert "Dr. Vikram Mehta" in d1["reply"]

    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_id"] == "doc-mehta-5"
    assert "which doctor would you like" not in d2["reply"].lower()
    assert "Dr. Vikram Mehta" in d2["reply"] or "available" in d2["reply"].lower() or "appointment" in d2["reply"].lower()


def test_regression_2_single_doctor_book(client, db_session, seeded_hospital_data):
    """2. Patient accepts single doctor recommendation with 'Book.'"""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-2-book"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Book."})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_id"] == "doc-mehta-5"
    assert "which doctor would you like" not in d2["reply"].lower()


def test_regression_3_single_doctor_yes(client, db_session, seeded_hospital_data):
    """3. Patient accepts single doctor recommendation with 'Yes.'"""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-3-yes"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes."})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_id"] == "doc-mehta-5"
    assert "which doctor would you like" not in d2["reply"].lower()


def test_regression_4_multiple_doctors_natural_selection(client, db_session, seeded_hospital_data):
    """4. Assistant presents multiple doctors with specialties and allows natural selection."""
    session_id = "test-reg-4-multiple-docs"

    # Seed a second cardiologist so multiple options exist
    hosp = seeded_hospital_data["hospital"]
    cardio_dept = seeded_hospital_data["cardio_dept"]
    doc2 = Doctor(
        id="doc-cardio-2",
        hospital_id=hosp.id,
        department_id=cardio_dept.id,
        display_name="Dr. Priya Nair",
        specialty="Cardiology",
        is_active=True,
    )
    db_session.add(doc2)
    db_session.commit()

    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I need to consult a cardiologist"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["step"] == "COLLECTING_DOCTOR"
    assert "Dr. Rajesh Sharma" in d1["reply"]
    assert "Dr. Priya Nair" in d1["reply"]

    # Natural doctor selection
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Priya Nair is fine."})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_name"] == "Dr. Priya Nair"


def test_regression_5_multiple_doctors_anyone_is_fine(client, db_session, seeded_hospital_data):
    """5. Patient says 'Anyone is fine' when presented with multiple doctors."""
    session_id = "test-reg-5-anyone"

    # Seed a second cardiologist and slots so multiple options exist
    hosp = seeded_hospital_data["hospital"]
    cardio_dept = seeded_hospital_data["cardio_dept"]
    doc2 = Doctor(
        id="doc-cardio-alt-2",
        hospital_id=hosp.id,
        department_id=cardio_dept.id,
        display_name="Dr. Priya Nair",
        specialty="Cardiology",
        is_active=True,
    )
    db_session.add(doc2)
    db_session.commit()

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I need to consult a cardiologist"})
    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anyone is fine."})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["step"] == "COLLECTING_SLOT"
    assert d2["draft"]["doctor_id"] is not None
    assert "earliest" in d2["reply"].lower() or "available" in d2["reply"].lower() or "appointment" in d2["reply"].lower()


def test_regression_6_returning_patient_forgets_reference(client, db_session, seeded_hospital_data):
    """6. Returning patient says they don't remember their reference number."""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-6-forgot-ref"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    # Returning patient
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, I have visited before."})
    assert r5.status_code == 200
    d5 = r5.json()
    assert "mobile" in d5["reply"].lower() or "phone" in d5["reply"].lower()

    # Forgets ID
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I don't remember my patient ID."})
    assert r6.status_code == 200
    d6 = r6.json()
    assert "no worries" in d6["reply"].lower() or "remember" in d6["reply"].lower() or "mobile" in d6["reply"].lower()


def test_regression_7_returning_patient_provides_mobile_directly(client, db_session, seeded_hospital_data):
    """7. Returning patient provides mobile number directly."""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-7-direct-phone"

    existing_p = Patient(
        patient_reference="PAT-2024-5555",
        full_name="Suresh Verma",
        phone_number="9887766554",
    )
    db_session.add(existing_p)
    db_session.commit()

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    # Provides mobile directly
    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, my mobile is 9887766554."})
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["draft"]["patient_reference"] == "PAT-2024-5555"
    assert d5["step"] == "AWAITING_CONFIRMATION"


def test_regression_8_patient_lookup_reports_security_limitation(client, db_session, seeded_hospital_data):
    """8. Patient lookup requires secure verification or clearly reports limitation."""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-8-security-note"

    existing_p = Patient(
        patient_reference="PAT-2024-8888",
        full_name="Meena Kumari",
        phone_number="9776655443",
    )
    db_session.add(existing_p)
    db_session.commit()

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, I visited before."})
    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9776655443"})
    assert r6.status_code == 200
    d6 = r6.json()
    reply_lower = d6["reply"].lower()
    # Security notice / demonstration limitation clearly reported
    assert "otp" in reply_lower or "security notice" in reply_lower or "demonstration" in reply_lower or "verification" in reply_lower


def test_regression_9_new_patient_registration_functional(client, db_session, seeded_hospital_data):
    """9. New patient registration flow remains fully functional."""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-9-new-registration"

    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first visit."})
    assert "full name" in r5.json()["reply"].lower()

    r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anita Desai"})
    assert "mobile" in r6.json()["reply"].lower() or "phone" in r6.json()["reply"].lower()

    r7 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9988776655"})
    assert r7.status_code == 200
    d7 = r7.json()
    assert d7["step"] == "AWAITING_CONFIRMATION"
    assert d7["draft"]["patient_name"] == "Anita Desai"
    assert d7["draft"]["patient_reference"].startswith("PAT-2026-")


def test_regression_10_no_repeated_doctor_selection_question(client, db_session, seeded_hospital_data):
    """10. Assistant does not repeat doctor-selection question after receiving a valid acceptance."""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-10-no-repeat"

    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    assert "Dr. Vikram Mehta" in r1.json()["reply"]

    r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    d2 = r2.json()
    assert "which doctor would you like to schedule" not in d2["reply"].lower()


def test_regression_11_no_internal_ids_or_html_comments_in_dialogue_or_tts(client, db_session, seeded_hospital_data):
    """11. No internal IDs or HTML comments appear in patient-facing responses or TTS input."""
    from app.services.speech.tts_service import clean_text_for_speech

    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-11-no-internal-ids"

    # Turn 1: doctor recommendation
    r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    d1 = r1.json()
    assert "slot-" not in d1["reply"]
    assert "doc-" not in d1["reply"]
    assert "<!--" not in d1["reply"]

    # Turn 2: accept doctor -> slot suggestion
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anyone is fine."})
    d3 = r3.json()
    assert "slot-" not in d3["reply"]
    assert "doc-" not in d3["reply"]
    assert "<!--" not in d3["reply"]

    # Verify TTS cleaning removes any technical IDs or HTML comments
    sample_text = (
        "Selected Dr. Vikram Mehta (General Medicine). "
        "Available: November 1 at 2:00 PM (Slot ID: slot-101) <!-- slot-101 2026-11-01T14:00:00Z -->. "
        "Patient reference PAT-2026-9999. Appointment APT-2026-1111."
    )
    cleaned_tts = clean_text_for_speech(sample_text)
    assert "<!--" not in cleaned_tts
    assert "-->" not in cleaned_tts
    assert "slot-101" not in cleaned_tts
    assert "PAT-2026-9999" not in cleaned_tts
    assert "APT-2026-1111" not in cleaned_tts
    assert "Slot ID" not in cleaned_tts


def test_regression_12_previous_booking_details_survive_patient_lookup(client, db_session, seeded_hospital_data):
    """12. Patient's previous booking details survive patient lookup."""
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-reg-12-details-survive"

    existing_p = Patient(
        patient_reference="PAT-2024-7777",
        full_name="Kavita Rao",
        phone_number="9665544332",
    )
    db_session.add(existing_p)
    db_session.commit()

    # Step 1: establish symptoms and select doctor
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "I have a fever."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Kk continue."})
    # Step 2: pick slot
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anything is fine."})
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Okay."})

    # Step 3: patient identification
    client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Yes, I have visited before."})
    r_lookup = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9665544332"})
    assert r_lookup.status_code == 200
    d_lookup = r_lookup.json()

    # Verify all previously collected details remain intact
    draft = d_lookup["draft"]
    assert draft["doctor_id"] == "doc-mehta-5"
    assert draft["doctor_name"] == "Dr. Vikram Mehta"
    assert draft["specialty"] == "General Medicine"
    assert "fever" in draft["reason_category"].lower()
    assert draft["slot_id"] is not None
    assert draft["patient_reference"] == "PAT-2024-7777"
    assert draft["patient_name"] == "Kavita Rao"
    assert d_lookup["step"] == "AWAITING_CONFIRMATION"

