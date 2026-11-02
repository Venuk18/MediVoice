import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.speech.tts_service import generate_synthetic_wav


def test_voice_config_endpoint():
    client = TestClient(app)
    res = client.get("/api/v1/voice/config")
    assert res.status_code == 200
    data = res.json()
    assert "voice_enabled" in data
    assert "stt_model" in data
    assert "tts_model" in data
    assert "supported_languages" in data
    # Verify no secret is leaked
    assert "api_key" not in str(data).lower()
    locales = [l["locale"] for l in data["supported_languages"]]
    assert "te-IN" in locales
    assert "hi-IN" in locales
    assert "en-IN" in locales


def test_voice_transcribe_endpoint():
    client = TestClient(app)
    fake_wav = generate_synthetic_wav(0.5)

    res = client.post(
        "/api/v1/voice/transcribe",
        files={"file": ("sample.wav", io.BytesIO(fake_wav), "audio/wav")},
        data={"language": "te-IN"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "transcript" in data
    assert data["detected_language"] == "te"


def test_voice_synthesize_endpoint():
    client = TestClient(app)
    res = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Welcome to Aarogya One Hospital", "language": "en"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"
    assert len(res.content) > 44
    assert res.content[:4] == b"RIFF"


def test_voice_respond_end_to_end_doctor_discovery(client, db_session, seeded_hospital_data):
    """
    Submitting audio with doctor query triggers STT -> search_doctors -> reply with TTS audio.
    """
    # Audio with mock text marker for cardiology query
    audio_content = b"RIFF" + b"MOCK_AUDIO_CONTENT:I need to consult a cardiologist"

    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("input.wav", io.BytesIO(audio_content), "audio/wav")},
        data={"language": "en", "session_id": "test-voice-session-1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "cardiologist" in data["transcript"].lower()
    assert "Sharma" in data["reply"] or "Cardiology" in data["reply"]
    assert data["session_id"] == "test-voice-session-1"
    # Audio response was synthesized
    assert data["audio_base64"] is not None
    assert data["audio_content_type"] == "audio/wav"
    assert data["tts_available"] is True


def test_voice_respond_confirmation_gate(client, db_session, seeded_hospital_data, monkeypatch):
    """
    Voice interactions strictly enforce explicit patient confirmation before booking.
    """
    from app.services.speech.voice_orchestrator import voice_orchestrator

    tts_calls = []

    def mock_synthesize(text, language=None, voice=None, speed=None):
        tts_calls.append({"text": text, "language": language})
        return generate_synthetic_wav(0.1)

    monkeypatch.setattr(voice_orchestrator.tts, "synthesize", mock_synthesize)
    session_id = "test-voice-confirm-gate"

    # Turn 1: Doctor selection
    audio_turn1 = b"RIFF" + b"MOCK_AUDIO_CONTENT:I choose Dr. Sharma"
    res1 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("t1.wav", io.BytesIO(audio_turn1), "audio/wav")},
        data={"session_id": session_id},
    )
    assert res1.status_code == 200

    # Turn 2: Slot selection
    audio_turn2 = b"RIFF" + b"MOCK_AUDIO_CONTENT:I pick slot-sharma-avail-1"
    res2 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("t2.wav", io.BytesIO(audio_turn2), "audio/wav")},
        data={"session_id": session_id},
    )
    assert res2.status_code == 200

    # Turn 3: Clinical reason
    audio_turn3 = b"RIFF" + b"MOCK_AUDIO_CONTENT:reason: Cardiac checkup"
    res3 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("t3.wav", io.BytesIO(audio_turn3), "audio/wav")},
        data={"session_id": session_id},
    )
    assert res3.status_code == 200

    # Turn 4: Patient reference -> Now enters AWAITING_CONFIRMATION / PENDING
    audio_turn4 = b"RIFF" + b"MOCK_AUDIO_CONTENT:PAT-2026-1122"
    res4 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("t4.wav", io.BytesIO(audio_turn4), "audio/wav")},
        data={"session_id": session_id},
    )
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["step"] == "AWAITING_CONFIRMATION"
    assert data4["confirmation_status"] == "PENDING"
    assert "confirm" in data4["reply"].lower() or "yes" in data4["reply"].lower()
    assert data4["audio_base64"] is not None
    assert data4["tts_available"] is True
    assert data4["booked_appointment"] is None
    assert len(tts_calls) == 4
    assert tts_calls[-1]["text"] == data4["reply"]
    assert tts_calls[-1]["language"] == "en"

    # Turn 5: Explicit confirmation
    audio_turn5 = b"RIFF" + b"MOCK_AUDIO_CONTENT:YES I confirm the booking"
    res5 = client.post(
        "/api/v1/voice/respond",
        files={"file": ("t5.wav", io.BytesIO(audio_turn5), "audio/wav")},
        data={"session_id": session_id},
    )
    assert res5.status_code == 200
    data5 = res5.json()
    assert data5["confirmation_status"] == "CONFIRMED"
    assert "confirmed" in data5["reply"].lower() or "booked" in data5["reply"].lower()
    assert data5["booked_appointment"] is not None
    assert len(tts_calls) == 5


