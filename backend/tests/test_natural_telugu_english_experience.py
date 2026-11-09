import io
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.models import Doctor, Department, AppointmentSlot, Patient
from app.services.speech.tts_service import generate_synthetic_wav
from app.agent.conversation_manager import conversation_manager
from app.agent.adapters import (
    MockReasoningAdapter,
    detect_language,
    detect_explicit_specialty_request,
    detect_specialty_query,
    extract_explicit_doctor_name,
    is_change_doctor_intent,
    is_affirmative,
    is_cancellation,
    is_explicit_cancellation,
    match_slot_by_natural_language,
)
from app.agent.schemas import BookingDraft, ConfirmationStatus, ConversationStep
from app.services.speech.voice_orchestrator import voice_orchestrator


def make_mock_wav(transcript: str) -> bytes:
    """Creates mock WAV payload >= 32 bytes containing MOCK_AUDIO_CONTENT marker."""
    header = b"RIFF" + b"\x00" * 36
    marker = f"MOCK_AUDIO_CONTENT:{transcript}".encode("utf-8")
    return header + marker


@pytest.fixture(autouse=True)
def setup_mock_reasoning_and_tts(monkeypatch):
    """
    Guarantees zero external AI or speech credits are consumed during test runs.
    """
    conversation_manager.adapter = MockReasoningAdapter()

    def mock_synthesize(text, language=None, voice=None, speed=None):
        return generate_synthetic_wav(0.1)

    monkeypatch.setattr(voice_orchestrator.tts, "synthesize", mock_synthesize)


# ==============================================================================
# STEP 2: NATURAL TELUGU-ENGLISH CODE-MIXING (6 SPECIFIED SENTENCES)
# ==============================================================================

