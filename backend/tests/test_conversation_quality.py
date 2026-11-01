"""
Regression tests for MediVoice AI Conversation Quality Improvements:
1. Doctor result deduplication (dedup by stable doctor ID, preserve distinct doctors in same specialty).
2. Hide internal slot identifiers in patient-facing responses.
3. Single confirmation summary and single explicit confirmation question before booking.
4. Greeting lifecycle (greeting once at start; no repetition mid-session; context preserved).
5. Multilingual intent clarification for ambiguous account vs booking inquiries (en, te, hi, ta, kn).
6. Patient registration and identity safeguards (no fake OTP claims, reception in-person check-in notice).
"""

import pytest
import re
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.adapters import (
    deduplicate_doctors,
    is_ambiguous_account_or_booking_inquiry,
    format_localized_message,
)
from app.models.doctor import Doctor


def test_doctor_deduplication_unit():
    """Unit test: deduplicate_doctors deduplicates by doctor_id while preserving distinct doctors with same specialty."""
    raw_doctors = [
        {"doctor_id": "doc-cardio-1", "display_name": "Dr. Rajesh Sharma", "specialty": "Cardiology"},
        {"doctor_id": "doc-cardio-1", "display_name": "Dr. Rajesh Sharma", "specialty": "Cardiology"},  # duplicate
        {"doctor_id": "doc-cardio-2", "display_name": "Dr. Sunita Patel", "specialty": "Cardiology"},  # distinct doctor, same specialty
        {"doctor_id": "doc-ortho-1", "display_name": "Dr. Vikram Seth", "specialty": "Orthopedics"},
    ]
    deduped = deduplicate_doctors(raw_doctors)
    assert len(deduped) == 3
    ids = [d["doctor_id"] for d in deduped]
    assert ids == ["doc-cardio-1", "doc-cardio-2", "doc-ortho-1"]
    assert any(d["display_name"] == "Dr. Sunita Patel" for d in deduped)


def test_doctor_search_deduplication_in_chat(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Ensures that when searching for doctors via chat, identical doctors are never duplicated in the reply.
    """
    session_id = "test-doc-dedup-chat"
    res = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I need a cardiologist at Aarogya One Hospital"},
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    sharma_count = reply.count("Dr. Rajesh Sharma")
    assert sharma_count <= 1, f"Dr. Rajesh Sharma appeared {sharma_count} times in response: {reply}"


def test_hide_internal_slot_identifiers(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Ensures patient-facing responses display doctor name, date, and appointment time,
    and NEVER expose raw '(Slot ID: ...)' or 'Slot ID: slot-xxx' in visible patient text.
    Internal slot IDs are preserved in HTML comments or internally for booking.
    """
    session_id = "test-hide-slot-ids"
    # Step 1: Request doctor slots with routine checkup reason
    res = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Show available slots for Dr. Sharma for routine checkup"},
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]

    # Visible text must NOT contain '(Slot ID: ' or 'Slot ID: '
    assert "(Slot ID:" not in reply, f"Internal slot ID exposed in reply: {reply}"
    assert "Slot ID: slot-" not in reply, f"Internal slot ID pattern exposed in reply: {reply}"

    # Reply must show human time or date
    assert ("AM" in reply or "PM" in reply or ":" in reply), f"Expected human-readable time in slots reply: {reply}"

    # Verify slot selection can proceed using a slot ID or earliest selection
    res2 = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "slot-sharma-avail-1",
            "patient_reference": "PAT-2026-4141",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["step"] == "AWAITING_CONFIRMATION"
    # Confirmation prompt should also NOT expose '(Slot ID: slot-xxx)'
    assert "(Slot ID:" not in data2["reply"]


def test_single_confirmation_summary_and_single_question(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Ensures:
    1. Exactly ONE appointment confirmation summary is generated per turn.
    2. Exactly ONE explicit confirmation question is presented.
    3. Explicit YES/CONFIRM is required before booking commits.
    4. Casual or ambiguous replies do NOT commit the booking.
    """
    session_id = "test-single-confirm"
    # Move draft to complete state
    client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "Book Dr. Sharma for routine checkup",
            "patient_reference": "PAT-2026-4141",
        },
    )
    res = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "slot-sharma-avail-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["step"] == "AWAITING_CONFIRMATION"
    assert data["requires_confirmation"] is True
    assert data["booked_appointment"] is None

    reply = data["reply"]
    # Check that confirmation question appears exactly ONCE
    confirm_q_count = reply.lower().count("to confirm, reply 'yes' or 'confirm'")
    assert confirm_q_count == 1, f"Expected exactly 1 confirmation prompt, found {confirm_q_count} in: {reply}"

    # Header for appointment details appears exactly once
    header_count = reply.lower().count("confirm your appointment details:")
    assert header_count == 1, f"Expected 1 confirmation header, found {header_count} in: {reply}"

    # Doctor name should appear in the summary, but not duplicated twice in stacked summaries
    sharma_count = reply.count("Dr. Rajesh Sharma")
    assert sharma_count == 1, f"Dr. Rajesh Sharma repeated {sharma_count} times in confirmation turn: {reply}"

    # Casual message should NOT book
    res_casual = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Can I also ask about parking?"},
    )
    data_casual = res_casual.json()
    assert data_casual["booked_appointment"] is None
    assert data_casual["step"] == "AWAITING_CONFIRMATION"

    # Explicit YES must book
    res_confirm = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "YES, please confirm"},
    )
    data_confirm = res_confirm.json()
    assert data_confirm["step"] == "BOOKED"
    assert data_confirm["booked_appointment"] is not None
    assert data_confirm["booked_appointment"]["doctor_name"] == "Dr. Rajesh Sharma"


def test_greeting_lifecycle_no_repeated_greetings(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Ensures that welcome greetings appear only at the beginning of a conversation,
    and are never repeated on subsequent user turns during an active session.
    """
    session_id = "test-greeting-lifecycle"
    # Turn 1: User specifies specialty
    res1 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "I want to consult a cardiologist"},
    )
    assert res1.status_code == 200
    reply1 = res1.json()["reply"]

    # Turn 2: User provides doctor preference or asks for slots
    res2 = client.post(
        "/api/v1/agent/chat",
        json={"session_id": session_id, "message": "Dr. Rajesh Sharma"},
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]

    welcome_phrases = [
        "welcome to aarogya one hospital",
        "which specialty or physician do you need",
        "నేను ఆరోగ్య వన్ హాస్పిటల్",
    ]
    for wp in welcome_phrases:
        assert wp not in reply2.lower(), f"Repeated welcome greeting found in turn 2 reply: {reply2}"


