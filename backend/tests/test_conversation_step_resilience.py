import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.agent.schemas import (
    ConversationStep,
    ConfirmationStatus,
    AgentSessionState,
    ChatResponse,
    BookingDraft,
)
from app.agent.conversation_manager import ConversationManager
from app.agent.adapters import extract_phone_number_candidate
from app.services.patient_service import normalize_spoken_phone_number
from app.services.speech.tts_service import generate_synthetic_wav
from app.models import Doctor, AppointmentSlot, Patient


def create_mock_voice_wav(transcript: str) -> bytes:
    """Creates a mock WAV payload containing the MOCK_AUDIO_CONTENT marker."""
    header = b"RIFF" + b"\x00" * 36 + b"WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00"
    return header + f"MOCK_AUDIO_CONTENT:{transcript}".encode("utf-8")


class TestConversationStepEnumAndSchemaResilience:
    """Tests the ConversationStep enum members and Pydantic deserialization resilience."""

    def test_conversation_step_enum_members_exist(self):
        """Verify COLLECTING_NAME and COLLECTING_PHONE exist and match expected values."""
        assert hasattr(ConversationStep, "COLLECTING_NAME")
        assert hasattr(ConversationStep, "COLLECTING_PHONE")
        assert ConversationStep.COLLECTING_NAME.value == "COLLECTING_NAME"
        assert ConversationStep.COLLECTING_PHONE.value == "COLLECTING_PHONE"

        # Verify existing standard members
        assert ConversationStep.GREETING.value == "GREETING"
        assert ConversationStep.COLLECTING_DOCTOR.value == "COLLECTING_DOCTOR"
        assert ConversationStep.COLLECTING_SLOT.value == "COLLECTING_SLOT"
        assert ConversationStep.COLLECTING_DETAILS.value == "COLLECTING_DETAILS"
        assert ConversationStep.AWAITING_CONFIRMATION.value == "AWAITING_CONFIRMATION"
        assert ConversationStep.BOOKED.value == "BOOKED"
        assert ConversationStep.CANCELLED.value == "CANCELLED"
        assert ConversationStep.NEW_PATIENT_REGISTRATION.value == "NEW_PATIENT_REGISTRATION"
        assert ConversationStep.PATIENT_IDENTIFICATION.value == "PATIENT_IDENTIFICATION"
        assert ConversationStep.EXISTING_PATIENT_VERIFICATION.value == "EXISTING_PATIENT_VERIFICATION"

    def test_agent_session_state_deserialization_with_valid_and_case_insensitive_steps(self):
        """Verify AgentSessionState parses known steps in various casings."""
        s1 = AgentSessionState(session_id="s1", step="COLLECTING_NAME")
        assert s1.step == ConversationStep.COLLECTING_NAME

        s2 = AgentSessionState(session_id="s2", step="collecting_phone")
        assert s2.step == ConversationStep.COLLECTING_PHONE

        s3 = AgentSessionState(session_id="s3", step="awaiting_confirmation")
        assert s3.step == ConversationStep.AWAITING_CONFIRMATION

    def test_agent_session_state_deserialization_with_unknown_legacy_step(self):
        """Verify AgentSessionState does not crash on unknown legacy steps and defaults to GREETING."""
        s = AgentSessionState(session_id="s_legacy", step="SOME_DEPRECATED_OR_FUTURE_STEP")
        assert s.step == ConversationStep.GREETING

    def test_chat_response_deserialization_with_unknown_step(self):
        """Verify ChatResponse handles unknown steps gracefully."""
        resp = ChatResponse(
            session_id="cr1",
            reply="Hello",
            step="NON_EXISTENT_STEP",
            draft=BookingDraft(),
            missing_details=[],
            confirmation_status=ConfirmationStatus.NONE,
        )
        assert resp.step == ConversationStep.GREETING