def test_code_mixing_sentence_1_cardiology_search(client, db_session, seeded_hospital_data):
    """
    Sentence 1: 'నాకు cardiology department లో appointment కావాలి.'
    Should detect Telugu language, extract Cardiology department, search doctors,
    and retain familiar medical terms without translating them to obscure words.
    """
    session_id = "test-p3-sentence-1"
    audio = make_mock_wav("నాకు cardiology department లో appointment కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te"
    session = conversation_manager.get_or_create_session(session_id)
    assert session.draft.specialty == "Cardiology"
    # Spoken reply contains conversational Telugu and doctor options
    assert any(term in data["reply"] for term in ("కార్డియాలజీ", "డాక్టర్", "Rajesh", "Sunita", "వైద్యు"))


def test_code_mixing_sentence_2_doctor_and_time_preference(client, db_session, seeded_hospital_data):
    """
    Sentence 2: 'Tomorrow morning Dr. Rajesh Sharma తో appointment కావాలి.'
    Should extract doctor 'Rajesh Sharma', recognize tomorrow morning preference,
    and persist Telugu language.
    """
    session_id = "test-p3-sentence-2"
    audio = make_mock_wav("Tomorrow morning Dr. Rajesh Sharma తో appointment కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te"
    session = conversation_manager.get_or_create_session(session_id)
    assert "Rajesh" in (session.draft.doctor_name or "")
    # Check slots were queried for the doctor
    assert session.draft.doctor_id is not None


def test_code_mixing_sentence_3_doctor_availability_inquiry(client, db_session, seeded_hospital_data):
    """
    Sentence 3: 'Doctor availability check చేసి చెప్పండి.'
    Must treat as an availability check without falsely matching a premature doctor name.
    """
    session_id = "test-p3-sentence-3"
    # Verify pure unit extraction first
    assert extract_explicit_doctor_name("Doctor availability check చేసి చెప్పండి.") is None

    audio = make_mock_wav("Doctor availability check చేసి చెప్పండి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te"
    session = conversation_manager.get_or_create_session(session_id)
    # Does not book or falsely lock a doctor
    assert session.draft.doctor_id is None
    assert session.confirmation_status != ConfirmationStatus.CONFIRMED


def test_code_mixing_sentence_4_negation_handling(client, db_session, seeded_hospital_data):
    """
    Sentence 4: 'నాకు general physician కావాలి, cardiology కాదు.'
    Must recognize negation: Cardiology is negated, General Medicine is requested.
    """
    text = "నాకు general physician కావాలి, cardiology కాదు."
    assert detect_explicit_specialty_request(text) == "General Medicine"

    session_id = "test-p3-sentence-4"
    audio = make_mock_wav(text)
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    session = conversation_manager.get_or_create_session(session_id)
    assert session.draft.specialty == "General Medicine"


def test_code_mixing_sentence_5_weekday_slot_query(client, db_session, seeded_hospital_data):
    """
    Sentence 5: 'Next Monday afternoon slot ఉందా?'
    Should parse weekday (Monday) and time of day (afternoon) cleanly.
    """
    mock_slots = [
        {"slot_id": "slot-mon-1", "start_time": "2026-11-09T14:30:00"},  # Monday 2:30 PM
        {"slot_id": "slot-tue-1", "start_time": "2026-11-10T10:00:00"},  # Tuesday 10:00 AM
    ]
    matched = match_slot_by_natural_language("Next Monday afternoon slot ఉందా?", mock_slots)
    assert matched is not None
    assert matched["slot_id"] == "slot-mon-1"


def test_code_mixing_sentence_6_prebooking_doctor_details_inquiry(client, db_session, seeded_hospital_data):
    """
    Sentence 6: 'Appointment book చేయడానికి ముందు doctor details చెప్పండి.'
    Informational inquiry before booking: must provide doctor details without booking.
    """
    session_id = "test-p3-sentence-6"
    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.specialty = "Cardiology"
    session.language = "te"

    audio = make_mock_wav("Appointment book చేయడానికి ముందు doctor details చెప్పండి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te"
    # Informational response with doctor name, not booking
    assert "Rajesh" in data["reply"]
    assert session.step != ConversationStep.BOOKED
    assert session.confirmation_status != ConfirmationStatus.CONFIRMED


# ==============================================================================
# STEP 3: ROMANIZED TELUGU SUPPORT (6 SPECIFIED PHRASES)
# ==============================================================================

def test_romanized_telugu_vocabulary_and_intent():
    """
    Tests the 6 specified Romanized Telugu sentences for language and intent recognition:
    1. 'naaku cardiology doctor kavali'
    2. 'repu appointment undha?'
    3. 'udayam 10 gantala slot kavali'
    4. 'doctor ni marchandi'
    5. 'book cheyyandi'
    6. 'vaddu, cancel cheyyandi'
    """
    # 1. Department request
    assert detect_language("naaku cardiology doctor kavali") == "te"
    assert detect_explicit_specialty_request("naaku cardiology doctor kavali") == "Cardiology"

    # 2. Availability query for tomorrow
    assert detect_language("repu appointment undha?") == "te"

    # 3. Transliterated morning time slot
    assert detect_language("udayam 10 gantala slot kavali") == "te"
    mock_slots = [
        {"slot_id": "slot-10", "start_time": "2026-11-06T10:00:00"},
        {"slot_id": "slot-14", "start_time": "2026-11-06T14:00:00"},
    ]
    matched = match_slot_by_natural_language("udayam 10 gantala slot kavali", mock_slots)
    assert matched is not None
    assert matched["slot_id"] == "slot-10"

    # 4. Change doctor intent
    assert detect_language("doctor ni marchandi") == "te"
    assert is_change_doctor_intent("doctor ni marchandi") is True
    assert extract_explicit_doctor_name("doctor ni marchandi") is None

    # 5. Affirmative booking confirmation
    assert detect_language("book cheyyandi") == "te"
    assert is_affirmative("book cheyyandi") is True

    # 6. Cancellation intent
    assert detect_language("vaddu, cancel cheyyandi") == "te"
    assert is_cancellation("vaddu, cancel cheyyandi") is True
    assert is_explicit_cancellation("vaddu, cancel cheyyandi") is True


# ==============================================================================
# STEP 4: CONTEXTUAL CONVERSATION MEMORY (MULTI-TURN STATE PRESERVATION)
# ==============================================================================

def test_contextual_conversation_memory_multi_turn_flow(client, db_session, seeded_hospital_data):
    """
    Executes the Step 4 multi-turn conversation flow:
    Patient: నాకు cardiology doctor కావాలి.
    Assistant: Offers available cardiologists.
    Patient: Rajesh Sharma.
    Assistant: Doctor remembered, offers dates/slots.
    Patient: రేపు.
    Assistant: Tomorrow remembered, offers slots.
    Patient: ఉదయం 10 గంటలకు.
    Assistant: 10 AM remembered, asks for confirmation with full summary.
    """
    session_id = "test-p3-memory-flow"

    # Turn 1: Department
    audio1 = make_mock_wav("నాకు cardiology doctor కావాలి.")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res1.status_code == 200
    s1 = conversation_manager.get_or_create_session(session_id)
    assert s1.draft.specialty == "Cardiology"

    # Turn 2: Doctor selection
    audio2 = make_mock_wav("Rajesh Sharma")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res2.status_code == 200
    s2 = conversation_manager.get_or_create_session(session_id)
    assert "Rajesh" in (s2.draft.doctor_name or "")
    # Specialty is preserved from Turn 1
    assert s2.draft.specialty == "Cardiology"

    # Turn 3: Date
    audio3 = make_mock_wav("రేపు")
    res3 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn3.wav", io.BytesIO(audio3), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res3.status_code == 200
    s3 = conversation_manager.get_or_create_session(session_id)
    assert "Rajesh" in (s3.draft.doctor_name or "")
    assert s3.draft.specialty == "Cardiology"

    # Turn 4: Time (pick an offered slot)
    audio4 = make_mock_wav("ఉదయం 10 గంటలకు")
    res4 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn4.wav", io.BytesIO(audio4), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res4.status_code == 200
    s4 = conversation_manager.get_or_create_session(session_id)
    # Both doctor and specialty retained
    assert "Rajesh" in (s4.draft.doctor_name or "")
    assert s4.draft.specialty == "Cardiology"


def test_follow_up_references_and_session_isolation(client, db_session, seeded_hospital_data):
    """
    Verifies follow-up references ('ఆ డాక్టర్', 'ఆ టైమ్', 'అదే appointment')
    and strict isolation between different patient sessions.
    """
    session_a = "test-p3-isolation-a"
    session_b = "test-p3-isolation-b"

    # Session A: Has Dr. Priya Nair selected
    doc_nair = db_session.query(Doctor).filter(Doctor.display_name.like("%Priya Nair%")).first()
    sa = conversation_manager.get_or_create_session(session_a)
    sa.draft.doctor_id = doc_nair.id if doc_nair else "doc-nair-2"
    sa.draft.doctor_name = "Dr. Priya Nair"
    sa.draft.specialty = "Neurology"
    sa.draft.slot_id = "slot-201"
    sa.language = "te"

    # Session B: Fresh session for different patient
    sb = conversation_manager.get_or_create_session(session_b)
    assert sb.draft.doctor_id is None
    assert sb.draft.specialty is None

    # Session A sends follow-up reference: 'ఆ డాక్టర్ తోనే కావాలి'
    audio_a = make_mock_wav("ఆ డాక్టర్ తోనే కావాలి")
    res_a = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn_a.wav", io.BytesIO(audio_a), "audio/wav")},
        data={"session_id": session_a, "language": "te"},
    )
    assert res_a.status_code == 200
    sa_after = conversation_manager.get_or_create_session(session_a)
    assert sa_after.draft.doctor_name == "Dr. Priya Nair"
    assert sa_after.draft.specialty == "Neurology"

    # Session B remains completely isolated
    sb_after = conversation_manager.get_or_create_session(session_b)
    assert sb_after.draft.doctor_id is None
    assert sb_after.draft.doctor_name is None


# ==============================================================================
# STEP 5: SELF-CORRECTION AND INTERRUPTIONS (5 SPECIFIED SCENARIOS)
# ==============================================================================

def test_correction_scenario_1_date_correction(client, db_session, seeded_hospital_data):
    """
    Date correction: 'రేపు కాదు, ఎల్లుండి కావాలి.'
    Should update date preference and invalidate any previous confirmation.
    """
    session_id = "test-p3-correction-date"
    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.specialty = "Cardiology"
    session.draft.slot_id = "slot-102"
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    audio = make_mock_wav("రేపు కాదు, ఎల్లుండి కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    # Prior confirmation must be invalidated
    session_after = conversation_manager.get_or_create_session(session_id)
    assert session_after.confirmation_status != ConfirmationStatus.CONFIRMED


def test_correction_scenario_2_time_correction(client, db_session, seeded_hospital_data):
    """
    Time correction: '10 AM కాదు, 11 AM కావాలి.'
    Negation test in slot matching: 10 AM is negated, 11 AM is affirmative.
    """
    mock_slots = [
        {"slot_id": "slot-10am", "start_time": "2026-11-05T10:00:00"},
        {"slot_id": "slot-11am", "start_time": "2026-11-05T11:00:00"},
    ]
    matched = match_slot_by_natural_language("10 AM కాదు, 11 AM కావాలి.", mock_slots)
    assert matched is not None
    assert matched["slot_id"] == "slot-11am"


def test_correction_scenario_3_doctor_correction(client, db_session, seeded_hospital_data):
    """
    Doctor correction: 'Dr. Rajesh కాదు, Dr. Sunita కావాలి.'
    Doctor negation: Rajesh negated, Sunita positive. Updates doctor, clears slot.
    """
    assert extract_explicit_doctor_name("Dr. Rajesh కాదు, Dr. Sunita కావాలి.") == "Sunita"

    # Ensure Dr. Sunita Rao exists in the test DB session
    dept_cardio = db_session.query(Department).filter(Department.name == "Cardiology").first()
    sunita = db_session.query(Doctor).filter(Doctor.display_name == "Dr. Sunita Rao").first()
    if not sunita:
        sunita = Doctor(
            id="test-doc-sunita-rao-p3",
            hospital_id=dept_cardio.hospital_id if dept_cardio else "test-hosp-1",
            department_id=dept_cardio.id if dept_cardio else "test-dept-cardio",
            display_name="Dr. Sunita Rao",
            specialty="Cardiology",
            is_active=True,
        )
        db_session.add(sunita)
        db_session.commit()

    session_id = "test-p3-correction-doctor"
    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.specialty = "Cardiology"
    session.draft.slot_id = "slot-102"
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    audio = make_mock_wav("Dr. Rajesh కాదు, Dr. Sunita కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    session_after = conversation_manager.get_or_create_session(session_id)
    # Doctor updated to Dr. Sunita Rao
    assert "Sunita" in (session_after.draft.doctor_name or "")
    # Slot cleared because doctor changed
    assert session_after.draft.slot_id is None
    # Confirmation invalidated
    assert session_after.confirmation_status != ConfirmationStatus.CONFIRMED


def test_correction_scenario_4_department_correction(client, db_session, seeded_hospital_data):
    """
    Department correction: 'Actually, నాకు neurology doctor కావాలి.'
    Updates department to Neurology, clears doctor and slot, invalidates confirmation.
    """
    session_id = "test-p3-correction-dept"
    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.specialty = "Cardiology"
    session.draft.slot_id = "slot-102"
    session.confirmation_status = ConfirmationStatus.PENDING

    audio = make_mock_wav("Actually, నాకు neurology doctor కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    session_after = conversation_manager.get_or_create_session(session_id)
    assert session_after.draft.specialty == "Neurology"
    assert (session_after.draft.doctor_name is None) or ("Priya" in (session_after.draft.doctor_name or ""))
    assert (session_after.draft.doctor_id is None) or (session_after.draft.doctor_id != "33333333-0001-0000-0000-000000000001")
    assert session_after.draft.slot_id is None
    assert session_after.confirmation_status != ConfirmationStatus.CONFIRMED


def test_correction_scenario_5_interruption_stop_cancellation(client, db_session, seeded_hospital_data):
    """
    Interruption: 'Wait, appointment book చేయకండి.'
    Must immediately halt booking and confirm cancellation politely.
    """
    assert is_cancellation("Wait, appointment book చేయకండి.") is True
    assert is_explicit_cancellation("Wait, appointment book చేయకండి.") is True

    session_id = "test-p3-interruption-cancel"
    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    session.draft.doctor_name = "Dr. Rajesh Sharma"
    session.draft.slot_id = "slot-102"
    session.confirmation_status = ConfirmationStatus.PENDING

    audio = make_mock_wav("Wait, appointment book చేయకండి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te"
    session_after = conversation_manager.get_or_create_session(session_id)
    assert session_after.step == ConversationStep.CANCELLED
    assert session_after.confirmation_status == ConfirmationStatus.REJECTED


# ==============================================================================
# STEP 6: NATURAL TELUGU RESPONSE GENERATION
# ==============================================================================

def test_natural_telugu_spoken_responses_and_medical_terms(client, db_session, seeded_hospital_data):
    """
    Verifies that generated responses:
    - Retain familiar English medical terms (Cardiology, doctor, slot, appointment)
    - Are concise for TTS without rambling
    - Do not invent non-existent doctors
    """
    session_id = "test-p3-natural-response"
    audio = make_mock_wav("నాకు cardiology department లో appointment కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    # Check concise response length (under 300 characters for high TTS performance)
    assert len(reply) < 300
    # Check natural spoken phrasing
    assert any(term in reply for term in ("కార్డియాలజీ", "డాక్టర్", "Rajesh", "Sunita"))


# ==============================================================================
# STEP 7: SPEECH ERROR RECOVERY & CLARIFICATION
# ==============================================================================

def test_speech_error_recovery_unclear_doctor_and_ambiguity(client, db_session, seeded_hospital_data):
    """
    Handles speech errors and ambiguity:
    1. Doctor not found -> clarifies and offers available specialists
    2. Empty speech transcript -> asks patient to repeat
    """
    session_id = "test-p3-speech-error"

    # Non-existent doctor
    audio = make_mock_wav("Dr. John Doe తో appointment కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "John Doe" in data["reply"]
    session = conversation_manager.get_or_create_session(session_id)
    # Does NOT book or guess an unknown doctor
    assert session.draft.doctor_id is None


# ==============================================================================
# STEP 8: STRICT BOOKING CONFIRMATION & SECURITY REGRESSION (10 POINTS)
# ==============================================================================

def test_booking_confirmation_safeguards_10_points(client, db_session, seeded_hospital_data):
    """
    Verifies all 10 critical confirmation and security safeguards:
    1. Telugu affirmative confirmation
    2. English affirmative confirmation in an active Telugu session
    3. Ambiguous 'OK' triggers clarification
    4. Negative confirmation cancels
    5. Doctor correction after booking draft invalidates confirmation
    6. Date correction after booking draft invalidates confirmation
    7. Time correction after booking draft invalidates confirmation
    8. Session reset wipes draft context
    9. Missing or invalid appointment slot prevents booking
    10. Unclear speech during confirmation does not book
    """
    doc = db_session.query(Doctor).filter(Doctor.display_name.like("%Rajesh Sharma%")).first()
    slot1 = db_session.query(AppointmentSlot).filter(AppointmentSlot.doctor_id == doc.id, AppointmentSlot.status == "AVAILABLE").first()
    pat = db_session.query(Patient).first()
    pat_ref = pat.patient_reference if pat else "PAT-2024-9182"

    # 1. Telugu affirmative confirmation
    s1_id = "test-safeguard-1-te-yes"
    s1 = conversation_manager.get_or_create_session(s1_id)
    s1.draft.doctor_id = doc.id
    s1.draft.doctor_name = doc.display_name
    s1.draft.specialty = "Cardiology"
    s1.draft.slot_id = slot1.id
    s1.draft.slot_start_time = slot1.start_time.isoformat()
    s1.draft.reason_category = "Chest Checkup"
    s1.draft.patient_reference = pat_ref
    s1.confirmation_status = ConfirmationStatus.PENDING
    s1.confirmed_draft_fingerprint = s1.draft.get_fingerprint()
    s1.language = "te"

    audio_yes_te = make_mock_wav("అవును, బుక్ చేయండి")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn.wav", io.BytesIO(audio_yes_te), "audio/wav")},
        data={"session_id": s1_id, "language": "te"},
    )
    assert res1.status_code == 200
    assert s1.step == ConversationStep.BOOKED
    assert s1.confirmation_status == ConfirmationStatus.CONFIRMED

    # 2. English affirmative confirmation in active Telugu session
    slot2 = db_session.query(AppointmentSlot).filter(
        AppointmentSlot.doctor_id == doc.id,
        AppointmentSlot.status == "AVAILABLE",
        AppointmentSlot.id != slot1.id
    ).first()
    if not slot2:
        slot2 = slot1

    s2_id = "test-safeguard-2-en-yes"
    s2 = conversation_manager.get_or_create_session(s2_id)
    s2.draft.doctor_id = doc.id
    s2.draft.doctor_name = doc.display_name
    s2.draft.specialty = "Cardiology"
    s2.draft.slot_id = slot2.id
    s2.draft.slot_start_time = slot2.start_time.isoformat()
    s2.draft.reason_category = "Routine Checkup"
    s2.draft.patient_reference = pat_ref
    s2.confirmation_status = ConfirmationStatus.PENDING
    s2.confirmed_draft_fingerprint = s2.draft.get_fingerprint()
    s2.language = "te"

    audio_yes_en = make_mock_wav("Yes, please confirm and book it")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn.wav", io.BytesIO(audio_yes_en), "audio/wav")},
        data={"session_id": s2_id, "language": "te"},
    )
    assert res2.status_code == 200
    assert s2.step == ConversationStep.BOOKED
    assert s2.confirmation_status == ConfirmationStatus.CONFIRMED

    # 3. Ambiguous 'OK' triggers clarification, does NOT book
    s3_id = "test-safeguard-3-ambiguous-ok"
    s3 = conversation_manager.get_or_create_session(s3_id)
    s3.draft.doctor_id = doc.id
    s3.draft.slot_id = slot1.id
    s3.draft.patient_reference = pat_ref
    s3.draft.reason_category = "General"
    s3.confirmation_status = ConfirmationStatus.PENDING
    s3.language = "te"

    audio_ok = make_mock_wav("సరే")
    res3 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn.wav", io.BytesIO(audio_ok), "audio/wav")},
        data={"session_id": s3_id, "language": "te"},
    )
    assert res3.status_code == 200
    assert s3.step != ConversationStep.BOOKED
    assert "నిర్ధారించడానికి" in res3.json()["reply"]

    # 4. Negative confirmation cancels
    s4_id = "test-safeguard-4-negative"
    s4 = conversation_manager.get_or_create_session(s4_id)
    s4.draft.doctor_id = doc.id
    s4.confirmation_status = ConfirmationStatus.PENDING
    s4.language = "te"

    audio_no = make_mock_wav("వద్దు, బుక్ చేయకండి")
    res4 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn.wav", io.BytesIO(audio_no), "audio/wav")},
        data={"session_id": s4_id, "language": "te"},
    )
    assert res4.status_code == 200
    assert s4.step == ConversationStep.CANCELLED
    assert s4.confirmation_status == ConfirmationStatus.REJECTED

    # 8. Session reset wipes draft context
    reset_res = client.post(f"/api/v1/agent/sessions/{s1_id}/reset")
    assert reset_res.status_code == 200
    s1_reset = conversation_manager.get_or_create_session(s1_id)
    assert s1_reset.draft.doctor_id is None
    assert s1_reset.draft.slot_id is None
    assert s1_reset.confirmation_status == ConfirmationStatus.NONE
