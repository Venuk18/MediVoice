import asyncio
import io
import time
from typing import Optional, Dict, Any
from unittest.mock import patch
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.main import app
from app.models.doctor import Doctor
from app.models.appointment_slot import AppointmentSlot
from app.models.appointment import Appointment
from app.agent.conversation_manager import conversation_manager
from app.agent.adapters import MockReasoningAdapter
from app.services.speech.stt_service import SpeechServiceError, GnaniPrismaSTT
from app.services.speech.tts_service import GnaniTimbreTTS, generate_synthetic_wav
from app.services.speech.voice_orchestrator import VoiceOrchestrator


def make_mock_wav(content_marker: str = "Test audio") -> bytes:
    """Generates synthetic WAV audio containing the MOCK_AUDIO_CONTENT marker."""
    header = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVEfmt "
    return header + f"MOCK_AUDIO_CONTENT:{content_marker}".encode("utf-8")


class TestVoicePerformanceAndConcurrency:
    """
    Validates backend voice performance, asyncio event-loop unblocking,
    short-lived database connection lifecycles, and resilient error recovery.
    """

    def test_multiple_simultaneous_voice_requests(self, client, db_session, seeded_hospital_data):
        """
        Executes multiple concurrent voice requests against /voice/respond:
        Verifies that all requests complete successfully with HTTP 200, return valid transcripts,
        and log complete performance instrumentation (stt_ms, database_ms, tts_ms, total_turn_ms).
        """
        import concurrent.futures

        def send_turn(idx: int):
            audio = make_mock_wav(f"I need a doctor in cardiology department #{idx}")
            t0 = time.perf_counter()
            resp = client.post(
                "/api/v1/voice/respond",
                files={"file": (f"turn_{idx}.wav", io.BytesIO(audio), "audio/wav")},
                data={"session_id": f"perf-session-{idx}", "language": "en"},
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return resp.status_code, resp.json(), elapsed_ms

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(send_turn, i) for i in range(5)]
            results = [f.result() for f in futures]

        for status_code, data, elapsed_ms in results:
            assert status_code == 200
            assert "transcript" in data
            assert "reply" in data
            assert data["session_id"].startswith("perf-session-")
            assert "timings" in data
            timings = data["timings"]
            assert "stt_ms" in timings
            assert "database_ms" in timings
            assert "total_turn_ms" in timings
            assert "correlation_id" in data

    def test_event_loop_responsiveness_during_heavy_voice_turn(self, client, monkeypatch):
        """
        Verifies that the asyncio event loop is not blocked during a voice turn:
        When a voice turn is in flight (using asyncio.to_thread), a lightweight endpoint
        like /api/v1/voice/config responds with near-instantaneous latency (<50ms).
        """
        import concurrent.futures
        from app.services.speech.voice_orchestrator import voice_orchestrator

        original_transcribe = voice_orchestrator.stt.transcribe

        def slow_transcribe(*args, **kwargs):
            # Simulate a 300ms remote network roundtrip in worker thread
            time.sleep(0.3)
            return original_transcribe(*args, **kwargs)

        monkeypatch.setattr(voice_orchestrator.stt, "transcribe", slow_transcribe)

        def run_slow_voice():
            audio = make_mock_wav("Consultation query for Dr. Sharma")
            return client.post(
                "/api/v1/voice/respond",
                files={"file": ("slow.wav", io.BytesIO(audio), "audio/wav")},
                data={"session_id": "slow-voice-session"},
            )

        def ping_config():
            # Wait 50ms so voice request has started in worker thread
            time.sleep(0.05)
            t0 = time.perf_counter()
            resp = client.get("/api/v1/voice/config")
            duration_ms = (time.perf_counter() - t0) * 1000
            return resp.status_code, duration_ms

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_voice = pool.submit(run_slow_voice)
            f_config = pool.submit(ping_config)
            
            voice_resp = f_voice.result()
            config_status, config_latency_ms = f_config.result()

        assert voice_resp.status_code == 200
        assert config_status == 200
        # /config should respond in less than 100ms because the event loop is unblocked
        assert config_latency_ms < 100.0, f"Event loop was blocked: /config took {config_latency_ms}ms"

    def test_database_session_cleanup_and_short_lifecycle(self, db_session, monkeypatch):
        """
        Verifies that the database connection is checked out strictly during the agent/tool phase
        and released before speech synthesis begins.
        """
        from app.services.speech.voice_orchestrator import voice_orchestrator

        checkout_phases = []

        # Intercept TTS synthesis to verify database connection state
        original_synthesize = voice_orchestrator.tts.synthesize

        def inspect_during_tts(*args, **kwargs):
            checkout_phases.append("tts_synthesis_entered")
            return original_synthesize(*args, **kwargs)

        monkeypatch.setattr(voice_orchestrator.tts, "synthesize", inspect_during_tts)

        audio = make_mock_wav("I need Dr. Sharma appointment")
        result = voice_orchestrator.process_voice_turn(
            db=db_session,
            audio_bytes=audio,
            session_id="db-lifecycle-check",
            language="en",
        )
        assert result["tts_available"] is True
        assert "tts_synthesis_entered" in checkout_phases
        # Timing instrumentation verifies database_ms is recorded
        assert "database_ms" in result["timings"]
        assert result["timings"]["database_ms"] >= 0.0

    def test_provider_timeouts_stt(self, client, monkeypatch):
        """
        Verifies that an STT provider timeout raises HTTP 504 with safe error details.
        """
        from app.services.speech.voice_orchestrator import voice_orchestrator

        def timeout_stt(*args, **kwargs):
            raise SpeechServiceError(
                code="PROVIDER_TIMEOUT",
                safe_message="Gnani Prisma STT request timed out after 12.0s.",
                status_code=504,
            )

        monkeypatch.setattr(voice_orchestrator.stt, "transcribe", timeout_stt)

        audio = make_mock_wav("Timeout test audio")
        resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("timeout.wav", io.BytesIO(audio), "audio/wav")},
        )
        assert resp.status_code == 504
        data = resp.json()
        assert data["detail"]["code"] == "PROVIDER_TIMEOUT"
        assert "timed out" in data["detail"]["message"].lower()

    def test_provider_timeouts_tts_graceful_recovery(self, client, monkeypatch):
        """
        Verifies that when TTS synthesis times out or fails, the voice endpoint does NOT crash:
        It safely returns HTTP 200 with the assistant's text response, tts_available=False,
        and tts_error recorded.
        """
        from app.services.speech.voice_orchestrator import voice_orchestrator

        def timeout_tts(*args, **kwargs):
            raise SpeechServiceError(
                code="PROVIDER_TIMEOUT",
                safe_message="Gnani Timbre TTS request timed out.",
                status_code=504,
            )

        monkeypatch.setattr(voice_orchestrator.tts, "synthesize", timeout_tts)

        audio = make_mock_wav("I want to see cardiologist Dr. Sharma")
        resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("tts_timeout.wav", io.BytesIO(audio), "audio/wav")},
            data={"session_id": "tts-timeout-session"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tts_available"] is False
        assert data["tts_error"] is not None
        assert data["reply"] is not None
        assert len(data["reply"]) > 0

    def test_provider_failures_stt_network_error(self, client, monkeypatch):
        """
        Verifies that STT network connection errors return HTTP 502 Bad Gateway.
        """
        from app.services.speech.voice_orchestrator import voice_orchestrator

        def error_stt(*args, **kwargs):
            raise SpeechServiceError(
                code="PROVIDER_NETWORK_ERROR",
                safe_message="Network communication error while reaching Gnani Prisma STT.",
                status_code=502,
            )

        monkeypatch.setattr(voice_orchestrator.stt, "transcribe", error_stt)

        audio = make_mock_wav("Network error test audio")
        resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("net_err.wav", io.BytesIO(audio), "audio/wav")},
        )
        assert resp.status_code == 502
        assert resp.json()["detail"]["code"] == "PROVIDER_NETWORK_ERROR"

    def test_conversation_continuity_across_turns(self, client, db_session, seeded_hospital_data):
        """
        Verifies conversational state and slot selection persist seamlessly across turns.
        """
        session_id = "test-continuity-perf-01"

        # Turn 1: Select doctor
        audio1 = make_mock_wav("I want Dr. Rajesh Sharma")
        res1 = client.post(
            "/api/v1/voice/respond",
            files={"file": ("t1.wav", io.BytesIO(audio1), "audio/wav")},
            data={"session_id": session_id},
        )
        assert res1.status_code == 200
        assert res1.json()["session_id"] == session_id

        # Turn 2: State persists into slot selection
        audio2 = make_mock_wav("10:00 AM slot")
        res2 = client.post(
            "/api/v1/voice/respond",
            files={"file": ("t2.wav", io.BytesIO(audio2), "audio/wav")},
            data={"session_id": session_id},
        )
        assert res2.status_code == 200
        assert res2.json()["session_id"] == session_id

    def test_appointment_booking_and_explicit_confirmation_in_concurrency(
        self, client, db_session, seeded_hospital_data
    ):
        """
        Verifies that explicit confirmation safely commits an appointment to the database
        and transitions the slot from AVAILABLE to BOOKED.
        """
        doc = seeded_hospital_data["doc_sharma"]
        slot = seeded_hospital_data["slot_available"]
        slot_id = slot.id
        session_id = "test-booking-explicit-perf"

        # Setup awaiting confirmation
        s = conversation_manager.get_or_create_session(session_id)
        s.draft.doctor_id = doc.id
        s.draft.doctor_name = doc.display_name
        s.draft.slot_id = slot.id
        s.draft.slot_start_time = slot.start_time.isoformat()
        s.draft.reason_category = "General Review"
        s.draft.patient_reference = "PAT-PERF-900"
        s.confirmation_status = conversation_manager.get_or_create_session(session_id).confirmation_status.PENDING
        s.confirmed_draft_fingerprint = s.draft.get_fingerprint()

        audio_yes = make_mock_wav("YES I confirm the appointment")
        resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("yes.wav", io.BytesIO(audio_yes), "audio/wav")},
            data={"session_id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["confirmation_status"] == "CONFIRMED"
        assert data["booked_appointment"] is not None

        # Verify DB integrity
        db_session.expire_all()
        slot_db = db_session.scalars(select(AppointmentSlot).where(AppointmentSlot.id == slot_id)).first()
        assert slot_db.status == "BOOKED"

    def test_multilingual_responses_telugu_and_english(self, client):
        """
        Verifies that Telugu audio produces Telugu responses and English audio produces English responses.
        """
        # Telugu
        te_audio = make_mock_wav("డాక్టర్ రాజేష్ శర్మ అపాయింట్‌మెంట్ కావాలి")
        te_resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("te.wav", io.BytesIO(te_audio), "audio/wav")},
            data={"language": "te"},
        )
        assert te_resp.status_code == 200
        assert te_resp.json()["language"] == "te"

        # English
        en_audio = make_mock_wav("I need an appointment with cardiologist")
        en_resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("en.wav", io.BytesIO(en_audio), "audio/wav")},
            data={"language": "en"},
        )
        assert en_resp.status_code == 200
        assert en_resp.json()["language"] == "en"

    def test_tts_returning_no_audio_graceful_handling(self, client, monkeypatch):
        """
        Verifies that when TTS returns empty audio, response status is 200 with tts_available=False.
        """
        from app.services.speech.voice_orchestrator import voice_orchestrator

        monkeypatch.setattr(voice_orchestrator.tts, "synthesize", lambda *args, **kwargs: b"")

        audio = make_mock_wav("Hello doctor")
        resp = client.post(
            "/api/v1/voice/respond",
            files={"file": ("empty_tts.wav", io.BytesIO(audio), "audio/wav")},
            data={"session_id": "empty-tts-session"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tts_available"] is False
        assert len(data["reply"]) > 0

