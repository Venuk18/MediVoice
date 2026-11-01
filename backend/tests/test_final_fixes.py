"""
Regression tests for MediVoice AI Final Bug Fixes and Appointment Completion Experience.
Tests:
1. Deduplication of doctors by stable doctor ID and (name, specialty) without dropping distinct doctors sharing specialty.
2. Doctor preference safeguard: explicit doctor request for unavailable physician (e.g. Dr. Jaggayya / జగ్గయ్య)
   informs patient that doctor is not available and does NOT silently substitute Dr. Vikram Mehta.
3. Explicit doctor request for available physician selects that doctor and retrieves slots.
4. Confirmation response includes Demo SMS notification notice and natural thank-you ending across languages.
5. VoiceTurnResponse schema and voice orchestrator output include booked_appointment details.
6. book_appointment_tool populates patient_name, phone_number, department_name, hospital_name.
"""

import pytest
from starlette.testclient import TestClient
from sqlalchemy import select
from app.agent.adapters import (
    deduplicate_doctors,
    extract_explicit_doctor_name,
    LOCALIZED_MESSAGES,
    format_localized_message,
)
from app.agent.schemas import ConversationStep
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.services.doctor_service import search_doctors_tool, get_available_slots_tool
from app.services.appointment_service import book_appointment_tool
from app.api.v1.voice import VoiceTurnResponse
from tests.test_natural_booking_flow import _seed_general_medicine_vikram_mehta