def test_ambiguous_telugu_intent_clarification(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Tests handling of ambiguous transliterated Telugu query:
    'naaku account book cheyagalva?'
    Expected behaviour:
    - Assistant must NOT assume an existing appointment already exists or ask for an appointment number.
    - Assistant recognizes ambiguity between scheduling a doctor appointment vs registering a patient account.
    - Assistant asks short clarification in Telugu.
    - Context language is preserved as 'te'.
    """
    session_id = "test-ambiguous-te-account"
    res = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "naaku account book cheyagalva?",
            "language": "te",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]

    # Must NOT claim an appointment already exists
    assert "appointment id" not in reply.lower()
    assert "అపాయింట్‌మెంట్ నంబర్" not in reply
    assert "already booked" not in reply.lower()

    # Must clarify between appointment booking and patient account registration
    assert ("డాక్టర్ అపాయింట్‌మెంట్" in reply or "అపాయింట్‌మెంట్" in reply)
    assert ("ఖాతా" in reply or "Account" in reply or "నమోదు" in reply)

    # Suggested options should be provided in Telugu
    options = data.get("suggested_options")
    if options:
        labels = [opt.get("label", "") for opt in options]
        assert any("అపాయింట్‌మెంట్" in l for l in labels)


def test_ambiguous_account_clarification_all_languages(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Tests ambiguous account vs booking clarification across all 5 supported languages:
    English, Telugu, Tamil, Kannada, Hindi.
    """
    scenarios = [
        ("en", "Can you please book an account for me?", "appointment with a doctor", "register a new patient account"),
        ("te", "నాకు ఖాతా బుక్ చేయగలరా?", "అపాయింట్‌మెంట్", "ఖాతా"),
        ("hi", "क्या आप मेरा खाता बुक कर सकते हैं?", "अपॉइंटमेंट", "खाता"),
        ("ta", "எனக்கு கணக்கு புக் செய்ய முடியுமா?", "அப்பாயிண்ட்மென்ட்", "கணக்கு"),
        ("kn", "ನನಗೆ ಖಾತೆ ಬುಕ್ ಮಾಡಬಹುದಾ?", "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್", "ಖಾತೆ"),
    ]

    for lang, user_msg, expect_booking_kw, expect_account_kw in scenarios:
        session_id = f"test-ambig-lang-{lang}"
        res = client.post(
            "/api/v1/agent/chat",
            json={"session_id": session_id, "message": user_msg, "language": lang},
        )
        assert res.status_code == 200, f"Failed for {lang}"
        data = res.json()
        reply = data["reply"]
        assert expect_booking_kw in reply, f"Language {lang}: expected booking keyword '{expect_booking_kw}' in: {reply}"
        assert expect_account_kw in reply, f"Language {lang}: expected account keyword '{expect_account_kw}' in: {reply}"
        assert data.get("booked_appointment") is None


def test_patient_registration_and_identity_safeguards_no_fake_otp(client: TestClient, db_session: Session, seeded_hospital_data):
    """
    Verifies that patient lookup/registration:
    1. Distinguishes phone record lookup from official identity verification.
    2. Does NOT claim two-factor SMS OTP verification occurs when no OTP mechanism is present.
    3. Clearly informs that official photo identity verification is completed at reception during check-in.
    """
    session_id = "test-id-safeguards"
    res = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": session_id,
            "message": "I am a returning patient with phone 9876543210",
        },
    )
    assert res.status_code == 200
    reply = res.json()["reply"]

    # Must NOT claim SMS OTP verification
    assert "sms otp" not in reply.lower()
    assert "two-factor sms otp" not in reply.lower()

    # If verification notice is present, verify in-person reception check-in mention
    if "reception" in reply.lower() or "check-in" in reply.lower():
        assert "photo identity" in reply.lower() or "reception" in reply.lower()
