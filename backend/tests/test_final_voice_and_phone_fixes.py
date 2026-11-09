import pytest
import re
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.services.patient_service import (
    normalize_spoken_phone_number,
    normalize_phone,
    format_phone_grouped,
    register_patient,
)
from app.agent.adapters import (
    extract_phone_number_candidate,
    format_localized_message,
    format_human_date_and_time,
    format_spoken_appointment_confirmation,
    MockReasoningAdapter,
)
from app.agent.schemas import (
    AgentSessionState,
    BookingDraft,
    ConfirmationStatus,
    ConversationStep,
    ChatResponse,
)
from app.agent.conversation_manager import ConversationManager
from app.services.speech.tts_service import clean_text_for_speech


# ==============================================================================
# PART 1: MOBILE-NUMBER RECOGNITION SUITE
# ==============================================================================

class TestMobileNumberRecognition:
    def test_phone_number_english_words(self):
        text = "nine eight seven six five four three two one zero"
        assert normalize_spoken_phone_number(text) == "9876543210"
        assert extract_phone_number_candidate(text) == "9876543210"

    def test_phone_number_telugu_words(self):
        text = "తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు నాలుగు మూడు రెండు ఒకటి సున్నా"
        assert normalize_spoken_phone_number(text) == "9876543210"
        assert extract_phone_number_candidate(text) == "9876543210"

    def test_phone_number_code_mixed(self):
        text = "nine eight నాలుగు తొమ్మిది zero ఒకటి two three four five"
        assert normalize_spoken_phone_number(text) == "9849012345"
        assert extract_phone_number_candidate(text) == "9849012345"

    def test_phone_number_continuous(self):
        text = "9876543210"
        assert normalize_spoken_phone_number(text) == "9876543210"
        assert extract_phone_number_candidate(text) == "9876543210"

    def test_phone_number_space_separated(self):
        assert normalize_spoken_phone_number("98490 12345") == "9849012345"
        assert normalize_spoken_phone_number("9 8 7 6 5 4 3 2 1 0") == "9876543210"
        assert normalize_spoken_phone_number("+91 98765 43210") == "9876543210"
        assert normalize_spoken_phone_number("098765 43210") == "9876543210"

    def test_phone_number_telugu_numerals(self):
        text = "౯౮౭౬౫౪౩౨౧౦"
        assert normalize_spoken_phone_number(text) == "9876543210"
        assert extract_phone_number_candidate(text) == "9876543210"

    def test_phone_number_spoken_pairs_and_tens_english(self):
        text = "ninety eight forty seven sixty five forty three twenty one"
        assert normalize_spoken_phone_number(text) == "9847654321"
        assert extract_phone_number_candidate(text) == "9847654321"

    def test_phone_number_spoken_pairs_and_tens_telugu(self):
        text = "తొంభై ఎనిమిది నలభై ఏడు అరవై ఐదు నలభై మూడు ఇరవై ఒకటి"
        assert normalize_spoken_phone_number(text) == "9847654321"
        assert extract_phone_number_candidate(text) == "9847654321"

    def test_phone_number_corrections_in_sentence(self):
        # Case A: complete number replaced by correction
        text1 = "my number is 9876543210 wait no, 9876543211"
        assert normalize_spoken_phone_number(text1) == "9876543211"
        assert extract_phone_number_candidate(text1) == "9876543211"

        # Case B: Telugu correction word
        text2 = "9876543210 కాదు 9876543211"
        assert normalize_spoken_phone_number(text2) == "9876543211"
        assert extract_phone_number_candidate(text2) == "9876543211"

        # Case C: Tail digit correction e.g. "wait not 0, 1"
        text3 = "9876543210 wait not 0, 1"
        assert normalize_spoken_phone_number(text3) == "9876543211"
        assert extract_phone_number_candidate(text3) == "9876543211"

    def test_phone_number_rejects_dates_times_slots(self):
        assert normalize_spoken_phone_number("2026-11-10 10:00 AM") is None
        assert extract_phone_number_candidate("2026-11-10 10:00 AM") is None

        assert normalize_spoken_phone_number("tomorrow at 10 AM") is None
        assert extract_phone_number_candidate("tomorrow at 10 AM") is None

        assert normalize_spoken_phone_number("slot-101") is None
        assert extract_phone_number_candidate("slot-101") is None

    def test_phone_number_rejects_non_indian_and_incomplete(self):
        # Reject 9 digits
        assert normalize_spoken_phone_number("987654321") is None
        assert extract_phone_number_candidate("987654321") is None

        # Reject non-Indian starting digits (1-5)
        assert normalize_spoken_phone_number("1234567890") is None
        assert extract_phone_number_candidate("1234567890") is None

        assert normalize_spoken_phone_number("5678901234") is None
        assert extract_phone_number_candidate("5678901234") is None

    def test_phone_number_grouped_format(self):
        assert format_phone_grouped("9849012345") == "98490 12345"
        assert format_phone_grouped("+91 98490 12345") == "98490 12345"

    def test_ambiguous_or_invalid_phone_prompts_repetition_in_patient_language(self):
        adapter = MockReasoningAdapter()

        # Telugu session requesting new patient phone
        state_te = AgentSessionState(
            session_id="test-sess-te",
            language="te",
            step=ConversationStep.NEW_PATIENT_REGISTRATION,
            pending_action="COLLECTING_NEW_PATIENT_PHONE",
            draft=BookingDraft(patient_name="రవి"),
        )
        action_te = adapter.plan_and_respond(state_te, "12345", available_tools=[])  # invalid phone
        assert "దయచేసి మీ 10 అంకెల మొబైల్ నంబర్‌ను" in action_te.reply

        # English session requesting new patient phone
        state_en = AgentSessionState(
            session_id="test-sess-en",
            language="en",
            step=ConversationStep.NEW_PATIENT_REGISTRATION,
            pending_action="COLLECTING_NEW_PATIENT_PHONE",
            draft=BookingDraft(patient_name="Ravi"),
        )
        action_en = adapter.plan_and_respond(state_en, "12345", available_tools=[])  # invalid phone
        assert "Please provide a valid 10-digit mobile number" in action_en.reply

    def test_identity_conflict_handling_preserved(self, db_session):
        # Register initial patient
        res1 = register_patient(db_session, "Ravi Kumar", "9849012345")
        assert res1["is_new"] is True

        # Second registration with same phone but different identity
        res2 = register_patient(db_session, "Suresh Gupta", "9849012345")
        assert res2["is_new"] is False
        assert res2["identity_conflict"] is True
        assert res2["phone_number"] == "9849012345"