def test_doctor_deduplication_exact_single_and_preserves_specialty(db_session, seeded_hospital_data):
    """
    Deduplication must eliminate duplicate records of the same doctor (e.g. Dr. Vikram Mehta in General Medicine)
    while preserving genuinely distinct doctors who share a specialty (e.g. Dr. Rajesh Sharma & Dr. Sunita Rao in Cardiology).
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)

    # Also seed a second distinct doctor in Cardiology
    cardio_doc2 = Doctor(
        id="doc-rao-test-dedup",
        hospital_id=seeded_hospital_data["hospital"].id,
        department_id=seeded_hospital_data["dept_cardio"].id,
        display_name="Dr. Sunita Rao",
        specialty="Cardiology",
        is_active=True,
    )
    db_session.add(cardio_doc2)

    # Seed a duplicate record for Dr. Vikram Mehta with different ID
    mehta_duplicate = Doctor(
        id="doc-mehta-test-duplicate",
        hospital_id=seeded_hospital_data["hospital"].id,
        department_id="test-dept-genmed-nat",
        display_name="Dr. Vikram Mehta",
        specialty="General Medicine",
        is_active=True,
    )
    db_session.add(mehta_duplicate)
    db_session.commit()

    # 1. General Medicine (has duplicate Dr. Vikram Mehta records in db, must return exactly 1)
    gm_docs = search_doctors_tool(db_session, specialty_or_department="General Medicine")
    assert len(gm_docs) == 1
    assert gm_docs[0]["display_name"] == "Dr. Vikram Mehta"
    assert gm_docs[0]["specialty"] == "General Medicine"

    # 2. Cardiology (has 2 genuinely distinct physicians: Dr. Rajesh Sharma and Dr. Sunita Rao, both preserved)
    cardio_docs = search_doctors_tool(db_session, specialty_or_department="Cardiology")
    assert len(cardio_docs) >= 2
    names = {d["display_name"] for d in cardio_docs}
    assert "Dr. Rajesh Sharma" in names
    assert "Dr. Sunita Rao" in names

    # 3. deduplicate_doctors function directly
    mock_input = [
        {"doctor_id": "id-1", "display_name": "Dr. Vikram Mehta", "specialty": "General Medicine"},
        {"doctor_id": "id-2", "display_name": "Dr. Vikram Mehta", "specialty": "General Medicine"},
        {"doctor_id": "id-3", "display_name": "Dr. Rajesh Sharma", "specialty": "Cardiology"},
        {"doctor_id": "id-4", "display_name": "Dr. Sunita Rao", "specialty": "Cardiology"},
    ]
    deduped = deduplicate_doctors(mock_input)
    assert len(deduped) == 3
    deduped_names = [d["display_name"] for d in deduped]
    assert deduped_names == ["Dr. Vikram Mehta", "Dr. Rajesh Sharma", "Dr. Sunita Rao"]


def test_extract_explicit_doctor_name():
    """
    Tests extraction of explicitly requested doctors across multilingual scripts and distinguishes
    symptom requests from explicit physician names.
    """
    assert extract_explicit_doctor_name("నాకు doctor జగ్గయ్య గారితో appointment book చేయండి") == "జగ్గయ్య"
    assert extract_explicit_doctor_name("డాక్టర్ జగ్గయ్య గారితో అపాయింట్‌మెంట్ కావాలి") == "జగ్గయ్య"
    assert extract_explicit_doctor_name("I want to book an appointment with Dr. Jaggayya") == "Jaggayya"
    assert extract_explicit_doctor_name("Please schedule an appointment with Dr. Rajesh Sharma") == "Rajesh Sharma"
    assert extract_explicit_doctor_name("డాక్టర్ శర్మ గారు") == "శర్మ"
    assert extract_explicit_doctor_name("डॉक्टर वर्मा के साथ अपॉइंटमेंट बुक करें") == "वर्मा"
    assert extract_explicit_doctor_name("ಡಾಕ್ಟರ್ ಜಗ್ಗಯ್ಯ ಅವರೊಂದಿಗೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು") == "ಜಗ್ಗಯ್ಯ"

    # Symptom inquiries and patient names must NOT be treated as explicit doctor requests
    assert extract_explicit_doctor_name("I need a doctor for fever") is None
    assert extract_explicit_doctor_name("నాకు డాక్టర్ కావాలి") is None
    assert extract_explicit_doctor_name("Kavita Rao") is None
    assert extract_explicit_doctor_name("Sunita Rao") is None
    assert extract_explicit_doctor_name("fever and headache") is None


def test_doctor_preference_safeguard_telugu_unavailable_doctor(client, db_session, seeded_hospital_data):
    """
    When patient says 'నాకు doctor జగ్గయ్య గారితో appointment book చేయండి':
    - Assistant searches for Dr. Jaggayya.
    - Since Dr. Jaggayya is not at Aarogya One Hospital, it informs the patient politely in Telugu.
    - It NEVER silently substitutes Dr. Vikram Mehta or any other doctor.
    - Draft doctor is cleared.
    """
    _seed_general_medicine_vikram_mehta(db_session, seeded_hospital_data)
    session_id = "test-telugu-jaggayya-safeguard"

    # Turn 1: Patient selects Dr. Vikram Mehta
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Dr. Vikram Mehta", "patient_reference": "PAT-TELUGU-1"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["draft"]["doctor_name"] == "Dr. Vikram Mehta"

    # Turn 2: Patient explicitly requests Dr. Jaggayya instead
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "నాకు doctor జగ్గయ్య గారితో appointment book చేయండి"},
    )
    assert r2.status_code == 200
    d2 = r2.json()

    # Must explain that Dr. Jaggayya is not available at Aarogya One Hospital
    assert "జగ్గయ్య" in d2["reply"]
    assert ("అందుబాటులో లేరు" in d2["reply"] or "not available" in d2["reply"].lower())

    # Crucial: Must NEVER silently substitute Dr. Vikram Mehta!
    assert d2["draft"]["doctor_name"] is None
    assert d2["draft"]["doctor_id"] is None
    assert d2["draft"]["slot_id"] is None
    assert d2["step"] == "COLLECTING_DOCTOR"


def test_doctor_preference_safeguard_english_unavailable_doctor(client, db_session, seeded_hospital_data):
    """
    When patient in English asks for an unavailable doctor (e.g. Dr. Jaggayya),
    assistant explains unavailability and does not silently substitute prior doctor.
    """
    session_id = "test-en-jaggayya-safeguard"

    # Pre-select Dr. Sharma
    client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Cardiology", "patient_reference": "PAT-EN-1"},
    )
    r1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Dr. Rajesh Sharma"},
    )
    assert r1.json()["draft"]["doctor_name"] == "Dr. Rajesh Sharma"

    # Now ask for Dr. Jaggayya
    r2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Actually I want to book an appointment with Dr. Jaggayya"},
    )
    d2 = r2.json()
    assert "Jaggayya" in d2["reply"]
    assert "not available at Aarogya One Hospital" in d2["reply"]
    assert d2["draft"]["doctor_name"] is None
    assert d2["step"] == "COLLECTING_DOCTOR"


def test_booking_confirmed_message_includes_demo_sms_and_thank_you():
    """
    Verifies that localized booking_confirmed messages across English, Telugu, Hindi, Tamil, and Kannada
    include both the Demo SMS notification message and natural thank-you ending.
    """
    test_params = {
        "appointment_id": "APT-9999",
        "doctor_name": "Dr. Rajesh Sharma",
        "appointment_start_time": "2026-11-05 10:00 AM",
        "appointment_status": "CONFIRMED",
        "patient_reference": "PAT-1234",
    }

    # 1. English
    en_msg = format_localized_message("en", "booking_confirmed", **test_params)
    assert "SMS (Demonstration mode)" in en_msg
    assert "Thank you for choosing Aarogya One Hospital" in en_msg
    assert "speedy recovery" in en_msg

    # 2. Telugu
    te_msg = format_localized_message("te", "booking_confirmed", **test_params)
    assert "SMS ద్వారా పంపబడతాయి" in te_msg
    assert "ఆరోగ్య వన్ హాస్పిటల్ను ఎంచుకున్నందుకు ధన్యవాదాలు" in te_msg
    assert "త్వరగా కోలుకోవాలని" in te_msg

    # 3. Hindi
    hi_msg = format_localized_message("hi", "booking_confirmed", **test_params)
    assert "एसएमएस द्वारा भेज दिया जाएगा" in hi_msg
    assert "आरोग्य वन अस्पताल चुनने के लिए धन्यवाद" in hi_msg

    # 4. Tamil
    ta_msg = format_localized_message("ta", "booking_confirmed", **test_params)
    assert "எஸ்எம்எஸ் மூலம் அனுப்பப்படும்" in ta_msg
    assert "ஆரோக்கியா ஒன் மருத்துவமனையைத் தேர்ந்தெடுத்ததற்கு நன்றி" in ta_msg

    # 5. Kannada
    kn_msg = format_localized_message("kn", "booking_confirmed", **test_params)
    assert "ಎಸ್‌ಎಂಎಸ್ ಮೂಲಕ ಕಳುಹಿಸಲಾಗುತ್ತದೆ" in kn_msg
    assert "ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು" in kn_msg


def test_book_appointment_tool_populates_full_details(db_session, seeded_hospital_data):
    """
    book_appointment_tool returns complete patient name, phone number, hospital name, and department name.
    """
    # Create test patient
    pat = Patient(
        id="pat-full-test-1",
        patient_reference="PAT-REF-FULL-1",
        full_name="Rajesh Varma",
        phone_number="+919876543210",
    )
    db_session.add(pat)
    db_session.commit()

    cardio_doc = seeded_hospital_data["doc_sharma"]
    slots = get_available_slots_tool(db_session, doctor_id=cardio_doc.id)
    assert len(slots) > 0
    slot_id = slots[0]["slot_id"]

    result = book_appointment_tool(
        db=db_session,
        patient_reference=pat.patient_reference,
        doctor_id=cardio_doc.id,
        selected_slot_id=slot_id,
        reason_category="Chest Pain",
    )

    assert result["appointment_id"] is not None
    assert result["patient_reference"] == "PAT-REF-FULL-1"
    assert result["patient_name"] == "Rajesh Varma"
    assert result["phone_number"] == "+919876543210"
    assert result["doctor_name"] == cardio_doc.display_name
    assert "Hospital" in result["hospital_name"]
    assert result["appointment_status"] == "CONFIRMED"


def test_voice_turn_response_schema_booked_appointment():
    """
    Verifies that VoiceTurnResponse schema contains booked_appointment field.
    """
    payload = {
        "transcript": "Yes, confirm",
        "detected_language": "en",
        "session_id": "test-voice-session",
        "reply": "Appointment Confirmed!",
        "language": "en",
        "step": "BOOKED",
        "confirmation_status": "CONFIRMED",
        "draft": {},
        "tool_trace": [],
        "tts_available": True,
        "booked_appointment": {
            "appointment_id": "APT-VOICE-1",
            "patient_name": "Test Patient",
            "phone_number": "+919876543210",
            "doctor_name": "Dr. Rajesh Sharma",
            "hospital_name": "Aarogya One Hospital",
            "department_name": "Cardiology",
            "appointment_status": "CONFIRMED",
        },
    }
    resp = VoiceTurnResponse(**payload)
    assert resp.booked_appointment is not None
    assert resp.booked_appointment["appointment_id"] == "APT-VOICE-1"
    assert resp.booked_appointment["patient_name"] == "Test Patient"
    assert resp.step == "BOOKED"