def test_voice_language_uses_selected_language_and_keeps_generated_session(db_session, monkeypatch):
    from app.agent.conversation_manager import conversation_manager
    from app.agent.schemas import ChatResponse
    from app.services.speech.voice_orchestrator import VoiceOrchestrator

    class HintingSTT:
        def transcribe(self, **kwargs):
            return {
                "transcript": "aku appointment book chey slot-505.",
                "detected_language": "en",
                "language_code": "en-IN",
                "stt_ms": 1.0,
                "transcode_ms": 0.0,
            }

    def inspect_message(db, message, session_id, patient_reference):
        session = conversation_manager._sessions[session_id]
        assert session.language == "te"
        assert message == "aku appointment book chey slot-505."
        return ChatResponse(
            session_id=session_id,
            reply="తెలుగులో కొనసాగిస్తాను.",
            language=session.language,
            step=session.step,
            draft=session.draft,
            missing_details=session.draft.missing_fields(),
            confirmation_status=session.confirmation_status,
        )

    previous_sessions = dict(conversation_manager._sessions)
    previous_voice_languages = dict(conversation_manager._voice_selected_languages)
    conversation_manager._sessions.clear()
    conversation_manager._voice_selected_languages.clear()
    monkeypatch.setattr(conversation_manager, "process_message", inspect_message)
    try:
        orchestrator = VoiceOrchestrator(stt_service=HintingSTT())
        result = orchestrator.process_voice_turn(
            db=db_session,
            audio_bytes=b"synthetic-test-audio",
            language="te-IN",
            session_id=None,
            synthesize_audio=False,
        )
        assert result["language"] == "te"
        assert "slot-505" not in result["transcript"]
        assert result["session_id"] in conversation_manager._sessions
        assert conversation_manager._sessions[result["session_id"]].language == "te"
    finally:
        conversation_manager._sessions.clear()
        conversation_manager._sessions.update(previous_sessions)
        conversation_manager._voice_selected_languages.clear()
        conversation_manager._voice_selected_languages.update(previous_voice_languages)


def test_voice_respond_empty_audio_rejected():
    client = TestClient(app)
    res = client.post(
        "/api/v1/voice/respond",
        files={"file": ("empty.wav", io.BytesIO(b""), "audio/wav")},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "EMPTY_AUDIO"


def test_experimental_text_turn_does_not_call_tts(client, monkeypatch):
    from app.services.speech.voice_orchestrator import voice_orchestrator

    def unexpected_synthesis(*args, **kwargs):
        raise AssertionError("text-only experimental turn must not synthesize")

    monkeypatch.setattr(voice_orchestrator.tts, "synthesize", unexpected_synthesis)
    response = client.post(
        "/api/v1/voice/respond/text",
        files={"file": ("input.wav", io.BytesIO(b"RIFF" + b"MOCK_AUDIO_CONTENT:I need to consult a cardiologist"), "audio/wav")},
        data={"language": "en", "session_id": "experimental-text-only"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"]
    assert body["audio_base64"] is None
    assert body["tts_available"] is False


def test_experimental_stream_route_emits_only_audio_events(client, monkeypatch):
    import app.api.v1.voice as voice_api

    class FakeTTS:
        sample_rate = 16000

        def __init__(self):
            pass

        def stream_synthesize(self, **kwargs):
            assert kwargs["language"] == "te"
            yield {"type": "start"}
            yield {"type": "chunk", "chunk_index": 1, "audio": b"\x00\x00"}
            yield {"type": "complete", "chunk_index": 1}

        def close(self):
            pass

    monkeypatch.setattr(voice_api, "GnaniTimbreTTS", FakeTTS)
    response = client.post(
        "/api/v1/voice/synthesize/stream",
        json={"text": "నమస్కారం", "language": "te"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: chunk" in response.text
    assert "event: complete" in response.text
    assert "secret" not in response.text.lower()
    assert "provider text" not in response.text.lower()


@pytest.mark.parametrize("chunks,expected_recoverable", [
    ([], True),
    ([{"type": "chunk", "chunk_index": 1, "audio": b"\x00\x00"}], False),
])
def test_experimental_stream_route_sanitizes_provider_failures(client, monkeypatch, chunks, expected_recoverable):
    import app.api.v1.voice as voice_api
    from app.services.speech.stt_service import SpeechServiceError

    class FailingTTS:
        sample_rate = 16000

        def __init__(self):
            pass

        def stream_synthesize(self, **kwargs):
            yield {"type": "start"}
            yield from chunks
            raise SpeechServiceError("PROVIDER_STREAM_ERROR", "private provider detail", 502)

        def close(self):
            pass

    monkeypatch.setattr(voice_api, "GnaniTimbreTTS", FailingTTS)
    response = client.post(
        "/api/v1/voice/synthesize/stream",
        json={"text": "Hello", "language": "en"},
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert f'"recoverable": {str(expected_recoverable).lower()}' in response.text
    assert "private provider detail" not in response.text