class TestForeignScriptVoiceTurnResilience:
    """
    Tests foreign Indic script STT output across all session steps.
    Specifically tests against the regression:
    `type object 'ConversationStep' has no attribute 'COLLECTING_NAME'`.
    """

    def test_voice_turn_foreign_script_at_greeting_step(self, client, monkeypatch):
        """Turn 1: STT produces foreign Gujarati text on empty/initial session."""
        from app.services.speech.voice_orchestrator import voice_orchestrator

        monkeypatch.setattr(
            voice_orchestrator.tts,
            "synthesize",
            lambda text, language=None, voice=None, speed=None: generate_synthetic_wav(0.1),
        )

        audio_gujarati = create_mock_voice_wav("હા, સારી સારી જરૂર છે।")
        res = client.post(
            "/api/v1/voice/respond",
            files={"file": ("turn1.wav", io.BytesIO(audio_gujarati), "audio/wav")},
            data={"session_id": "test-resilience-greeting"},
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["step"] == ConversationStep.GREETING.value
        # Clarification prompt returned instead of 500 error
        assert "repeat" in data["reply"].lower() or "understand" in data["reply"].lower()

    def test_voice_turn_foreign_script_in_telugu_session(self, client, monkeypatch):
        """Telugu conversation receives foreign Malayalam script -> replies in Telugu clarification."""
        from app.services.speech.voice_orchestrator import voice_orchestrator

        monkeypatch.setattr(
            voice_orchestrator.tts,
            "synthesize",
            lambda text, language=None, voice=None, speed=None: generate_synthetic_wav(0.1),
        )

        session_id = "test-resilience-telugu"
        # Prime session with Telugu
        cm = ConversationManager()
        sess = cm.get_or_create_session(session_id)
        sess.language = "te"

        audio_malayalam = create_mock_voice_wav("ആ, അപ്പോൾ അതിൻ്റെ പേര്?")
        res = client.post(
            "/api/v1/voice/respond",
            files={"file": ("turn_te.wav", io.BytesIO(audio_malayalam), "audio/wav")},
            data={"session_id": session_id, "language": "te"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["language"] == "te"
        assert "క్షమించండి" in data["reply"]

    def test_conversation_manager_foreign_script_during_registration(self, db_session):
        """During registration, foreign script returns registration-specific clarification."""
        cm = ConversationManager()
        session = cm.get_or_create_session("test-reg-noise")
        session.language = "en"
        session.pending_action = "COLLECTING_NEW_PATIENT_NAME"
        session.step = ConversationStep.NEW_PATIENT_REGISTRATION

        res = cm.process_message(db_session, "હા, સારી સારી જરૂર છે।", session_id="test-reg-noise")
        assert res.step == ConversationStep.NEW_PATIENT_REGISTRATION
        assert "state your name or 10-digit phone number" in res.reply.lower()

    def test_conversation_manager_foreign_script_during_confirmation(self, db_session):
        """During pending confirmation, foreign script returns confirmation-specific clarification."""
        cm = ConversationManager()
        session = cm.get_or_create_session("test-confirm-noise")
        session.language = "en"
        session.step = ConversationStep.AWAITING_CONFIRMATION
        session.confirmation_status = ConfirmationStatus.PENDING

        res = cm.process_message(db_session, "আর তুলতে পেরেছি সবাই।", session_id="test-confirm-noise")
        assert res.step == ConversationStep.AWAITING_CONFIRMATION
        assert "book this appointment" in res.reply.lower()


class TestPatientRegistrationAndPhoneFlows:
    """Verifies patient registration, phone number recognition, correction, and identity conflict."""

    def test_fresh_patient_registration_flow(self, client, db_session, seeded_hospital_data):
        """End-to-end chat flow for a new patient registering their name and phone."""
        session_id = "test-new-patient-flow"

        # Step 1: Request department
        r1 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
        assert r1.status_code == 200

        # Step 2: Choose doctor/slot
        r2 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "First available doctor"})
        assert r2.status_code == 200

        # Step 3: Advance to patient identification
        r3 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Proceed"})
        assert r3.status_code == 200
        assert "visited" in r3.json()["reply"].lower()

        # Step 4: Say 'No' to indicate new patient
        r4 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first time"})
        assert r4.status_code == 200
        assert "name" in r4.json()["reply"].lower()

        # Step 5: Provide full name
        r5 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "My name is Rajeshwar Rao"})
        assert r5.status_code == 200
        assert "phone" in r5.json()["reply"].lower() or "mobile" in r5.json()["reply"].lower() or "number" in r5.json()["reply"].lower()

        # Step 6: Provide phone number as words
        r6 = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "nine eight four nine zero one two three four five"})
        assert r6.status_code == 200
        d6 = r6.json()
        assert d6["step"] in (ConversationStep.COLLECTING_DETAILS.value, ConversationStep.AWAITING_CONFIRMATION.value)
        assert "9849012345" in str(d6["draft"]) or "Rajeshwar" in d6["reply"]

    def test_phone_number_correction_during_registration(self, client, db_session, seeded_hospital_data):
        """User corrects their phone number mid-sentence or in speech."""
        # 1. Test unit normalization for spoken correction
        spoken_correction_1 = "My number is 9876500000 sorry my number is 9876543210"
        assert normalize_spoken_phone_number(spoken_correction_1) == "9876543210"
        assert extract_phone_number_candidate(spoken_correction_1) == "9876543210"

        spoken_correction_te = "నా నెంబర్ 9876500000 కాదు కాదు 9876543210"
        assert normalize_spoken_phone_number(spoken_correction_te) == "9876543210"
        assert extract_phone_number_candidate(spoken_correction_te) == "9876543210"

        # 2. Test in end-to-end chat conversation
        session_id = "test-phone-correction"
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "First available doctor"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Proceed"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No, this is my first time"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "My name is Sunita Verma"})

        # Phone input with self-correction in utterance
        r = client.post(
            "/api/v1/agent/chat",
            json={"session_id": session_id, "message": "It is 9876500000 sorry my number is 9876543210"},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["step"] in (ConversationStep.COLLECTING_DETAILS.value, ConversationStep.AWAITING_CONFIRMATION.value)
        assert d["draft"]["patient_phone"] == "9876543210" or "9876543210" in str(d["draft"]) or "Sunita" in d["reply"]

    def test_patient_identity_conflict_handling(self, client, db_session, seeded_hospital_data):
        """Phone number belongs to another patient name, triggers identity clarification."""
        # Seed an existing patient
        existing = Patient(
            patient_reference="PAT-EXISTING-99",
            full_name="Vikram Singh",
            phone_number="9988776655",
        )
        db_session.add(existing)
        db_session.commit()

        session_id = "test-identity-conflict"
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Cardiology"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "First doctor"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Proceed"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "No"})
        client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "Anil Kapoor"})

        # Provide existing phone number with different name
        r = client.post("/api/v1/agent/chat", json={"session_id": session_id, "message": "9988776655"})
        assert r.status_code == 200
        d = r.json()
        # Should ask whether they are Vikram Singh or want a new profile
        assert "vikram" in d["reply"].lower() or "conflict" in d["reply"].lower() or "different" in d["reply"].lower() or "record" in d["reply"].lower()


