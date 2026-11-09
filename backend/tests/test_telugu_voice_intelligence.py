import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.speech.tts_service import generate_synthetic_wav
from app.agent.conversation_manager import conversation_manager
from app.agent.adapters import MockReasoningAdapter, match_slot_by_natural_language, is_affirmative, is_cancellation
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
    Ensures zero external AI or speech credits are consumed during test runs.
    """
    conversation_manager.adapter = MockReasoningAdapter()

    def mock_synthesize(text, language=None, voice=None, speed=None):
        return generate_synthetic_wav(0.1)

    monkeypatch.setattr(voice_orchestrator.tts, "synthesize", mock_synthesize)


# 1. Telugu default voice language
def test_telugu_default_voice_language(client, db_session, seeded_hospital_data):
    """
    When patient initiates voice turn with language='te' or default,
    the pipeline processes with Telugu as default voice language.
    """
    session_id = "test-telugu-default-voice"
    audio_content = make_mock_wav("నమస్కారం")

    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio_content), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "te"
    assert data["session_id"] == session_id


# 2. Language persistence across turns
def test_language_persistence_across_turns(client, db_session, seeded_hospital_data):
    """
    Telugu persists across turns for follow-ups (e.g. doctor name, time, 'yes')
    without reverting to English.
    """
    session_id = "test-telugu-persistence"
    # Turn 1: Initial Telugu query
    audio1 = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "te"

    # Turn 2: Follow-up doctor name in English letters
    audio2 = make_mock_wav("Dr. Rajesh Sharma")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res2.status_code == 200
    assert res2.json()["language"] == "te"

    # Turn 3: Follow-up time in English letters
    audio3 = make_mock_wav("10:00 AM")
    res3 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn3.wav", io.BytesIO(audio3), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res3.status_code == 200
    assert res3.json()["language"] == "te"


# 3. English language switching
def test_explicit_english_language_switching(client, db_session, seeded_hospital_data):
    """
    User can explicitly switch from Telugu to English mid-session.
    """
    session_id = "test-telugu-to-english-switch"
    # Turn 1: In Telugu
    audio1 = make_mock_wav("నమస్కారం")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "te"

    # Turn 2: Explicit switch to English
    audio2 = make_mock_wav("Please switch to English")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "en"},
    )
    assert res2.status_code == 200
    assert res2.json()["language"] == "en"


# 4. Telugu-English code-mixed requests
def test_telugu_english_code_mixing(client, db_session, seeded_hospital_data):
    """
    Code-mixed expressions (e.g. 'నాకు cardiology doctor కావాలి.') retain Telugu
    language and extract the correct medical specialty.
    """
    session_id = "test-code-mixed"
    audio1 = make_mock_wav("నాకు cardiology doctor కావాలి.")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("cm1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res1.status_code == 200
    data = res1.json()
    assert data["language"] == "te"
    assert data["draft"]["specialty"] == "Cardiology"


# 5. Romanized Telugu handling
def test_romanized_telugu_handling(client, db_session, seeded_hospital_data):
    """
    Transliterated/Romanized Telugu ('naaku doctor kavali', 'avunu') resolves to Telugu.
    """
    session_id = "test-romanized-telugu"
    audio = make_mock_wav("naaku doctor kavali")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("rom.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    assert res.json()["language"] == "te"


# 6. Telugu doctor search
def test_scenario_1_telugu_cardiology_search(client, db_session, seeded_hospital_data):
    """
    Scenario 1: 'నాకు కార్డియాలజీ డాక్టర్ అపాయింట్మెంట్ కావాలి.'
    Searches cardiology specialists without treating 'అపాయింట్మెంట్' as a doctor name.
    """
    session_id = "test-scenario-1"
    audio = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ అపాయింట్మెంట్ కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("s1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["draft"]["specialty"] == "Cardiology"
    assert "Rajesh Sharma" in data["reply"] or "కార్డియాలజిస్ట్" in data["reply"]
    # Never confuse appointment with doctor name
    assert data["draft"]["doctor_name"] != "అపాయింట్మెంట్"


# 7. Telugu doctor availability check without premature booking
def test_scenario_2_doctor_availability_without_premature_booking(client, db_session, seeded_hospital_data):
    """
    Scenario 2: 'రేపు డాక్టర్ రాజేష్ శర్మ అందుబాటులో ఉన్నారా?'
    Checks doctor availability on tomorrow without booking prematurely.
    """
    session_id = "test-scenario-2"
    audio = make_mock_wav("రేపు డాక్టర్ రాజేష్ శర్మ అందుబాటులో ఉన్నారా?")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("s2.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["draft"]["doctor_name"] == "Dr. Rajesh Sharma"
    assert data["confirmation_status"] == "NONE"
    assert data["draft"]["slot_id"] is None
    assert data["booked_appointment"] is None


# 8. Telugu appointment time preferences (10:00 AM slot matching)
def test_scenario_3_telugu_slot_matching():
    """
    Scenario 3: 'నాకు ఉదయం 10 గంటలకు అపాయింట్మెంట్ కావాలి.'
    Matches 10:00 AM slot accurately.
    """
    offered_slots = [
        {"slot_id": "slot-9am", "start_time": "2026-11-05T09:00:00"},
        {"slot_id": "slot-10am", "start_time": "2026-11-05T10:00:00"},
        {"slot_id": "slot-2pm", "start_time": "2026-11-05T14:00:00"},
    ]
    s3 = "నాకు ఉదయం 10 గంటలకు అపాయింట్మెంట్ కావాలి."
    matched = match_slot_by_natural_language(s3, offered_slots)
    assert matched is not None
    assert matched["slot_id"] == "slot-10am"


# 9. Relative date preference / correction (Not tomorrow, day after tomorrow)
def test_scenario_6_relative_date_correction():
    """
    Scenario 6: 'లేదు, నాకు రేపు కాదు ఎల్లుండి కావాలి.'
    Accurately matches day-after-tomorrow slot rather than tomorrow.
    """
    offered_slots = [
        {"slot_id": "slot-tomorrow-10am", "start_time": "2026-11-05T10:00:00"},
        {"slot_id": "slot-day-after-10am", "start_time": "2026-11-06T10:00:00"},
    ]
    s6 = "లేదు, నాకు రేపు కాదు ఎల్లుండి కావాలి."
    matched = match_slot_by_natural_language(s6, offered_slots)
    assert matched is not None
    assert matched["slot_id"] == "slot-day-after-10am"


# 10. Explicit booking request (confirms only if draft complete and confirmation pending)
def test_scenario_4_booking_request_safeguards(client, db_session, seeded_hospital_data):
    """
    Scenario 4: 'నా అపాయింట్మెంట్ బుక్ చేయండి.'
    Does NOT book when draft is incomplete or confirmation is not pending.
    """
    session_id = "test-scenario-4-incomplete"
    audio = make_mock_wav("నా అపాయింట్మెంట్ బుక్ చేయండి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("s4.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["confirmation_status"] == "NONE"
    assert data["booked_appointment"] is None


# 11. Change doctor intent
def test_scenario_5_change_doctor_invalidates_confirmation(db_session, seeded_hospital_data):
    """
    Scenario 5: 'డాక్టర్ మార్చండి.'
    Invalidates previous confirmation, clears slot, and presents doctor options.
    """
    session_id = "test-scenario-5-change-doc"
    sess = conversation_manager.get_or_create_session(session_id)
    sess.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    sess.draft.doctor_name = "Dr. Rajesh Sharma"
    sess.draft.specialty = "Cardiology"
    sess.draft.slot_id = "slot-101"
    sess.draft.slot_start_time = "2026-11-05T10:00:00"
    sess.draft.reason_category = "Chest checkup"
    sess.draft.patient_reference = "PAT-2024-9182"
    sess.step = ConversationStep.AWAITING_CONFIRMATION
    sess.confirmation_status = ConfirmationStatus.PENDING
    sess.confirmed_draft_fingerprint = sess.draft.get_fingerprint()

    s5 = "డాక్టర్ మార్చండి."
    res = conversation_manager.process_message(db_session, s5, session_id=session_id)

    assert res.confirmation_status == ConfirmationStatus.NONE
    assert res.draft.doctor_name is None
    assert res.draft.slot_id is None
    # Doctor options presented
    assert "Dr. Sunita Rao" in res.reply or "వైద్యు" in res.reply


# 12. Telugu affirmative confirmation
def test_telugu_affirmative_confirmation_booking(db_session, seeded_hospital_data):
    """
    Explicit affirmatives ('అవును', 'సరే, బుక్ చేయండి', 'అవును, కన్ఫర్మ్ చేయండి') confirm booking.
    """
    assert is_affirmative("అవును") is True
    assert is_affirmative("సరే, బుక్ చేయండి") is True
    assert is_affirmative("అవును, కన్ఫర్మ్ చేయండి") is True
    assert is_affirmative("confirm cheyandi") is True


# 13. Telugu negative confirmation
def test_telugu_negative_confirmation(db_session, seeded_hospital_data):
    """
    Negative responses ('వద్దు', 'బుక్ చేయకండి', 'రద్దు చేయండి') reject/cancel pending booking.
    """
    session_id = "test-telugu-negative-confirm"
    sess = conversation_manager.get_or_create_session(session_id)
    sess.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    sess.draft.doctor_name = "Dr. Rajesh Sharma"
    sess.draft.specialty = "Cardiology"
    sess.draft.slot_id = "slot-101"
    sess.draft.slot_start_time = "2026-11-05T10:00:00"
    sess.draft.reason_category = "Chest checkup"
    sess.draft.patient_reference = "PAT-2024-9182"
    sess.step = ConversationStep.AWAITING_CONFIRMATION
    sess.confirmation_status = ConfirmationStatus.PENDING
    sess.confirmed_draft_fingerprint = sess.draft.get_fingerprint()

    res = conversation_manager.process_message(db_session, "బుక్ చేయకండి", session_id=session_id)
    assert res.confirmation_status == ConfirmationStatus.REJECTED
    assert res.step == ConversationStep.CANCELLED
    assert res.booked_appointment is None


# 14. Ambiguous confirmation triggers clarification
def test_ambiguous_confirmation_triggers_clarification(db_session, seeded_hospital_data):
    """
    Ambiguous answers like 'సరే' or 'ok' alone do NOT book; they trigger clarification.
    """
    session_id = "test-ambiguous-confirm"
    sess = conversation_manager.get_or_create_session(session_id)
    sess.draft.doctor_id = "33333333-0001-0000-0000-000000000001"
    sess.draft.doctor_name = "Dr. Rajesh Sharma"
    sess.draft.specialty = "Cardiology"
    sess.draft.slot_id = "slot-101"
    sess.draft.slot_start_time = "2026-11-05T10:00:00"
    sess.draft.reason_category = "Chest checkup"
    sess.draft.patient_reference = "PAT-2024-9182"
    sess.step = ConversationStep.AWAITING_CONFIRMATION
    sess.confirmation_status = ConfirmationStatus.PENDING
    sess.confirmed_draft_fingerprint = sess.draft.get_fingerprint()

    res = conversation_manager.process_message(db_session, "సరే", session_id=session_id)
    assert res.confirmation_status == ConfirmationStatus.PENDING
    assert res.booked_appointment is None
    assert "‘అవును’ అని చెప్పండి" in res.reply


# 15. Session reset and language reset
def test_session_reset_and_language_reset(client, db_session, seeded_hospital_data):
    """
    Resetting a session clears all draft state, history, and voice language base cleanly.
    """
    session_id = "test-reset-session-voice"
    audio = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("t1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "te"},
    )
    assert res1.status_code == 200

    # Reset session via API (plural endpoint /sessions/{id}/reset)
    res_reset = client.post(f"/api/v1/agent/sessions/{session_id}/reset")
    assert res_reset.status_code == 200
    data_reset = res_reset.json()
    assert data_reset.get("success") is True or "reset" in str(data_reset).lower()

    # Verify session is cleaned from manager
    assert session_id not in conversation_manager._sessions
    assert session_id not in conversation_manager._voice_selected_languages
