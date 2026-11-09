import base64
from datetime import datetime, timezone
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.hospital import Hospital
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.services.patient_service import (
    normalize_spoken_phone_number,
    normalize_phone,
    register_patient,
)
from app.agent.adapters import (
    extract_phone_number_candidate,
    matches_doctor_name,
    MockReasoningAdapter,
)
from app.agent.conversation_manager import ConversationManager
from app.agent.schemas import ConversationStep, ConfirmationStatus, AgentSessionState, BookingDraft
from app.services.speech.tts_service import clean_text_for_speech, GnaniTimbreTTS, generate_synthetic_wav
from app.services.speech.voice_orchestrator import VoiceOrchestrator


@pytest.fixture
def test_hospital_setup(db_session: Session):
    """Seeds hospital, department, and doctor records for deterministic testing."""
    hosp = Hospital(name="Aarogya One Hospital", address="Hyderabad, Telangana")
    db_session.add(hosp)
    db_session.commit()
    db_session.refresh(hosp)

    dept = Department(name="Cardiology", hospital_id=hosp.id)
    db_session.add(dept)
    db_session.commit()
    db_session.refresh(dept)

    doc = Doctor(
        id="doc-rajesh-sharma-1",
        hospital_id=hosp.id,
        department_id=dept.id,
        display_name="Dr. Rajesh Sharma",
        specialty="Cardiology",
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    from datetime import timedelta
    start_dt = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(minutes=30)
    slot = AppointmentSlot(
        id=f"slot-{start_dt.strftime('%Y-%m-%d')}-1000",
        doctor_id=doc.id,
        start_time=start_dt,
        end_time=end_dt,
        status="AVAILABLE",
    )
    db_session.add(slot)
    db_session.commit()
    db_session.refresh(slot)

    return {"hospital": hosp, "department": dept, "doctor": doc, "slot": slot}


# -----------------------------------------------------------------------------
# 1. Spoken Phone Number Normalization Tests across 5 Languages
# -----------------------------------------------------------------------------
def test_spoken_phone_number_normalization_all_formats():
    # 1. Standard continuous 10 digits
    assert normalize_spoken_phone_number("9876543210") == "9876543210"

    # 2. Spaced digits
    assert normalize_spoken_phone_number("9 8 7 6 5 4 3 2 1 0") == "9876543210"

    # 3. Leading +91 and 0
    assert normalize_spoken_phone_number("+91 9876543210") == "9876543210"
    assert normalize_spoken_phone_number("09876543210") == "9876543210"

    # 4. Indic Telugu Numerals
    assert normalize_spoken_phone_number("౯౮౭౬౫౪౩౨౧౦") == "9876543210"

    # 5. Indic Devanagari (Hindi) Numerals
    assert normalize_spoken_phone_number("९८७६५४३२१०") == "9876543210"

    # 6. Telugu spoken words
    telugu_spoken = "తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు నాలుగు మూడు రెండు ఒకటి సున్నా"
    assert normalize_spoken_phone_number(telugu_spoken) == "9876543210"

    # 7. Hindi spoken words
    hindi_spoken = "नौ आठ सात छह पाँच चार तीन दो एक शून्य"
    assert normalize_spoken_phone_number(hindi_spoken) == "9876543210"

    # 8. Tamil spoken words
    tamil_spoken = "ஒன்பது எட்டு ஏழு ஆறு ஐந்து நான்கு மூன்று இரண்டு ஒன்று பூஜ்ஜியம்"
    assert normalize_spoken_phone_number(tamil_spoken) == "9876543210"

    # 9. Kannada spoken words
    kannada_spoken = "ಒಂಬತ್ತು ಎಂಟು ಏಳು ಆರು ಐದು ನಾಲ್ಕು ಮೂರು ಎರಡು ಒಂದು ಸೊನ್ನೆ"
    assert normalize_spoken_phone_number(kannada_spoken) == "9876543210"

    # 10. Multipliers (double/triple)
    assert normalize_spoken_phone_number("డబుల్ 9 8 7 6 5 4 3 2 1") == "9987654321"
    assert normalize_spoken_phone_number("double nine eight seven six five four three two one") == "9987654321"

    # 11. Rejection of invalid inputs
    assert normalize_spoken_phone_number("12345") is None
    assert normalize_spoken_phone_number("987654321") is None
    assert normalize_spoken_phone_number("987654321000") is None
    assert normalize_spoken_phone_number("hello world") is None
    assert normalize_spoken_phone_number("") is None


def test_extract_phone_number_candidate_with_spoken_indic():
    msg = "నా ఫోన్ నెంబర్ తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు నాలుగు మూడు రెండు ఒకటి సున్నా అండి"
    assert extract_phone_number_candidate(msg) == "9876543210"

    msg_hi = "मेरा मोबाइल नंबर नौ आठ सात छह पाँच चार तीन दो एक शून्य है"
    assert extract_phone_number_candidate(msg_hi) == "9876543210"


# -----------------------------------------------------------------------------
# 2. Patient Identity Inconsistency and Conflict Resolution
# -----------------------------------------------------------------------------
def test_register_patient_identity_conflict_detection(db_session: Session):
    # Register original patient Sethu
    p1 = register_patient(db_session, "Sethu", "9871231231")
    assert p1["is_new"] is True
    assert p1["full_name"] == "Sethu"

    # Now attempt registering Venu with the same phone number
    p2 = register_patient(db_session, "Venu", "9871231231")
    assert p2["is_new"] is False
    assert p2["identity_conflict"] is True
    assert p2["provided_name"] == "Venu"
    assert p2["full_name"] == "Sethu"

    # Attempt registering same person with alias (Sethu Kumar)
    p3 = register_patient(db_session, "Sethu Kumar", "9871231231")
    assert p3["identity_conflict"] is False


def test_conversation_identity_conflict_clarification_flow(db_session: Session, test_hospital_setup):
    # Seed Sethu in database with phone 9871231231
    register_patient(db_session, "Sethu", "9871231231")

    cm = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-session-identity-conflict"
    session = cm.get_or_create_session(session_id)

    # Set up draft with doctor and slot ready, awaiting patient phone number
    session.draft.doctor_id = test_hospital_setup["doctor"].id
    session.draft.doctor_name = test_hospital_setup["doctor"].display_name
    session.draft.specialty = "Cardiology"
    session.draft.slot_id = test_hospital_setup["slot"].id
    session.draft.slot_start_time = str(test_hospital_setup["slot"].start_time)
    session.draft.patient_name = "Venu"
    session.step = ConversationStep.COLLECTING_DETAILS
    session.pending_action = "COLLECTING_NEW_PATIENT_PHONE"

    # User provides phone number that belongs to Sethu in database
    res1 = cm.process_message(db_session, "My phone number is 9871231231", session_id=session_id)
    assert session.pending_action == "CLARIFY_PATIENT_IDENTITY_CONFLICT"
    assert "Sethu" in res1.reply
    assert "Venu" in res1.reply

    # User clarifies: "Continue as Venu"
    res2 = cm.process_message(db_session, "Continue as Venu", session_id=session_id)
    assert session.pending_action is None
    assert session.draft.patient_name == "Venu"
    assert session.confirmation_status == ConfirmationStatus.PENDING
    assert "Venu" in res2.reply
    assert "Sethu" not in res2.reply


# -----------------------------------------------------------------------------
# 3. Exact Utterance Doctor Selection Trace Comparison
# -----------------------------------------------------------------------------
def test_multilingual_doctor_name_matcher():
    # English vs Indic Telugu
    assert matches_doctor_name("రాజేష్ శర్మ", "Dr. Rajesh Sharma") is True
    assert matches_doctor_name("రాజేష్", "Dr. Rajesh Sharma") is True
    assert matches_doctor_name("శర్మ", "Dr. Rajesh Sharma") is True

    # English vs Indic Hindi
    assert matches_doctor_name("राजेश शर्मा", "Dr. Rajesh Sharma") is True

    # English vs Indic Tamil
    assert matches_doctor_name("ராஜேஷ் சர்மா", "Dr. Rajesh Sharma") is True

    # Nair
    assert matches_doctor_name("ప్రియ నాయర్", "Dr. Priya Nair") is True
    assert matches_doctor_name("Dr. Priya", "Dr. Priya Nair") is True


def test_utterance_1_telugu_doctor_selection_hydrates_and_shows_slots(db_session: Session, test_hospital_setup):
    """
    Verifies that 'సరే, doctor రాజేష్ శర్మతో book చెయ్యి.' following a doctor search
    correctly matches Dr. Rajesh Sharma, hydrates session draft, and calls get_available_slots.
    """
    cm = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-utterance-1-rajesh"
    session = cm.get_or_create_session(session_id)
    session.language = "te"

    # Simulate prior search_doctors tool trace offering Dr. Rajesh Sharma
    from app.agent.schemas import ToolExecutionResult
    session.tool_trace.append(
        ToolExecutionResult(
            tool_name="search_doctors",
            success=True,
            data=[{
                "doctor_id": test_hospital_setup["doctor"].id,
                "display_name": test_hospital_setup["doctor"].display_name,
                "specialty": test_hospital_setup["doctor"].specialty,
            }],
        )
    )
    session.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
    session.pending_action_data = {
        "doctor_id": test_hospital_setup["doctor"].id,
        "doctor_name": test_hospital_setup["doctor"].display_name,
        "specialty": test_hospital_setup["doctor"].specialty,
    }

    # User utterance 1
    u1 = "సరే, doctor రాజేష్ శర్మతో book చెయ్యి."
    res = cm.process_message(db_session, u1, session_id=session_id)

    # Doctor should be hydrated into draft
    assert session.draft.doctor_id == test_hospital_setup["doctor"].id
    assert session.draft.doctor_name == test_hospital_setup["doctor"].display_name

    # Tool calls should include get_available_slots, NOT a redundant search_doctors
    executed_tools = [tr.tool_name for tr in session.tool_trace]
    assert "get_available_slots" in executed_tools
    # Reply should contain slot listing
    assert "అందుబాటులో ఉన్న" in res.reply or "సమయం" in res.reply


# -----------------------------------------------------------------------------
# 4. Consolidated Single Confirmation Prompt with All 5 Fields
# -----------------------------------------------------------------------------
def test_consolidated_single_confirmation_prompt_fields(db_session: Session, test_hospital_setup):
    cm = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-confirm-summary-fields"
    session = cm.get_or_create_session(session_id)
    session.language = "en"

    session.draft.doctor_id = test_hospital_setup["doctor"].id
    session.draft.doctor_name = test_hospital_setup["doctor"].display_name
    session.draft.specialty = test_hospital_setup["doctor"].specialty
    session.draft.slot_id = test_hospital_setup["slot"].id
    session.draft.slot_start_time = str(test_hospital_setup["slot"].start_time)
    session.draft.patient_reference = "PAT-2026-6910"
    session.draft.patient_name = "Venu"
    session.draft.reason_category = "Cardiology Consultation"

    # Transition to confirmation
    session.step = ConversationStep.AWAITING_CONFIRMATION
    session.confirmation_status = ConfirmationStatus.PENDING

    # Trigger summary prompt construction
    res = cm.process_message(db_session, "Show summary", session_id=session_id)

    # Verify all 5 canonical fields are present in the authoritative summary
    assert "• Patient: Venu (PAT-2026-6910)" in res.reply or "Patient: Venu" in res.reply
    assert "• Doctor: Dr. Rajesh Sharma" in res.reply or "Doctor: Dr. Rajesh Sharma" in res.reply
    assert "• Department: Cardiology" in res.reply
    assert "• Date & Time:" in res.reply
    assert "• Reason: Cardiology Consultation" in res.reply

    # Verify no duplicate confirm summaries stacked
    assert res.reply.count("Please verify and confirm") <= 1


def test_explicit_confirmation_gate(db_session: Session, test_hospital_setup):
    cm = ConversationManager(adapter=MockReasoningAdapter())
    session_id = "test-explicit-confirm-gate"
    session = cm.get_or_create_session(session_id)
    session.language = "en"

    session.draft.doctor_id = test_hospital_setup["doctor"].id
    session.draft.doctor_name = test_hospital_setup["doctor"].display_name
    session.draft.specialty = test_hospital_setup["doctor"].specialty
    session.draft.slot_id = test_hospital_setup["slot"].id
    session.draft.slot_start_time = str(test_hospital_setup["slot"].start_time)
    session.draft.patient_reference = "PAT-2026-6910"
    session.draft.patient_name = "Venu"
    session.draft.reason_category = "Cardiology Consultation"
    session.step = ConversationStep.AWAITING_CONFIRMATION
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    # User message that is NOT an explicit confirmation (e.g. asking a question)
    res_inquiry = cm.process_message(db_session, "Is parking available at the hospital?", session_id=session_id)
    assert session.confirmation_status == ConfirmationStatus.PENDING
    assert session.step != ConversationStep.BOOKED
    assert session.booked_appointment is None

    # User message that declines/changes
    res_decline = cm.process_message(db_session, "No, change the date", session_id=session_id)
    assert session.step != ConversationStep.BOOKED
    assert session.booked_appointment is None

    # Re-establish pending confirmation
    session.confirmation_status = ConfirmationStatus.PENDING
    session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

    # Explicit positive confirmation
    res_confirm = cm.process_message(db_session, "Yes, confirm booking", session_id=session_id)
    assert session.confirmation_status == ConfirmationStatus.CONFIRMED
    assert session.step == ConversationStep.BOOKED
    assert session.booked_appointment is not None


# -----------------------------------------------------------------------------
# 5. Spoken Slot List Trimming in clean_text_for_speech
# -----------------------------------------------------------------------------
def test_clean_text_for_speech_slot_trimming_telugu():
    raw_telugu_reply = (
        "డాక్టర్ రాజేష్ శర్మ గారికి అందుబాటులో ఉన్న అపాయింట్‌మెంట్‌లు:\n"
        "• ఆదివారం, 8 నవంబర్ 2026, ఉదయం 10:00\n"
        "• ఆదివారం, 8 నవంబర్ 2026, ఉదయం 10:30\n"
        "• ఆదివారం, 8 నవంబర్ 2026, ఉదయం 11:00\n"
        "• ఆదివారం, 8 నవంబర్ 2026, ఉదయం 11:30\n"
        "• ఆదివారం, 8 నవంబర్ 2026, మధ్యాహ్నం 02:00\n\n"
        "మీకు ఏ సమయం అనుకూలంగా ఉంటుంది?"
    )

    cleaned = clean_text_for_speech(raw_telugu_reply)
    # Kept top 3 slots
    assert "ఉదయం 10:00" in cleaned
    assert "ఉదయం 10:30" in cleaned
    assert "ఉదయం 11:00" in cleaned
    # Omitted 4th and 5th from speech and appended concise notice
    assert "మధ్యాహ్నం 02:00" not in cleaned
    assert "మరిన్ని సమయాలు స్క్రీన్‌పై ఉన్నాయి" in cleaned
    # Final question intact
    assert "మీకు ఏ సమయం అనుకూలంగా ఉంటుంది" in cleaned


def test_clean_text_for_speech_slot_trimming_english():
    raw_english_reply = (
        "Here are the available slots for Dr. Rajesh Sharma:\n"
        "• Sunday, 8 November 2026, 10:00 AM\n"
        "• Sunday, 8 November 2026, 10:30 AM\n"
        "• Sunday, 8 November 2026, 11:00 AM\n"
        "• Sunday, 8 November 2026, 11:30 AM\n"
        "• Sunday, 8 November 2026, 02:00 PM\n\n"
        "Which time works best for you?"
    )

    cleaned = clean_text_for_speech(raw_english_reply)
    assert "10:00 AM" in cleaned
    assert "10:30 AM" in cleaned
    assert "11:00 AM" in cleaned
    assert "02:00 PM" not in cleaned
    assert "More options are displayed on your screen" in cleaned


# -----------------------------------------------------------------------------
# 6. End-to-End Voice Turn with Mock Audio and Structured Diagnostics
# -----------------------------------------------------------------------------
def test_voice_orchestrator_mock_turn_with_diagnostics(db_session: Session, test_hospital_setup):
    vo = VoiceOrchestrator()
    synth_wav = generate_synthetic_wav(duration_seconds=0.5)

    with patch.object(vo.stt, "transcribe", return_value={"transcript": "Cardiology doctor", "confidence": 0.95, "language_code": "en"}):
        with patch.object(vo.tts, "synthesize", return_value=generate_synthetic_wav(duration_seconds=1.0)):
            result = vo.process_voice_turn(
                db=db_session,
                audio_bytes=synth_wav,
                session_id="test-voice-turn-diag",
                correlation_id="test-corr-1234",
                language="en",
                include_audio_base64=True,
            )

    assert result["correlation_id"] == "test-corr-1234"
    assert result["detected_language"] == "en"
    assert result["tts_available"] is True
    assert result["audio_base64"] is not None
    assert result["audio_content_type"] == "audio/wav"

    # Verify base64 decodes back to valid WAV
    decoded_audio = base64.b64decode(result["audio_base64"])
    assert decoded_audio.startswith(b"RIFF")
    assert b"WAVE" in decoded_audio[:12]


# -----------------------------------------------------------------------------
# 7. GnaniTimbreTTS Bounded Timeout Configuration
# -----------------------------------------------------------------------------
def test_tts_service_timeout_bounds():
    tts_default = GnaniTimbreTTS()
    assert tts_default.timeout_seconds == 35.0

    tts_custom = GnaniTimbreTTS(timeout_seconds=50.0)
    assert tts_custom.timeout_seconds == 50.0

    # Upper bound 60.0
    tts_over = GnaniTimbreTTS(timeout_seconds=120.0)
    assert tts_over.timeout_seconds == 60.0

    # Lower bound 1.0
    tts_under = GnaniTimbreTTS(timeout_seconds=0.2)
    assert tts_under.timeout_seconds == 1.0
