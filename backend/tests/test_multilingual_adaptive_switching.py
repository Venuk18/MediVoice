import io
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.models import Doctor, Department, AppointmentSlot, Patient
from app.services.speech.tts_service import generate_synthetic_wav, GNANI_DEFAULT_VOICES
from app.agent.conversation_manager import conversation_manager
from app.agent.adapters import (
    MockReasoningAdapter,
    detect_language,
    detect_explicit_language_switch,
    has_expected_language_script,
    is_affirmative,
    is_cancellation,
)
from app.agent.language_resolver import (
    resolve_adaptive_language,
    detect_explicit_language_command,
    is_entity_only_or_patient_info,
    detect_script_language,
    detect_romanized_language,
    detect_english_utterance,
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
# TEST 1: English input receives English response
# ==============================================================================
def test_01_english_input_receives_english_response(client, db_session, seeded_hospital_data):
    """
    Patient asks 'Can you book an appointment?'
    Must respond in English, NOT Telugu!
    """
    session_id = "test-multi-01-english"
    audio = make_mock_wav("Can you book an appointment?")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "en"
    assert data["language"] == "en"
    # Verify reply is in English
    reply = data["reply"]
    assert any(phrase in reply.lower() for phrase in ("of course", "help you book", "which doctor", "department", "specialty"))
    assert not any(0x0C00 <= ord(ch) <= 0x0C7F for ch in reply), "Reply must not contain Telugu script"
    assert not any(0x0C00 <= ord(ch) <= 0x0C7F for ch in reply), "Reply must not contain Telugu script"


# ==============================================================================
# TEST 2: Telugu input receives Telugu response
# ==============================================================================
def test_02_telugu_input_receives_telugu_response(client, db_session, seeded_hospital_data):
    """
    Patient speaks Telugu: 'నాకు కార్డియాలజీ డాక్టర్ కావాలి.'
    Must respond in Telugu with Telugu script.
    """
    session_id = "test-multi-02-telugu"
    audio = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "te"
    assert data["language"] == "te"
    reply = data["reply"]
    assert any(0x0C00 <= ord(ch) <= 0x0C7F for ch in reply), "Reply must contain Telugu script"


# ==============================================================================
# TEST 3: Hindi input receives Hindi response
# ==============================================================================
def test_03_hindi_input_receives_hindi_response(client, db_session, seeded_hospital_data):
    """
    Patient speaks Hindi: 'मुझे डॉक्टर से मिलना है'
    Must respond in Hindi with Devanagari script.
    """
    session_id = "test-multi-03-hindi"
    audio = make_mock_wav("मुझे डॉक्टर से मिलना है")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "hi"
    assert data["language"] == "hi"
    reply = data["reply"]
    assert any(0x0900 <= ord(ch) <= 0x097F for ch in reply), "Reply must contain Devanagari script"


# ==============================================================================
# TEST 4: Tamil input receives Tamil response
# ==============================================================================
def test_04_tamil_input_receives_tamil_response(client, db_session, seeded_hospital_data):
    """
    Patient speaks Tamil: 'எனக்கு மருத்துவரை பார்க்க வேண்டும்'
    Must respond in Tamil with Tamil script.
    """
    session_id = "test-multi-04-tamil"
    audio = make_mock_wav("எனக்கு மருத்துவரை பார்க்க வேண்டும்")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "ta"
    assert data["language"] == "ta"
    reply = data["reply"]
    assert any(0x0B80 <= ord(ch) <= 0x0BFF for ch in reply), "Reply must contain Tamil script"


# ==============================================================================
# TEST 5: Kannada input receives Kannada response
# ==============================================================================
def test_05_kannada_input_receives_kannada_response(client, db_session, seeded_hospital_data):
    """
    Patient speaks Kannada: 'ನನಗೆ ವೈದ್ಯರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು'
    Must respond in Kannada with Kannada script.
    """
    session_id = "test-multi-05-kannada"
    audio = make_mock_wav("ನನಗೆ ವೈದ್ಯರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "kn"
    assert data["language"] == "kn"
    reply = data["reply"]
    assert any(0x0C80 <= ord(ch) <= 0x0CFF for ch in reply), "Reply must contain Kannada script"


# ==============================================================================
# TEST 6: Telugu-English code-mixing
# ==============================================================================
def test_06_telugu_english_code_mixing(client, db_session, seeded_hospital_data):
    """
    Sentence: 'నాకు cardiology department లో appointment కావాలి.'
    Must recognize Telugu despite English loan words ('cardiology', 'department', 'appointment').
    """
    session_id = "test-multi-06-codemix"
    audio = make_mock_wav("నాకు cardiology department లో appointment కావాలి.")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "te"
    assert data["language"] == "te"
    assert data["draft"]["specialty"] == "Cardiology"


# ==============================================================================
# TEST 7: English to Telugu switching in one session
# ==============================================================================
def test_07_english_to_telugu_switching_in_one_session(client, db_session, seeded_hospital_data):
    """
    Turn 1: 'Can you book an appointment?' -> English.
    Turn 2: 'నాకు కార్డియాలజీ డాక్టర్ కావాలి.' -> Telugu.
    Verify seamless language transition in the same session.
    """
    session_id = "test-multi-07-en-to-te"

    # Turn 1: English
    audio1 = make_mock_wav("Can you book an appointment?")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "en"

    # Turn 2: Telugu
    audio2 = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి.")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res2.status_code == 200
    assert res2.json()["language"] == "te"
    assert res2.json()["draft"]["specialty"] == "Cardiology"


# ==============================================================================
# TEST 8: Telugu to English switching in one session
# ==============================================================================
def test_08_telugu_to_english_switching_in_one_session(client, db_session, seeded_hospital_data):
    """
    Turn 1: 'నాకు కార్డియాలజీ డాక్టర్ కావాలి.' -> Telugu.
    Turn 2: 'Tomorrow morning.' -> English.
    Verify language switches to English and preserves draft specialty.
    """
    session_id = "test-multi-08-te-to-en"

    # Turn 1: Telugu
    audio1 = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి.")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "te"

    # Turn 2: English
    audio2 = make_mock_wav("Tomorrow morning.")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res2.status_code == 200
    assert res2.json()["language"] == "en"
    # Specialty Cardiology from Turn 1 is preserved
    assert res2.json()["draft"]["specialty"] == "Cardiology"


# ==============================================================================
# TEST 9: Short doctor names do not trigger language switching
# ==============================================================================
def test_09_short_doctor_names_do_not_trigger_language_switching(client, db_session, seeded_hospital_data):
    """
    When in Telugu conversation, naming 'Dr. Rajesh Sharma' or 'Rajesh Sharma'
    must NOT cause the conversation to revert to English.
    """
    session_id = "test-multi-09-doc-name"

    # Turn 1: Telugu
    audio1 = make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి.")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "te"

    # Turn 2: Doctor name in Latin/English characters
    audio2 = make_mock_wav("Dr. Rajesh Sharma")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res2.status_code == 200
    # Must remain in Telugu!
    assert res2.json()["language"] == "te"
    assert "Rajesh" in (res2.json()["draft"]["doctor_name"] or "")


# ==============================================================================
# TEST 10: Dates and times do not trigger false language switching
# ==============================================================================
def test_10_dates_and_times_do_not_trigger_false_language_switching(client, db_session, seeded_hospital_data):
    """
    When in Telugu conversation, specifying numeric time '10:00 AM'
    must NOT cause the conversation to revert to English.
    """
    session_id = "test-multi-10-time-slot"

    # Start session in Telugu with doctor selected
    doc = db_session.query(Doctor).filter(Doctor.display_name.like("%Rajesh Sharma%")).first()
    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = doc.id
    session.draft.doctor_name = doc.display_name
    session.draft.specialty = "Cardiology"
    session.language = "te"

    audio = make_mock_wav("10:00 AM")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    assert res.json()["language"] == "te"


# ==============================================================================
# TEST 11: Manual language selection
# ==============================================================================
def test_11_manual_language_selection(client, db_session, seeded_hospital_data):
    """
    When manual mode is pinned to Tamil ('ta'), an English-phrase utterance
    is answered in Tamil respecting the manual preference.
    """
    session_id = "test-multi-11-manual-tamil"

    audio = make_mock_wav("I want an appointment")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "ta"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "ta"
    assert data["language_mode"] == "manual"


# ==============================================================================
# TEST 12: Switching from manual mode to automatic mode
# ==============================================================================
def test_12_switching_from_manual_mode_to_automatic_mode(client, db_session, seeded_hospital_data):
    """
    When user is in manual mode and switches to auto mode, subsequent turns adapt dynamically.
    """
    session_id = "test-multi-12-manual-to-auto"

    # Turn 1: Manual Tamil
    audio1 = make_mock_wav("I want an appointment")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "ta"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "ta"

    # Turn 2: Switch to auto mode
    audio2 = make_mock_wav("switch to auto")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res2.status_code == 200
    assert res2.json()["language_mode"] == "auto"

    # Turn 3: User speaks English
    audio3 = make_mock_wav("Can you book an appointment?")
    res3 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn3.wav", io.BytesIO(audio3), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res3.status_code == 200
    assert res3.json()["language"] == "en"


# ==============================================================================
# TEST 13: Dynamic TTS language selection
# ==============================================================================
def test_13_dynamic_tts_language_selection(monkeypatch, db_session, seeded_hospital_data):
    """
    Verifies that TTS synthesis uses the language of the assistant reply:
    - English response -> en
    - Telugu response -> te
    - Hindi response -> hi
    """
    synthesize_calls = []

    def spy_synthesize(text, language=None, voice=None, speed=None):
        synthesize_calls.append({"text": text, "language": language, "voice": voice})
        return generate_synthetic_wav(0.1)

    monkeypatch.setattr(voice_orchestrator.tts, "synthesize", spy_synthesize)

    # 1. English turn
    voice_orchestrator.process_voice_turn(
        db=db_session,
        audio_bytes=make_mock_wav("Can you book an appointment?"),
        session_id="tts-dyn-en",
        language="auto",
    )
    assert len(synthesize_calls) >= 1
    assert synthesize_calls[-1]["language"] in ("en", "en-IN")

    # 2. Telugu turn
    voice_orchestrator.process_voice_turn(
        db=db_session,
        audio_bytes=make_mock_wav("నాకు కార్డియాలజీ డాక్టర్ కావాలి."),
        session_id="tts-dyn-te",
        language="auto",
    )
    assert len(synthesize_calls) >= 2
    assert synthesize_calls[-1]["language"] in ("te", "te-IN")

    # 3. Hindi turn
    voice_orchestrator.process_voice_turn(
        db=db_session,
        audio_bytes=make_mock_wav("मुझे डॉक्टर से मिलना है"),
        session_id="tts-dyn-hi",
        language="auto",
    )
    assert len(synthesize_calls) >= 3
    assert synthesize_calls[-1]["language"] in ("hi", "hi-IN")


# ==============================================================================
# TEST 14: Unsupported or uncertain language handling
# ==============================================================================
def test_14_unsupported_or_uncertain_language_handling(client, db_session, seeded_hospital_data):
    """
    Uncertain or ambiguous utterance falls back gracefully to a safe supported language
    without throwing 500 errors.
    """
    session_id = "test-multi-14-uncertain"
    audio = make_mock_wav("xyzabc123 blah")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] in ("en", "te", "hi", "ta", "kn")
    assert bool(data["reply"])


# ==============================================================================
# TEST 15: Existing booking confirmation safety preserved
# ==============================================================================
def test_15_existing_booking_confirmation_safety_preserved(client, db_session, seeded_hospital_data):
    """
    Booking confirmation safeguards remain strictly enforced across languages:
    - Never books without explicit affirmative confirmation in PENDING state.
    """
    session_id = "test-multi-15-safety"
    doc = db_session.query(Doctor).filter(Doctor.display_name.like("%Rajesh Sharma%")).first()
    slot = db_session.query(AppointmentSlot).filter(AppointmentSlot.doctor_id == doc.id).first()

    session = conversation_manager.get_or_create_session(session_id)
    session.draft.doctor_id = doc.id
    session.draft.doctor_name = doc.display_name
    session.draft.specialty = doc.specialty
    session.draft.slot_id = slot.id
    session.draft.slot_start_time = slot.start_time.isoformat()
    session.draft.reason_category = "Chest Pain"
    session.draft.patient_reference = "PAT-101-SAFE"
    session.confirmation_status = ConfirmationStatus.NONE

    # User says "yes" while confirmation_status is NOT PENDING
    audio = make_mock_wav("yes")
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res.status_code == 200
    session_after = conversation_manager.get_or_create_session(session_id)
    assert session_after.step != ConversationStep.BOOKED
    assert session_after.confirmation_status != ConfirmationStatus.CONFIRMED


# ==============================================================================
# TEST 16: Existing Phase 2 & 3 Telugu functionality preserved
# ==============================================================================
def test_16_phase2_and_phase3_telugu_functionality_preserved(client, db_session, seeded_hospital_data):
    """
    Verifies that Romanized Telugu and Telugu-first workflows still execute with 100% precision:
    - 'naaku cardiology doctor kavali' -> te, extracts Cardiology
    - 'vaddu, cancel cheyyandi' -> cancels appointment politely
    """
    # 1. Romanized Telugu search
    session_id = "test-multi-16-preservation"
    audio1 = make_mock_wav("naaku cardiology doctor kavali")
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn1.wav", io.BytesIO(audio1), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res1.status_code == 200
    assert res1.json()["language"] == "te"
    assert res1.json()["draft"]["specialty"] == "Cardiology"

    # 2. Romanized cancellation
    audio2 = make_mock_wav("vaddu, cancel cheyyandi")
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("turn2.wav", io.BytesIO(audio2), "audio/wav")},
        data={"session_id": session_id, "language": "auto"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["step"] == ConversationStep.CANCELLED.value
    assert data2["confirmation_status"] == ConfirmationStatus.REJECTED.value