# ==============================================================================
# PART 2: SPOKEN CONFIRMATION & UI SEPARATION SUITE
# ==============================================================================

class TestSpokenConfirmationAndUiSeparation:
    def test_spoken_appointment_confirmation_english(self):
        booked_data = {
            "appointment_id": "7b84f3e2-1234-5678-90ab-cdef12345678",
            "patient_reference": "PAT-2026-1001",
            "doctor_name": "Dr. Rajesh Sharma",
            "department_name": "Cardiology",
            "appointment_start_time": "2026-11-10T10:00:00+05:30",
            "appointment_status": "BOOKED",
        }

        spoken = format_spoken_appointment_confirmation(booked_data, lang="en", notification_sent=False)

        # 1. Preferred sentence structure
        assert "Your appointment has been successfully booked!" in spoken
        assert "Here are your appointment details." in spoken
        assert "Doctor: Dr. Rajesh Sharma." in spoken
        assert "Department: Cardiology." in spoken
        assert "Date: November 10, 2026." in spoken
        assert "Time: 10:00 AM." in spoken
        assert "Your appointment confirmation details are available here." in spoken
        assert "Thank you for choosing Aarogya One Hospital." in spoken

        # 2. Strict exclusion of technical metadata
        assert "7b84f3e2" not in spoken
        assert "PAT-2026" not in spoken
        assert "•" not in spoken
        assert "-" not in spoken
        assert "UUID" not in spoken
        assert "reference" not in spoken.lower() or "details are available here" in spoken

    def test_spoken_appointment_confirmation_telugu(self):
        booked_data = {
            "appointment_id": "7b84f3e2-1234-5678-90ab-cdef12345678",
            "patient_reference": "PAT-2026-1001",
            "doctor_name": "Dr. Rajesh Sharma",
            "department_name": "Cardiology",
            "appointment_start_time": "2026-11-10T10:00:00+05:30",
            "appointment_status": "BOOKED",
        }

        spoken = format_spoken_appointment_confirmation(booked_data, lang="te", notification_sent=False)

        # 1. Preferred Telugu structure
        assert "మీ అపాయింట్‌మెంట్ విజయవంతంగా బుక్ చేయబడింది!" in spoken
        assert "ఇక్కడ మీ అపాయింట్‌మెంట్ వివరాలు ఉన్నాయి." in spoken
        assert "డాక్టర్: డాక్టర్ రాజేష్ శర్మ." in spoken
        assert "విభాగం: కార్డియాలజీ." in spoken
        assert "తేదీ: 10 నవంబర్ 2026." in spoken
        assert "సమయం: ఉదయం 10:00 గంటలకు." in spoken
        assert "మీ అపాయింట్‌మెంట్ నిర్ధారణ వివరాలు ఇక్కడ అందుబాటులో ఉన్నాయి." in spoken
        assert "ఆరోగ్య వన్ హాస్పిటల్‌ను ఎంచుకున్నందుకు ధన్యవాదాలు." in spoken

        # 2. Strict exclusion of technical metadata
        assert "7b84f3e2" not in spoken
        assert "PAT-2026" not in spoken
        assert "•" not in spoken

    def test_spoken_vs_ui_separation_in_conversation_manager(self, db_session, seeded_hospital_data):
        cm = ConversationManager()

        # Step 1: Initialize session and complete booking parameters
        from app.models.doctor import Doctor
        from app.models.appointment_slot import AppointmentSlot
        doc = db_session.query(Doctor).first()
        slot = db_session.query(AppointmentSlot).filter(AppointmentSlot.doctor_id == doc.id, AppointmentSlot.status == "AVAILABLE").first()

        session = cm.get_or_create_session("test-spoken-ui-session", "PAT-2026-1001")
        session.language = "en"
        session.draft.doctor_id = doc.id
        session.draft.doctor_name = doc.display_name
        session.draft.specialty = doc.specialty
        session.draft.slot_id = slot.id
        session.draft.slot_start_time = slot.start_time.isoformat()
        session.draft.reason_category = "CONSULTATION"
        session.draft.patient_reference = "PAT-2026-1001"
        session.draft.patient_phone = "9849012345"
        session.step = ConversationStep.AWAITING_CONFIRMATION
        session.confirmation_status = ConfirmationStatus.PENDING
        session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

        # Step 2: User explicitly confirms booking
        res = cm.process_message(db_session, "YES", session_id="test-spoken-ui-session")

        # UI Response: Structured summary with ID, doctor, and confirmation
        assert res.step == ConversationStep.BOOKED
        assert "Rajesh Sharma" in res.reply
        assert "confirmed" in res.reply.lower() or "booked" in res.reply.lower()
        assert (
            str(res.booked_appointment.get("appointment_id")) in res.reply
            or "reference" in res.reply.lower()
        )

        # Spoken Response: Clean natural confirmation with NO UUIDs, NO reference IDs, NO bullet points
        assert res.spoken_reply is not None
        assert "Your appointment has been successfully booked!" in res.spoken_reply
        assert "Doctor: Dr. Rajesh Sharma." in res.spoken_reply
        assert "Department: Cardiology." in res.spoken_reply
        assert "•" not in res.spoken_reply
        assert "PAT-2026" not in res.spoken_reply
        assert str(res.booked_appointment.get("appointment_id")) not in res.spoken_reply

    def test_spoken_confirmation_notification_truthfulness(self):
        booked_data = {
            "doctor_name": "Dr. Rajesh Sharma",
            "department_name": "Cardiology",
            "appointment_start_time": "2026-11-10T10:00:00+05:30",
        }
        # Without notification gateway: truthful wording
        spoken_no_gateway = format_spoken_appointment_confirmation(booked_data, lang="en", notification_sent=False)
        assert "Your appointment confirmation details are available here." in spoken_no_gateway
        assert "sent to your registered mobile number" not in spoken_no_gateway

        # If notification was successfully dispatched:
        spoken_with_gateway = format_spoken_appointment_confirmation(booked_data, lang="en", notification_sent=True)
        assert "Your appointment details have been sent to your registered mobile number." in spoken_with_gateway

    def test_failed_booking_never_produces_success_spoken_reply(self, db_session):
        cm = ConversationManager()
        session = cm.get_or_create_session("test-failed-booking", "PAT-2026-1001")
        session.language = "en"
        session.draft.doctor_id = "non-existent-doc"
        session.draft.doctor_name = "Dr. Unknown"
        session.draft.slot_id = "slot-invalid"
        session.draft.slot_start_time = "2026-11-10T10:00:00+05:30"
        session.draft.reason_category = "CONSULTATION"
        session.draft.patient_reference = "PAT-2026-1001"
        session.step = ConversationStep.AWAITING_CONFIRMATION
        session.confirmation_status = ConfirmationStatus.PENDING
        session.confirmed_draft_fingerprint = session.draft.get_fingerprint()

        res = cm.process_message(db_session, "YES", session_id="test-failed-booking")

        # Booking failed: spoken_reply must be None and reply must indicate failure
        assert res.spoken_reply is None
        assert res.step != ConversationStep.BOOKED
        assert "could not be completed" in res.reply.lower() or "unavailable" in res.reply.lower()

    def test_clean_text_for_speech_scrubs_uuids_and_references(self):
        raw_text = (
            "Appointment Confirmed! • Appointment ID: 7b84f3e2-1234-5678-90ab-cdef12345678 "
            "Patient Reference: PAT-2026-9999 Doctor ID: doc-101 Slot ID: slot-202 "
            "Doctor: Dr. Rajesh Sharma at 10:00 AM."
        )
        cleaned = clean_text_for_speech(raw_text)
        assert "7b84f3e2-1234-5678-90ab-cdef12345678" not in cleaned
        assert "PAT-2026-9999" not in cleaned
        assert "doc-101" not in cleaned
        assert "slot-202" not in cleaned
        assert "•" not in cleaned