class TestResumedConversationsAndRepeatedVoiceTurns:
    """Verifies that multi-turn voice sessions remain stable across repeated turns."""

    def test_multi_turn_voice_conversation_flow(self, client, db_session, seeded_hospital_data, monkeypatch):
        """Executes consecutive voice turns without state degradation."""
        from app.services.speech.voice_orchestrator import voice_orchestrator

        monkeypatch.setattr(
            voice_orchestrator.tts,
            "synthesize",
            lambda text, language=None, voice=None, speed=None: generate_synthetic_wav(0.1),
        )

        session_id = "test-multi-turn-voice"

        # Turn 1: Cardiology search
        wav1 = create_mock_voice_wav("I want an appointment in Cardiology")
        res1 = client.post(
            "/api/v1/voice/respond",
            files={"file": ("t1.wav", io.BytesIO(wav1), "audio/wav")},
            data={"session_id": session_id},
        )
        assert res1.status_code == 200
        assert res1.json()["step"] in (
            ConversationStep.COLLECTING_DOCTOR.value,
            ConversationStep.COLLECTING_SLOT.value,
        )

        # Turn 2: Unclear audio with foreign script noise
        wav2 = create_mock_voice_wav("હા, સારી સારી જરૂર છે।")
        res2 = client.post(
            "/api/v1/voice/respond",
            files={"file": ("t2.wav", io.BytesIO(wav2), "audio/wav")},
            data={"session_id": session_id},
        )
        assert res2.status_code == 200
        # Voice turn handled without crashing
        assert res2.json()["tts_available"] is True
        assert len(res2.json()["reply"]) > 5

        # Turn 3: Doctor selection
        wav3 = create_mock_voice_wav("Dr. Sharma please")
        res3 = client.post(
            "/api/v1/voice/respond",
            files={"file": ("t3.wav", io.BytesIO(wav3), "audio/wav")},
            data={"session_id": session_id},
        )
        assert res3.status_code == 200
        assert res3.json()["draft"]["doctor_name"] is not None or "sharma" in res3.json()["reply"].lower()
